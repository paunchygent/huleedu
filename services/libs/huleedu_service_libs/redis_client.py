"""
Redis client wrapper for HuleEdu microservices.

Provides minimal Redis operations needed for event idempotency patterns.
Follows the same lifecycle management pattern as KafkaBus.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from .logging_utils import create_service_logger

logger = create_service_logger("redis-client")  # Use structured logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class RedisClient:
    """HuleEdu Redis client with lifecycle management for idempotency operations."""

    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.client_id = client_id  # Store client_id for logging
        self.client = redis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self._started = False

    async def start(self) -> None:
        """Initialize Redis connection with health verification."""
        if not self._started:
            try:
                await self.client.ping()
                self._started = True
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
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
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
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running."
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.set(key, value, ex=ttl_seconds, nx=True)
            success = bool(result)
            logger.debug(
                f"Redis SETNX by '{self.client_id}': key='{key}' "
                f"ttl={ttl_seconds}s result={'SET' if success else 'EXISTS'}"
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
            deleted_count = await self.client.delete(key)
            logger.debug(f"Redis DELETE by '{self.client_id}': key='{key}' deleted={deleted_count}")
            return int(deleted_count)
        except Exception as e:
            logger.error(
                f"Error deleting Redis key '{key}' by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise
