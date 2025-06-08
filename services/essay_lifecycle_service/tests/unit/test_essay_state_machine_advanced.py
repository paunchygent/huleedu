"""
Essay state machine advanced scenario tests.

Tests for string representation, complex multi-phase workflows,
and edge cases for the essay state machine.
"""

from __future__ import annotations

from services.essay_lifecycle_service.tests.unit.essay_state_machine_utils import (
    CMD_INITIATE_AI_FEEDBACK,
    CMD_INITIATE_SPELLCHECK,
    CMD_MARK_PIPELINE_COMPLETE,
    EVT_AI_FEEDBACK_STARTED,
    EVT_AI_FEEDBACK_SUCCEEDED,
    EVT_CJ_ASSESSMENT_STARTED,
    EVT_CJ_ASSESSMENT_SUCCEEDED,
    EVT_SPELLCHECK_STARTED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
    EssayStatus,
)


class TestEssayStateMachineStringRepresentation:
    """Test string representation methods."""

    def test_str_representation(self) -> None:
        """Test __str__ method."""
        machine = EssayStateMachine("str-test", EssayStatus.READY_FOR_PROCESSING)

        str_repr = str(machine)
        assert "EssayStateMachine" in str_repr
        assert "str-test" in str_repr
        assert "ready_for_processing" in str_repr

    def test_repr_representation(self) -> None:
        """Test __repr__ method."""
        machine = EssayStateMachine("repr-test", EssayStatus.AWAITING_SPELLCHECK)

        repr_str = repr(machine)
        assert "EssayStateMachine" in repr_str
        assert "repr-test" in repr_str
        assert "AWAITING_SPELLCHECK" in repr_str
        assert "valid_triggers" in repr_str


class TestEssayStateMachineMultiPhaseWorkflows:
    """Test complex multi-phase pipeline workflows."""

    def test_spellcheck_to_ai_feedback_to_completion(self) -> None:
        """Test workflow: Spellcheck -> AI Feedback -> Complete."""
        machine = EssayStateMachine("multi-phase-1", EssayStatus.READY_FOR_PROCESSING)

        # Phase 1: Spellcheck
        assert machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        assert machine.trigger(EVT_SPELLCHECK_STARTED)
        assert machine.current_status == EssayStatus.SPELLCHECKING_IN_PROGRESS

        assert machine.trigger(EVT_SPELLCHECK_SUCCEEDED)
        assert machine.current_status == EssayStatus.SPELLCHECKED_SUCCESS

        # Phase 2: AI Feedback
        assert machine.trigger(CMD_INITIATE_AI_FEEDBACK)
        assert machine.current_status == EssayStatus.AWAITING_AI_FEEDBACK

        assert machine.trigger(EVT_AI_FEEDBACK_STARTED)
        assert machine.current_status == EssayStatus.AI_FEEDBACK_IN_PROGRESS

        assert machine.trigger(EVT_AI_FEEDBACK_SUCCEEDED)
        assert machine.current_status == EssayStatus.AI_FEEDBACK_SUCCESS

        # Phase 3: Complete
        assert machine.trigger(CMD_MARK_PIPELINE_COMPLETE)
        assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED

    def test_spellcheck_to_cj_assessment_to_completion(self) -> None:
        """Test workflow: Spellcheck -> CJ Assessment -> Complete."""
        machine = EssayStateMachine("multi-phase-2", EssayStatus.READY_FOR_PROCESSING)

        # Phase 1: Spellcheck (abbreviated)
        assert machine.cmd_initiate_spellcheck()
        assert machine.trigger(EVT_SPELLCHECK_STARTED)
        assert machine.trigger(EVT_SPELLCHECK_SUCCEEDED)
        assert machine.current_status == EssayStatus.SPELLCHECKED_SUCCESS

        # Phase 2: CJ Assessment
        assert machine.cmd_initiate_cj_assessment()
        assert machine.current_status == EssayStatus.AWAITING_CJ_ASSESSMENT

        assert machine.trigger(EVT_CJ_ASSESSMENT_STARTED)
        assert machine.current_status == EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        assert machine.trigger(EVT_CJ_ASSESSMENT_SUCCEEDED)
        assert machine.current_status == EssayStatus.CJ_ASSESSMENT_SUCCESS

        # Phase 3: Complete
        assert machine.cmd_mark_pipeline_complete()
        assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED

    def test_full_pipeline_workflow(self) -> None:
        """Test full pipeline: Spellcheck -> AI Feedback -> CJ Assessment -> Complete."""
        machine = EssayStateMachine("full-pipeline", EssayStatus.READY_FOR_PROCESSING)

        # Spellcheck phase
        assert machine.cmd_initiate_spellcheck()
        assert machine.trigger(EVT_SPELLCHECK_STARTED)
        assert machine.trigger(EVT_SPELLCHECK_SUCCEEDED)

        # AI Feedback phase
        assert machine.cmd_initiate_ai_feedback()
        assert machine.trigger(EVT_AI_FEEDBACK_STARTED)
        assert machine.trigger(EVT_AI_FEEDBACK_SUCCEEDED)

        # CJ Assessment phase
        assert machine.cmd_initiate_cj_assessment()
        assert machine.trigger(EVT_CJ_ASSESSMENT_STARTED)
        assert machine.trigger(EVT_CJ_ASSESSMENT_SUCCEEDED)

        # Completion
        assert machine.cmd_mark_pipeline_complete()
        assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED


class TestEssayStateMachineEdgeCases:
    """Test edge cases and error scenarios."""

    def test_multiple_same_triggers(self) -> None:
        """Test triggering the same transition multiple times."""
        machine = EssayStateMachine("multiple-triggers", EssayStatus.READY_FOR_PROCESSING)

        # First trigger should succeed
        assert machine.trigger(CMD_INITIATE_SPELLCHECK) is True
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        # Second trigger should fail (already transitioned)
        assert machine.trigger(CMD_INITIATE_SPELLCHECK) is False
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

    def test_trigger_name_validation(self) -> None:
        """Test handling of various trigger name formats."""
        machine = EssayStateMachine("trigger-validation", EssayStatus.READY_FOR_PROCESSING)

        # Valid trigger should work
        assert machine.can_trigger(CMD_INITIATE_SPELLCHECK) is True

        # Empty string should return False
        assert machine.can_trigger("") is False

        # Invalid string should return False
        assert machine.can_trigger("INVALID_TRIGGER") is False

    def test_current_status_consistency(self) -> None:
        """Test that current_status property remains consistent."""
        machine = EssayStateMachine("status-consistency", EssayStatus.READY_FOR_PROCESSING)

        # Initial status
        assert machine.current_status == EssayStatus.READY_FOR_PROCESSING

        # After valid transition
        machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        # After invalid transition attempt
        machine.trigger("INVALID_TRIGGER")
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK  # Should remain unchanged
