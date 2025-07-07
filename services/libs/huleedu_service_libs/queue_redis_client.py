"""
Queue-specific Redis client implementation for HuleEdu services.

Provides specialized Redis operations for queue implementations, separate from
general-purpose Redis operations. Designed for reuse across services that need
queue functionality.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

import redis.asyncio as aioredis
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.queue_protocols import (
    QueueRedisClientProtocol,
    QueueRedisPipelineProtocol,
)
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = create_service_logger("queue-redis-client")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class QueueRedisPipeline:
    """Pipeline implementation for queue Redis operations."""

    def __init__(self, pipeline: aioredis.Pipeline, client_id: str):
        self._pipeline = pipeline
        self._client_id = client_id

    def zadd(self, key: str, mapping: dict[str, float]) -> QueueRedisPipelineProtocol:
        """Queue zadd operation in pipeline."""
        self._pipeline.zadd(key, mapping)
        logger.debug(f"Queue Redis ZADD queued by '{self._client_id}': key='{key}'")
        return self

    def zrem(self, key: str, *members: str) -> QueueRedisPipelineProtocol:
        """Queue zrem operation in pipeline."""
        self._pipeline.zrem(key, *members)
        logger.debug(
            f"Queue Redis ZREM queued by '{self._client_id}': key='{key}' members={members}"
        )
        return self

    def hset(self, key: str, field: str, value: str) -> QueueRedisPipelineProtocol:
        """Queue hset operation in pipeline."""
        self._pipeline.hset(key, field, value)
        logger.debug(f"Queue Redis HSET queued by '{self._client_id}': key='{key}' field='{field}'")
        return self

    def hdel(self, key: str, *fields: str) -> QueueRedisPipelineProtocol:
        """Queue hdel operation in pipeline."""
        self._pipeline.hdel(key, *fields)
        logger.debug(f"Queue Redis HDEL queued by '{self._client_id}': key='{key}' fields={fields}")
        return self

    def delete(self, key: str) -> QueueRedisPipelineProtocol:
        """Queue delete operation in pipeline."""
        self._pipeline.delete(key)
        logger.debug(f"Queue Redis DELETE queued by '{self._client_id}': key='{key}'")
        return self

    def setex(self, key: str, ttl_seconds: int, value: str) -> QueueRedisPipelineProtocol:
        """Queue setex operation in pipeline."""
        self._pipeline.setex(key, ttl_seconds, value)
        logger.debug(
            f"Queue Redis SETEX queued by '{self._client_id}': key='{key}' ttl={ttl_seconds}s"
        )
        return self

    async def execute(self) -> List[Any]:
        """Execute all queued operations atomically."""
        try:
            result = await self._pipeline.execute()
            logger.debug(
                f"Queue Redis pipeline executed by '{self._client_id}': {len(result)} operations"
            )
            return result
        except Exception as e:
            logger.error(
                f"Queue Redis pipeline execution failed for '{self._client_id}': {e}", exc_info=True
            )
            raise


class QueueRedisClient(QueueRedisClientProtocol):
    """Redis client specialized for queue operations."""

    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.client_id = client_id
        self.client = aioredis.from_url(
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
                logger.info(f"Queue Redis client '{self.client_id}' connected to {self.redis_url}")
            except RedisConnectionError as e:
                logger.error(f"Queue Redis client '{self.client_id}' failed to connect: {e}")
                raise
            except Exception as e:
                logger.error(f"Queue Redis client '{self.client_id}' startup error: {e}")
                raise

    async def stop(self) -> None:
        """Clean shutdown of Redis connection."""
        if self._started:
            try:
                await self.client.aclose()
                self._started = False
                logger.info(f"Queue Redis client '{self.client_id}' disconnected")
            except Exception as e:
                logger.error(
                    f"Error stopping Queue Redis client '{self.client_id}': {e}",
                    exc_info=True,
                )

    async def ping(self) -> bool:
        """Health check method to verify Redis connectivity."""
        if not self._started:
            logger.warning(
                f"Queue Redis client '{self.client_id}' not started. Attempting to start."
            )
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform ping, Queue Redis client '{self.client_id}' is not running."
                )
                raise RuntimeError(f"Queue Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.ping()
            success = bool(result)
            logger.debug(
                f"Queue Redis PING by '{self.client_id}': result={'SUCCESS' if success else 'FAILED'}"
            )
            return success
        except RedisConnectionError:
            logger.error(
                f"Queue Redis ping failed - connection error for client '{self.client_id}'"
            )
            raise
        except RedisTimeoutError:
            logger.error(f"Queue Redis ping failed - timeout for client '{self.client_id}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Queue Redis ping operation by '{self.client_id}': {e}", exc_info=True
            )
            raise

    # Sorted Set Operations
    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        """Add members to sorted set with scores."""
        self._ensure_started()
        try:
            result = await self.client.zadd(key, mapping)
            logger.debug(f"Queue Redis ZADD by '{self.client_id}': key='{key}' added={result}")
            return int(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis ZADD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def zrange(
        self, key: str, start: int, end: int, withscores: bool = False
    ) -> List[str] | List[tuple[str, float]]:
        """Get range of members from sorted set by rank."""
        self._ensure_started()
        try:
            result = await self.client.zrange(key, start, end, withscores=withscores)
            logger.debug(
                f"Queue Redis ZRANGE by '{self.client_id}': key='{key}' found={len(result)}"
            )
            return result
        except Exception as e:
            logger.error(
                f"Error in Queue Redis ZRANGE operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def zrem(self, key: str, *members: str) -> int:
        """Remove members from sorted set."""
        self._ensure_started()
        try:
            result = await self.client.zrem(key, *members)
            logger.debug(f"Queue Redis ZREM by '{self.client_id}': key='{key}' removed={result}")
            return int(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis ZREM operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def zcard(self, key: str) -> int:
        """Get cardinality (count) of sorted set."""
        self._ensure_started()
        try:
            result = await self.client.zcard(key)
            logger.debug(f"Queue Redis ZCARD by '{self.client_id}': key='{key}' count={result}")
            return int(result or 0)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis ZCARD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    # Hash Operations
    async def hset(self, key: str, field: str, value: str) -> int:
        """Set field in hash."""
        self._ensure_started()
        try:
            result = await self.client.hset(key, field, value)
            logger.debug(
                f"Queue Redis HSET by '{self.client_id}': key='{key}' field='{field}' result={result}"
            )
            return int(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HSET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get field from hash."""
        self._ensure_started()
        try:
            result = await self.client.hget(key, field)
            logger.debug(
                f"Queue Redis HGET by '{self.client_id}': key='{key}' field='{field}' result={'HIT' if result else 'MISS'}"
            )
            return str(result) if result is not None else None
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HGET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from hash."""
        self._ensure_started()
        try:
            result = await self.client.hdel(key, *fields)
            logger.debug(
                f"Queue Redis HDEL by '{self.client_id}': key='{key}' fields={fields} deleted={result}"
            )
            return int(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HDEL operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hmget(self, key: str, *fields: str) -> List[Optional[str]]:
        """Get multiple fields from hash."""
        self._ensure_started()
        try:
            result = await self.client.hmget(key, *fields)
            logger.debug(
                f"Queue Redis HMGET by '{self.client_id}': key='{key}' fields={len(fields)} hits={sum(1 for r in result if r is not None)}"
            )
            return [str(r) if r is not None else None for r in result]
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HMGET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hexists(self, key: str, field: str) -> bool:
        """Check if field exists in hash."""
        self._ensure_started()
        try:
            result = await self.client.hexists(key, field)
            logger.debug(
                f"Queue Redis HEXISTS by '{self.client_id}': key='{key}' field='{field}' exists={result}"
            )
            return bool(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HEXISTS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hkeys(self, key: str) -> List[str]:
        """Get all field names from hash."""
        self._ensure_started()
        try:
            result = await self.client.hkeys(key)
            logger.debug(
                f"Queue Redis HKEYS by '{self.client_id}': key='{key}' count={len(result)}"
            )
            return result
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HKEYS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hgetall(self, key: str) -> dict[str, str]:
        """Get all fields and values from hash."""
        self._ensure_started()
        try:
            result = await self.client.hgetall(key)
            logger.debug(
                f"Queue Redis HGETALL by '{self.client_id}': key='{key}' fields={len(result)}"
            )
            return result
        except Exception as e:
            logger.error(
                f"Error in Queue Redis HGETALL operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    # Key Operations
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        self._ensure_started()
        try:
            result = await self.client.exists(key)
            logger.debug(
                f"Queue Redis EXISTS by '{self.client_id}': key='{key}' exists={bool(result)}"
            )
            return bool(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis EXISTS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def delete(self, key: str) -> int:
        """Delete key."""
        self._ensure_started()
        try:
            result = await self.client.delete(key)
            logger.debug(f"Queue Redis DELETE by '{self.client_id}': key='{key}' deleted={result}")
            return int(result)
        except Exception as e:
            logger.error(
                f"Error in Queue Redis DELETE operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Set key with expiration."""
        self._ensure_started()
        try:
            result = await self.client.setex(key, ttl_seconds, value)
            success = bool(result)
            logger.debug(
                f"Queue Redis SETEX by '{self.client_id}': key='{key}' ttl={ttl_seconds}s result={'SUCCESS' if success else 'FAILED'}"
            )
            return success
        except Exception as e:
            logger.error(
                f"Error in Queue Redis SETEX operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    # Pipeline Operations
    def pipeline(self) -> QueueRedisPipelineProtocol:
        """Create pipeline for batch operations."""
        self._ensure_started()
        try:
            redis_pipeline = self.client.pipeline()
            logger.debug(f"Queue Redis pipeline created by '{self.client_id}'")
            return QueueRedisPipeline(redis_pipeline, self.client_id)
        except Exception as e:
            logger.error(
                f"Error creating Queue Redis pipeline by '{self.client_id}': {e}", exc_info=True
            )
            raise

    def _ensure_started(self) -> None:
        """Ensure client is started."""
        if not self._started:
            raise RuntimeError(f"Queue Redis client '{self.client_id}' is not running.")
