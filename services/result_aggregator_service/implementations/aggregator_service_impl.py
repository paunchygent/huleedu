"""Aggregator service implementation for batch queries."""
from __future__ import annotations

from typing import List, Optional

from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.models_db import BatchResult
from services.result_aggregator_service.protocols import (
    BatchQueryServiceProtocol,
    BatchRepositoryProtocol,
    CacheManagerProtocol,
)

logger = create_service_logger("result_aggregator.aggregator_service")


class AggregatorServiceImpl(BatchQueryServiceProtocol):
    """Implementation of batch query service."""

    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        settings: Settings,
    ):
        """Initialize the service."""
        self.batch_repository = batch_repository
        self.cache_manager = cache_manager
        self.settings = settings

    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """Get comprehensive batch status."""
        try:
            # Note: Caching is now handled at the API layer since we cache JSON responses
            # This service method just retrieves from the database
            return await self.batch_repository.get_batch(batch_id)

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
