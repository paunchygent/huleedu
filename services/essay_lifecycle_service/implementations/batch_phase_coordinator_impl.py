"""
Batch phase coordinator implementation for Essay Lifecycle Service.

Handles batch-level phase completion aggregation and ELSBatchPhaseOutcomeV1 event publishing.
This provides clean separation between individual essay processing and batch-level coordination.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common_core.domain_enums import ContentType
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
    EssayState,
    EventPublisher,
)

logger = create_service_logger("batch_phase_coordinator")


class DefaultBatchPhaseCoordinator(BatchPhaseCoordinator):
    """Default implementation of BatchPhaseCoordinator protocol."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        event_publisher: EventPublisher,
        batch_tracker: BatchEssayTracker,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.event_publisher = event_publisher
        self.batch_tracker = batch_tracker
        self.session_factory = session_factory

    async def check_batch_completion(
        self,
        essay_state: EssayState,
        phase_name: PhaseName | str,
        correlation_id: UUID,
        session: AsyncSession,
    ) -> None:
        """
        Check if all essays in a batch phase are complete and publish ELSBatchPhaseOutcomeV1 if so.

        Args:
            essay_state: The essay state that was just updated
            phase_name: Name of the processing phase (e.g., 'spellcheck',
                'cj_assessment') as string or PhaseName enum
            correlation_id: Optional correlation ID for event tracking
        """
        # Convert phase_name to PhaseName if it's a string
        if isinstance(phase_name, str):
            try:
                phase_name = PhaseName(phase_name.lower())
            except ValueError:
                logger.warning(
                    f"Invalid phase name: {phase_name}",
                    extra={"phase_name": phase_name, "correlation_id": str(correlation_id)},
                )
                return
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

            if current_phase != phase_name.value and phase_name.value not in commanded_phases:
                logger.debug(
                    "Essay not part of specified phase, skipping batch outcome check",
                    extra={
                        "essay_id": essay_state.essay_id,
                        "phase_name": phase_name.value,
                        "current_phase": current_phase,
                        "commanded_phases": commanded_phases,
                        "correlation_id": str(correlation_id),
                    },
                )
                return

            batch_id = essay_state.batch_id

            # Get all essays in this batch/phase
            essays_in_phase = await self.repository.list_essays_by_batch_and_phase(
                batch_id=batch_id, phase_name=phase_name.value, session=session
            )

            if not essays_in_phase:
                logger.warning(
                    "No essays found for batch/phase aggregation",
                    extra={
                        "batch_id": batch_id,
                        "phase_name": phase_name.value,
                        "correlation_id": str(correlation_id),
                    },
                )
                return

            # Get terminal statuses for this phase
            terminal_statuses_for_phase = self._get_terminal_statuses_for_phase(phase_name.value)

            # Check if all essays have reached terminal states for this phase
            completed_essays = []
            failed_essays = []
            still_processing = []

            for essay in essays_in_phase:
                if essay.current_status in terminal_statuses_for_phase:
                    if self._is_success_status_for_phase(essay.current_status, phase_name.value):
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
                        "phase_name": phase_name.value,
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
                session=session,
            )

        except Exception as e:
            logger.error(
                "Error checking batch phase completion",
                extra={
                    "essay_id": getattr(essay_state, "essay_id", "unknown"),
                    "batch_id": getattr(essay_state, "batch_id", "unknown"),
                    "phase_name": phase_name.value,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )

    def _get_terminal_statuses_for_phase(self, phase_name: PhaseName | str) -> set[EssayStatus]:
        """
        Get terminal statuses for a specific phase.

        Args:
            phase_name: The phase name as string or PhaseName enum

        Returns:
            Set of EssayStatus enums that are considered terminal for the given phase
        """
        # Convert phase_name to PhaseName if it's a string
        if isinstance(phase_name, str):
            try:
                phase_name = PhaseName(phase_name.lower())
            except ValueError:
                return set()

        if phase_name == PhaseName.SPELLCHECK:
            return {
                EssayStatus.SPELLCHECKED_SUCCESS,
                EssayStatus.SPELLCHECK_FAILED,
            }
        elif phase_name == PhaseName.AI_FEEDBACK:
            return {
                EssayStatus.AI_FEEDBACK_SUCCESS,
                EssayStatus.AI_FEEDBACK_FAILED,
            }
        elif phase_name == PhaseName.CJ_ASSESSMENT:
            return {
                EssayStatus.CJ_ASSESSMENT_SUCCESS,
                EssayStatus.CJ_ASSESSMENT_FAILED,
            }
        elif phase_name == PhaseName.NLP:
            return {
                EssayStatus.NLP_SUCCESS,
                EssayStatus.NLP_FAILED,
            }
        return set()

    def _is_success_status_for_phase(
        self, status: str | EssayStatus, phase_name: PhaseName | str
    ) -> bool:
        """
        Check if a status indicates success for a specific phase.

        Args:
            status: The status to check (string or EssayStatus enum)
            phase_name: The phase name as string or PhaseName enum

        Returns:
            True if the status indicates success for the given phase, False otherwise
        """
        # Convert status to string if it's an EssayStatus
        status_str = status.value if isinstance(status, EssayStatus) else str(status)

        # Convert phase_name to PhaseName if it's a string
        if isinstance(phase_name, str):
            try:
                phase_name = PhaseName(phase_name.lower())
            except ValueError:
                return False

        if phase_name == PhaseName.SPELLCHECK:
            return status_str in ("spellchecked_success", "spellcheck_success")
        elif phase_name == PhaseName.AI_FEEDBACK:
            return status_str in ("ai_feedback_generated", "ai_feedback_success")
        elif phase_name == PhaseName.CJ_ASSESSMENT:
            return status_str in ("cj_assessment_success", "cj_assessment_completed")
        elif phase_name == PhaseName.NLP:
            return status_str in ("nlp_processing_completed", "nlp_success")
        return False

    async def _publish_batch_phase_outcome(
        self,
        batch_id: str,
        phase_name: PhaseName,
        completed_essays: list[EssayState],
        failed_essays: list[EssayState],
        correlation_id: UUID,
        session: AsyncSession,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event for completed batch phase."""

        # Build processed_essays list with required fields
        processed_essays = []
        for essay in completed_essays:
            # Get the text_storage_id for the output of this phase
            text_storage_id = self._get_text_storage_id_for_phase(essay, phase_name.value)
            if not text_storage_id:
                continue  # Skip if no text storage ID found (shouldn't happen for completed essays)

            processed_essays.append(
                EssayProcessingInputRefV1(
                    essay_id=essay.essay_id,
                    text_storage_id=text_storage_id,
                )
            )

        # Build failed_essay_ids list
        failed_essay_ids = [essay.essay_id for essay in failed_essays]

        # Create the outcome event
        essay_outcomes = [
            (
                essay.essay_id,
                self._is_success_status_for_phase(essay.current_status, phase_name.value),
            )
            for essay in completed_essays + failed_essays
        ]
        success_count = sum(1 for _, success in essay_outcomes if success)
        total_essays = len(essay_outcomes)

        if success_count == total_essays:
            batch_status = BatchStatus.COMPLETED_SUCCESSFULLY
        elif success_count > 0:
            batch_status = BatchStatus.COMPLETED_WITH_FAILURES
        else:
            batch_status = BatchStatus.FAILED_CRITICALLY

        outcome_event = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=phase_name,
            phase_status=batch_status,
            processed_essays=processed_essays,
            failed_essay_ids=failed_essay_ids,
            correlation_id=correlation_id,
        )

        # Publish the event
        await self.event_publisher.publish_els_batch_phase_outcome(
            event_data=outcome_event,
            correlation_id=correlation_id,
            session=session,
        )

        # If this is the final phase (CJ Assessment), schedule delayed cleanup
        if phase_name == PhaseName.CJ_ASSESSMENT:
            logger.info(
                f"Final phase completed for batch {batch_id}, scheduling cleanup in 5 minutes",
                extra={"batch_id": batch_id, "correlation_id": str(correlation_id)},
            )
            # Schedule delayed cleanup to ensure all downstream processing completes
            asyncio.create_task(
                self._delayed_batch_cleanup(batch_id, correlation_id, delay_minutes=5)
            )

    def _get_text_storage_id_for_phase(
        self, essay_state: EssayState, phase_name: PhaseName | str
    ) -> str | None:
        """
        Get the appropriate text_storage_id for the *output* of the completed 'phase_name',
        which will be used as input for the *next* phase.

        Args:
            essay_state: The essay state containing storage references
            phase_name: The phase name as string or PhaseName enum

        Returns:
            The storage ID for the phase output, or None if not found
        """
        # Convert phase_name to PhaseName if it's a string
        if isinstance(phase_name, str):
            try:
                phase_name = PhaseName(phase_name.lower())
            except ValueError:
                return None

        # First try to get from specific phase output attributes (production path)
        result = None
        if phase_name == PhaseName.SPELLCHECK:
            result = getattr(essay_state, "spellchecked_text_storage_id", None)
        elif phase_name == PhaseName.AI_FEEDBACK:
            result = getattr(essay_state, "ai_feedback_text_storage_id", None)
        elif phase_name == PhaseName.CJ_ASSESSMENT:
            # CJ Assessment works on spellchecked content, not original
            result = getattr(essay_state, "spellchecked_text_storage_id", None)
        elif phase_name == PhaseName.NLP:
            result = getattr(essay_state, "nlp_processed_text_storage_id", None)

        if result is not None:
            return str(result)

        # Fallback to storage_references dictionary
        if hasattr(essay_state, "storage_references") and essay_state.storage_references:
            refs = essay_state.storage_references
            if isinstance(refs, dict):
                # For spellcheck phase, return CORRECTED_TEXT if available
                if phase_name == PhaseName.SPELLCHECK:
                    corrected_text_id = refs.get(ContentType.CORRECTED_TEXT)
                    if corrected_text_id:
                        return str(corrected_text_id)

                # For other phases or fallback, return ORIGINAL_ESSAY
                original_text_id = refs.get(ContentType.ORIGINAL_ESSAY)
                if original_text_id:
                    return str(original_text_id)

        # Final fallback for missing storage references
        if hasattr(essay_state, "essay_id") and hasattr(essay_state, "storage_references"):
            logger.warning(
                f"No text storage ID found for essay {essay_state.essay_id} phase {phase_name}",
                extra={"essay_id": essay_state.essay_id, "phase_name": phase_name},
            )

        return None

    async def _delayed_batch_cleanup(
        self, batch_id: str, correlation_id: UUID, delay_minutes: int = 5
    ) -> None:
        """Perform delayed cleanup of batch tracker records after final phase completion.

        Args:
            batch_id: ID of the batch to clean up
            correlation_id: Correlation ID for tracing
            delay_minutes: Minutes to wait before cleanup (default: 5)
        """
        try:
            # Wait for the specified delay to ensure all downstream processing completes
            await asyncio.sleep(delay_minutes * 60)

            logger.info(
                f"Starting delayed cleanup for batch {batch_id}",
                extra={"batch_id": batch_id, "correlation_id": str(correlation_id)},
            )

            # Remove the batch tracker record from the database
            await self.batch_tracker.remove_batch_from_database(batch_id)

            logger.info(
                f"Successfully cleaned up batch tracker for batch {batch_id}",
                extra={"batch_id": batch_id, "correlation_id": str(correlation_id)},
            )

        except Exception as e:
            # Log the error but don't raise - cleanup failures shouldn't break the pipeline
            logger.error(
                f"Failed to cleanup batch tracker for batch {batch_id}: {e}",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": str(correlation_id),
                    "error": str(e),
                },
            )
