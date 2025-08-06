"""
Essay state machine validation and utility method tests.

Tests for invalid transition handling, can_trigger functionality,
get_valid_triggers method, and convenience methods.
"""

from __future__ import annotations

from services.essay_lifecycle_service.tests.unit.essay_state_machine_utils import (
    CMD_INITIATE_AI_FEEDBACK,
    CMD_INITIATE_CJ_ASSESSMENT,
    CMD_INITIATE_SPELLCHECK,
    CMD_MARK_PIPELINE_COMPLETE,
    EVT_AI_FEEDBACK_STARTED,
    EVT_CRITICAL_FAILURE,
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_STARTED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
    EssayStatus,
)


class TestEssayStateMachineInvalidTransitions:
    """Test invalid transition rejection."""

    def test_invalid_triggers_return_false(self) -> None:
        """Test that invalid triggers return False."""
        machine = EssayStateMachine("invalid-test", EssayStatus.READY_FOR_PROCESSING)

        # These should be invalid from READY_FOR_PROCESSING
        invalid_triggers = [
            EVT_SPELLCHECK_SUCCEEDED,  # Haven't started spellcheck yet
            EVT_AI_FEEDBACK_STARTED,  # Can't start AI feedback from initial state
            CMD_INITIATE_CJ_ASSESSMENT,  # Need spellcheck first
            CMD_MARK_PIPELINE_COMPLETE,  # Nothing completed yet
        ]

        for trigger in invalid_triggers:
            success = machine.trigger_event(trigger)
            assert success is False
            # Status should remain unchanged
            assert machine.current_status == EssayStatus.READY_FOR_PROCESSING

    def test_invalid_transition_from_terminal_state(self) -> None:
        """Test that no transitions are possible from terminal states."""
        machine = EssayStateMachine("terminal-test", EssayStatus.ALL_PROCESSING_COMPLETED)

        # All command triggers should fail from completed state
        invalid_triggers = [
            CMD_INITIATE_SPELLCHECK,
            CMD_INITIATE_AI_FEEDBACK,
            CMD_INITIATE_CJ_ASSESSMENT,
            EVT_SPELLCHECK_STARTED,
        ]

        for trigger in invalid_triggers:
            success = machine.trigger_event(trigger)
            assert success is False
            assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED

    def test_nonexistent_trigger(self) -> None:
        """Test handling of non-existent triggers."""
        machine = EssayStateMachine("nonexistent", EssayStatus.READY_FOR_PROCESSING)

        success = machine.trigger_event("INVALID_TRIGGER_FOR_STATE")
        assert success is False
        assert machine.current_status == EssayStatus.READY_FOR_PROCESSING


class TestEssayStateMachineCanTrigger:
    """Test can_trigger functionality."""

    def test_can_trigger_valid_transitions(self) -> None:
        """Test can_trigger returns True for valid transitions."""
        machine = EssayStateMachine("can-trigger-test", EssayStatus.READY_FOR_PROCESSING)

        # Should be able to initiate spellcheck
        assert machine.can_trigger(CMD_INITIATE_SPELLCHECK) is True
        # Should be able to trigger critical failure
        assert machine.can_trigger(EVT_CRITICAL_FAILURE) is True

    def test_can_trigger_invalid_transitions(self) -> None:
        """Test can_trigger returns False for invalid transitions."""
        machine = EssayStateMachine("cannot-trigger", EssayStatus.READY_FOR_PROCESSING)

        # Should not be able to complete spellcheck without starting
        assert machine.can_trigger(EVT_SPELLCHECK_SUCCEEDED) is False
        # Should not be able to start AI feedback without spellcheck
        assert machine.can_trigger(CMD_INITIATE_AI_FEEDBACK) is False

    def test_can_trigger_after_state_change(self) -> None:
        """Test can_trigger behavior changes after state transitions."""
        machine = EssayStateMachine("trigger-change", EssayStatus.READY_FOR_PROCESSING)

        # Initially can initiate spellcheck
        assert machine.can_trigger(CMD_INITIATE_SPELLCHECK) is True
        assert machine.can_trigger(EVT_SPELLCHECK_STARTED) is False

        # After initiating spellcheck
        machine.trigger_event(CMD_INITIATE_SPELLCHECK)
        assert machine.can_trigger(CMD_INITIATE_SPELLCHECK) is False
        assert machine.can_trigger(EVT_SPELLCHECK_STARTED) is True


class TestEssayStateMachineGetValidTriggers:
    """Test get_valid_triggers functionality."""

    def test_get_valid_triggers_initial_state(self) -> None:
        """Test getting valid triggers from initial state."""
        machine = EssayStateMachine("triggers-initial", EssayStatus.READY_FOR_PROCESSING)

        valid_triggers = machine.get_valid_triggers()

        assert isinstance(valid_triggers, list)
        assert CMD_INITIATE_SPELLCHECK in valid_triggers
        assert EVT_CRITICAL_FAILURE in valid_triggers

        # Should not include invalid triggers
        assert EVT_SPELLCHECK_SUCCEEDED not in valid_triggers
        assert CMD_INITIATE_AI_FEEDBACK not in valid_triggers

    def test_get_valid_triggers_spellcheck_awaiting(self) -> None:
        """Test valid triggers from AWAITING_SPELLCHECK state."""
        machine = EssayStateMachine("triggers-awaiting", EssayStatus.AWAITING_SPELLCHECK)

        valid_triggers = machine.get_valid_triggers()

        assert EVT_SPELLCHECK_STARTED in valid_triggers
        assert EVT_SPELLCHECK_SUCCEEDED in valid_triggers  # Direct success path allowed
        assert EVT_SPELLCHECK_FAILED in valid_triggers
        assert EVT_CRITICAL_FAILURE in valid_triggers

        # Should not include inappropriate triggers
        assert CMD_INITIATE_SPELLCHECK not in valid_triggers

    def test_get_valid_triggers_terminal_state(self) -> None:
        """Test valid triggers from terminal state."""
        machine = EssayStateMachine("triggers-terminal", EssayStatus.ALL_PROCESSING_COMPLETED)

        valid_triggers = machine.get_valid_triggers()

        # Terminal state should have no valid triggers except critical failure
        expected_triggers = [EVT_CRITICAL_FAILURE]
        assert set(valid_triggers) == set(expected_triggers)


class TestEssayStateMachineConvenienceMethods:
    """Test convenience methods for common operations."""

    def test_convenience_method_initiate_spellcheck(self) -> None:
        """Test cmd_initiate_spellcheck convenience method."""
        machine = EssayStateMachine("convenience-spell", EssayStatus.READY_FOR_PROCESSING)

        success = machine.cmd_initiate_spellcheck()
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

    def test_convenience_method_initiate_ai_feedback(self) -> None:
        """Test cmd_initiate_ai_feedback convenience method."""
        machine = EssayStateMachine("convenience-ai", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.cmd_initiate_ai_feedback()
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_AI_FEEDBACK

    def test_convenience_method_initiate_cj_assessment(self) -> None:
        """Test cmd_initiate_cj_assessment convenience method."""
        machine = EssayStateMachine("convenience-cj", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.cmd_initiate_cj_assessment()
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_CJ_ASSESSMENT

    def test_convenience_method_mark_complete(self) -> None:
        """Test cmd_mark_pipeline_complete convenience method."""
        machine = EssayStateMachine("convenience-complete", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.cmd_mark_pipeline_complete()
        assert success is True
        assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED
