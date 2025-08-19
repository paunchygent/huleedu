"""Event processor implementation for Result Aggregator Service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from common_core.error_enums import ErrorCode
from common_core.events.assessment_result_events import AssessmentResultV1
from common_core.events.batch_coordination_events import BatchPipelineCompletedV1
from common_core.events.result_events import (
    BatchAssessmentCompletedV1,
    BatchResultsReadyV1,
    PhaseResultSummary,
)
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.error_handling import (
    create_error_detail_with_context,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.protocols import (
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
    EventPublisherProtocol,
    StateStoreProtocol,
)

if TYPE_CHECKING:
    from common_core.events import (
        BatchEssaysRegistered,
        ELSBatchPhaseOutcomeV1,
        EventEnvelope,
        SpellcheckResultDataV1,
    )
    from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1

logger = create_service_logger("result_aggregator.event_processor")


class EventProcessorImpl(EventProcessorProtocol):
    """Processes incoming events and updates aggregated results."""

    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
        cache_manager: CacheManagerProtocol,
        event_publisher: EventPublisherProtocol,
    ):
        """Initialize the event processor."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher

    async def process_batch_registered(
        self, envelope: "EventEnvelope[BatchEssaysRegistered]", data: "BatchEssaysRegistered"
    ) -> None:
        """Create the initial batch result record upon registration."""
        try:
            logger.info(
                "Processing batch registration",
                batch_id=data.entity_id,  # entity_id is the batch identifier
                user_id=data.user_id,
                essay_count=data.expected_essay_count,
                essay_ids=data.essay_ids if hasattr(data, "essay_ids") else None,
            )

            # Create the initial batch record
            await self.batch_repository.create_batch(
                batch_id=data.entity_id,  # entity_id is the batch identifier
                user_id=data.user_id,
                essay_count=data.expected_essay_count,
                metadata={"requested_pipelines": data.requested_pipelines}
                if hasattr(data, "requested_pipelines")
                else None,
            )

            # Associate any orphaned essays with this batch
            if hasattr(data, "essay_ids") and data.essay_ids:
                logger.info(
                    "Attempting to associate essays with batch",
                    batch_id=data.entity_id,
                    essay_ids=data.essay_ids,
                    essay_count=len(data.essay_ids),
                )

                associated_count = 0
                failed_count = 0

                for essay_id in data.essay_ids:
                    try:
                        await self.batch_repository.associate_essay_with_batch(
                            essay_id=essay_id,
                            batch_id=data.entity_id,
                        )
                        associated_count += 1
                        logger.debug(
                            "Successfully associated essay",
                            essay_id=essay_id,
                            batch_id=data.entity_id,
                        )
                    except Exception as e:
                        failed_count += 1
                        logger.warning(
                            "Failed to associate essay with batch",
                            essay_id=essay_id,
                            batch_id=data.entity_id,
                            error=str(e),
                        )

                logger.info(
                    "Essay association complete",
                    batch_id=data.entity_id,
                    total_essays=len(data.essay_ids),
                    associated=associated_count,
                    failed=failed_count,
                )
            else:
                logger.warning(
                    "No essay_ids provided in batch registration event",
                    batch_id=data.entity_id,
                )

            await self.cache_manager.invalidate_user_batches(data.user_id)

            logger.info(
                "Created initial batch record and invalidated user cache",
                batch_id=data.entity_id,  # entity_id is the batch identifier
                user_id=data.user_id,
            )

        except Exception as e:
            logger.error(
                "Failed to process batch registration",
                batch_id=data.entity_id,  # entity_id is the batch identifier
                error=str(e),
                exc_info=True,
            )
            raise

    async def process_essay_slot_assigned(
        self, envelope: "EventEnvelope[EssaySlotAssignedV1]", data: "EssaySlotAssignedV1"
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

            # Update the essay record with file_upload_id mapping
            await self.batch_repository.update_essay_file_mapping(
                essay_id=data.essay_id,
                file_upload_id=data.file_upload_id,
                text_storage_id=data.text_storage_id,
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

            # Set processing_started_at if this is the first phase event
            batch = await self.batch_repository.get_batch(data.batch_id)
            if batch and not batch.processing_started_at:
                # This is the first phase event - mark processing as started
                await self.batch_repository.set_batch_processing_started(data.batch_id)
                logger.info(
                    "Set processing_started_at for batch",
                    batch_id=data.batch_id,
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
                # Create structured error detail for phase failure
                error_detail = create_error_detail_with_context(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=f"Phase {data.phase_name.value} failed critically",
                    service="result_aggregator_service",
                    operation="process_batch_phase_outcome",
                    correlation_id=envelope.correlation_id,
                    details={
                        "batch_id": data.batch_id,
                        "phase": data.phase_name.value,
                        "status": data.phase_status.value,
                    },
                )
                await self.batch_repository.update_batch_failed(
                    batch_id=data.batch_id,
                    error_detail=error_detail,
                    correlation_id=envelope.correlation_id,
                )

            # Invalidate cache
            await self.state_store.invalidate_batch(data.batch_id)

            # Check if all phases are complete and publish event if so
            if await self._check_batch_completion(data.batch_id):
                # Get batch to get user_id
                batch = await self.batch_repository.get_batch(data.batch_id)
                if batch:
                    # Calculate phase results and overall status
                    phase_results = await self._calculate_phase_results(data.batch_id)
                    overall_status = self._determine_overall_status(phase_results)
                    duration = await self._calculate_duration(data.batch_id)

                    # Get total essays from batch
                    essays = await self.batch_repository.get_batch_essays(data.batch_id)
                    total_essays = len(essays)
                    completed_essays = sum(
                        1
                        for e in essays
                        if e.spellcheck_status == ProcessingStage.COMPLETED
                        or e.cj_assessment_status == ProcessingStage.COMPLETED
                    )

                    # Create and publish BatchResultsReadyV1 event
                    event_data = BatchResultsReadyV1(
                        batch_id=data.batch_id,
                        user_id=batch.user_id,
                        total_essays=total_essays,
                        completed_essays=completed_essays,
                        phase_results=phase_results,
                        overall_status=overall_status,
                        processing_duration_seconds=duration,
                        status=overall_status,  # Required by ProcessingUpdate base class
                        system_metadata=SystemProcessingMetadata(
                            entity_id=data.batch_id,
                            entity_type="batch",
                            parent_id=None,
                            event="results_ready",
                        ),
                    )

                    await self.event_publisher.publish_batch_results_ready(
                        event_data=event_data,
                        correlation_id=envelope.correlation_id,
                    )

                    logger.info(
                        "Published BatchResultsReadyV1 event for completed batch",
                        batch_id=data.batch_id,
                        user_id=batch.user_id,
                        overall_status=overall_status.value,
                    )

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
                from common_core.domain_enums import ContentType

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

    async def process_assessment_result(
        self, envelope: "EventEnvelope[AssessmentResultV1]", data: AssessmentResultV1
    ) -> None:
        """Process assessment result event with rich business data from CJ Assessment Service."""
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
            student_results = [r for r in data.essay_results if not r.get("is_anchor", False)]

            for essay_result in student_results:
                essay_id = essay_result["essay_id"]
                rank = essay_result.get("rank")
                bt_score = essay_result.get("bt_score")

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
                        "essay_id": r["essay_id"],
                        "rank": r.get("rank"),
                        "score": r.get("bt_score"),
                        "letter_grade": r.get("letter_grade"),
                        "confidence_score": r.get("confidence_score"),
                        "confidence_label": r.get("confidence_label"),
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

    async def process_pipeline_completed(self, event: BatchPipelineCompletedV1) -> None:
        """Process pipeline completion for final result aggregation."""
        try:
            logger.info(
                "Processing pipeline completion",
                batch_id=event.batch_id,
                final_status=event.final_status,
                successful_essays=event.successful_essay_count,
                failed_essays=event.failed_essay_count,
                correlation_id=str(event.correlation_id),
            )

            # Mark batch as completed in aggregator
            await self.batch_repository.mark_batch_completed(
                batch_id=event.batch_id,
                final_status=event.final_status,
                completion_stats={
                    "successful_essays": event.successful_essay_count,
                    "failed_essays": event.failed_essay_count,
                    "duration_seconds": event.processing_duration_seconds,
                    "completed_phases": event.completed_phases,
                },
            )

            # Invalidate relevant cache entries
            await self.state_store.invalidate_batch(event.batch_id)

            # Get batch to find user_id for cache invalidation
            batch = await self.batch_repository.get_batch(event.batch_id)
            if batch:
                await self.cache_manager.invalidate_user_batches(batch.user_id)

            logger.info(
                "Pipeline completion processed successfully",
                batch_id=event.batch_id,
                final_status=event.final_status,
            )

        except Exception as e:
            logger.error(
                "Failed to process pipeline completion",
                batch_id=event.batch_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _check_batch_completion(self, batch_id: str) -> bool:
        """Check if all phases are complete for a batch."""
        batch = await self.batch_repository.get_batch(batch_id)
        if not batch:
            return False

        # Check if all essays have been processed for both phases
        essays = await self.batch_repository.get_batch_essays(batch_id)
        if not essays:
            return False

        # Check spellcheck phase
        spellcheck_complete = all(
            essay.spellcheck_status in [ProcessingStage.COMPLETED, ProcessingStage.FAILED]
            for essay in essays
        )

        # Check CJ assessment phase
        cj_complete = all(
            essay.cj_assessment_status in [ProcessingStage.COMPLETED, ProcessingStage.FAILED]
            for essay in essays
        )

        # Both phases must be complete
        return spellcheck_complete and cj_complete

    async def _calculate_phase_results(self, batch_id: str) -> dict[str, PhaseResultSummary]:
        """Calculate phase result summaries for a batch."""
        essays = await self.batch_repository.get_batch_essays(batch_id)

        # Calculate spellcheck phase results
        spellcheck_completed = sum(
            1 for e in essays if e.spellcheck_status == ProcessingStage.COMPLETED
        )
        spellcheck_failed = sum(1 for e in essays if e.spellcheck_status == ProcessingStage.FAILED)

        # Calculate CJ assessment phase results
        cj_completed = sum(1 for e in essays if e.cj_assessment_status == ProcessingStage.COMPLETED)
        cj_failed = sum(1 for e in essays if e.cj_assessment_status == ProcessingStage.FAILED)

        # Calculate processing times if available
        spellcheck_times = [e.spellcheck_completed_at for e in essays if e.spellcheck_completed_at]
        spellcheck_duration = None
        if spellcheck_times:
            batch = await self.batch_repository.get_batch(batch_id)
            if batch and batch.processing_started_at:
                spellcheck_duration = (
                    max(spellcheck_times) - batch.processing_started_at
                ).total_seconds()

        cj_times = [e.cj_assessment_completed_at for e in essays if e.cj_assessment_completed_at]
        cj_duration = None
        if cj_times:
            batch = await self.batch_repository.get_batch(batch_id)
            if batch and batch.processing_started_at:
                cj_duration = (max(cj_times) - batch.processing_started_at).total_seconds()

        return {
            "spellcheck": PhaseResultSummary(
                phase_name="spellcheck",
                status="completed" if spellcheck_failed == 0 else "completed_with_failures",
                completed_count=spellcheck_completed,
                failed_count=spellcheck_failed,
                processing_time_seconds=spellcheck_duration,
            ),
            "cj_assessment": PhaseResultSummary(
                phase_name="cj_assessment",
                status="completed" if cj_failed == 0 else "completed_with_failures",
                completed_count=cj_completed,
                failed_count=cj_failed,
                processing_time_seconds=cj_duration,
            ),
        }

    def _determine_overall_status(
        self, phase_results: dict[str, PhaseResultSummary]
    ) -> BatchStatus:
        """Determine overall batch status from phase results."""
        has_failures = any(phase.failed_count > 0 for phase in phase_results.values())

        if has_failures:
            return BatchStatus.COMPLETED_WITH_FAILURES
        return BatchStatus.COMPLETED_SUCCESSFULLY

    async def _calculate_duration(self, batch_id: str) -> float:
        """Calculate total processing duration for a batch."""
        batch = await self.batch_repository.get_batch(batch_id)
        if not batch or not batch.processing_started_at:
            return 0.0

        # Use completed_at if available, otherwise use current time
        # Both timestamps should be timezone-naive for consistency with database storage
        end_time = batch.processing_completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
        duration = (end_time - batch.processing_started_at).total_seconds()
        return max(0.0, duration)  # Ensure non-negative
