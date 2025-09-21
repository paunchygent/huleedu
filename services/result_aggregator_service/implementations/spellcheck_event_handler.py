"""Handles spellcheck events for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common_core.error_enums import ErrorCode
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.error_handling import create_error_detail_with_context
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import EventEnvelope, SpellcheckResultV1

    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.spellcheck_handler")


class SpellcheckEventHandler:
    """Handles both thin and rich spellcheck events following dual-event pattern."""

    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
    ):
        """Initialize with dependencies."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager

    async def process_spellcheck_result(
        self,
        envelope: "EventEnvelope[SpellcheckResultV1]",
        data: "SpellcheckResultV1",
    ) -> None:
        """Process rich spellcheck result event with enhanced business metrics."""
        try:
            logger.info(
                "Processing rich spellcheck result",
                entity_id=data.entity_id,
                batch_id=data.parent_id,
                status=data.status,
                total_corrections=data.corrections_made,
            )

            # Extract essay_id and batch_id (now explicit field, no fallback)
            essay_id = data.entity_id
            batch_id = data.batch_id  # Use explicit batch_id field

            if not essay_id:
                logger.error("Missing essay_id in spellcheck result")
                raise ValueError("Missing essay_id in entity reference")

            if not batch_id:
                logger.error("Missing batch_id in spellcheck result - no fallback to parent_id")
                raise ValueError("Missing batch_id field in SpellcheckResultV1")

            # Determine status
            status = (
                ProcessingStage.COMPLETED
                if "SUCCESS" in data.status.upper()
                else ProcessingStage.FAILED
            )

            # Extract corrected text storage ID
            corrected_text_storage_id = data.corrected_text_storage_id

            # Create error detail if spellcheck failed
            error_detail = None
            if status == ProcessingStage.FAILED and data.system_metadata.error_info:
                error_detail = create_error_detail_with_context(
                    error_code=ErrorCode.SPELLCHECK_SERVICE_ERROR,
                    message=str(data.system_metadata.error_info),
                    service="result_aggregator_service",
                    operation="process_spellcheck_result",
                    correlation_id=envelope.correlation_id,
                    details={
                        "essay_id": essay_id,
                        "batch_id": batch_id,
                        "status": data.status,
                    },
                )

            # Extract enhanced metrics from the rich event
            metrics = data.correction_metrics

            # Update essay result with enhanced metrics
            await self.batch_repository.update_essay_spellcheck_result_with_metrics(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correlation_id=envelope.correlation_id,
                correction_count=data.corrections_made,
                corrected_text_storage_id=corrected_text_storage_id,
                error_detail=error_detail,
                # Enhanced metrics from rich event
                l2_corrections=metrics.l2_dictionary_corrections,
                spell_corrections=metrics.spellchecker_corrections,
                word_count=metrics.word_count,
                correction_density=metrics.correction_density,
                processing_duration_ms=data.processing_duration_ms,
            )

            # Invalidate cache
            await self.state_store.invalidate_batch(batch_id)

            logger.info(
                "Rich spellcheck result processed successfully",
                essay_id=essay_id,
                batch_id=batch_id,
                l2_corrections=metrics.l2_dictionary_corrections,
                spell_corrections=metrics.spellchecker_corrections,
                word_count=metrics.word_count,
                correction_density=metrics.correction_density,
            )

        except Exception as e:
            logger.error(
                "Failed to process rich spellcheck result",
                error=str(e),
                exc_info=True,
            )
            raise
