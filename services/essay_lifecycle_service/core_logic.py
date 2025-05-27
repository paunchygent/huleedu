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

    # Define valid state transitions as a mapping
    _VALID_TRANSITIONS: dict[EssayStatus, set[EssayStatus]] = {
        EssayStatus.UPLOADED: {EssayStatus.TEXT_EXTRACTED, EssayStatus.ESSAY_CRITICAL_FAILURE},
        EssayStatus.TEXT_EXTRACTED: {
            EssayStatus.AWAITING_SPELLCHECK,
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
            EssayStatus.AWAITING_NLP,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.SPELLCHECK_FAILED: {
            EssayStatus.AWAITING_SPELLCHECK,  # Retry
            EssayStatus.AWAITING_NLP,  # Skip to next phase
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AWAITING_NLP: {
            EssayStatus.NLP_IN_PROGRESS,
            EssayStatus.NLP_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.NLP_IN_PROGRESS: {
            EssayStatus.NLP_COMPLETED_SUCCESS,
            EssayStatus.NLP_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.NLP_COMPLETED_SUCCESS: {
            EssayStatus.AWAITING_AI_FEEDBACK,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.NLP_FAILED: {
            EssayStatus.AWAITING_NLP,  # Retry
            EssayStatus.AWAITING_AI_FEEDBACK,  # Skip to next phase
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AWAITING_AI_FEEDBACK: {
            EssayStatus.AI_FEEDBACK_IN_PROGRESS,
            EssayStatus.AI_FEEDBACK_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AI_FEEDBACK_IN_PROGRESS: {
            EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS,
            EssayStatus.AI_FEEDBACK_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS: {
            EssayStatus.AWAITING_EDITOR_REVISION,
            EssayStatus.AWAITING_GRAMMAR_CHECK,
            EssayStatus.AWAITING_CJ_INCLUSION,
            EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AI_FEEDBACK_FAILED: {
            EssayStatus.AWAITING_AI_FEEDBACK,  # Retry
            EssayStatus.AWAITING_EDITOR_REVISION,  # Skip to next phase
            EssayStatus.AWAITING_GRAMMAR_CHECK,  # Skip to next phase
            EssayStatus.AWAITING_CJ_INCLUSION,  # Skip to next phase
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        # Additional states for optional processing phases
        EssayStatus.AWAITING_EDITOR_REVISION: {
            EssayStatus.EDITOR_REVISION_IN_PROGRESS,
            EssayStatus.EDITOR_REVISION_FAILED,
            EssayStatus.AWAITING_GRAMMAR_CHECK,
            EssayStatus.AWAITING_CJ_INCLUSION,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.EDITOR_REVISION_IN_PROGRESS: {
            EssayStatus.EDITOR_REVISION_COMPLETED_SUCCESS,
            EssayStatus.EDITOR_REVISION_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.EDITOR_REVISION_COMPLETED_SUCCESS: {
            EssayStatus.AWAITING_GRAMMAR_CHECK,
            EssayStatus.AWAITING_CJ_INCLUSION,
            EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.EDITOR_REVISION_FAILED: {
            EssayStatus.AWAITING_EDITOR_REVISION,  # Retry
            EssayStatus.AWAITING_GRAMMAR_CHECK,  # Skip
            EssayStatus.AWAITING_CJ_INCLUSION,  # Skip
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AWAITING_GRAMMAR_CHECK: {
            EssayStatus.GRAMMAR_CHECK_IN_PROGRESS,
            EssayStatus.GRAMMAR_CHECK_FAILED,
            EssayStatus.AWAITING_CJ_INCLUSION,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.GRAMMAR_CHECK_IN_PROGRESS: {
            EssayStatus.GRAMMAR_CHECK_COMPLETED_SUCCESS,
            EssayStatus.GRAMMAR_CHECK_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.GRAMMAR_CHECK_COMPLETED_SUCCESS: {
            EssayStatus.AWAITING_CJ_INCLUSION,
            EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.GRAMMAR_CHECK_FAILED: {
            EssayStatus.AWAITING_GRAMMAR_CHECK,  # Retry
            EssayStatus.AWAITING_CJ_INCLUSION,  # Skip
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.AWAITING_CJ_INCLUSION: {
            EssayStatus.CJ_PROCESSING_ACTIVE,
            EssayStatus.CJ_PROCESSING_FAILED,
            EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.CJ_PROCESSING_ACTIVE: {
            EssayStatus.CJ_RANKING_COMPLETED,
            EssayStatus.CJ_PROCESSING_FAILED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.CJ_RANKING_COMPLETED: {
            EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        EssayStatus.CJ_PROCESSING_FAILED: {
            EssayStatus.AWAITING_CJ_INCLUSION,  # Retry
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        },
        # Terminal states (no transitions allowed)
        EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED: set(),
        EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES: set(),
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
            EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        }

    @classmethod
    def is_failure_status(cls, status: EssayStatus) -> bool:
        """Check if a status indicates a failure state."""
        return status.value.endswith("_failed") or status in {
            EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        }

    @classmethod
    def is_processing_status(cls, status: EssayStatus) -> bool:
        """Check if a status indicates active processing."""
        return status.value.endswith("_in_progress") or status == EssayStatus.CJ_PROCESSING_ACTIVE


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
