"""Handles batch lifecycle events for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any

from common_core.error_enums import ErrorCode
from common_core.events.batch_coordination_events import BatchPipelineCompletedV1
from common_core.events.result_events import (
    BatchResultsReadyV1,
)
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.error_handling import create_error_detail_with_context
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events import (
        BatchEssaysRegistered,
        ELSBatchPhaseOutcomeV1,
        EventEnvelope,
    )

    from services.result_aggregator_service.implementations.batch_completion_calculator import (
        BatchCompletionCalculator,
    )
    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        EventPublisherProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.batch_lifecycle")


class BatchLifecycleHandler:
    """Handles batch registration, phase outcomes, and pipeline completion."""

    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
        event_publisher: "EventPublisherProtocol",
        completion_calculator: Optional["BatchCompletionCalculator"] = None,
    ):
        """Initialize with dependencies."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher

        # Create calculator if not provided (for backwards compatibility)
        if completion_calculator is None:
            from services.result_aggregator_service.implementations import (
                batch_completion_calculator,
            )

            BatchCompletionCalculator = batch_completion_calculator.BatchCompletionCalculator

            completion_calculator = BatchCompletionCalculator(batch_repository)
        self.completion_calculator = completion_calculator

    async def process_batch_registered(
        self,
        envelope: "EventEnvelope[BatchEssaysRegistered]",
        data: "BatchEssaysRegistered",
    ) -> None:
        """Create the initial batch result record upon registration."""
        try:
            logger.info(
                "Processing batch registration",
                batch_id=data.entity_id,
                user_id=data.user_id,
                essay_count=data.expected_essay_count,
                essay_ids=data.essay_ids if hasattr(data, "essay_ids") else None,
            )

            # Create the initial batch record
            metadata_payload = self._build_batch_metadata(data)

            await self.batch_repository.create_batch(
                batch_id=data.entity_id,
                user_id=data.user_id,
                essay_count=data.expected_essay_count,
                metadata=metadata_payload,
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
                batch_id=data.entity_id,
                user_id=data.user_id,
            )

        except Exception as e:
            logger.error(
                "Failed to process batch registration",
                batch_id=data.entity_id,
                error=str(e),
                exc_info=True,
            )
            raise

    def _build_batch_metadata(self, data: "BatchEssaysRegistered") -> dict[str, Any] | None:
        """Capture relevant metadata (requested pipelines, prompt references) for Result Aggregator."""
        metadata: dict[str, Any] = {}

        if hasattr(data, "requested_pipelines") and getattr(data, "requested_pipelines"):
            metadata["requested_pipelines"] = getattr(data, "requested_pipelines")

        prompt_ref = getattr(data, "student_prompt_ref", None)
        if prompt_ref is not None:
            metadata["student_prompt_ref"] = prompt_ref.model_dump(mode="json")

        return metadata or None

    async def process_batch_phase_outcome(
        self,
        envelope: "EventEnvelope[ELSBatchPhaseOutcomeV1]",
        data: "ELSBatchPhaseOutcomeV1",
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
            if await self.completion_calculator.check_batch_completion(data.batch_id):
                # Get batch to get user_id
                batch = await self.batch_repository.get_batch(data.batch_id)
                if batch:
                    # Calculate phase results and overall status
                    phase_results = await self.completion_calculator.calculate_phase_results(
                        data.batch_id
                    )
                    overall_status = self.completion_calculator.determine_overall_status(
                        phase_results
                    )
                    duration = await self.completion_calculator.calculate_duration(data.batch_id)

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

    async def process_pipeline_completed(
        self,
        event: BatchPipelineCompletedV1,
    ) -> None:
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
