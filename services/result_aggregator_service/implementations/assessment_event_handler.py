"""Handles assessment events for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common_core.events.cj_assessment_events import AssessmentResultV1
from common_core.events.result_events import BatchAssessmentCompletedV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import EventEnvelope

    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        EventPublisherProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.assessment_handler")


class AssessmentEventHandler:
    """Handles CJ assessment results and essay file mapping."""

    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
        event_publisher: "EventPublisherProtocol",
    ):
        """Initialize with dependencies."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher

    async def process_essay_slot_assigned(
        self,
        envelope: "EventEnvelope[Any]",
        data: Any,  # EssaySlotAssignedV1
    ) -> None:
        """Process essay slot assignment event for file traceability."""
        try:
            # Type checking - data is EssaySlotAssignedV1
            logger.info(
                "Processing essay slot assignment",
                batch_id=data.batch_id,
                essay_id=data.essay_id,
                file_upload_id=data.file_upload_id,
            )

            # Update the essay record with file_upload_id mapping and filename
            await self.batch_repository.update_essay_file_mapping(
                essay_id=data.essay_id,
                file_upload_id=data.file_upload_id,
                text_storage_id=data.text_storage_id,
                filename=data.original_file_name,
            )

            # Invalidate cache to ensure fresh data includes file_upload_id
            await self.state_store.invalidate_batch(data.batch_id)

            # Get batch to find user_id for cache invalidation
            batch = await self.batch_repository.get_batch(data.batch_id)
            if batch:
                await self.cache_manager.invalidate_user_batches(batch.user_id)

            logger.info(
                "Essay slot assignment processed successfully",
                essay_id=data.essay_id,
                file_upload_id=data.file_upload_id,
            )

        except Exception as e:
            logger.error(
                "Failed to process essay slot assignment",
                essay_id=getattr(data, "essay_id", "unknown"),
                error=str(e),
                exc_info=True,
            )
            raise

    async def process_assessment_result(
        self,
        envelope: "EventEnvelope[AssessmentResultV1]",
        data: AssessmentResultV1,
    ) -> None:
        """Process rich CJ assessment result event with business data."""
        try:
            batch_id = data.batch_id

            logger.info(
                "Processing assessment results",
                batch_id=batch_id,
                cj_job_id=data.cj_assessment_job_id,
                essay_count=len(data.essay_results),
                assessment_method=data.assessment_method,
            )

            # Process each essay result (excluding anchors for student results)
            student_results = [r for r in data.essay_results if not r.is_anchor]

            for essay_result in student_results:
                essay_id = essay_result.essay_id
                rank = essay_result.rank
                bt_score = essay_result.bt_score

                await self.batch_repository.update_essay_cj_assessment_result(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    status=ProcessingStage.COMPLETED,
                    correlation_id=envelope.correlation_id,
                    rank=rank,
                    score=bt_score,
                    comparison_count=data.assessment_metadata.get("comparison_count"),
                    error_detail=None,
                )

            # Invalidate cache
            await self.state_store.invalidate_batch(batch_id)

            # Publish BatchAssessmentCompletedV1 event for downstream services
            batch = await self.batch_repository.get_batch(batch_id)
            if batch:
                # Create enriched rankings summary with business data
                rankings_summary = [
                    {
                        "essay_id": r.essay_id,
                        "rank": r.rank,
                        "score": r.bt_score,
                        "letter_grade": r.letter_grade,
                        "confidence_score": r.confidence_score,
                        "confidence_label": r.confidence_label,
                    }
                    for r in student_results
                ]

                # Create and publish BatchAssessmentCompletedV1 event
                event_data = BatchAssessmentCompletedV1(
                    batch_id=batch_id,
                    user_id=batch.user_id,
                    assessment_job_id=data.cj_assessment_job_id,
                    rankings_summary=rankings_summary,
                    status=BatchStatus.COMPLETED_SUCCESSFULLY,
                    system_metadata=SystemProcessingMetadata(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                        event="assessment_completed",
                    ),
                )

                await self.event_publisher.publish_batch_assessment_completed(
                    event_data=event_data,
                    correlation_id=envelope.correlation_id,
                )

                logger.info(
                    "Published BatchAssessmentCompletedV1 event",
                    batch_id=batch_id,
                    user_id=batch.user_id,
                    assessment_job_id=data.cj_assessment_job_id,
                    rankings_count=len(rankings_summary),
                    anchor_essays_used=data.assessment_metadata.get("anchor_essays_used", 0),
                )

            logger.info(
                "Assessment results processed successfully",
                batch_id=batch_id,
                student_results=len(student_results),
                assessment_method=data.assessment_method,
                model_used=data.model_used,
            )

        except Exception as e:
            logger.error(
                "Failed to process assessment results",
                batch_id=data.batch_id,
                error=str(e),
                exc_info=True,
            )
            raise
