"""Pipeline state management service for batch processing."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus

logger = create_service_logger("bos.pipeline.state_manager")


class PipelineStateManager:
    """Service responsible for managing and updating pipeline state in the repository."""

    def __init__(self, batch_repo: BatchRepositoryProtocol) -> None:
        self.batch_repo = batch_repo

    async def update_phase_status(
        self,
        batch_id: str,
        phase: PhaseName,
        status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
    ) -> None:
        """
        Update the status of a specific pipeline phase.

        Args:
            batch_id: The batch identifier
            phase: The phase to update
            status: The new status for the phase
            completion_timestamp: Optional timestamp of completion
        """
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

    def get_phase_status(self, pipeline_state: dict[str, Any], phase: str) -> str | None:
        """
        Extract phase status from pipeline state, handling both dict and object formats.

        Args:
            pipeline_state: The pipeline state dictionary or object
            phase: The phase name to get status for

        Returns:
            The phase status string or None if not found
        """
        if hasattr(pipeline_state, phase):  # Pydantic object
            phase_obj = getattr(pipeline_state, phase)
            return getattr(phase_obj, "status", None) if phase_obj else None
        else:  # Dictionary
            return pipeline_state.get(f"{phase}_status")
