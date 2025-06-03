"""
Core business logic for the Essay Lifecycle Service.

This module contains the essential business logic for essay state management,
state transition validation, and processing coordination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from common_core.enums import EssayStatus
from common_core.metadata_models import EntityReference

if TYPE_CHECKING:
    from essay_state_machine import EssayStateMachine


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

    def validate_transition(self, machine_or_status: EssayStateMachine | EssayStatus, trigger_or_target: str | EssayStatus) -> bool:
        """
        Validate if state transition is allowed.

        Can be called in two ways:
        1. validate_transition(current_status: EssayStatus, target_status: EssayStatus) -> bool
        2. validate_transition(machine: EssayStateMachine, trigger: str) -> bool

        Returns:
            True if transition is valid, False otherwise
        """
        # Check if first argument is a state machine
        if hasattr(machine_or_status, 'can_trigger'):
            # State machine pattern: validate_transition(machine, trigger)
            result = machine_or_status.can_trigger(trigger_or_target)  # type: ignore[arg-type]
            return bool(result)
        else:
            # Status pattern: validate_transition(current_status, target_status)
            current_status = machine_or_status  # type: ignore[assignment]
            target_status = trigger_or_target  # type: ignore[assignment]
            return target_status in self._VALID_TRANSITIONS.get(current_status, set())

    def validate_transition_with_machine(self, machine: EssayStateMachine, trigger: str) -> bool:
        """
        Validate if trigger can be fired on state machine.

        Args:
            machine: EssayStateMachine instance
            trigger: Name of the trigger to validate

        Returns:
            True if trigger is valid from current state
        """
        return bool(machine.can_trigger(trigger))

    def get_possible_triggers(self, machine: EssayStateMachine) -> list[str]:
        """
        Get list of possible triggers for state machine.

        Args:
            machine: EssayStateMachine instance

        Returns:
            List of trigger names that can be fired from current state
        """
        # Cast to list[str] since we know get_valid_triggers returns this type
        triggers = machine.get_valid_triggers()
        return list(triggers) if triggers else []

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
