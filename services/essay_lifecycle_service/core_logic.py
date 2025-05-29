"""
Core business logic for the Essay Lifecycle Service.

This module contains the essential business logic for essay state management,
state transition validation, and processing coordination.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from common_core.enums import EssayStatus
from common_core.metadata_models import EntityReference


class StateTransitionValidator:
    """
    Validates essay state transitions according to business rules.

    Implements the state machine logic for essay processing workflow,
    ensuring only valid transitions are allowed.
    """

    # Define valid state transitions as a mapping - Walking Skeleton: Spellcheck Pipeline Only
    # NOTE: ELS receives essays from BOS in READY_FOR_PROCESSING state after File Service completes content ingestion
    _VALID_TRANSITIONS: dict[EssayStatus, set[EssayStatus]] = {
        EssayStatus.READY_FOR_PROCESSING: {
            EssayStatus.AWAITING_SPELLCHECK,  # BOS assigns spellcheck pipeline
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AWAITING_SPELLCHECK: {
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECK_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.SPELLCHECKING_IN_PROGRESS: {
            EssayStatus.SPELLCHECKED_SUCCESS,
            EssayStatus.SPELLCHECK_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.SPELLCHECKED_SUCCESS: {
            EssayStatus.ESSAY_CRITICAL_FAILURE,  # Terminal success state for walking skeleton
        },
        EssayStatus.SPELLCHECK_FAILED: {
            EssayStatus.AWAITING_SPELLCHECK,  # Allow retry
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        # Terminal states have no valid transitions
        EssayStatus.ESSAY_CRITICAL_FAILURE: set(),
    }

    def validate_transition(self, current_status: EssayStatus, target_status: EssayStatus) -> bool:
        """
        Validate if state transition is allowed.

        Args:
            current_status: Current essay status
            target_status: Target essay status to transition to

        Returns:
            True if transition is valid, False otherwise
        """
        return target_status in self._VALID_TRANSITIONS.get(current_status, set())

    def get_next_valid_statuses(self, current_status: EssayStatus) -> list[EssayStatus]:
        """
        Get list of valid next statuses from current state.

        Args:
            current_status: Current essay status

        Returns:
            List of valid next statuses
        """
        return list(self._VALID_TRANSITIONS.get(current_status, set()))

    @classmethod
    def is_terminal_status(cls, status: EssayStatus) -> bool:
        """Check if a status is terminal (no further transitions allowed)."""
        return status in {
            EssayStatus.SPELLCHECKED_SUCCESS,  # Walking skeleton terminal success
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        }

    @classmethod
    def is_failure_status(cls, status: EssayStatus) -> bool:
        """Check if a status indicates a failure state."""
        return status.value.endswith("_failed") or status in {
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        }

    @classmethod
    def is_processing_status(cls, status: EssayStatus) -> bool:
        """Check if a status indicates active processing."""
        return status.value.endswith("_in_progress")


def generate_correlation_id() -> UUID:
    """Generate a new correlation ID for event tracking."""
    return uuid4()


def create_entity_reference(essay_id: str, batch_id: str | None = None) -> EntityReference:
    """
    Create an EntityReference for an essay.

    Args:
        essay_id: The essay identifier
        batch_id: Optional batch identifier

    Returns:
        EntityReference instance for the essay
    """
    return EntityReference(entity_id=essay_id, entity_type="essay", parent_id=batch_id)
