"""Handles spellcheck events for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common_core.domain_enums import ContentType
from common_core.error_enums import ErrorCode
from common_core.status_enums import ProcessingStage
from huleedu_service_libs.error_handling import create_error_detail_with_context
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import EventEnvelope, SpellcheckResultDataV1, SpellcheckResultV1

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

    async def process_spellcheck_completed(
        self,
        envelope: "EventEnvelope[SpellcheckResultDataV1]",
        data: "SpellcheckResultDataV1",
    ) -> None:
        """Process thin spellcheck completion event for state transitions."""
        try:
            # Extract entity information from system metadata using primitive fields
            if not data.system_metadata or not data.system_metadata.entity_id:
                logger.error("Missing entity information in spellcheck result")
                raise ValueError("Missing entity information")

            logger.info(
                "Processing spellcheck completed",
                entity_id=data.system_metadata.entity_id,
                entity_type=data.system_metadata.entity_type,
                parent_id=data.system_metadata.parent_id,
                status=data.status,
            )

            # Extract essay_id and batch_id from system metadata
            essay_id = data.system_metadata.entity_id
            batch_id = data.system_metadata.parent_id

            if not batch_id:
                logger.error("Missing batch_id in entity reference")
                raise ValueError("Missing batch_id in entity reference")

            # Determine status
            status = (
                ProcessingStage.COMPLETED
                if "SUCCESS" in data.status.upper()
                else ProcessingStage.FAILED
            )

            # Get corrected text storage ID from storage metadata
            corrected_text_storage_id = None
            if data.storage_metadata and hasattr(data.storage_metadata, "references"):
                # Check if there's a corrected text reference
                corrected_refs = data.storage_metadata.references.get(
                    ContentType.CORRECTED_TEXT, {}
                )
                if corrected_refs:
                    # Get the first storage ID from the references
                    corrected_text_storage_id = next(iter(corrected_refs.values()), None)

            # Create error detail if spellcheck failed
            error_detail = None
            if (
                status == ProcessingStage.FAILED
                and data.system_metadata
                and data.system_metadata.error_info
            ):
                error_detail = create_error_detail_with_context(
                    error_code=ErrorCode.SPELLCHECK_SERVICE_ERROR,
                    message=str(data.system_metadata.error_info),
                    service="result_aggregator_service",
                    operation="process_spellcheck_completed",
                    correlation_id=envelope.correlation_id,
                    details={
                        "essay_id": essay_id,
                        "batch_id": batch_id,
                        "status": data.status,
                    },
                )

            # Update essay result
            await self.batch_repository.update_essay_spellcheck_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correlation_id=envelope.correlation_id,
                correction_count=data.corrections_made,
                corrected_text_storage_id=corrected_text_storage_id,
                error_detail=error_detail,
            )

            # Invalidate cache
            await self.state_store.invalidate_batch(batch_id)

            logger.info(
                "Spellcheck result processed successfully",
                essay_id=essay_id,
                batch_id=batch_id,
            )

        except Exception as e:
            logger.error(
                "Failed to process spellcheck completed",
                error=str(e),
                exc_info=True,
            )
            raise

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

            # Extract essay_id and batch_id
            essay_id = data.entity_id
            batch_id = data.parent_id

            if not essay_id:
                logger.error("Missing essay_id in spellcheck result")
                raise ValueError("Missing essay_id in entity reference")

            if not batch_id:
                logger.error("Missing batch_id in spellcheck result")
                raise ValueError("Missing batch_id in entity reference")

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
            if (
                status == ProcessingStage.FAILED
                and data.system_metadata
                and data.system_metadata.error_info
            ):
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
