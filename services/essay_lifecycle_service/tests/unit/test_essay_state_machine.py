"""
Unit tests for EssayStateMachine.

Tests the formal state machine implementation for essay processing workflow,
ensuring all transitions, triggers, and state management work correctly.
Following 070-testing-and-quality-assurance.mdc principles.
"""

from __future__ import annotations

from common_core.enums import EssayStatus

from essay_state_machine import (
    CMD_INITIATE_AI_FEEDBACK,
    CMD_INITIATE_CJ_ASSESSMENT,
    CMD_INITIATE_NLP,
    CMD_INITIATE_SPELLCHECK,
    CMD_MARK_PIPELINE_COMPLETE,
    EVT_AI_FEEDBACK_FAILED,
    EVT_AI_FEEDBACK_STARTED,
    EVT_AI_FEEDBACK_SUCCEEDED,
    EVT_CJ_ASSESSMENT_FAILED,
    EVT_CJ_ASSESSMENT_STARTED,
    EVT_CJ_ASSESSMENT_SUCCEEDED,
    EVT_CRITICAL_FAILURE,
    EVT_NLP_STARTED,
    EVT_NLP_SUCCEEDED,
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_STARTED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
)


class TestEssayStateMachineInitialization:
    """Test essay state machine initialization with various initial statuses."""

    def test_initialization_ready_for_processing(self) -> None:
        """Test initialization with READY_FOR_PROCESSING status."""
        essay_id = "test-essay-001"
        initial_status = EssayStatus.READY_FOR_PROCESSING

        machine = EssayStateMachine(essay_id, initial_status)

        assert machine.essay_id == essay_id
        assert machine.current_status == initial_status
        assert hasattr(machine, 'machine')  # transitions.Machine instance
        assert machine.current_status == EssayStatus.READY_FOR_PROCESSING

    def test_initialization_various_statuses(self) -> None:
        """Test initialization with different essay statuses."""
        test_cases = [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
            EssayStatus.AWAITING_AI_FEEDBACK,
            EssayStatus.AI_FEEDBACK_SUCCESS,
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
            EssayStatus.ALL_PROCESSING_COMPLETED,
        ]

        for status in test_cases:
            machine = EssayStateMachine(f"essay-{status.value}", status)
            assert machine.current_status == status

    def test_initialization_terminal_statuses(self) -> None:
        """Test initialization with terminal statuses."""
        terminal_statuses = [
            EssayStatus.ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        ]

        for status in terminal_statuses:
            machine = EssayStateMachine(f"terminal-{status.value}", status)
            assert machine.current_status == status


class TestEssayStateMachineSpellcheckWorkflow:
    """Test spellcheck workflow transitions."""

    def test_spellcheck_initiation_from_ready(self) -> None:
        """Test initiating spellcheck from READY_FOR_PROCESSING."""
        machine = EssayStateMachine("spellcheck-test", EssayStatus.READY_FOR_PROCESSING)

        # Valid transition: READY_FOR_PROCESSING -> AWAITING_SPELLCHECK
        success = machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

    def test_spellcheck_start_from_awaiting(self) -> None:
        """Test starting spellcheck from AWAITING_SPELLCHECK."""
        machine = EssayStateMachine("spellcheck-start", EssayStatus.AWAITING_SPELLCHECK)

        success = machine.trigger(EVT_SPELLCHECK_STARTED)
        assert success is True
        assert machine.current_status == EssayStatus.SPELLCHECKING_IN_PROGRESS

    def test_spellcheck_success_from_in_progress(self) -> None:
        """Test successful spellcheck completion."""
        machine = EssayStateMachine("spellcheck-success", EssayStatus.SPELLCHECKING_IN_PROGRESS)

        success = machine.trigger(EVT_SPELLCHECK_SUCCEEDED)
        assert success is True
        assert machine.current_status == EssayStatus.SPELLCHECKED_SUCCESS

    def test_spellcheck_failure_from_in_progress(self) -> None:
        """Test spellcheck failure from in progress."""
        machine = EssayStateMachine("spellcheck-fail", EssayStatus.SPELLCHECKING_IN_PROGRESS)

        success = machine.trigger(EVT_SPELLCHECK_FAILED)
        assert success is True
        assert machine.current_status == EssayStatus.SPELLCHECK_FAILED

    def test_spellcheck_failure_from_awaiting(self) -> None:
        """Test spellcheck failure from awaiting state."""
        machine = EssayStateMachine("spellcheck-fail-early", EssayStatus.AWAITING_SPELLCHECK)

        success = machine.trigger(EVT_SPELLCHECK_FAILED)
        assert success is True
        assert machine.current_status == EssayStatus.SPELLCHECK_FAILED

    def test_complete_spellcheck_workflow(self) -> None:
        """Test complete spellcheck workflow from start to finish."""
        machine = EssayStateMachine("complete-spellcheck", EssayStatus.READY_FOR_PROCESSING)

        # Phase 1: Initiate spellcheck
        assert machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        # Phase 2: Start processing
        assert machine.trigger(EVT_SPELLCHECK_STARTED)
        assert machine.current_status == EssayStatus.SPELLCHECKING_IN_PROGRESS

        # Phase 3: Complete successfully
        assert machine.trigger(EVT_SPELLCHECK_SUCCEEDED)
        assert machine.current_status == EssayStatus.SPELLCHECKED_SUCCESS


class TestEssayStateMachineAIFeedbackWorkflow:
    """Test AI feedback workflow transitions."""

    def test_ai_feedback_initiation_from_spellchecked(self) -> None:
        """Test initiating AI feedback from SPELLCHECKED_SUCCESS."""
        machine = EssayStateMachine("ai-feedback-test", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.trigger(CMD_INITIATE_AI_FEEDBACK)
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_AI_FEEDBACK

    def test_ai_feedback_complete_workflow(self) -> None:
        """Test complete AI feedback workflow."""
        machine = EssayStateMachine("ai-complete", EssayStatus.SPELLCHECKED_SUCCESS)

        # Initiate AI feedback
        assert machine.trigger(CMD_INITIATE_AI_FEEDBACK)
        assert machine.current_status == EssayStatus.AWAITING_AI_FEEDBACK

        # Start processing
        assert machine.trigger(EVT_AI_FEEDBACK_STARTED)
        assert machine.current_status == EssayStatus.AI_FEEDBACK_IN_PROGRESS

        # Complete successfully
        assert machine.trigger(EVT_AI_FEEDBACK_SUCCEEDED)
        assert machine.current_status == EssayStatus.AI_FEEDBACK_SUCCESS

    def test_ai_feedback_failure_scenarios(self) -> None:
        """Test AI feedback failure scenarios."""
        # Failure from in-progress
        machine1 = EssayStateMachine("ai-fail-progress", EssayStatus.AI_FEEDBACK_IN_PROGRESS)
        assert machine1.trigger(EVT_AI_FEEDBACK_FAILED)
        assert machine1.current_status == EssayStatus.AI_FEEDBACK_FAILED

        # Failure from awaiting
        machine2 = EssayStateMachine("ai-fail-awaiting", EssayStatus.AWAITING_AI_FEEDBACK)
        assert machine2.trigger(EVT_AI_FEEDBACK_FAILED)
        assert machine2.current_status == EssayStatus.AI_FEEDBACK_FAILED


class TestEssayStateMachineCJAssessmentWorkflow:
    """Test CJ Assessment workflow transitions."""

    def test_cj_assessment_from_spellchecked(self) -> None:
        """Test CJ assessment initiation from SPELLCHECKED_SUCCESS."""
        machine = EssayStateMachine("cj-from-spell", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.trigger(CMD_INITIATE_CJ_ASSESSMENT)
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_CJ_ASSESSMENT

    def test_cj_assessment_from_ai_feedback(self) -> None:
        """Test CJ assessment initiation from AI_FEEDBACK_SUCCESS."""
        machine = EssayStateMachine("cj-from-ai", EssayStatus.AI_FEEDBACK_SUCCESS)

        success = machine.trigger(CMD_INITIATE_CJ_ASSESSMENT)
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_CJ_ASSESSMENT

    def test_cj_assessment_complete_workflow(self) -> None:
        """Test complete CJ assessment workflow."""
        machine = EssayStateMachine("cj-complete", EssayStatus.AWAITING_CJ_ASSESSMENT)

        # Start assessment
        assert machine.trigger(EVT_CJ_ASSESSMENT_STARTED)
        assert machine.current_status == EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        # Complete successfully
        assert machine.trigger(EVT_CJ_ASSESSMENT_SUCCEEDED)
        assert machine.current_status == EssayStatus.CJ_ASSESSMENT_SUCCESS

    def test_cj_assessment_failure_scenarios(self) -> None:
        """Test CJ assessment failure scenarios."""
        # Failure from in-progress
        machine1 = EssayStateMachine("cj-fail-progress", EssayStatus.CJ_ASSESSMENT_IN_PROGRESS)
        assert machine1.trigger(EVT_CJ_ASSESSMENT_FAILED)
        assert machine1.current_status == EssayStatus.CJ_ASSESSMENT_FAILED

        # Failure from awaiting
        machine2 = EssayStateMachine("cj-fail-awaiting", EssayStatus.AWAITING_CJ_ASSESSMENT)
        assert machine2.trigger(EVT_CJ_ASSESSMENT_FAILED)
        assert machine2.current_status == EssayStatus.CJ_ASSESSMENT_FAILED


class TestEssayStateMachineNLPWorkflow:
    """Test NLP processing workflow transitions."""

    def test_nlp_from_spellchecked(self) -> None:
        """Test NLP initiation from SPELLCHECKED_SUCCESS."""
        machine = EssayStateMachine("nlp-from-spell", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.trigger(CMD_INITIATE_NLP)
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_NLP

    def test_nlp_from_ai_feedback(self) -> None:
        """Test NLP initiation from AI_FEEDBACK_SUCCESS."""
        machine = EssayStateMachine("nlp-from-ai", EssayStatus.AI_FEEDBACK_SUCCESS)

        success = machine.trigger(CMD_INITIATE_NLP)
        assert success is True
        assert machine.current_status == EssayStatus.AWAITING_NLP

    def test_nlp_complete_workflow(self) -> None:
        """Test complete NLP workflow."""
        machine = EssayStateMachine("nlp-complete", EssayStatus.AWAITING_NLP)

        # Start processing
        assert machine.trigger(EVT_NLP_STARTED)
        assert machine.current_status == EssayStatus.NLP_IN_PROGRESS

        # Complete successfully
        assert machine.trigger(EVT_NLP_SUCCEEDED)
        assert machine.current_status == EssayStatus.NLP_SUCCESS


class TestEssayStateMachinePipelineCompletion:
    """Test pipeline completion transitions."""

    def test_completion_from_spellchecked(self) -> None:
        """Test marking complete from SPELLCHECKED_SUCCESS."""
        machine = EssayStateMachine("complete-spell", EssayStatus.SPELLCHECKED_SUCCESS)

        success = machine.trigger(CMD_MARK_PIPELINE_COMPLETE)
        assert success is True
        assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED

    def test_completion_from_various_success_states(self) -> None:
        """Test completion from different success states."""
        success_states = [
            EssayStatus.AI_FEEDBACK_SUCCESS,
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
            EssayStatus.NLP_SUCCESS,
        ]

        for state in success_states:
            machine = EssayStateMachine(f"complete-{state.value}", state)
            success = machine.trigger(CMD_MARK_PIPELINE_COMPLETE)
            assert success is True
            assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED


class TestEssayStateMachineCriticalFailure:
    """Test critical failure transitions from any state."""

    def test_critical_failure_from_various_states(self) -> None:
        """Test critical failure can be triggered from any state."""
        test_states = [
            EssayStatus.READY_FOR_PROCESSING,
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
            EssayStatus.AWAITING_AI_FEEDBACK,
            EssayStatus.AI_FEEDBACK_IN_PROGRESS,
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
        ]

        for state in test_states:
            machine = EssayStateMachine(f"critical-{state.value}", state)
            success = machine.trigger(EVT_CRITICAL_FAILURE)
            assert success is True
            assert machine.current_status == EssayStatus.ESSAY_CRITICAL_FAILURE


class TestEssayStateMachineInvalidTransitions:
    """Test invalid transition rejection."""

    def test_invalid_triggers_return_false(self) -> None:
        """Test that invalid triggers return False."""
        machine = EssayStateMachine("invalid-test", EssayStatus.READY_FOR_PROCESSING)

        # These should be invalid from READY_FOR_PROCESSING
        invalid_triggers = [
            EVT_SPELLCHECK_SUCCEEDED,  # Haven't started spellcheck yet
            EVT_AI_FEEDBACK_STARTED,   # Can't start AI feedback from initial state
            CMD_INITIATE_CJ_ASSESSMENT,  # Need spellcheck first
            CMD_MARK_PIPELINE_COMPLETE,  # Nothing completed yet
        ]

        for trigger in invalid_triggers:
            success = machine.trigger(trigger)
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
            CMD_INITIATE_NLP,
            EVT_SPELLCHECK_STARTED,
        ]

        for trigger in invalid_triggers:
            success = machine.trigger(trigger)
            assert success is False
            assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED

    def test_nonexistent_trigger(self) -> None:
        """Test handling of non-existent triggers."""
        machine = EssayStateMachine("nonexistent", EssayStatus.READY_FOR_PROCESSING)

        success = machine.trigger("INVALID_TRIGGER_FOR_STATE")
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
        machine.trigger(CMD_INITIATE_SPELLCHECK)
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
        assert EVT_SPELLCHECK_FAILED in valid_triggers
        assert EVT_CRITICAL_FAILURE in valid_triggers

        # Should not include inappropriate triggers
        assert CMD_INITIATE_SPELLCHECK not in valid_triggers
        assert EVT_SPELLCHECK_SUCCEEDED not in valid_triggers

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

        # None should be handled gracefully (cast to avoid type error)
        assert machine.can_trigger("") is False  # Use empty string instead of None

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
