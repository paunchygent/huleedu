"""Redis implementation of state store."""
from typing import Optional

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClientProtocol

from ..protocols import StateStoreProtocol

logger = create_service_logger("result_aggregator.state_store")


class StateStoreRedisImpl(StateStoreProtocol):
    """Redis implementation for caching and state management."""

    def __init__(self, redis_client: RedisClientProtocol, cache_ttl: int = 300):
        """Initialize with Redis client."""
        self.redis = redis_client
        self.cache_ttl = cache_ttl

    async def get_cached_batch(self, batch_id: str) -> Optional[str]:
        """Get cached batch data."""
        cache_key = f"ras:batch:{batch_id}"
        try:
            return await self.redis.get(cache_key)
        except Exception as e:
            logger.warning(
                "Failed to get cached batch",
                batch_id=batch_id,
                error=str(e),
            )
            return None

    async def cache_batch(self, batch_id: str, data: str) -> None:
        """Cache batch data."""
        cache_key = f"ras:batch:{batch_id}"
        try:
            await self.redis.setex(cache_key, self.cache_ttl, data)
        except Exception as e:
            logger.warning(
                "Failed to cache batch",
                batch_id=batch_id,
                error=str(e),
            )

    async def invalidate_batch(self, batch_id: str) -> None:
        """Invalidate cached batch data."""
        cache_key = f"ras:batch:{batch_id}"
        try:
            await self.redis.delete(cache_key)
        except Exception as e:
            logger.warning(
                "Failed to invalidate batch cache",
                batch_id=batch_id,
                error=str(e),
            )

    async def record_processing(self, event_id: str, ttl: int = 86400) -> bool:
        """Record event processing for idempotency."""
        key = f"ras:processed:{event_id}"
        try:
            # Use SET NX (set if not exists) for atomic operation
            result = await self.redis.setnx(key, "1")
            if result:
                await self.redis.expire(key, ttl)
            return result
        except Exception as e:
            logger.error(
                "Failed to record processing",
                event_id=event_id,
                error=str(e),
            )
            # Fail open - allow processing to continue
            return True