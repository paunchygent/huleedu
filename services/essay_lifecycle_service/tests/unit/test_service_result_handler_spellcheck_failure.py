"""
Unit tests for DefaultServiceResultHandler spellcheck phase completion failure scenarios.

Tests the thin spellcheck event handler for failure processing cases,
including error code handling and state transition to failure states.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)
from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
)


class TestServiceResultHandlerSpellcheckFailure:
    """Test suite for spellcheck phase completion failure handling."""

    @pytest.fixture
    def mock_essay_repository(self) -> AsyncMock:
        """Mock EssayRepositoryProtocol for testing using protocol-based mocking."""
        return AsyncMock(spec=EssayRepositoryProtocol)

    @pytest.fixture
    def mock_batch_coordinator(self) -> AsyncMock:
        """Mock BatchPhaseCoordinator for testing using protocol-based mocking."""
        return AsyncMock(spec=BatchPhaseCoordinator)

    @pytest.fixture
    def handler(
        self,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> DefaultServiceResultHandler:
        """Create DefaultServiceResultHandler instance for testing."""
        return DefaultServiceResultHandler(
            repository=mock_essay_repository,
            batch_coordinator=mock_batch_coordinator,
            session_factory=mock_session_factory,
        )

    @pytest.fixture
    def mock_essay_state(self) -> MagicMock:
        """Create mock EssayState in AWAITING_SPELLCHECK status."""
        essay_state = MagicMock()
        essay_state.essay_id = "essay-123"
        essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        essay_state.batch_id = "batch-456"
        essay_state.processing_metadata = {
            "current_phase": "spellcheck",
            "commanded_phases": ["spellcheck"],
        }
        return essay_state

    async def test_handle_spellcheck_phase_completed_failure_basic(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test basic spellcheck phase completion failure with error code."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        corrected_text_storage_id = None
        error_code = "SPELL_CHECK_TIMEOUT"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        # Create updated essay state for batch coordinator
        updated_essay_state = MagicMock()
        updated_essay_state.essay_id = essay_id
        updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=error_code,
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True

        # Verify essay state was retrieved
        assert mock_essay_repository.get_essay_state.call_count == 2
        first_call = mock_essay_repository.get_essay_state.call_args_list[0]
        assert first_call.args[0] == essay_id

        # Verify essay status was updated via state machine
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args

        # Check positional arguments - status should be mapped to SPELLCHECK_FAILED
        assert call_args.args[0] == essay_id
        assert call_args.args[1] == EssayStatus.SPELLCHECK_FAILED

        # Check metadata structure
        metadata = call_args.args[2]
        assert "spellcheck_result" in metadata
        assert metadata["spellcheck_result"]["success"] is False
        assert metadata["spellcheck_result"]["status"] == EssayStatus.SPELLCHECK_FAILED.value
        assert metadata["spellcheck_result"]["corrected_text_storage_id"] is None
        assert metadata["spellcheck_result"]["error_code"] == error_code
        assert metadata["current_phase"] == "spellcheck"
        assert metadata["phase_outcome_status"] == EssayStatus.SPELLCHECK_FAILED.value

        # Check no storage reference was added for failure case
        assert call_args.kwargs["storage_reference"] is None
        assert call_args.kwargs["correlation_id"] == test_correlation_id

        # Verify batch completion check
        mock_batch_coordinator.check_batch_completion.assert_called_once_with(
            essay_state=updated_essay_state,
            phase_name=PhaseName.SPELLCHECK,
            correlation_id=test_correlation_id,
            session=ANY,
        )

    async def test_handle_spellcheck_phase_completed_failure_various_error_codes(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test spellcheck failure with various error codes."""
        test_cases = [
            "SPELL_CHECK_TIMEOUT",
            "INVALID_LANGUAGE_DETECTED",
            "CORRUPTED_TEXT_INPUT",
            "SERVICE_UNAVAILABLE",
            "MEMORY_EXHAUSTED",
        ]

        for error_code in test_cases:
            # Reset mocks
            mock_essay_repository.reset_mock()
            mock_batch_coordinator.reset_mock()
            test_correlation_id = uuid4()

            # Setup
            mock_essay_repository.get_essay_state.return_value = mock_essay_state
            updated_essay_state = MagicMock()
            updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
            mock_essay_repository.get_essay_state.side_effect = [
                mock_essay_state,
                updated_essay_state,
            ]

            # Act
            result = await handler.handle_spellcheck_phase_completed(
                essay_id="essay-123",
                batch_id="batch-456",
                status=EssayStatus.SPELLCHECK_FAILED,
                corrected_text_storage_id=None,
                error_code=error_code,
                correlation_id=test_correlation_id,
            )

            # Assert
            assert result is True

            # Verify error code is correctly stored
            call_args = mock_essay_repository.update_essay_status_via_machine.call_args
            metadata = call_args.args[2]
            assert metadata["spellcheck_result"]["error_code"] == error_code

    async def test_handle_spellcheck_phase_completed_failure_no_error_code(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test spellcheck failure with no error code provided."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        corrected_text_storage_id = None
        error_code = None  # No error code provided
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=error_code,
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True

        # Verify metadata contains None for error_code
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        metadata = call_args.args[2]
        assert metadata["spellcheck_result"]["error_code"] is None

    async def test_handle_spellcheck_phase_completed_failure_correlation_propagation(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test that correlation ID is properly propagated in failure cases."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        error_code = "PROCESSING_ERROR"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=None,
            error_code=error_code,
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True

        # Verify correlation ID is passed to repository update
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.kwargs["correlation_id"] == test_correlation_id

        # Verify correlation ID is passed to batch coordinator
        batch_call_args = mock_batch_coordinator.check_batch_completion.call_args
        assert batch_call_args.kwargs["correlation_id"] == test_correlation_id

    async def test_handle_spellcheck_phase_completed_failure_metadata_structure(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test that metadata structure is correct for failed spellcheck completion."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        error_code = "TIMEOUT_EXCEEDED"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=None,
            error_code=error_code,
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True

        # Verify complete metadata structure
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        metadata = call_args.args[2]

        # Check spellcheck_result structure
        spellcheck_result = metadata["spellcheck_result"]
        assert spellcheck_result == {
            "success": False,
            "status": EssayStatus.SPELLCHECK_FAILED.value,
            "corrected_text_storage_id": None,
            "error_code": error_code,
        }

        # Check phase tracking metadata
        assert metadata["current_phase"] == "spellcheck"
        assert metadata["phase_outcome_status"] == EssayStatus.SPELLCHECK_FAILED.value

    async def test_handle_spellcheck_phase_completed_failure_with_idempotency_callback(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test spellcheck failure with idempotency confirmation callback."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        error_code = "SERVICE_ERROR"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Create mock idempotency callback
        mock_confirm_idempotency = AsyncMock()

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=None,
            error_code=error_code,
            correlation_id=test_correlation_id,
            confirm_idempotency=mock_confirm_idempotency,
        )

        # Assert
        assert result is True

        # Verify idempotency callback was called after successful transaction
        mock_confirm_idempotency.assert_called_once()

    async def test_handle_spellcheck_phase_completed_failure_state_machine_transition(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
    ) -> None:
        """Test that state machine transition works correctly for failure cases from different initial states."""
        # Test case 1: From SPELLCHECKING_IN_PROGRESS
        essay_state_in_progress = MagicMock()
        essay_state_in_progress.essay_id = "essay-123"
        essay_state_in_progress.current_status = EssayStatus.SPELLCHECKING_IN_PROGRESS
        essay_state_in_progress.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = essay_state_in_progress

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_essay_repository.get_essay_state.side_effect = [
            essay_state_in_progress,
            updated_essay_state,
        ]

        test_correlation_id = uuid4()

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECK_FAILED,
            corrected_text_storage_id=None,
            error_code="SPELLCHECK_FAILED",
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()

        # Verify the new status is SPELLCHECK_FAILED
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.args[1] == EssayStatus.SPELLCHECK_FAILED

    async def test_handle_spellcheck_phase_completed_failure_retry_eligibility(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
    ) -> None:
        """Test that failure cases maintain proper state for potential retry."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        error_code = "TEMPORARY_SERVICE_FAILURE"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=None,
            error_code=error_code,
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True

        # Verify that the failure state is properly set (allows for potential retry)
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.args[1] == EssayStatus.SPELLCHECK_FAILED

        # Verify error information is preserved for retry decision making
        metadata = call_args.args[2]
        assert metadata["spellcheck_result"]["error_code"] == error_code
        assert metadata["current_phase"] == "spellcheck"
