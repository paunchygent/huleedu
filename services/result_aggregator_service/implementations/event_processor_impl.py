"""Event processor implementation for Result Aggregator Service."""
from huleedu_service_libs.logging_utils import create_service_logger

from ..models_db import ProcessingPhaseStatus
from ..protocols import BatchRepositoryProtocol, EventProcessorProtocol, StateStoreProtocol

logger = create_service_logger("result_aggregator.event_processor")


class EventProcessorImpl(EventProcessorProtocol):
    """Processes incoming events and updates aggregated results."""

    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
    ):
        """Initialize the event processor."""
        self.batch_repository = batch_repository
        self.state_store = state_store

    async def process_batch_phase_outcome(
        self, envelope: "EventEnvelope", data: "ELSBatchPhaseOutcomeV1"
    ) -> None:
        """Process batch phase outcome from ELS."""
        try:
            logger.info(
                "Processing batch phase outcome",
                batch_id=data.batch_id,
                phase=data.phase,
                outcome=data.outcome,
            )

            # Update batch status based on phase outcome
            if data.outcome == "COMPLETED":
                await self.batch_repository.update_batch_phase_completed(
                    batch_id=data.batch_id,
                    phase=data.phase,
                    completed_count=data.metadata.get("completed_essay_count", 0),
                    failed_count=data.metadata.get("failed_essay_count", 0),
                )
            elif data.outcome == "FAILED":
                await self.batch_repository.update_batch_failed(
                    batch_id=data.batch_id,
                    error_message=data.metadata.get("error_message", "Phase failed"),
                )

            # Invalidate cache
            await self.state_store.invalidate_batch(data.batch_id)

            logger.info(
                "Batch phase outcome processed successfully",
                batch_id=data.batch_id,
                phase=data.phase,
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
        self, envelope: "EventEnvelope", data: "SpellcheckResultDataV1"
    ) -> None:
        """Process spellcheck completion event."""
        try:
            logger.info(
                "Processing spellcheck completed",
                entity_ref=data.entity_ref,
                status=data.status,
            )

            # Extract essay_id and batch_id from entity_ref
            # Assuming entity_ref format is "batch_id:essay_id"
            parts = data.entity_ref.split(":")
            if len(parts) != 2:
                logger.error("Invalid entity_ref format", entity_ref=data.entity_ref)
                raise ValueError(f"Invalid entity_ref format: {data.entity_ref}")
            
            batch_id, essay_id = parts

            # Determine status
            status = (
                ProcessingPhaseStatus.COMPLETED
                if "SUCCESS" in data.status.upper()
                else ProcessingPhaseStatus.FAILED
            )

            # Get corrected text storage ID from storage metadata
            corrected_text_storage_id = None
            if data.storage_metadata and data.storage_metadata.storage_ids:
                corrected_text_storage_id = data.storage_metadata.storage_ids.get("corrected_text")

            # Update essay result
            await self.batch_repository.update_essay_spellcheck_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correction_count=data.corrections_made,
                corrected_text_storage_id=corrected_text_storage_id,
                error=data.system_metadata.error_info if status == ProcessingPhaseStatus.FAILED else None,
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
                entity_ref=data.entity_ref,
                error=str(e),
                exc_info=True,
            )
            raise

    async def process_cj_assessment_completed(
        self, envelope: "EventEnvelope", data: "CJAssessmentCompletedV1"
    ) -> None:
        """Process CJ assessment completion event."""
        try:
            logger.info(
                "Processing CJ assessment completed",
                entity_ref=data.entity_ref,
                job_id=data.cj_assessment_job_id,
            )

            # entity_ref is the batch_id for CJ assessment events
            batch_id = data.entity_ref

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
                    status=ProcessingPhaseStatus.COMPLETED,
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