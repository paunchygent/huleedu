"""Pipeline phase coordinator implementation for batch processing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from protocols import (
    BatchRepositoryProtocol,
    DataValidationError,
    InitiationError,
    PipelinePhaseInitiatorProtocol,
)

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus
from common_core.status_enums import BatchStatus

logger = create_service_logger("bos.pipeline.coordinator")


class DefaultPipelinePhaseCoordinator:
    """Default implementation for coordinating pipeline phase transitions."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
        redis_client: AtomicRedisClientProtocol,
    ) -> None:
        self.batch_repo = batch_repo
        self.phase_initiators_map = phase_initiators_map
        self.redis_client = redis_client

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        phase_status: BatchStatus,
        correlation_id: str,
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
        # (per common_core/enums.py - it's a terminal success state with partial failures)
        success_statuses = {BatchStatus.COMPLETED_SUCCESSFULLY, BatchStatus.COMPLETED_WITH_FAILURES}
        if phase_status in success_statuses:
            updated_status = PipelineExecutionStatus.COMPLETED_SUCCESSFULLY
        else:
            updated_status = PipelineExecutionStatus.FAILED

        await self.update_phase_status(
            batch_id,
            completed_phase,
            updated_status,
            datetime.now(UTC).isoformat(),
        )

        # Publish real-time update to Redis for UI notifications
        await self._publish_phase_completion_to_redis(
            batch_id, completed_phase, phase_status, correlation_id
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

    async def update_phase_status(
        self,
        batch_id: str,
        phase: PhaseName,
        status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
    ) -> None:
        """Update the status of a specific pipeline phase."""
        current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if not current_pipeline_state:
            logger.error(f"No pipeline state found for batch {batch_id}")
            return

        # Handle both dict and ProcessingPipelineState object cases
        if hasattr(current_pipeline_state, "model_dump"):  # Pydantic object
            updated_pipeline_state = current_pipeline_state.model_dump()
        else:  # Dictionary
            updated_pipeline_state = current_pipeline_state.copy()

        # Update the specific phase status
        phase_updates = {f"{phase.value}_status": status.value}
        if completion_timestamp:
            phase_updates[f"{phase.value}_completed_at"] = completion_timestamp

        updated_pipeline_state.update(phase_updates)
        await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

        logger.info(f"Updated {phase.value} status to {status.value} for batch {batch_id}")

    async def _initiate_next_phase(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        correlation_id: str,
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

            # Handle both dict and ProcessingPipelineState object cases for backwards compatibility
            if hasattr(current_pipeline_state, "requested_pipelines"):  # Pydantic object
                requested_pipelines = current_pipeline_state.requested_pipelines
            else:  # Dictionary
                requested_pipelines = current_pipeline_state.get("requested_pipelines")

            if not requested_pipelines:
                raise DataValidationError(f"No requested pipelines found for batch {batch_id}")

            # Dynamic next phase determination
            try:
                current_index = requested_pipelines.index(completed_phase.value)
            except ValueError:
                logger.error(
                    f"Completed phase '{completed_phase.value}' not found in requested_pipelines "
                    f"for batch {batch_id}",
                )
                return

            # Check if there's a next phase
            if current_index + 1 >= len(requested_pipelines):
                logger.info(
                    f"Pipeline completed for batch {batch_id} - no more phases after "
                    f"'{completed_phase.value}'",
                )
                # TODO: Mark batch as COMPLETED when batch completion events are available
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

            # Generic idempotency check
            if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
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
            else:  # Dictionary - backwards compatibility
                phase_status_key = f"{next_phase_name.value}_status"
                phase_status = current_pipeline_state.get(phase_status_key)
                if phase_status in [
                    PipelineExecutionStatus.DISPATCH_INITIATED.value,
                    PipelineExecutionStatus.IN_PROGRESS.value,
                    PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value,
                    PipelineExecutionStatus.FAILED.value,
                ]:
                    logger.info(
                        f"Phase {next_phase_name.value} already initiated for batch {batch_id}, "
                        "skipping",
                        extra={"current_status": phase_status},
                    )
                    return

            # Retrieve and use generic initiator
            initiator = self.phase_initiators_map.get(next_phase_name)
            if not initiator:
                raise DataValidationError(f"No initiator found for phase {next_phase_name}")

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
                # Convert correlation_id from string to UUID if needed
                correlation_uuid = UUID(correlation_id) if correlation_id else None
                await initiator.initiate_phase(
                    batch_id=batch_id,
                    phase_to_initiate=next_phase_name,
                    correlation_id=correlation_uuid,
                    essays_for_processing=essays_to_process,
                    batch_context=batch_context,
                )
            except InitiationError as e:
                logger.error(
                    f"Failed to initiate phase {next_phase_name} for batch {batch_id}: {e}",
                )

                # Mark phase as FAILED and save state
                if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                    pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
                    if pipeline_detail:
                        pipeline_detail.status = PipelineExecutionStatus.FAILED
                        pipeline_detail.error_info = {
                            "error": str(e),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                        await self.batch_repo.save_processing_pipeline_state(
                            batch_id,
                            current_pipeline_state,
                        )
                else:  # Dictionary - backwards compatibility
                    updated_pipeline_state = current_pipeline_state.copy()
                    updated_pipeline_state.update(
                        {
                            f"{next_phase_name.value}_status": PipelineExecutionStatus.FAILED.value,
                            f"{next_phase_name.value}_error": str(e),
                            f"{next_phase_name.value}_failed_at": (datetime.now(UTC).isoformat()),
                        },
                    )
                    await self.batch_repo.save_processing_pipeline_state(
                        batch_id,
                        updated_pipeline_state,
                    )

                # TODO: Publish diagnostic event when error event models are available
                raise

            # Generic state update - mark phase as DISPATCH_INITIATED
            if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
                if pipeline_detail:
                    pipeline_detail.status = PipelineExecutionStatus.DISPATCH_INITIATED
                    pipeline_detail.started_at = datetime.now(UTC)
                    await self.batch_repo.save_processing_pipeline_state(
                        batch_id,
                        current_pipeline_state,
                    )
            else:  # Dictionary - backwards compatibility
                updated_pipeline_state = current_pipeline_state.copy()
                updated_pipeline_state.update(
                    {
                        f"{next_phase_name.value}_status": (
                            PipelineExecutionStatus.DISPATCH_INITIATED.value
                        ),
                        f"{next_phase_name.value}_initiated_at": (datetime.now(UTC).isoformat()),
                    },
                )
                await self.batch_repo.save_processing_pipeline_state(
                    batch_id,
                    updated_pipeline_state,
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
        resolved_pipeline: list[str],
        correlation_id: str,
        batch_context: Any,
    ) -> None:
        """Initiate execution of the first phase in a BCS-resolved pipeline."""
        logger.info(
            f"Initiating resolved pipeline for batch {batch_id}",
            extra={
                "resolved_pipeline": resolved_pipeline,
                "correlation_id": correlation_id,
            },
        )

        # Validate resolved pipeline
        if not resolved_pipeline:
            raise DataValidationError(f"Empty resolved pipeline for batch {batch_id}")

        # Get first phase from resolved pipeline
        first_phase_str = resolved_pipeline[0]
        try:
            first_phase_name = PhaseName(first_phase_str)
        except ValueError as e:
            raise DataValidationError(
                f"Invalid first phase '{first_phase_str}' in resolved pipeline "
                f"for batch {batch_id}: {e}",
            )

        # Check idempotency - don't re-initiate if already started
        current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if current_pipeline_state:
            if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                pipeline_detail = current_pipeline_state.get_pipeline(first_phase_name.value)
                if pipeline_detail and pipeline_detail.status in [
                    PipelineExecutionStatus.DISPATCH_INITIATED,
                    PipelineExecutionStatus.IN_PROGRESS,
                    PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
                ]:
                    logger.info(
                        f"First phase {first_phase_name.value} already initiated for "
                        f"batch {batch_id}, skipping",
                        extra={"current_status": pipeline_detail.status.value},
                    )
                    return
            else:  # Dictionary - backwards compatibility
                phase_status_key = f"{first_phase_name.value}_status"
                phase_status = current_pipeline_state.get(phase_status_key)
                if phase_status in [
                    PipelineExecutionStatus.DISPATCH_INITIATED.value,
                    PipelineExecutionStatus.IN_PROGRESS.value,
                    PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value,
                ]:
                    logger.info(
                        f"First phase {first_phase_name.value} already initiated, skipping",
                        extra={"batch_id": batch_id, "current_status": phase_status},
                    )
                    return

        # Get phase initiator
        initiator = self.phase_initiators_map.get(first_phase_name)
        if not initiator:
            raise DataValidationError(f"No initiator found for first phase {first_phase_name}")

        # Get essays that were stored from the original BatchEssaysReady event
        essays_for_processing = await self.batch_repo.get_batch_essays(batch_id)

        if not essays_for_processing:
            raise DataValidationError(
                f"No essays found for batch {batch_id}. Batch may not be ready for processing.",
            )

        logger.info(f"Retrieved {len(essays_for_processing)} essays for pipeline initiation")

        # Initiate first phase
        try:
            correlation_uuid = UUID(correlation_id) if correlation_id else None
            await initiator.initiate_phase(
                batch_id=batch_id,
                phase_to_initiate=first_phase_name,
                correlation_id=correlation_uuid,
                essays_for_processing=essays_for_processing,
                batch_context=batch_context,
            )
        except InitiationError as e:
            logger.error(
                f"Failed to initiate first phase {first_phase_name} for batch {batch_id}: {e}",
            )
            raise

        # Update pipeline state - mark first phase as DISPATCH_INITIATED
        await self.update_phase_status(
            batch_id=batch_id,
            phase=first_phase_name,
            status=PipelineExecutionStatus.DISPATCH_INITIATED,
            completion_timestamp=datetime.now(UTC).isoformat(),
        )

        logger.info(
            f"Successfully initiated first phase {first_phase_name.value} for batch {batch_id}",
            extra={"correlation_id": correlation_id},
        )

    def _get_phase_status(self, pipeline_state: dict, phase: str) -> str | None:
        """Extract phase status from pipeline state, handling both dict and object formats."""
        if hasattr(pipeline_state, phase):  # Pydantic object
            phase_obj = getattr(pipeline_state, phase)
            return getattr(phase_obj, "status", None) if phase_obj else None
        else:  # Dictionary
            return pipeline_state.get(f"{phase}_status")

    async def _publish_phase_completion_to_redis(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        phase_status: BatchStatus,
        correlation_id: str,
    ) -> None:
        """Publish phase completion notification to Redis for real-time UI updates."""
        try:
            # Get batch context to extract user_id
            batch_context = await self.batch_repo.get_batch_context(batch_id)
            user_id = batch_context.user_id if batch_context else None

            if user_id:
                await self.redis_client.publish_user_notification(
                    user_id=user_id,
                    event_type="batch_phase_concluded",
                    data={
                        "batch_id": batch_id,
                        "phase": completed_phase.value,
                        "status": phase_status.value,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "correlation_id": correlation_id,
                    },
                )

                logger.info(
                    f"Published phase completion notification to Redis for user {user_id}",
                    extra={
                        "batch_id": batch_id,
                        "phase": completed_phase.value,
                        "user_id": user_id,
                        "correlation_id": correlation_id,
                    },
                )
            else:
                logger.warning(
                    "No user_id found in batch context, skipping Redis notification",
                    extra={"batch_id": batch_id, "correlation_id": correlation_id},
                )

        except Exception as e:
            logger.error(
                f"Error publishing phase completion to Redis: {e}",
                extra={
                    "batch_id": batch_id,
                    "phase": completed_phase.value,
                    "correlation_id": correlation_id,
                },
                exc_info=True,
            )
            # Don't fail the entire phase handling if Redis fails
