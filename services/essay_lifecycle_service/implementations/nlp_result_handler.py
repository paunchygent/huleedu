"""
NLP result handler for Essay Lifecycle Service.

Handles NLP analysis completion events, managing state transitions
for essays in NLP analysis batches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.events.nlp_events import BatchNlpAnalysisCompletedV1
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.logging_utils import create_service_logger

# Import event constants from state machine to ensure consistency
from services.essay_lifecycle_service.essay_state_machine import (
    EVT_NLP_FAILED,
    EVT_NLP_SUCCEEDED,
    EssayStateMachine,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
    )

logger = create_service_logger("nlp_result_handler")


class NLPResultHandler:
    """Handler for NLP analysis results."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> None:
        """Initialize NLP result handler."""
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory

    async def handle_nlp_analysis_completed(
        self,
        result_data: BatchNlpAnalysisCompletedV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle NLP analysis completion from NLP Service.

        CRITICAL: This handler follows clean architecture principles.
        It ONLY updates state machine status - NO business data storage.
        Business data (NLP metrics, grammar analysis) is sent to RAS via separate events.

        Args:
            result_data: Batch NLP analysis completion event (thin event)
            correlation_id: Correlation ID for tracking
            confirm_idempotency: Optional idempotency confirmation callback

        Returns:
            True if all essay states were successfully updated, False otherwise
        """
        try:
            logger.info(
                "Processing NLP analysis completion for batch",
                extra={
                    "batch_id": result_data.batch_id,
                    "successful_count": result_data.processing_summary.get("successful", 0),
                    "failed_count": result_data.processing_summary.get("failed", 0),
                    "correlation_id": str(correlation_id),
                },
            )

            # Extract essay IDs from the processing summary
            successful_essay_ids = result_data.processing_summary.get("successful_essay_ids", [])
            failed_essay_ids = result_data.processing_summary.get("failed_essay_ids", [])

            if not successful_essay_ids and not failed_essay_ids:
                logger.warning(
                    "No essay IDs found in NLP analysis completion event",
                    extra={
                        "batch_id": result_data.batch_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

            # START UNIT OF WORK
            async with self.session_factory() as session:
                async with session.begin():
                    # Process successful essays
                    for essay_id in successful_essay_ids:
                        # Get current essay state
                        essay_state = await self.repository.get_essay_state(essay_id, session)
                        if essay_state is None:
                            logger.error(
                                "Essay not found for NLP analysis result",
                                extra={
                                    "essay_id": essay_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            continue

                        # Create state machine and trigger success event
                        state_machine = EssayStateMachine(
                            essay_id=essay_id, initial_status=essay_state.current_status
                        )

                        # Attempt state transition
                        if state_machine.trigger_event(EVT_NLP_SUCCEEDED):
                            # Preserve existing commanded_phases metadata
                            existing_commanded_phases = essay_state.processing_metadata.get(
                                "commanded_phases", []
                            )

                            # Ensure nlp_analysis is in commanded_phases
                            if "nlp_analysis" not in existing_commanded_phases:
                                existing_commanded_phases.append("nlp_analysis")

                            # CRITICAL: Only update state, NO business data storage
                            # Business data (NLP metrics, grammar analysis) goes to RAS only
                            await self.repository.update_essay_status_via_machine(
                                essay_id,
                                state_machine.current_status,
                                {
                                    "nlp_analysis_result": {
                                        "success": True,
                                        # NO NLP metrics here - violates clean architecture
                                        # NO grammar analysis here - violates clean architecture
                                    },
                                    "current_phase": "nlp_analysis",
                                    "commanded_phases": existing_commanded_phases,
                                    "phase_outcome_status": "NLP_ANALYSIS_SUCCESS",
                                },
                                session,
                                correlation_id=correlation_id,
                            )

                            logger.info(
                                "Successfully processed NLP analysis completion for essay",
                                extra={
                                    "essay_id": essay_id,
                                    "new_status": state_machine.current_status.value,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                        else:
                            logger.error(
                                f"State machine trigger '{EVT_NLP_SUCCEEDED}' failed "
                                f"for essay {essay_id} from status "
                                f"{essay_state.current_status.value}.",
                                extra={"correlation_id": str(correlation_id)},
                            )
                            continue

                    # Process failed essays
                    for essay_id in failed_essay_ids:
                        # Get current essay state
                        essay_state = await self.repository.get_essay_state(essay_id, session)
                        if essay_state is None:
                            logger.error(
                                "Essay not found for NLP analysis failure",
                                extra={
                                    "essay_id": essay_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            continue

                        # Create state machine and trigger failure event
                        state_machine = EssayStateMachine(
                            essay_id=essay_id, initial_status=essay_state.current_status
                        )

                        # Attempt state transition
                        if state_machine.trigger_event(EVT_NLP_FAILED):
                            # Preserve existing commanded_phases metadata
                            existing_commanded_phases = essay_state.processing_metadata.get(
                                "commanded_phases", []
                            )

                            # Ensure nlp_analysis is in commanded_phases
                            if "nlp_analysis" not in existing_commanded_phases:
                                existing_commanded_phases.append("nlp_analysis")

                            await self.repository.update_essay_status_via_machine(
                                essay_id,
                                state_machine.current_status,
                                {
                                    "nlp_analysis_result": {
                                        "success": False,
                                        # NO error details here - clean architecture
                                    },
                                    "current_phase": "nlp_analysis",
                                    "commanded_phases": existing_commanded_phases,
                                    "phase_outcome_status": "NLP_ANALYSIS_FAILED",
                                },
                                session,
                                correlation_id=correlation_id,
                            )

                            logger.info(
                                "Processed NLP analysis failure for essay",
                                extra={
                                    "essay_id": essay_id,
                                    "new_status": state_machine.current_status.value,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                        else:
                            logger.error(
                                f"State machine trigger '{EVT_NLP_FAILED}' failed "
                                f"for essay {essay_id} from status "
                                f"{essay_state.current_status.value}.",
                                extra={"correlation_id": str(correlation_id)},
                            )
                            continue

                    # Check batch completion after processing all essays
                    logger.info(
                        "Checking batch phase completion for NLP analysis",
                        extra={
                            "batch_id": result_data.batch_id,
                            "total_essays": len(successful_essay_ids) + len(failed_essay_ids),
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Get a representative essay state to trigger batch completion check
                    representative_essay_id = (
                        (successful_essay_ids + failed_essay_ids)[0]
                        if (successful_essay_ids + failed_essay_ids)
                        else None
                    )
                    if representative_essay_id:
                        representative_essay_state = await self.repository.get_essay_state(
                            representative_essay_id, session
                        )
                        if representative_essay_state:
                            await self.batch_coordinator.check_batch_completion(
                                essay_state=representative_essay_state,
                                phase_name=PhaseName.NLP,
                                correlation_id=correlation_id,
                                session=session,
                            )
                    # Transaction commits here

            # Confirm idempotency after successful transaction commit
            if confirm_idempotency is not None:
                await confirm_idempotency()

            return True

        except Exception as e:
            logger.error(
                "Error handling NLP analysis completion",
                extra={
                    "batch_id": getattr(result_data, "batch_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False
