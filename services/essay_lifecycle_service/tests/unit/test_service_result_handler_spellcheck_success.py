"""
Unit tests for DefaultServiceResultHandler spellcheck phase completion success scenarios.

Tests the thin spellcheck event handler for successful processing cases.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)
from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
)


class TestServiceResultHandlerSpellcheckSuccess:
    """Test suite for successful spellcheck phase completion handling."""

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

    @pytest.fixture
    def correlation_id(self) -> str:
        """Generate correlation ID for test."""
        return str(uuid4())

    async def test_handle_spellcheck_phase_completed_success_basic(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test successful spellcheck phase completion with corrected text storage ID."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-corrected-789"
        error_code = None

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        # Create updated essay state for batch coordinator
        updated_essay_state = MagicMock()
        updated_essay_state.essay_id = essay_id
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Create correlation ID for this test
        test_correlation_id = uuid4()

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

        # Check positional arguments
        assert call_args.args[0] == essay_id
        assert call_args.args[1] == EssayStatus.SPELLCHECKED_SUCCESS

        # Check metadata structure
        metadata = call_args.args[2]
        assert "spellcheck_result" in metadata
        assert metadata["spellcheck_result"]["success"] is True
        assert metadata["spellcheck_result"]["status"] == EssayStatus.SPELLCHECKED_SUCCESS.value
        assert (
            metadata["spellcheck_result"]["corrected_text_storage_id"] == corrected_text_storage_id
        )
        assert metadata["spellcheck_result"]["error_code"] is None
        assert metadata["current_phase"] == "spellcheck"
        assert metadata["phase_outcome_status"] == EssayStatus.SPELLCHECKED_SUCCESS.value

        # Check storage reference was added
        assert call_args.kwargs["storage_reference"] == (
            ContentType.CORRECTED_TEXT,
            corrected_text_storage_id,
        )
        assert call_args.kwargs["correlation_id"] == test_correlation_id

        # Verify batch completion check
        mock_batch_coordinator.check_batch_completion.assert_called_once_with(
            essay_state=updated_essay_state,
            phase_name=PhaseName.SPELLCHECK,
            correlation_id=test_correlation_id,
            session=ANY,
        )

    async def test_handle_spellcheck_phase_completed_success_no_corrected_text(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test successful spellcheck with no corrected text storage ID (no corrections needed)."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = None  # No corrections needed
        error_code = None

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.essay_id = essay_id
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Create correlation ID for this test
        test_correlation_id = uuid4()

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

        # Verify no storage reference was added when corrected_text_storage_id is None
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.kwargs["storage_reference"] is None

        # Verify metadata still contains None for corrected_text_storage_id
        metadata = call_args.args[2]
        assert metadata["spellcheck_result"]["corrected_text_storage_id"] is None

    async def test_handle_spellcheck_phase_completed_success_correlation_propagation(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test that correlation ID is properly propagated through all operations."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-corrected-789"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.essay_id = essay_id
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
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

    async def test_handle_spellcheck_phase_completed_success_metadata_structure(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test that metadata structure is correct for successful spellcheck completion."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-corrected-789"
        error_code = None

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Create correlation ID for this test
        test_correlation_id = uuid4()

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

        # Verify complete metadata structure
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        metadata = call_args.args[2]

        # Check spellcheck_result structure
        spellcheck_result = metadata["spellcheck_result"]
        assert spellcheck_result == {
            "success": True,
            "status": EssayStatus.SPELLCHECKED_SUCCESS.value,
            "corrected_text_storage_id": corrected_text_storage_id,
            "error_code": None,
        }

        # Check phase tracking metadata
        assert metadata["current_phase"] == "spellcheck"
        assert metadata["phase_outcome_status"] == EssayStatus.SPELLCHECKED_SUCCESS.value

    async def test_handle_spellcheck_phase_completed_success_with_idempotency_callback(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test successful spellcheck completion with idempotency confirmation callback."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-corrected-789"
        error_code = None

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Create mock idempotency callback
        mock_confirm_idempotency = AsyncMock()

        # Create correlation ID for this test
        test_correlation_id = uuid4()

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=error_code,
            correlation_id=test_correlation_id,
            confirm_idempotency=mock_confirm_idempotency,
        )

        # Assert
        assert result is True

        # Verify idempotency callback was called after successful transaction
        mock_confirm_idempotency.assert_called_once()

    async def test_handle_spellcheck_phase_completed_success_state_machine_transition(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test that state machine transition works correctly for different initial states."""
        # Arrange - essay in SPELLCHECKING_IN_PROGRESS state
        essay_state_in_progress = MagicMock()
        essay_state_in_progress.essay_id = "essay-123"
        essay_state_in_progress.current_status = EssayStatus.SPELLCHECKING_IN_PROGRESS
        essay_state_in_progress.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = essay_state_in_progress

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [
            essay_state_in_progress,
            updated_essay_state,
        ]

        # Create correlation ID for this test
        test_correlation_id = uuid4()

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=test_correlation_id,
        )

        # Assert
        assert result is True
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()

        # Verify the new status is SPELLCHECKED_SUCCESS
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.args[1] == EssayStatus.SPELLCHECKED_SUCCESS
