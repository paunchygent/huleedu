"""
Batch phase coordinator implementation for Essay Lifecycle Service.

Handles batch-level phase completion aggregation and ELSBatchPhaseOutcomeV1 event publishing.
This provides clean separation between individual essay processing and batch-level coordination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.enums import EssayStatus

from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
    EssayState,
    EventPublisher,
)

logger = create_service_logger("batch_phase_coordinator")


class DefaultBatchPhaseCoordinator(BatchPhaseCoordinator):
    """Default implementation of BatchPhaseCoordinator protocol."""

    def __init__(
        self, repository: EssayRepositoryProtocol, event_publisher: EventPublisher
    ) -> None:
        self.repository = repository
        self.event_publisher = event_publisher

    async def check_batch_completion(
        self,
        essay_state: EssayState,
        phase_name: str,
        correlation_id: UUID | None = None,
    ) -> None:
        """
        Check if all essays in a batch phase are complete and publish ELSBatchPhaseOutcomeV1 if so.

        This implements the core logic for Task 2.3: ELSBatchPhaseOutcomeV1 Event
        Aggregation and Publishing.
        """
        try:
            # Only check for batch completion if this essay belongs to a batch
            # and has phase metadata
            if not essay_state.batch_id:
                logger.debug(
                    "Essay not part of a batch, skipping batch outcome check",
                    extra={"essay_id": essay_state.essay_id, "correlation_id": str(correlation_id)},
                )
                return

            # Check if this essay was part of the specified phase
            processing_metadata = essay_state.processing_metadata
            current_phase = processing_metadata.get("current_phase")
            commanded_phases = processing_metadata.get("commanded_phases", [])

            if current_phase != phase_name and phase_name not in commanded_phases:
                logger.debug(
                    "Essay not part of specified phase, skipping batch outcome check",
                    extra={
                        "essay_id": essay_state.essay_id,
                        "phase_name": phase_name,
                        "current_phase": current_phase,
                        "commanded_phases": commanded_phases,
                        "correlation_id": str(correlation_id),
                    },
                )
                return

            batch_id = essay_state.batch_id

            # Get all essays in this batch/phase
            essays_in_phase = await self.repository.list_essays_by_batch_and_phase(
                batch_id=batch_id, phase_name=phase_name
            )

            if not essays_in_phase:
                logger.warning(
                    "No essays found for batch/phase aggregation",
                    extra={
                        "batch_id": batch_id,
                        "phase_name": phase_name,
                        "correlation_id": str(correlation_id),
                    },
                )
                return

            # Check if all essays have reached terminal states for this phase
            terminal_statuses_for_phase = self._get_terminal_statuses_for_phase(phase_name)

            completed_essays = []
            failed_essays = []
            still_processing = []

            for essay in essays_in_phase:
                if essay.current_status in terminal_statuses_for_phase:
                    if self._is_success_status_for_phase(essay.current_status, phase_name):
                        completed_essays.append(essay)
                    else:
                        failed_essays.append(essay)
                else:
                    still_processing.append(essay)

            # If there are still essays processing, batch is not complete yet
            if still_processing:
                logger.debug(
                    "Batch phase not yet complete, essays still processing",
                    extra={
                        "batch_id": batch_id,
                        "phase_name": phase_name,
                        "completed_count": len(completed_essays),
                        "failed_count": len(failed_essays),
                        "still_processing_count": len(still_processing),
                        "correlation_id": str(correlation_id),
                    },
                )
                return

            # All essays in phase are complete - aggregate and publish outcome
            await self._publish_batch_phase_outcome(
                batch_id=batch_id,
                phase_name=phase_name,
                completed_essays=completed_essays,
                failed_essays=failed_essays,
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                "Error checking batch phase completion",
                extra={
                    "essay_id": getattr(essay_state, "essay_id", "unknown"),
                    "batch_id": getattr(essay_state, "batch_id", "unknown"),
                    "phase_name": phase_name,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )

    def _get_terminal_statuses_for_phase(self, phase_name: str) -> set[EssayStatus]:
        """Get terminal statuses for a specific phase."""
        from common_core.enums import EssayStatus

        phase_terminal_statuses = {
            "spellcheck": {
                EssayStatus.SPELLCHECKED_SUCCESS,
                EssayStatus.SPELLCHECK_FAILED,
            },
            "cj_assessment": {
                EssayStatus.CJ_ASSESSMENT_SUCCESS,
                EssayStatus.CJ_ASSESSMENT_FAILED,
            },
            "ai_feedback": {
                EssayStatus.AI_FEEDBACK_SUCCESS,
                EssayStatus.AI_FEEDBACK_FAILED,
            },
            "nlp": {
                EssayStatus.NLP_SUCCESS,
                EssayStatus.NLP_FAILED,
            },
        }

        return phase_terminal_statuses.get(phase_name, set())

    def _is_success_status_for_phase(self, status: EssayStatus, phase_name: str) -> bool:
        """Check if a status indicates success for a specific phase."""
        from common_core.enums import EssayStatus

        phase_success_statuses = {
            "spellcheck": {EssayStatus.SPELLCHECKED_SUCCESS},
            "cj_assessment": {EssayStatus.CJ_ASSESSMENT_SUCCESS},
            "ai_feedback": {EssayStatus.AI_FEEDBACK_SUCCESS},
            "nlp": {EssayStatus.NLP_SUCCESS},
        }

        success_statuses = phase_success_statuses.get(phase_name, set())
        return status in success_statuses

    async def _publish_batch_phase_outcome(
        self,
        batch_id: str,
        phase_name: str,
        completed_essays: list[EssayState],
        failed_essays: list[EssayState],
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event for completed batch phase."""
        try:
            from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
            from common_core.metadata_models import EssayProcessingInputRefV1

            # Determine overall phase status
            if len(failed_essays) == 0:
                phase_status = "COMPLETED_SUCCESSFULLY"
            elif len(completed_essays) == 0:
                phase_status = "FAILED_CRITICALLY"
            else:
                phase_status = "COMPLETED_WITH_FAILURES"

            # Build processed_essays list with updated text_storage_ids
            processed_essays = []
            for essay in completed_essays:
                # Get the appropriate text_storage_id for this phase
                text_storage_id = self._get_text_storage_id_for_phase(essay, phase_name)

                if text_storage_id:
                    processed_essays.append(
                        EssayProcessingInputRefV1(
                            essay_id=essay.essay_id,
                            text_storage_id=text_storage_id,
                        )
                    )

            # Build failed_essay_ids list
            failed_essay_ids = [essay.essay_id for essay in failed_essays]

            # Create the outcome event
            outcome_event = ELSBatchPhaseOutcomeV1(
                batch_id=batch_id,
                phase_name=phase_name,
                phase_status=phase_status,
                processed_essays=processed_essays,
                failed_essay_ids=failed_essay_ids,
                correlation_id=correlation_id,
            )

            # Publish the event
            await self.event_publisher.publish_els_batch_phase_outcome(
                event_data=outcome_event,
                correlation_id=correlation_id,
            )

            logger.info(
                "Published ELSBatchPhaseOutcomeV1 event",
                extra={
                    "batch_id": batch_id,
                    "phase_name": phase_name,
                    "phase_status": phase_status,
                    "processed_count": len(processed_essays),
                    "failed_count": len(failed_essays),
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            logger.error(
                "Error publishing batch phase outcome",
                extra={
                    "batch_id": batch_id,
                    "phase_name": phase_name,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )

    def _get_text_storage_id_for_phase(
        self, essay_state: EssayState, phase_name: str
    ) -> str | None:
        """
        Get the appropriate text_storage_id for the *output* of the completed 'phase_name',
        which will be used as input for the *next* phase.
        """
        from common_core.enums import ContentType
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("batch_phase_coordinator")

        # This map defines which ContentType holds the *output* of a given phase
        # that should be used as input for the next phase.
        phase_output_content_type_map = {
            "spellcheck": ContentType.CORRECTED_TEXT,
            # For AI Feedback, if it modifies text, it would be something like:
            # "ai_feedback": ContentType.AI_EDITOR_REVISION_TEXT,
            #
            # For CJ and NLP, they usually work on a stable input (e.g.,
            # corrected text or original) and produce analysis, not a new version
            # of the essay text itself for further processing. So, the
            # text_storage_id might not change *after* CJ or NLP for the
            # *next text processing* phase.
            #
            # However, ELSBatchPhaseOutcomeV1 still needs *a* text_storage_id.
            # Default to original if specific output type not found or not
            # applicable.
        }

        output_content_type = phase_output_content_type_map.get(phase_name)

        if output_content_type and output_content_type in essay_state.storage_references:
            storage_id = essay_state.storage_references[output_content_type]
            return str(storage_id) if storage_id is not None else None
        else:
            # Fallback: if the phase doesn't produce a new text version,
            # or if its specific output isn't found, use the original text as
            # reference for the next phase.
            # This might need to be more sophisticated, e.g., using the LATEST_TEXT_VERSION.
            # For now, using ORIGINAL_ESSAY as a safe fallback.
            # If spellcheck was the phase, and CORRECTED_TEXT isn't there, something went wrong.
            if phase_name == "spellcheck":
                logger.warning(
                    "Corrected text storage ID not found for essay {essay_state.essay_id} "
                    "after spellcheck. Falling back to original.",
                    extra={"essay_id": essay_state.essay_id, "phase_name": phase_name},
                )

            fallback_storage_id = essay_state.storage_references.get(ContentType.ORIGINAL_ESSAY)
            if fallback_storage_id:
                return str(fallback_storage_id)

        logger.warning(
            "Could not determine relevant text_storage_id for essay "
            f"{essay_state.essay_id} after phase {phase_name}",
            extra={"essay_id": essay_state.essay_id, "phase_name": phase_name},
        )
        return None
