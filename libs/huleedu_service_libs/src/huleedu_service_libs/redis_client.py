"""
Redis client wrapper for HuleEdu microservices.

Provides minimal Redis operations needed for event idempotency patterns.
Follows the same lifecycle management pattern as KafkaBus.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_pubsub import RedisPubSub

logger = create_service_logger("redis-client")  # Use structured logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class RedisClient:
    """HuleEdu Redis client with lifecycle management for idempotency operations."""

    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.client_id = client_id  # Store client_id for logging
        self.client = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self._started = False
        self._transaction_pipeline = None  # Track transaction state
        self._pubsub: RedisPubSub | None = None

    async def start(self) -> None:
        """Initialize Redis connection with health verification."""
        if not self._started:
            try:
                await self.client.ping()
                self._started = True
                self._pubsub = RedisPubSub(self.client, self.client_id)
                logger.info(f"Redis client '{self.client_id}' connected to {self.redis_url}")
            except RedisConnectionError as e:
                logger.error(f"Redis client '{self.client_id}' failed to connect: {e}")
                raise
            except Exception as e:
                logger.error(f"Redis client '{self.client_id}' startup error: {e}")
                raise

    async def stop(self) -> None:
        """Clean shutdown of Redis connection."""
        if self._started:
            try:
                await self.client.aclose()
                self._started = False
                logger.info(f"Redis client '{self.client_id}' disconnected")
            except Exception as e:
                logger.error(
                    f"Error stopping Redis client '{self.client_id}': {e}",
                    exc_info=True,
                )

    async def set_if_not_exists(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Atomic SET if NOT EXISTS operation for idempotency.

        Args:
            key: Redis key for idempotency check
            value: Value to store (typically event processing marker)
            ttl_seconds: Optional TTL in seconds (recommended: 24-48 hours)

        Returns:
            True if key was set (first time processing), False if key already exists
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.set(key, value, ex=ttl_seconds, nx=True)
            success = bool(result)
            logger.debug(
                f"Redis SETNX by '{self.client_id}': key='{key}' "
                f"ttl={ttl_seconds}s result={'SET' if success else 'EXISTS'}",
            )
            return success
        except RedisTimeoutError:
            logger.error(f"Timeout on Redis operation by '{self.client_id}' for key '{key}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def delete_key(self, key: str) -> int:
        """
        Delete a key from Redis.

        Args:
            key: Redis key to delete

        Returns:
            Number of keys deleted (0 or 1)
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            # Use pipeline if in transaction, otherwise use direct client
            redis_client = self._transaction_pipeline or self.client
            deleted_count = await redis_client.delete(key)

            if self._transaction_pipeline is None:
                # Only log and return for non-transaction operations
                logger.debug(
                    f"Redis DELETE by '{self.client_id}': key='{key}' deleted={deleted_count}",
                )
                return int(deleted_count)
            else:
                # In transaction - command is queued, success determined by EXEC
                logger.debug(f"Redis DELETE queued by '{self.client_id}': key='{key}'")
                return 1  # Assume success for transaction queuing
        except Exception as e:
            logger.error(
                f"Error deleting Redis key '{key}' by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def get(self, key: str) -> str | None:
        """
        Get string value from Redis.

        Args:
            key: Redis key to retrieve

        Returns:
            String value if key exists, None otherwise
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            value = await self.client.get(key)
            logger.debug(
                f"Redis GET by '{self.client_id}': key='{key}' "
                f"result={'HIT' if value is not None else 'MISS'}",
            )
            return str(value) if value is not None else None
        except RedisTimeoutError:
            logger.error(f"Timeout on Redis GET operation by '{self.client_id}' for key '{key}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis GET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """
        Set string value with TTL.

        Args:
            key: Redis key to set
            ttl_seconds: TTL in seconds
            value: String value to store

        Returns:
            True if operation succeeded
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            # Use pipeline if in transaction, otherwise use direct client
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.setex(key, ttl_seconds, value)

            if self._transaction_pipeline is None:
                # Only log and return for non-transaction operations
                success = bool(result)
                logger.debug(
                    f"Redis SETEX by '{self.client_id}': key='{key}' "
                    f"ttl={ttl_seconds}s result={'SUCCESS' if success else 'FAILED'}",
                )
                return success
            else:
                # In transaction - command is queued, success determined by EXEC
                logger.debug(
                    f"Redis SETEX queued by '{self.client_id}': key='{key}' ttl={ttl_seconds}s",
                )
                return True
        except RedisTimeoutError:
            logger.error(f"Timeout on Redis SETEX operation by '{self.client_id}' for key '{key}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis SETEX operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def watch(self, *keys: str) -> bool:
        """
        Watch one or more keys for changes during transaction.

        Args:
            keys: Redis keys to watch

        Returns:
            True if WATCH command succeeded
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.watch(*keys)
            success = bool(result)
            logger.debug(
                f"Redis WATCH by '{self.client_id}': keys={keys} "
                f"result={'SUCCESS' if success else 'FAILED'}",
            )
            return success
        except Exception as e:
            logger.error(
                f"Error in Redis WATCH operation by '{self.client_id}' for keys {keys}: {e}",
                exc_info=True,
            )
            raise

    async def multi(self) -> bool:
        """
        Start a Redis transaction (MULTI) by creating a pipeline.

        Returns:
            True if MULTI command succeeded
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            # Create a pipeline for the transaction
            self._transaction_pipeline = self.client.pipeline()
            # Multi is implicit when using pipeline
            logger.debug(f"Redis pipeline created for transaction by '{self.client_id}'")
            return True
        except Exception as e:
            self._transaction_pipeline = None
            logger.error(
                f"Error creating Redis pipeline by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def exec(self) -> list[Any] | None:
        """
        Execute a Redis transaction (EXEC).

        Returns:
            List of command results if transaction succeeded,
            None if transaction was discarded (watched key changed)
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        if self._transaction_pipeline is None:
            raise RuntimeError("No active transaction to execute")

        try:
            result = await self._transaction_pipeline.execute()
            self._transaction_pipeline = None  # Reset transaction state
            logger.debug(
                f"Redis EXEC by '{self.client_id}': "
                f"result={'SUCCESS' if result is not None else 'DISCARDED'}",
            )
            return result
        except Exception as e:
            self._transaction_pipeline = None  # Reset on error
            logger.error(
                f"Error in Redis EXEC operation by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def unwatch(self) -> bool:
        """
        Remove all watches from current connection.

        Returns:
            True if UNWATCH command succeeded
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.unwatch()
            success = bool(result)
            logger.debug(
                f"Redis UNWATCH by '{self.client_id}': result={'SUCCESS' if success else 'FAILED'}",
            )
            return success
        except Exception as e:
            logger.error(
                f"Error in Redis UNWATCH operation by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def scan_pattern(self, pattern: str) -> list[str]:
        """
        Scan for keys matching a pattern.

        Args:
            pattern: Redis pattern to match (e.g., "bcs:essay_state:batch_001:*")

        Returns:
            List of keys matching the pattern
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            keys = []
            cursor = 0
            while True:
                cursor, batch_keys = await self.client.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch_keys)
                if cursor == 0:  # Scan complete
                    break

            logger.debug(
                f"Redis SCAN by '{self.client_id}': pattern='{pattern}' found={len(keys)} keys",
            )
            return keys
        except RedisTimeoutError:
            logger.error(
                f"Timeout on Redis SCAN operation by '{self.client_id}' for pattern '{pattern}'",
            )
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis SCAN operation by '{self.client_id}' for pattern '{pattern}': {e}",
                exc_info=True,
            )
            raise

    async def publish(self, channel: str, message: str) -> int:
        """
        Publish a message to a Redis channel.
        Delegates to RedisPubSub for pub/sub functionality.
        """
        if not self._started or not self._pubsub:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
        return await self._pubsub.publish(channel, message)

    @asynccontextmanager
    async def subscribe(self, channel: str):
        """
        Subscribe to a Redis channel.
        Delegates to RedisPubSub for pub/sub functionality.
        """
        if not self._started or not self._pubsub:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
        async with self._pubsub.subscribe(channel) as pubsub:
            yield pubsub

    def get_user_channel(self, user_id: str) -> str:
        """
        Generate standardized user-specific channel name.
        Delegates to RedisPubSub for consistency.
        """
        if not self._pubsub:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
        return self._pubsub.get_user_channel(user_id)

    async def publish_user_notification(
        self, user_id: str, event_type: str, data: dict[str, Any]
    ) -> int:
        """
        Convenience method to publish structured notifications to user-specific channels.
        Delegates to RedisPubSub for pub/sub functionality.
        """
        if not self._started or not self._pubsub:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
        return await self._pubsub.publish_user_notification(user_id, event_type, data)

    async def ping(self) -> bool:
        """
        Health check method to verify Redis connectivity.

        Returns:
            True if Redis connection is healthy

        Raises:
            RuntimeError: If client is not started
            RedisConnectionError: If Redis is not reachable
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform ping, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.ping()
            success = bool(result)
            logger.debug(
                f"Redis PING by '{self.client_id}': result={'SUCCESS' if success else 'FAILED'}"
            )
            return success
        except RedisConnectionError:
            logger.error(f"Redis ping failed - connection error for client '{self.client_id}'")
            raise
        except RedisTimeoutError:
            logger.error(f"Redis ping failed - timeout for client '{self.client_id}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis ping operation by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise
