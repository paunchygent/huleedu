"""Pipeline phase coordinator implementation for batch processing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchRepositoryProtocol,
    DataValidationError,
    InitiationError,
    PipelinePhaseInitiatorProtocol,
)

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus

logger = create_service_logger("bos.pipeline.coordinator")


class DefaultPipelinePhaseCoordinator:
    """Default implementation for coordinating pipeline phase transitions."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> None:
        self.batch_repo = batch_repo
        self.phase_initiators_map = phase_initiators_map

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: str,
        phase_status: str,
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
        """
        logger.info(
            f"Handling phase conclusion: batch={batch_id}, phase={completed_phase}, "
            f"status={phase_status}",
            extra={"correlation_id": correlation_id},
        )

        # Update the phase status in pipeline state
        # COMPLETED_WITH_FAILURES is treated as success for progression purposes
        # (per common_core/enums.py - it's a terminal success state with partial failures)
        if phase_status in ["COMPLETED_SUCCESSFULLY", "COMPLETED_WITH_FAILURES"]:
            updated_status = "COMPLETED_SUCCESSFULLY"
        else:
            updated_status = "FAILED"

        await self.update_phase_status(
            batch_id,
            completed_phase,
            updated_status,
            datetime.now(timezone.utc).isoformat(),
        )

        # Allow progression for both COMPLETED_SUCCESSFULLY and COMPLETED_WITH_FAILURES
        # COMPLETED_WITH_FAILURES indicates partial success and should proceed with
        # successful essays
        if phase_status not in ["COMPLETED_SUCCESSFULLY", "COMPLETED_WITH_FAILURES"]:
            logger.info(
                f"Phase {completed_phase} for batch {batch_id} did not complete successfully "
                f"(status: {phase_status}), skipping next phase initiation"
            )
            return

        # Log progression decision for COMPLETED_WITH_FAILURES cases
        if phase_status == "COMPLETED_WITH_FAILURES":
            successful_count = (
                len(processed_essays_for_next_phase) if processed_essays_for_next_phase else 0
            )
            logger.info(
                f"Phase {completed_phase} completed with partial failures for batch {batch_id}. "
                f"Proceeding to next phase with {successful_count} successful essays.",
                extra={"correlation_id": correlation_id},
            )

        # Determine and initiate next phase with data propagation
        await self._initiate_next_phase(
            batch_id, completed_phase, correlation_id, processed_essays_for_next_phase
        )

    async def update_phase_status(
        self,
        batch_id: str,
        phase: str,
        status: str,
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
        phase_updates = {f"{phase}_status": status}
        if completion_timestamp:
            phase_updates[f"{phase}_completed_at"] = completion_timestamp

        updated_pipeline_state.update(phase_updates)
        await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

        logger.info(f"Updated {phase} status to {status} for batch {batch_id}")

    async def _initiate_next_phase(
        self,
        batch_id: str,
        completed_phase: str,
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
                current_index = requested_pipelines.index(completed_phase)
            except ValueError:
                logger.error(
                    f"Completed phase '{completed_phase}' not found in requested_pipelines "
                    f"for batch {batch_id}"
                )
                return

            # Check if there's a next phase
            if current_index + 1 >= len(requested_pipelines):
                logger.info(
                    f"Pipeline completed for batch {batch_id} - no more phases after "
                    f"'{completed_phase}'"
                )
                # TODO: Mark batch as COMPLETED when batch completion events are available
                return

            # Get next phase and validate
            next_phase_str = requested_pipelines[current_index + 1]
            try:
                next_phase_name = PhaseName(next_phase_str)
            except ValueError as e:
                logger.error(
                    f"Invalid next phase name '{next_phase_str}' for batch {batch_id}: {e}"
                )
                return

            logger.info(
                f"Initiating next phase '{next_phase_name.value}' for batch {batch_id} after "
                f"'{completed_phase}'",
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
                    "DISPATCH_INITIATED",
                    "IN_PROGRESS",
                    "COMPLETED_SUCCESSFULLY",
                    "FAILED",
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
                    "this may indicate a data flow issue"
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
                    f"Failed to initiate phase {next_phase_name} for batch {batch_id}: {e}"
                )

                # Mark phase as FAILED and save state
                if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                    pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
                    if pipeline_detail:
                        pipeline_detail.status = PipelineExecutionStatus.FAILED
                        pipeline_detail.error_info = {
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        await self.batch_repo.save_processing_pipeline_state(
                            batch_id, current_pipeline_state
                        )
                else:  # Dictionary - backwards compatibility
                    updated_pipeline_state = current_pipeline_state.copy()
                    updated_pipeline_state.update(
                        {
                            f"{next_phase_name.value}_status": "FAILED",
                            f"{next_phase_name.value}_error": str(e),
                            f"{next_phase_name.value}_failed_at": (
                                datetime.now(timezone.utc).isoformat()
                            ),
                        }
                    )
                    await self.batch_repo.save_processing_pipeline_state(
                        batch_id, updated_pipeline_state
                    )

                # TODO: Publish diagnostic event when error event models are available
                raise

            # Generic state update - mark phase as DISPATCH_INITIATED
            if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
                if pipeline_detail:
                    pipeline_detail.status = PipelineExecutionStatus.DISPATCH_INITIATED
                    pipeline_detail.started_at = datetime.now(timezone.utc)
                    await self.batch_repo.save_processing_pipeline_state(
                        batch_id, current_pipeline_state
                    )
            else:  # Dictionary - backwards compatibility
                updated_pipeline_state = current_pipeline_state.copy()
                updated_pipeline_state.update(
                    {
                        f"{next_phase_name.value}_status": "DISPATCH_INITIATED",
                        f"{next_phase_name.value}_initiated_at": (
                            datetime.now(timezone.utc).isoformat()
                        ),
                    }
                )
                await self.batch_repo.save_processing_pipeline_state(
                    batch_id, updated_pipeline_state
                )

            logger.info(
                f"Successfully initiated {next_phase_name.value} pipeline for batch {batch_id}"
            )

        except Exception as e:
            logger.error(
                f"Error determining/initiating next phase for batch {batch_id}: {e}", exc_info=True
            )
            raise

    def _get_phase_status(self, pipeline_state: dict, phase: str) -> str | None:
        """Extract phase status from pipeline state, handling both dict and object formats."""
        if hasattr(pipeline_state, phase):  # Pydantic object
            phase_obj = getattr(pipeline_state, phase)
            return getattr(phase_obj, "status", None) if phase_obj else None
        else:  # Dictionary
            return pipeline_state.get(f"{phase}_status")
