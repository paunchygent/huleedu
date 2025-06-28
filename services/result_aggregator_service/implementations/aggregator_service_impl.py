"""Aggregator service implementation for batch queries."""
from typing import Any, List, Optional

from huleedu_service_libs.logging_utils import create_service_logger

from ..models_db import BatchResult
from ..protocols import BatchQueryServiceProtocol, BatchRepositoryProtocol, CacheManagerProtocol

logger = create_service_logger("result_aggregator.aggregator_service")


class AggregatorServiceImpl(BatchQueryServiceProtocol):
    """Implementation of batch query service."""

    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        settings: Any,  # Settings type
    ):
        """Initialize the service."""
        self.batch_repository = batch_repository
        self.cache_manager = cache_manager
        self.settings = settings

    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """Get comprehensive batch status."""
        try:
            # Try cache first if enabled
            if self.settings.CACHE_ENABLED:
                cached = await self.cache_manager.get_batch_status(batch_id)
                if cached:
                    logger.debug("Batch status retrieved from cache", batch_id=batch_id)
                    return cached

            # Get from database
            batch = await self.batch_repository.get_batch(batch_id)
            
            if batch and self.settings.CACHE_ENABLED:
                # Cache the result
                await self.cache_manager.set_batch_status(
                    batch_id, batch, ttl=self.settings.REDIS_CACHE_TTL_SECONDS
                )

            return batch

        except Exception as e:
            logger.error(
                "Failed to get batch status",
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_user_batches(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BatchResult]:
        """Get all batches for a user."""
        try:
            return await self.batch_repository.get_user_batches(
                user_id=user_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            logger.error(
                "Failed to get user batches",
                user_id=user_id,
                error=str(e),
                exc_info=True,
            )
            raise