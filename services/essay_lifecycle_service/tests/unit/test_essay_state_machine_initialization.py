"""
Essay state machine initialization and spellcheck workflow tests.

Tests essay state machine initialization with various statuses and complete
spellcheck workflow transitions from start to completion.
"""

from __future__ import annotations

from services.essay_lifecycle_service.tests.unit.essay_state_machine_utils import (
    CMD_INITIATE_SPELLCHECK,
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_STARTED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
    EssayStatus,
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
