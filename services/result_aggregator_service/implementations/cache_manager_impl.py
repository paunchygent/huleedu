"""Cache manager implementation for Result Aggregator Service."""
from typing import Optional

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from ..models_api import BatchStatusResponse
from ..models_db import BatchResult
from ..protocols import CacheManagerProtocol

logger = create_service_logger("result_aggregator.cache_manager")


class CacheManagerImpl(CacheManagerProtocol):
    """Redis-based cache manager implementation.
    
    Note: This implementation caches the API response (BatchStatusResponse) as JSON,
    but the protocol expects BatchResult (SQLAlchemy model). This is a design
    limitation - we can cache writes but not serve cached reads directly.
    
    Future improvement: Create a separate cache protocol that works with API models
    or implement a caching layer at the API route level instead.
    """

    def __init__(self, redis_client: RedisClientProtocol, cache_ttl: int = 300):
        """Initialize with Redis client."""
        self.redis = redis_client
        self.cache_ttl = cache_ttl

    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """Get cached batch status."""
        # TODO: Implement caching strategy for SQLAlchemy models
        # For now, always return None (cache miss) to force DB query
        # Options:
        # 1. Cache the API response model separately
        # 2. Implement SQLAlchemy model serialization
        # 3. Cache only the IDs and re-query with those
        return None

    async def set_batch_status(
        self,
        batch_id: str,
        status: BatchResult,
        ttl: int = 300,
    ) -> None:
        """Cache batch status."""
        try:
            # Convert SQLAlchemy model to API response model
            response = BatchStatusResponse.from_domain(status)
            
            # Serialize to JSON using Pydantic's built-in method
            json_data = response.model_dump_json()
            
            # Store in Redis with TTL
            cache_key = f"ras:batch:{batch_id}"
            await self.redis.setex(cache_key, ttl, json_data)
            
            logger.debug(
                "Cached batch status",
                batch_id=batch_id,
                ttl=ttl,
                cache_key=cache_key
            )
        except Exception as e:
            # Caching failures should not break the service
            logger.warning(
                "Failed to cache batch status",
                batch_id=batch_id,
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