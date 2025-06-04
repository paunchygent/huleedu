"""
Unit tests for DefaultServiceResultHandler implementation.

Tests the service result handler's integration with EssayStateMachine
and batch phase coordination for Task 2.2.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.enums import EssayStatus

from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)


class TestDefaultServiceResultHandler:
    """Test suite for DefaultServiceResultHandler."""

    @pytest.fixture
    def mock_state_store(self) -> AsyncMock:
        """Mock EssayStateStore for testing."""
        return AsyncMock()

    @pytest.fixture
    def mock_batch_coordinator(self) -> AsyncMock:
        """Mock BatchPhaseCoordinator for testing."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_state_store: AsyncMock, mock_batch_coordinator: AsyncMock) -> DefaultServiceResultHandler:
        """Create DefaultServiceResultHandler instance for testing."""
        return DefaultServiceResultHandler(
            state_store=mock_state_store,
            batch_coordinator=mock_batch_coordinator
        )

    @pytest.fixture
    def mock_essay_state(self) -> MagicMock:
        """Create mock EssayState for testing."""
        essay_state = MagicMock()
        essay_state.essay_id = "test-essay-1"
        essay_state.current_status = EssayStatus.SPELLCHECKING_IN_PROGRESS
        essay_state.batch_id = "test-batch-1"
        essay_state.processing_metadata = {
            "current_phase": "spellcheck",
            "commanded_phases": ["spellcheck"]
        }
        return essay_state

    @pytest.fixture
    def mock_spellcheck_result_success(self) -> MagicMock:
        """Create successful spellcheck result data."""
        result = MagicMock()
        entity_ref = MagicMock()
        entity_ref.entity_id = "test-essay-1"
        result.entity_ref = entity_ref
        result.status = EssayStatus.SPELLCHECKED_SUCCESS
        result.original_text_storage_id = "original-123"
        result.storage_metadata = {"corrected_text_id": "corrected-456"}
        result.corrections_made = 5
        result.system_metadata = None
        return result

    @pytest.fixture
    def mock_spellcheck_result_failure(self) -> MagicMock:
        """Create failed spellcheck result data."""
        result = MagicMock()
        entity_ref = MagicMock()
        entity_ref.entity_id = "test-essay-1"
        result.entity_ref = entity_ref
        result.status = EssayStatus.SPELLCHECK_FAILED
        result.original_text_storage_id = "original-123"
        result.storage_metadata = {}
        result.corrections_made = 0
        system_metadata = MagicMock()
        system_metadata.error_info = {"error": "Spell checker timeout"}
        result.system_metadata = system_metadata
        return result

    async def test_handle_spellcheck_result_success(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        mock_spellcheck_result_success: MagicMock
    ) -> None:
        """Test successful spellcheck result handling."""
        # Setup
        correlation_id = uuid4()
        mock_state_store.get_essay_state.return_value = mock_essay_state
        mock_state_store.update_essay_status_via_machine.return_value = None

        # Create updated essay state for batch coordinator
        updated_essay_state = MagicMock()
        updated_essay_state.essay_id = "test-essay-1"
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_state_store.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Execute
        result = await handler.handle_spellcheck_result(mock_spellcheck_result_success, correlation_id)

        # Verify
        assert result is True
        mock_state_store.get_essay_state.assert_called_with("test-essay-1")
        mock_state_store.update_essay_status_via_machine.assert_called_once()

        # Check the call arguments
        call_args = mock_state_store.update_essay_status_via_machine.call_args
        assert call_args[1]["essay_id"] == "test-essay-1"
        assert call_args[1]["new_status"] == EssayStatus.SPELLCHECKED_SUCCESS
        assert "spellcheck_result" in call_args[1]["metadata"]
        assert call_args[1]["metadata"]["current_phase"] == "spellcheck"

        mock_batch_coordinator.check_batch_completion.assert_called_once_with(
            essay_state=updated_essay_state,
            phase_name="spellcheck",
            correlation_id=correlation_id
        )

    async def test_handle_spellcheck_result_failure(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        mock_spellcheck_result_failure: MagicMock
    ) -> None:
        """Test failed spellcheck result handling."""
        # Setup
        correlation_id = uuid4()
        mock_state_store.get_essay_state.return_value = mock_essay_state
        mock_state_store.update_essay_status_via_machine.return_value = None

        # Create updated essay state for batch coordinator
        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_state_store.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Execute
        result = await handler.handle_spellcheck_result(mock_spellcheck_result_failure, correlation_id)

        # Verify
        assert result is True
        mock_state_store.update_essay_status_via_machine.assert_called_once()

        # Check metadata includes error info
        call_args = mock_state_store.update_essay_status_via_machine.call_args
        assert call_args[1]["new_status"] == EssayStatus.SPELLCHECK_FAILED
        assert call_args[1]["metadata"]["spellcheck_result"]["error_info"] == {"error": "Spell checker timeout"}

        mock_batch_coordinator.check_batch_completion.assert_called_once()

    async def test_handle_spellcheck_result_essay_not_found(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_spellcheck_result_success: MagicMock
    ) -> None:
        """Test spellcheck result when essay not found."""
        # Setup
        correlation_id = uuid4()
        mock_state_store.get_essay_state.return_value = None

        # Execute
        result = await handler.handle_spellcheck_result(mock_spellcheck_result_success, correlation_id)

        # Verify
        assert result is False
        mock_state_store.get_essay_state.assert_called_once_with("test-essay-1")
        mock_state_store.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_result_state_machine_trigger_fails(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        mock_spellcheck_result_success: MagicMock
    ) -> None:
        """Test spellcheck result when state machine trigger fails."""
        # Setup - essay in wrong state for transition
        correlation_id = uuid4()
        mock_essay_state.current_status = EssayStatus.READY_FOR_PROCESSING  # Wrong state
        mock_state_store.get_essay_state.return_value = mock_essay_state

        # Execute
        result = await handler.handle_spellcheck_result(mock_spellcheck_result_success, correlation_id)

        # Verify
        assert result is False
        mock_state_store.get_essay_state.assert_called_once()
        mock_state_store.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    @pytest.fixture
    def mock_cj_assessment_completed(self) -> MagicMock:
        """Create CJ assessment completed result data."""
        result = MagicMock()
        entity_ref = MagicMock()
        entity_ref.entity_id = "test-batch-1"
        result.entity_ref = entity_ref
        result.cj_assessment_job_id = "job-123"
        result.rankings = [
            {"els_essay_id": "essay-1", "rank": 1, "score": 0.85},
            {"els_essay_id": "essay-2", "rank": 2, "score": 0.75}
        ]
        return result

    @pytest.fixture
    def mock_cj_assessment_failed(self) -> MagicMock:
        """Create CJ assessment failed result data."""
        result = MagicMock()
        entity_ref = MagicMock()
        entity_ref.entity_id = "test-batch-1"
        result.entity_ref = entity_ref
        result.cj_assessment_job_id = "job-123"
        result.error_message = "CJ service unavailable"
        result.affected_essay_ids = ["essay-1", "essay-2"]
        return result

    async def test_handle_cj_assessment_completed_success(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_cj_assessment_completed: MagicMock
    ) -> None:
        """Test successful CJ assessment completion handling."""
        # Setup
        correlation_id = uuid4()

        # Mock essay states
        essay1_state = MagicMock()
        essay1_state.essay_id = "essay-1"
        essay1_state.current_status = EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        essay2_state = MagicMock()
        essay2_state.essay_id = "essay-2"
        essay2_state.current_status = EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        # The implementation calls get_essay_state for each ranking (2 essays)
        # then calls get_essay_state once more for the first essay to get batch representative state
        mock_state_store.get_essay_state.side_effect = [
            essay1_state,  # First essay get
            essay2_state,  # Second essay get
            essay1_state   # Batch representative state get
        ]

        # Execute
        result = await handler.handle_cj_assessment_completed(mock_cj_assessment_completed, correlation_id)

        # Verify
        assert result is True
        assert mock_state_store.get_essay_state.call_count == 3  # 2 essays + 1 batch representative
        assert mock_state_store.update_essay_status_via_machine.call_count == 2
        assert mock_batch_coordinator.check_batch_completion.call_count == 1

    async def test_handle_cj_assessment_completed_essay_not_found(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_cj_assessment_completed: MagicMock
    ) -> None:
        """Test CJ assessment completion when essay not found."""
        # Setup
        correlation_id = uuid4()
        mock_state_store.get_essay_state.return_value = None

        # Execute
        result = await handler.handle_cj_assessment_completed(mock_cj_assessment_completed, correlation_id)

        # Verify - should still return True but skip missing essays
        assert result is True
        mock_state_store.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_cj_assessment_failed_success(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_cj_assessment_failed: MagicMock
    ) -> None:
        """Test CJ assessment failure handling."""
        # Setup
        correlation_id = uuid4()

        # Mock essay states - NOTE: implementation only processes essays in AWAITING_CJ_ASSESSMENT status
        essay1_state = MagicMock()
        essay1_state.essay_id = "essay-1"
        essay1_state.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT

        essay2_state = MagicMock()
        essay2_state.essay_id = "essay-2"
        essay2_state.current_status = EssayStatus.AWAITING_CJ_ASSESSMENT

        # Mock list_essays_by_batch call - implementation gets all essays then filters by status
        mock_state_store.list_essays_by_batch.return_value = [essay1_state, essay2_state]

        # Execute
        result = await handler.handle_cj_assessment_failed(mock_cj_assessment_failed, correlation_id)

        # Verify
        assert result is True
        mock_state_store.list_essays_by_batch.assert_called_once_with("test-batch-1")
        assert mock_state_store.update_essay_status_via_machine.call_count == 2

        # Check that failures were recorded properly
        for call in mock_state_store.update_essay_status_via_machine.call_args_list:
            assert call[1]["new_status"] == EssayStatus.CJ_ASSESSMENT_FAILED
            assert "cj_assessment_result" in call[1]["metadata"]
            assert call[1]["metadata"]["cj_assessment_result"]["success"] is False
            assert call[1]["metadata"]["cj_assessment_result"]["batch_failure"] is True

    async def test_handle_cj_assessment_failed_essay_not_found(
        self,
        handler: DefaultServiceResultHandler,
        mock_state_store: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_cj_assessment_failed: MagicMock
    ) -> None:
        """Test CJ assessment failure when essay not found."""
        # Setup
        correlation_id = uuid4()
        mock_state_store.get_essay_state.return_value = None

        # Execute
        result = await handler.handle_cj_assessment_failed(mock_cj_assessment_failed, correlation_id)

        # Verify - should still return True but skip missing essays
        assert result is True
        mock_state_store.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()
