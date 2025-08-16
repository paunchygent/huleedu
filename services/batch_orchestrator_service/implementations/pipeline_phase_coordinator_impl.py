"""Pipeline phase coordinator implementation for batch processing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_core.events import BatchPipelineCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus, ProcessingPipelineState
from common_core.status_enums import BatchStatus
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.batch_orchestrator_service.implementations.batch_pipeline_state_manager import (
    BatchPipelineStateManager,
)
from services.batch_orchestrator_service.implementations.notification_service import (
    NotificationService,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseInitiatorProtocol,
)

logger = create_service_logger("bos.pipeline.coordinator")


class DefaultPipelinePhaseCoordinator:
    """Default implementation for coordinating pipeline phase transitions."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
        redis_client: AtomicRedisClientProtocol,
        notification_service: NotificationService,
        state_manager: BatchPipelineStateManager,
        event_publisher: BatchEventPublisherProtocol,
    ) -> None:
        self.batch_repo = batch_repo
        self.phase_initiators_map = phase_initiators_map
        self.redis_client = redis_client
        self.notification_service = notification_service
        self.state_manager = state_manager
        self.event_publisher = event_publisher

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        phase_status: BatchStatus,
        correlation_id: UUID,
        processed_essays_for_next_phase: list[Any] | None = None,
    ) -> None:
        """
        Handle completion of a pipeline phase and determine next actions.

        ARCHITECTURE IMPLEMENTATION:
        ===========================
        This implementation uses dynamic phase resolution to initiate subsequent
        phases based on the requested_pipelines list, replacing hardcoded logic:

        1. Update completed phase status in ProcessingPipelineState
        2. Determine next phase from requested_pipelines list dynamically
        3. Perform generic idempotency check using PipelineExecutionStatus
        4. Resolve and delegate to appropriate phase initiator from phase_initiators_map
        5. Handle end-of-pipeline completion scenarios
        6. Handle errors with proper state updates and diagnostic logging
        7. Publish real-time updates to Redis for UI notifications
        """
        logger.info(
            f"Handling phase conclusion: batch={batch_id}, phase={completed_phase.value}, "
            f"status={phase_status.value}",
            extra={"correlation_id": correlation_id},
        )

        # Update the phase status in pipeline state
        # COMPLETED_WITH_FAILURES is treated as success for progression purposes
        # (per common_core/status_enums.py - it's a terminal success state with partial failures)
        success_statuses = {BatchStatus.COMPLETED_SUCCESSFULLY, BatchStatus.COMPLETED_WITH_FAILURES}
        if phase_status in success_statuses:
            updated_status = PipelineExecutionStatus.COMPLETED_SUCCESSFULLY
        else:
            updated_status = PipelineExecutionStatus.FAILED

        # Update status from DISPATCH_INITIATED to completion status
        # Note: Phases go directly from DISPATCH_INITIATED to completion
        # without an intermediate IN_PROGRESS state in the current implementation
        await self.state_manager.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=completed_phase,
            expected_status=PipelineExecutionStatus.DISPATCH_INITIATED,
            new_status=updated_status,
            completion_timestamp=datetime.now(UTC).isoformat(),
            correlation_id=str(correlation_id),
        )

        # Publish real-time update to Redis for UI notifications
        await self.notification_service.publish_phase_completion(
            batch_id=batch_id,
            completed_phase=completed_phase,
            phase_status=phase_status,
            correlation_id=correlation_id,
        )

        # Allow progression for both COMPLETED_SUCCESSFULLY and COMPLETED_WITH_FAILURES
        # COMPLETED_WITH_FAILURES indicates partial success and should proceed with
        # successful essays
        if phase_status not in success_statuses:
            logger.info(
                f"Phase {completed_phase.value} for batch {batch_id} did not complete successfully "
                f"(status: {phase_status.value}), skipping next phase initiation",
            )
            return

        # Log progression decision for COMPLETED_WITH_FAILURES cases
        if phase_status == BatchStatus.COMPLETED_WITH_FAILURES:
            successful_count = (
                len(processed_essays_for_next_phase) if processed_essays_for_next_phase else 0
            )
            message = (
                "Phase %s completed with partial failures for batch %s. "
                "Proceeding to next phase with %s successful essays."
                % (completed_phase.value, batch_id, successful_count)
            )
            logger.info(message, extra={"correlation_id": correlation_id})

        # Determine and initiate next phase with data propagation
        await self._initiate_next_phase(
            batch_id,
            completed_phase,
            correlation_id,
            processed_essays_for_next_phase,
        )

    async def _initiate_next_phase(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        correlation_id: UUID,
        processed_essays_from_previous_phase: list[Any] | None = None,
    ) -> None:
        """
        Determine and initiate the next pipeline phase dynamically based on requested_pipelines.

        DYNAMIC PHASE PROGRESSION LOGIC:
        ================================
        1. Get batch context to access requested_pipelines list
        2. Find current phase index in requested_pipelines
        3. Calculate next phase index and validate pipeline bounds
        4. Resolve next phase initiator from phase_initiators_map
        5. Check idempotency before initiation
        6. Delegate to standardized initiate_phase() method
        7. Handle pipeline completion when no more phases
        """
        try:
            # Get batch context to determine requested pipelines
            batch_context = await self.batch_repo.get_batch_context(batch_id)
            if not batch_context:
                logger.error(f"Missing batch context for batch {batch_id}")
                return

            # Get current pipeline state for idempotency checks
            current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
            if not current_pipeline_state:
                logger.error(f"No pipeline state found for batch {batch_id}")
                return

            # Direct access to Pydantic model - no backwards compatibility needed
            requested_pipelines = current_pipeline_state.requested_pipelines

            if not requested_pipelines:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="handle_phase_concluded",
                    field="requested_pipelines",
                    message=f"No requested pipelines found for batch {batch_id}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                )

            # DEBUG: Log what's actually in requested_pipelines
            logger.info(
                f"DEBUG: Processing phase conclusion - batch={batch_id}, "
                f"completed_phase={completed_phase.value}, "
                f"requested_pipelines={requested_pipelines}",
                extra={
                    "batch_id": batch_id,
                    "requested_pipelines": requested_pipelines,
                    "completed_phase": completed_phase.value,
                    "correlation_id": correlation_id,
                },
            )

            # Dynamic next phase determination
            try:
                current_index = requested_pipelines.index(completed_phase.value)
                logger.info(
                    f"DEBUG: Found completed phase at index {current_index} of {len(requested_pipelines)}",
                    extra={
                        "batch_id": batch_id,
                        "current_index": current_index,
                        "total_phases": len(requested_pipelines),
                        "correlation_id": correlation_id,
                    },
                )
            except ValueError:
                logger.error(
                    f"Completed phase '{completed_phase.value}' not found in requested_pipelines "
                    f"for batch {batch_id}. requested_pipelines={requested_pipelines}",
                )
                return

            # Check if there's a next phase
            if current_index + 1 >= len(requested_pipelines):
                logger.info(
                    f"Pipeline completed for batch {batch_id} - no more phases after "
                    f"'{completed_phase.value}'",
                )
                # Publish pipeline completion event for multi-pipeline support
                await self._publish_pipeline_completion_event(
                    batch_id=batch_id,
                    pipeline_state=current_pipeline_state,
                    correlation_id=correlation_id,
                )
                return

            # Get next phase and validate
            next_phase_str = requested_pipelines[current_index + 1]
            try:
                next_phase_name = PhaseName(next_phase_str)
            except ValueError as e:
                logger.error(
                    f"Invalid next phase name '{next_phase_str}' for batch {batch_id}: {e}",
                )
                return

            logger.info(
                f"Initiating next phase '{next_phase_name.value}' for batch {batch_id} after "
                f"'{completed_phase.value}'",
                extra={"correlation_id": correlation_id},
            )

            # Idempotency check - direct Pydantic access
            pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
            if pipeline_detail and pipeline_detail.status in [
                PipelineExecutionStatus.DISPATCH_INITIATED,
                PipelineExecutionStatus.IN_PROGRESS,
                PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
                PipelineExecutionStatus.FAILED,
            ]:
                logger.info(
                    f"Phase {next_phase_name.value} already initiated for batch {batch_id}, "
                    "skipping",
                    extra={"current_status": pipeline_detail.status.value},
                )
                return

            # Retrieve and use generic initiator
            initiator = self.phase_initiators_map.get(next_phase_name)
            if not initiator:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="handle_phase_concluded",
                    field="phase_initiator",
                    message=f"No initiator found for phase {next_phase_name}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    phase=next_phase_name.value,
                )

            # Prepare essays for processing (use provided or fall back to batch context)
            essays_to_process = processed_essays_from_previous_phase
            if not essays_to_process:
                logger.warning(
                    f"No processed essays provided for next phase {next_phase_name.value}, "
                    "this may indicate a data flow issue",
                )
                # Continue anyway as some phases might not require previous phase results
                essays_to_process = []

            # Delegate to phase initiator with standardized interface
            try:
                await initiator.initiate_phase(
                    batch_id=batch_id,
                    phase_to_initiate=next_phase_name,
                    correlation_id=correlation_id,
                    essays_for_processing=essays_to_process,
                    batch_context=batch_context,
                )
            except HuleEduError as e:
                logger.error(
                    f"Failed to initiate phase {next_phase_name} for batch {batch_id}: {e}",
                )

                # Record phase failure with structured error details
                await self.state_manager.record_phase_failure(
                    batch_id=batch_id,
                    phase_name=next_phase_name,
                    error=e,
                    correlation_id=str(correlation_id),
                )

                # Mark phase as FAILED in pipeline state - direct Pydantic access
                pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
                if pipeline_detail:
                    pipeline_detail.status = PipelineExecutionStatus.FAILED
                    pipeline_detail.error_info = e.error_detail.model_dump()
                    pipeline_detail.completed_at = datetime.now(UTC)
                    await self.batch_repo.save_processing_pipeline_state(
                        batch_id,
                        current_pipeline_state,
                    )

                raise

            # State update - mark phase as DISPATCH_INITIATED
            pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
            if pipeline_detail:
                pipeline_detail.status = PipelineExecutionStatus.DISPATCH_INITIATED
                pipeline_detail.started_at = datetime.now(UTC)
                await self.batch_repo.save_processing_pipeline_state(
                    batch_id,
                    current_pipeline_state,
                )

            logger.info(
                f"Successfully initiated {next_phase_name.value} pipeline for batch {batch_id}",
            )

        except Exception as e:
            logger.error(
                f"Error determining/initiating next phase for batch {batch_id}: {e}",
                exc_info=True,
            )
            raise

    async def initiate_resolved_pipeline(
        self,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        correlation_id: UUID,
        batch_context: Any,
    ) -> None:
        """Initiate execution of the first uncompleted phase in a BCS-resolved pipeline."""
        logger.info(
            f"Initiating resolved pipeline for batch {batch_id}",
            extra={
                "resolved_pipeline": [phase.value for phase in resolved_pipeline],
                "correlation_id": correlation_id,
            },
        )

        # Validate resolved pipeline
        if not resolved_pipeline:
            raise_validation_error(
                service="batch_orchestrator_service",
                operation="initiate_resolved_pipeline",
                field="resolved_pipeline",
                message=f"Empty resolved pipeline for batch {batch_id}",
                correlation_id=correlation_id,
                batch_id=batch_id,
            )

        # Get current pipeline state for checking phase statuses
        current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        
        # Find the first uncompleted phase in the resolved pipeline
        phase_to_initiate = None
        for phase_name in resolved_pipeline:
            if current_pipeline_state:
                pipeline_detail = current_pipeline_state.get_pipeline(phase_name.value)
                if pipeline_detail and pipeline_detail.status in [
                    PipelineExecutionStatus.DISPATCH_INITIATED,
                    PipelineExecutionStatus.IN_PROGRESS,
                    PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
                ]:
                    logger.info(
                        f"Phase {phase_name.value} already completed/in-progress for "
                        f"batch {batch_id}, checking next phase",
                        extra={"current_status": pipeline_detail.status.value},
                    )
                    continue  # Check next phase
            
            # Found first uncompleted phase
            phase_to_initiate = phase_name
            logger.info(
                f"Found first uncompleted phase {phase_name.value} for batch {batch_id}",
                extra={"correlation_id": correlation_id},
            )
            break
        
        # If all phases are complete, nothing to do
        if phase_to_initiate is None:
            logger.info(
                f"All phases in resolved pipeline already completed for batch {batch_id}",
                extra={"resolved_pipeline": [p.value for p in resolved_pipeline]},
            )
            return

        # Get phase initiator for the uncompleted phase
        initiator = self.phase_initiators_map.get(phase_to_initiate)
        if not initiator:
            raise_validation_error(
                service="batch_orchestrator_service",
                operation="initiate_resolved_pipeline",
                field="phase_initiator",
                message=f"No initiator found for phase {phase_to_initiate}",
                correlation_id=correlation_id,
                batch_id=batch_id,
                phase=phase_to_initiate.value,
            )

        # Get essays that were stored from the original BatchEssaysReady event
        essays_for_processing = await self.batch_repo.get_batch_essays(batch_id)

        if not essays_for_processing:
            raise_validation_error(
                service="batch_orchestrator_service",
                operation="initiate_resolved_pipeline",
                field="essays_for_processing",
                message=(
                    f"No essays found for batch {batch_id}. Batch may not be ready for processing."
                ),
                correlation_id=correlation_id,
                batch_id=batch_id,
            )

        logger.info(f"Retrieved {len(essays_for_processing)} essays for pipeline initiation")

        # Initiate the uncompleted phase
        try:
            await initiator.initiate_phase(
                batch_id=batch_id,
                phase_to_initiate=phase_to_initiate,
                correlation_id=correlation_id,
                essays_for_processing=essays_for_processing,
                batch_context=batch_context,
            )
        except HuleEduError as e:
            logger.error(
                f"Failed to initiate phase {phase_to_initiate} for batch {batch_id}: {e}",
            )
            # Record phase failure with structured error details
            await self.state_manager.record_phase_failure(
                batch_id=batch_id,
                phase_name=phase_to_initiate,
                error=e,
                correlation_id=str(correlation_id),
            )
            raise

        # Update pipeline state - mark phase as DISPATCH_INITIATED
        await self.state_manager.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_to_initiate,
            expected_status=PipelineExecutionStatus.PENDING_DEPENDENCIES,
            new_status=PipelineExecutionStatus.DISPATCH_INITIATED,
            completion_timestamp=datetime.now(UTC).isoformat(),
            correlation_id=str(correlation_id),
        )

        logger.info(
            f"Successfully initiated phase {phase_to_initiate.value} for batch {batch_id}",
            extra={"correlation_id": correlation_id},
        )

    async def update_phase_status(
        self,
        batch_id: str,
        phase: PhaseName,
        status: PipelineExecutionStatus,
        correlation_id: UUID,
        completion_timestamp: str | None = None,
    ) -> None:
        """Update the status of a specific phase in the pipeline.

        Args:
            batch_id: The batch identifier
            phase: The phase to update
            status: The new status for the phase
            completion_timestamp: Optional completion timestamp
        """
        # Get current state to determine expected status
        current_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if not current_state:
            logger.error(f"No pipeline state found for batch {batch_id}")
            return

        # Determine current status - direct Pydantic access
        pipeline_detail = current_state.get_pipeline(phase.value)
        current_status = (
            pipeline_detail.status
            if pipeline_detail
            else PipelineExecutionStatus.PENDING_DEPENDENCIES
        )

        # Update the phase status in the pipeline state
        await self.state_manager.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase,
            expected_status=current_status,
            new_status=status,
            completion_timestamp=completion_timestamp,
            correlation_id=str(correlation_id),
        )

        logger.info(
            f"Updated phase {phase.value} status to {status.value} for batch {batch_id}",
            extra={"completion_timestamp": completion_timestamp, "correlation_id": correlation_id},
        )

    async def _publish_pipeline_completion_event(
        self,
        batch_id: str,
        pipeline_state: ProcessingPipelineState,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchPipelineCompletedV1 event when all pipeline phases are complete.
        
        This enables:
        1. Multi-pipeline support by clearing active pipeline state
        2. UI notifications of pipeline completion
        3. BCS to track completed phases for dependency resolution
        """
        # Calculate pipeline metrics
        completed_phases = []
        has_any_failures = False
        successful_essays = 0
        failed_essays = 0
        pipeline_start_time = None
        
        # Iterate through all requested pipelines to gather completion metrics
        for phase_name in pipeline_state.requested_pipelines:
            phase_detail = pipeline_state.get_pipeline(phase_name)
            if phase_detail:
                if phase_detail.status == PipelineExecutionStatus.COMPLETED_SUCCESSFULLY:
                    completed_phases.append(phase_name)
                elif phase_detail.status == PipelineExecutionStatus.FAILED:
                    has_any_failures = True
                    
                # Track earliest start time for duration calculation
                if phase_detail.started_at and (
                    not pipeline_start_time or phase_detail.started_at < pipeline_start_time
                ):
                    pipeline_start_time = phase_detail.started_at
        
        # Calculate processing duration
        processing_duration_seconds = 0.0
        if pipeline_start_time:
            processing_duration_seconds = (
                datetime.now(UTC) - pipeline_start_time
            ).total_seconds()
        
        # Determine final status based on whether there were any failures
        final_status = (
            "COMPLETED_WITH_FAILURES" if has_any_failures else "COMPLETED_SUCCESSFULLY"
        )
        
        # Get essay counts from batch context if available
        batch_context = await self.batch_repo.get_batch_context(batch_id)
        if batch_context:
            total_essays = batch_context.expected_essay_count
            
            # TODO: Track actual essay-level success/failure counts from ELSBatchPhaseOutcomeV1
            # For now, use conservative approach: any failure means at least one essay failed
            # In production, we should aggregate actual counts from phase outcomes
            if has_any_failures:
                # Without detailed tracking, we can't know exact counts
                # Conservative: report that at least 1 essay failed
                successful_essays = total_essays - 1  
                failed_essays = 1
            else:
                # All phases completed successfully, all essays succeeded
                successful_essays = total_essays
                failed_essays = 0
        
        # Create the pipeline completion event
        completion_event = BatchPipelineCompletedV1(
            batch_id=batch_id,
            completed_phases=completed_phases,
            final_status=final_status,
            processing_duration_seconds=processing_duration_seconds,
            successful_essay_count=successful_essays,
            failed_essay_count=failed_essays,
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
                event="batch.pipeline.completed",
            ),
        )
        
        # Wrap in event envelope
        event_envelope: EventEnvelope[BatchPipelineCompletedV1] = EventEnvelope(
            event_type="batch.pipeline.completed",
            source_service="batch_orchestrator_service",
            data=completion_event,
            correlation_id=correlation_id,
            metadata={
                "batch_id": batch_id,
                "completed_phases": completed_phases,
                "final_status": final_status,
            },
        )
        
        # Publish event using outbox pattern for reliability
        await self.event_publisher.publish_batch_event(
            event_envelope=event_envelope,
            key=batch_id,
        )
        
        logger.info(
            f"Published BatchPipelineCompletedV1 for batch {batch_id}",
            extra={
                "completed_phases": completed_phases,
                "final_status": final_status,
                "duration_seconds": processing_duration_seconds,
                "correlation_id": correlation_id,
            },
        )
        
        # Mark batch as ready for new pipeline requests
        # The pipeline completion event signals the end of this pipeline execution
        # Next pipeline request will check completed phases and skip them
