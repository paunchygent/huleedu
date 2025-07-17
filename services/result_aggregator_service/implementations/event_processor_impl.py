"""Event processor implementation for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.protocols import (
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
    StateStoreProtocol,
)

if TYPE_CHECKING:
    from common_core.events import (
        BatchEssaysRegistered,
        CJAssessmentCompletedV1,
        ELSBatchPhaseOutcomeV1,
        EventEnvelope,
        SpellcheckResultDataV1,
    )

logger = create_service_logger("result_aggregator.event_processor")


class EventProcessorImpl(EventProcessorProtocol):
    """Processes incoming events and updates aggregated results."""

    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
        cache_manager: CacheManagerProtocol,
    ):
        """Initialize the event processor."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager

    async def process_batch_registered(
        self, envelope: "EventEnvelope[BatchEssaysRegistered]", data: "BatchEssaysRegistered"
    ) -> None:
        """Create the initial batch result record upon registration."""
        try:
            logger.info(
                "Processing batch registration",
                batch_id=data.batch_id,
                user_id=data.user_id,
                essay_count=data.expected_essay_count,
            )

            # Create the initial batch record
            await self.batch_repository.create_batch(
                batch_id=data.batch_id,
                user_id=data.user_id,
                essay_count=data.expected_essay_count,
                metadata={"requested_pipelines": data.requested_pipelines}
                if hasattr(data, "requested_pipelines")
                else None,
            )

            await self.cache_manager.invalidate_user_batches(data.user_id)

            logger.info(
                "Created initial batch record and invalidated user cache",
                batch_id=data.batch_id,
                user_id=data.user_id,
            )

        except Exception as e:
            logger.error(
                "Failed to process batch registration",
                batch_id=data.batch_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def process_batch_phase_outcome(
        self, envelope: "EventEnvelope[ELSBatchPhaseOutcomeV1]", data: "ELSBatchPhaseOutcomeV1"
    ) -> None:
        """Process batch phase outcome from ELS."""
        try:
            logger.info(
                "Processing batch phase outcome",
                batch_id=data.batch_id,
                phase=data.phase_name.value,
                outcome=data.phase_status.value,
            )

            # Update batch status based on phase outcome
            if data.phase_status in [
                BatchStatus.COMPLETED_SUCCESSFULLY,
                BatchStatus.COMPLETED_WITH_FAILURES,
            ]:
                completed_count = len(data.processed_essays)
                failed_count = len(data.failed_essay_ids)

                await self.batch_repository.update_batch_phase_completed(
                    batch_id=data.batch_id,
                    phase=data.phase_name.value,
                    completed_count=completed_count,
                    failed_count=failed_count,
                )
            elif data.phase_status == BatchStatus.FAILED_CRITICALLY:
                await self.batch_repository.update_batch_failed(
                    batch_id=data.batch_id,
                    error_message=f"Phase {data.phase_name.value} failed critically",
                )

            # Invalidate cache
            await self.state_store.invalidate_batch(data.batch_id)

            logger.info(
                "Batch phase outcome processed successfully",
                batch_id=data.batch_id,
                phase=data.phase_name.value,
            )

        except Exception as e:
            logger.error(
                "Failed to process batch phase outcome",
                batch_id=data.batch_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def process_spellcheck_completed(
        self, envelope: "EventEnvelope[SpellcheckResultDataV1]", data: "SpellcheckResultDataV1"
    ) -> None:
        """Process spellcheck completion event."""
        try:
            # Extract entity reference from system metadata
            entity_ref = data.system_metadata.entity if data.system_metadata else None
            if not entity_ref:
                logger.error("Missing entity reference in spellcheck result")
                raise ValueError("Missing entity reference")

            logger.info(
                "Processing spellcheck completed",
                entity_id=entity_ref.entity_id,
                entity_type=entity_ref.entity_type,
                parent_id=entity_ref.parent_id,
                status=data.status,
            )

            # Extract essay_id and batch_id from entity reference
            essay_id = entity_ref.entity_id
            batch_id = entity_ref.parent_id

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
                from common_core.domain_enums import ContentType

                corrected_refs = data.storage_metadata.references.get(
                    ContentType.CORRECTED_TEXT, {}
                )
                if corrected_refs:
                    # Get the first storage ID from the references
                    corrected_text_storage_id = next(iter(corrected_refs.values()), None)

            # Update essay result
            await self.batch_repository.update_essay_spellcheck_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correction_count=data.corrections_made,
                corrected_text_storage_id=corrected_text_storage_id,
                error=str(data.system_metadata.error_info)
                if (
                    status == ProcessingStage.FAILED
                    and data.system_metadata
                    and data.system_metadata.error_info
                )
                else None,
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

    async def process_cj_assessment_completed(
        self, envelope: "EventEnvelope[CJAssessmentCompletedV1]", data: "CJAssessmentCompletedV1"
    ) -> None:
        """Process CJ assessment completion event."""
        try:
            logger.info(
                "Processing CJ assessment completed",
                entity_id=data.entity_ref.entity_id,
                entity_type=data.entity_ref.entity_type,
                job_id=data.cj_assessment_job_id,
            )

            # entity_ref.entity_id is the batch_id for CJ assessment events
            batch_id = data.entity_ref.entity_id

            # Process each ranking result
            for ranking in data.rankings:
                essay_id = ranking.get("els_essay_id")
                rank = ranking.get("rank")
                score = ranking.get("score")

                if not essay_id:
                    logger.warning("Missing essay_id in ranking", ranking=ranking)
                    continue

                await self.batch_repository.update_essay_cj_assessment_result(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    status=ProcessingStage.COMPLETED,
                    rank=rank,
                    score=score,
                    comparison_count=None,  # Not provided in current event
                    error=None,
                )

            # Invalidate cache
            await self.state_store.invalidate_batch(batch_id)

            logger.info(
                "CJ assessment results processed successfully",
                batch_id=batch_id,
                rankings_count=len(data.rankings),
            )

        except Exception as e:
            logger.error(
                "Failed to process CJ assessment completed",
                entity_ref=data.entity_ref,
                error=str(e),
                exc_info=True,
            )
            raise
