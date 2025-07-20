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
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_pubsub import RedisPubSub

logger = create_service_logger("redis-client")  # Use structured logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class RedisClient(AtomicRedisClientProtocol):
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

    # Set operations for atomic batch coordination
    async def sadd(self, key: str, *members: str) -> int:
        """Add one or more members to a Redis set."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.sadd(key, *members)

            if self._transaction_pipeline is None:
                added_count = int(result)
                logger.debug(
                    f"Redis SADD by '{self.client_id}': key='{key}' added={added_count} members"
                )
                return added_count
            else:
                logger.debug(f"Redis SADD queued by '{self.client_id}': key='{key}'")
                return 0  # Command queued, actual count determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis SADD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def spop(self, key: str) -> str | None:
        """Remove and return a random member from a Redis set."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.spop(key)

            if self._transaction_pipeline is None:
                member = result.decode() if isinstance(result, bytes) else result
                logger.debug(
                    f"Redis SPOP by '{self.client_id}': key='{key}' "
                    f"result={'MEMBER' if member else 'EMPTY'}"
                )
                return member
            else:
                logger.debug(f"Redis SPOP queued by '{self.client_id}': key='{key}'")
                return None  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis SPOP operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def scard(self, key: str) -> int:
        """Get the number of members in a Redis set."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.scard(key)

            if self._transaction_pipeline is None:
                count = int(result)
                logger.debug(f"Redis SCARD by '{self.client_id}': key='{key}' count={count}")
                return count
            else:
                logger.debug(f"Redis SCARD queued by '{self.client_id}': key='{key}'")
                return 0  # Command queued, actual count determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis SCARD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def smembers(self, key: str) -> set[str]:
        """Get all members of a Redis set."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.smembers(key)

            if self._transaction_pipeline is None:
                members = set(result) if result else set()
                logger.debug(
                    f"Redis SMEMBERS by '{self.client_id}': key='{key}' "
                    f"returned {len(members)} members"
                )
                return members
            else:
                logger.debug(f"Redis SMEMBERS queued by '{self.client_id}': key='{key}'")
                return set()  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis SMEMBERS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    # Hash operations for metadata storage
    async def hset(self, key: str, field: str, value: str) -> int:
        """Set field in a Redis hash."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.hset(key, field, value)

            if self._transaction_pipeline is None:
                is_new = int(result)
                logger.debug(
                    f"Redis HSET by '{self.client_id}': key='{key}' field='{field}' "
                    f"result={'NEW' if is_new else 'UPDATED'}"
                )
                return is_new
            else:
                logger.debug(
                    f"Redis HSET queued by '{self.client_id}': key='{key}' field='{field}'"
                )
                return 0  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis HSET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hget(self, key: str, field: str) -> str | None:
        """Get field value from a Redis hash."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.hget(key, field)

            if self._transaction_pipeline is None:
                value = result.decode() if isinstance(result, bytes) else result
                logger.debug(
                    f"Redis HGET by '{self.client_id}': key='{key}' field='{field}' "
                    f"result={'FOUND' if value else 'NOT_FOUND'}"
                )
                return value
            else:
                logger.debug(
                    f"Redis HGET queued by '{self.client_id}': key='{key}' field='{field}'"
                )
                return None  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis HGET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hlen(self, key: str) -> int:
        """Get the number of fields in a Redis hash."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.hlen(key)

            if self._transaction_pipeline is None:
                count = int(result)
                logger.debug(f"Redis HLEN by '{self.client_id}': key='{key}' count={count}")
                return count
            else:
                logger.debug(f"Redis HLEN queued by '{self.client_id}': key='{key}'")
                return 0  # Command queued, actual count determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis HLEN operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hgetall(self, key: str) -> dict[str, str]:
        """Get all fields and values from a Redis hash."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.hgetall(key)

            if self._transaction_pipeline is None:
                data = dict(result) if result else {}
                logger.debug(
                    f"Redis HGETALL by '{self.client_id}': key='{key}' returned {len(data)} fields"
                )
                return data
            else:
                logger.debug(f"Redis HGETALL queued by '{self.client_id}': key='{key}'")
                return {}  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis HGETALL operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hexists(self, key: str, field: str) -> bool:
        """Check if field exists in a Redis hash."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.hexists(key, field)

            if self._transaction_pipeline is None:
                exists = bool(result)
                logger.debug(
                    f"Redis HEXISTS by '{self.client_id}': key='{key}' field='{field}' "
                    f"exists={'YES' if exists else 'NO'}"
                )
                return exists
            else:
                logger.debug(
                    f"Redis HEXISTS queued by '{self.client_id}': key='{key}' field='{field}'"
                )
                return False  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis HEXISTS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL for a Redis key."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.expire(key, ttl_seconds)

            if self._transaction_pipeline is None:
                success = bool(result)
                logger.debug(
                    f"Redis EXPIRE by '{self.client_id}': key='{key}' ttl={ttl_seconds}s "
                    f"result={'SUCCESS' if success else 'FAILED'}"
                )
                return success
            else:
                logger.debug(
                    f"Redis EXPIRE queued by '{self.client_id}': key='{key}' ttl={ttl_seconds}s"
                )
                return True  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis EXPIRE operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def rpush(self, key: str, *values: str) -> int:
        """Append values to a Redis list."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.rpush(key, *values)

            if self._transaction_pipeline is None:
                length = int(result)
                logger.debug(
                    f"Redis RPUSH by '{self.client_id}': key='{key}' "
                    f"values={len(values)} new_length={length}"
                )
                return length
            else:
                logger.debug(f"Redis RPUSH queued by '{self.client_id}': key='{key}'")
                return 0  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis RPUSH operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """Get range of elements from a Redis list."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.lrange(key, start, stop)

            if self._transaction_pipeline is None:
                elements = result or []
                logger.debug(
                    f"Redis LRANGE by '{self.client_id}': key='{key}' "
                    f"range=({start},{stop}) count={len(elements)}"
                )
                return elements
            else:
                logger.debug(f"Redis LRANGE queued by '{self.client_id}': key='{key}'")
                return []  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis LRANGE operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def llen(self, key: str) -> int:
        """Get the length of a Redis list."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.llen(key)

            if self._transaction_pipeline is None:
                length = int(result)
                logger.debug(f"Redis LLEN by '{self.client_id}': key='{key}' length={length}")
                return length
            else:
                logger.debug(f"Redis LLEN queued by '{self.client_id}': key='{key}'")
                return 0  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis LLEN operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def ttl(self, key: str) -> int:
        """Get time to live for a key in seconds."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.ttl(key)

            if self._transaction_pipeline is None:
                ttl_seconds = int(result)
                logger.debug(f"Redis TTL by '{self.client_id}': key='{key}' ttl={ttl_seconds}s")
                return ttl_seconds
            else:
                logger.debug(f"Redis TTL queued by '{self.client_id}': key='{key}'")
                return -1  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis TTL operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def exists(self, key: str) -> int:
        """Check if a key exists."""
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            redis_client = self._transaction_pipeline or self.client
            result = await redis_client.exists(key)

            if self._transaction_pipeline is None:
                exists_count = int(result)
                logger.debug(
                    f"Redis EXISTS by '{self.client_id}': key='{key}' "
                    f"exists={'YES' if exists_count > 0 else 'NO'}"
                )
                return exists_count
            else:
                logger.debug(f"Redis EXISTS queued by '{self.client_id}': key='{key}'")
                return 0  # Command queued, actual result determined by EXEC
        except Exception as e:
            logger.error(
                f"Error in Redis EXISTS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise
