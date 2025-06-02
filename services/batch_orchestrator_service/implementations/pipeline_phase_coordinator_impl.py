"""Pipeline phase coordinator implementation for batch processing."""

from __future__ import annotations

from datetime import datetime, timezone

from api_models import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchRepositoryProtocol,
    CJAssessmentInitiatorProtocol,
)

logger = create_service_logger("bos.pipeline.coordinator")


class DefaultPipelinePhaseCoordinator:
    """Default implementation for coordinating pipeline phase transitions."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        cj_initiator: CJAssessmentInitiatorProtocol,
    ) -> None:
        self.batch_repo = batch_repo
        self.cj_initiator = cj_initiator

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: str,
        phase_status: str,
        correlation_id: str,
    ) -> None:
        """
        Handle completion of a pipeline phase and determine next actions.

        Coordinates phase transitions and initiates next phases when appropriate.
        """
        logger.info(
            f"Handling phase conclusion: batch={batch_id}, phase={completed_phase}, "
            f"status={phase_status}",
            extra={"correlation_id": correlation_id},
        )

        # Update the phase status in pipeline state
        await self.update_phase_status(
            batch_id,
            completed_phase,
            "COMPLETED" if phase_status == "completed" else "FAILED",
            datetime.now(timezone.utc).isoformat(),
        )

        # Only proceed with next phase if current phase completed successfully
        if phase_status != "completed":
            logger.info(
                f"Phase {completed_phase} for batch {batch_id} did not complete successfully, "
                f"skipping next phase initiation"
            )
            return

        # Determine and initiate next phase
        await self._initiate_next_phase(batch_id, completed_phase, correlation_id)

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
        self, batch_id: str, completed_phase: str, correlation_id: str
    ) -> None:
        """Determine and initiate the next pipeline phase based on the completed phase."""
        # Get batch context to determine what phases are enabled
        batch_context = await self.batch_repo.get_batch_context(batch_id)
        if not batch_context:
            logger.error(f"Missing batch context for batch {batch_id}")
            return

        # Handle phase transitions
        if completed_phase == "spellcheck":
            await self._handle_spellcheck_completion(batch_id, batch_context, correlation_id)
        else:
            logger.info(
                f"No next phase defined for completed phase '{completed_phase}' "
                f"in batch {batch_id}"
            )

    async def _handle_spellcheck_completion(
        self,
        batch_id: str,
        batch_context: BatchRegistrationRequestV1,
        correlation_id: str,
    ) -> None:
        """Handle spellcheck completion and potentially initiate CJ assessment."""
        # Check if CJ assessment should be initiated
        if not batch_context.enable_cj_assessment:
            logger.info(f"CJ assessment not enabled for batch {batch_id}")
            return

        # Check if CJ assessment hasn't been initiated yet
        current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if not current_pipeline_state:
            logger.error(f"No pipeline state found for batch {batch_id}")
            return

        # Check current CJ assessment status
        cj_status = self._get_phase_status(current_pipeline_state, "cj_assessment")
        if cj_status in ["DISPATCH_INITIATED", "IN_PROGRESS", "COMPLETED", "FAILED"]:
            logger.info(
                f"CJ assessment already processed for batch {batch_id}, status: {cj_status}"
            )
            return

        # Initiate CJ assessment
        await self.cj_initiator.initiate_cj_assessment(
            batch_id, batch_context, correlation_id
        )

    def _get_phase_status(self, pipeline_state: dict, phase: str) -> str | None:
        """Extract phase status from pipeline state, handling both dict and object formats."""
        if hasattr(pipeline_state, phase):  # Pydantic object
            phase_obj = getattr(pipeline_state, phase)
            return getattr(phase_obj, "status", None) if phase_obj else None
        else:  # Dictionary
            return pipeline_state.get(f"{phase}_status")
