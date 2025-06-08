"""
Essay state machine workflow tests.

Tests for AI feedback, CJ assessment, NLP processing, and pipeline completion
workflows including success and failure scenarios.
"""

from __future__ import annotations

from services.essay_lifecycle_service.tests.unit.essay_state_machine_utils import (
    CMD_INITIATE_AI_FEEDBACK,
    CMD_INITIATE_CJ_ASSESSMENT,
    CMD_INITIATE_NLP,
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
    EssayStateMachine,
    EssayStatus,
)


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
