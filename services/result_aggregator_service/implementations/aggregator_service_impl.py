"""Aggregator service implementation for batch queries."""

from __future__ import annotations

from typing import List, Optional

from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.bos_data_transformer import (
    BOSDataTransformer,
)
from services.result_aggregator_service.models_db import BatchResult
from services.result_aggregator_service.protocols import (
    BatchOrchestratorClientProtocol,
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
        bos_client: BatchOrchestratorClientProtocol,
        bos_transformer: BOSDataTransformer,
        settings: Settings,
    ):
        """Initialize the service."""
        self.batch_repository = batch_repository
        self.cache_manager = cache_manager
        self.bos_client = bos_client
        self.bos_transformer = bos_transformer
        self.settings = settings

    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """
        Get comprehensive batch status with BOS fallback for consistency.

        This method implements internal consistency logic that was previously
        handled in the API Gateway. When batch data is not found in RAS database,
        it falls back to querying BOS directly and transforms the data internally.
        """
        try:
            # First try to get batch from local database
            batch_result = await self.batch_repository.get_batch(batch_id)
            if batch_result is not None:
                logger.debug(
                    "Found batch in local database",
                    batch_id=batch_id
                )
                return batch_result

            # Fallback to BOS for consistency
            logger.info(
                "Batch not found in RAS database, querying BOS for consistency",
                batch_id=batch_id
            )

            bos_data = await self.bos_client.get_pipeline_state(batch_id)
            if bos_data is None:
                logger.info(
                    "Batch not found in BOS either",
                    batch_id=batch_id
                )
                return None

            # Transform BOS data to RAS format
            # Note: We use the BOS user_id since we don't have user context here
            # This will be validated at the API Gateway level for ownership
            user_id = bos_data.get("user_id")
            if not user_id:
                logger.error(
                    "BOS data missing user_id field",
                    batch_id=batch_id,
                    bos_data_keys=list(bos_data.keys())
                )
                return None

            transformed_batch = self.bos_transformer.transform_bos_to_batch_result(
                bos_data, user_id
            )

            logger.info(
                "Successfully transformed BOS data to BatchResult",
                batch_id=batch_id,
                status=transformed_batch.overall_status,
                user_id=user_id
            )

            return transformed_batch

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
