"""Cache manager implementation for Result Aggregator Service."""

from typing import Optional

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from ..protocols import CacheManagerProtocol

logger = create_service_logger("result_aggregator.cache_manager")


class CacheManagerImpl(CacheManagerProtocol):
    """Redis-based cache manager implementation.

    This implementation caches the final API response as JSON strings,
    providing a clean abstraction for caching serialized data.
    """

    def __init__(self, redis_client: RedisClientProtocol, cache_ttl: int = 300):
        """Initialize with Redis client."""
        self.redis = redis_client
        self.cache_ttl = cache_ttl

    async def get_batch_status_json(self, batch_id: str) -> Optional[str]:
        """Get cached batch status as JSON string."""
        try:
            cache_key = f"ras:batch:{batch_id}"
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                logger.debug("Cache hit for batch status", batch_id=batch_id)
                return cached_data
            else:
                logger.debug("Cache miss for batch status", batch_id=batch_id)
                return None
        except Exception as e:
            logger.warning(
                "Failed to get cached batch status",
                batch_id=batch_id,
                error=str(e),
            )
            return None

    async def set_batch_status_json(
        self,
        batch_id: str,
        status_json: str,
        ttl: int = 300,
    ) -> None:
        """Cache batch status as JSON string."""
        try:
            cache_key = f"ras:batch:{batch_id}"
            await self.redis.setex(cache_key, ttl, status_json)

            logger.debug("Cached batch status", batch_id=batch_id, ttl=ttl, cache_key=cache_key)
        except Exception as e:
            # Caching failures should not break the service
            logger.warning(
                "Failed to cache batch status",
                batch_id=batch_id,
                error=str(e),
            )

    async def get_user_batches_json(
        self, user_id: str, limit: int, offset: int, status: Optional[str]
    ) -> Optional[str]:
        """Get cached user batches list as JSON string."""
        try:
            cache_key = self._build_user_batches_key(user_id, limit, offset, status)
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                logger.debug("Cache hit for user batches", user_id=user_id, cache_key=cache_key)
                return cached_data
            else:
                logger.debug("Cache miss for user batches", user_id=user_id, cache_key=cache_key)
                return None
        except Exception as e:
            logger.warning(
                "Failed to get cached user batches",
                user_id=user_id,
                error=str(e),
            )
            return None

    async def set_user_batches_json(
        self, user_id: str, limit: int, offset: int, status: Optional[str], data_json: str, ttl: int
    ) -> None:
        """Cache user batches list as JSON string."""
        try:
            cache_key = self._build_user_batches_key(user_id, limit, offset, status)
            await self.redis.setex(cache_key, ttl, data_json)

            logger.debug("Cached user batches", user_id=user_id, ttl=ttl, cache_key=cache_key)
        except Exception as e:
            logger.warning(
                "Failed to cache user batches",
                user_id=user_id,
                error=str(e),
            )

    async def invalidate_batch(self, batch_id: str) -> None:
        """Invalidate cached batch data."""
        cache_key = f"ras:batch:{batch_id}"
        try:
            await self.redis.delete_key(cache_key)
        except Exception as e:
            logger.warning(
                "Failed to invalidate batch cache",
                batch_id=batch_id,
                error=str(e),
            )

    async def invalidate_user_batches(self, user_id: str) -> None:
        """Invalidate all cached user batch lists.

        Design Decision: This method intentionally does not perform active cache
        invalidation. We rely on TTL-based expiration (5 minutes) instead because:
        1. Pattern-based deletion is expensive at scale
        2. The short TTL is sufficient for our use case
        3. Batch data doesn't change frequently enough to require immediate invalidation

        The method exists to maintain the protocol interface and logs a warning
        to document this limitation.
        """
        try:
            pattern = f"ras:user:{user_id}:batches:*"
            logger.warning(
                "User cache invalidation not implemented - using TTL-based expiration",
                user_id=user_id,
                pattern=pattern,
                ttl_seconds=self.cache_ttl,
            )
        except Exception as e:
            logger.warning(
                "Failed to invalidate user batches cache",
                user_id=user_id,
                error=str(e),
            )

    def _build_user_batches_key(
        self, user_id: str, limit: int, offset: int, status: Optional[str]
    ) -> str:
        """Build cache key for user batches list."""
        status_part = status or "all"
        return f"ras:user:{user_id}:batches:{limit}:{offset}:{status_part}"
