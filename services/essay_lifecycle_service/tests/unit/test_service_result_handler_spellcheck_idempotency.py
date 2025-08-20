"""
Unit tests for DefaultServiceResultHandler spellcheck phase completion idempotency scenarios.

Tests the thin spellcheck event handler for duplicate event processing,
Redis-based deduplication, and concurrent event handling scenarios.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)
from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
)


class TestServiceResultHandlerSpellcheckIdempotency:
    """Test suite for spellcheck phase completion idempotency handling."""

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
    def mock_essay_state_awaiting(self) -> MagicMock:
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
    def mock_essay_state_completed(self) -> MagicMock:
        """Create mock EssayState in SPELLCHECKED_SUCCESS status (already processed)."""
        essay_state = MagicMock()
        essay_state.essay_id = "essay-123"
        essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        essay_state.batch_id = "batch-456"
        essay_state.processing_metadata = {
            "current_phase": "spellcheck",
            "commanded_phases": ["spellcheck"],
            "spellcheck_result": {
                "success": True,
                "status": "completed",
                "corrected_text_storage_id": "storage-existing-123",
            },
        }
        return essay_state

    @pytest.fixture
    def correlation_id(self) -> str:
        """Generate correlation ID for test."""
        return str(uuid4())

    async def test_handle_spellcheck_phase_completed_duplicate_success_event(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_completed: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test handling duplicate success event when essay is already in SPELLCHECKED_SUCCESS state."""
        # Arrange - Essay already processed and in success state
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-duplicate-789"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state_completed

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=test_correlation_id,
        )

        # Assert - Should fail gracefully since state machine won't allow transition
        assert result is False

        # Verify essay state was retrieved
        mock_essay_repository.get_essay_state.assert_called_once_with(essay_id, ANY)

        # Verify no database update occurred (idempotent behavior)
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()

        # Verify no batch coordination occurred
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_phase_completed_duplicate_failure_event(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling duplicate failure event when essay is already in SPELLCHECK_FAILED state."""
        # Arrange - Essay already failed
        mock_essay_state_failed = MagicMock()
        mock_essay_state_failed.essay_id = "essay-123"
        mock_essay_state_failed.current_status = EssayStatus.SPELLCHECK_FAILED
        mock_essay_state_failed.batch_id = "batch-456"
        mock_essay_state_failed.processing_metadata = {
            "spellcheck_result": {
                "success": False,
                "error_code": "PREVIOUS_FAILURE",
            }
        }

        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECK_FAILED
        error_code = "DUPLICATE_FAILURE"
        test_correlation_id = uuid4()

        mock_essay_repository.get_essay_state.return_value = mock_essay_state_failed

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=None,
            error_code=error_code,
            correlation_id=test_correlation_id,
        )

        # Assert - Should fail gracefully since state machine won't allow transition
        assert result is False

        # Verify no database update occurred
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()

        # Verify no batch coordination occurred
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_phase_completed_idempotency_callback_invoked(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_awaiting: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test that idempotency callback is invoked exactly once after successful processing."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-789"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state_awaiting

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [
            mock_essay_state_awaiting,
            updated_essay_state,
        ]

        # Create mock idempotency callback
        mock_confirm_idempotency = AsyncMock()

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=uuid4(),
            confirm_idempotency=mock_confirm_idempotency,
        )

        # Assert
        assert result is True

        # Verify idempotency callback was called exactly once
        mock_confirm_idempotency.assert_called_once()

    async def test_handle_spellcheck_phase_completed_idempotency_callback_not_called_on_failure(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_completed: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test that idempotency callback is not called when processing fails due to duplicate."""
        # Arrange - Essay already in success state
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS

        mock_essay_repository.get_essay_state.return_value = mock_essay_state_completed

        # Create mock idempotency callback
        mock_confirm_idempotency = AsyncMock()

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id="duplicate-storage",
            error_code=None,
            correlation_id=uuid4(),
            confirm_idempotency=mock_confirm_idempotency,
        )

        # Assert
        assert result is False

        # Verify idempotency callback was NOT called
        mock_confirm_idempotency.assert_not_called()

    async def test_handle_spellcheck_phase_completed_concurrent_processing_simulation(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_awaiting: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test concurrent processing scenario where two identical events are processed."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-789"
        correlation_id_1 = uuid4()
        correlation_id_2 = uuid4()

        # First call succeeds
        mock_essay_repository.get_essay_state.return_value = mock_essay_state_awaiting
        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS

        # Mock first event processing
        mock_essay_repository.get_essay_state.side_effect = [
            mock_essay_state_awaiting,  # First event - initial state
            updated_essay_state,  # First event - after update
        ]

        mock_confirm_idempotency_1 = AsyncMock()

        # Act - First event processing
        result_1 = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=correlation_id_1,
            confirm_idempotency=mock_confirm_idempotency_1,
        )

        # Reset mocks for second event
        mock_essay_repository.reset_mock()
        mock_batch_coordinator.reset_mock()

        # Setup for second event (essay already in success state)
        mock_essay_state_already_completed = MagicMock()
        mock_essay_state_already_completed.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.return_value = mock_essay_state_already_completed

        mock_confirm_idempotency_2 = AsyncMock()

        # Act - Second event processing (duplicate)
        result_2 = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=correlation_id_2,
            confirm_idempotency=mock_confirm_idempotency_2,
        )

        # Assert
        assert result_1 is True  # First event succeeded
        assert result_2 is False  # Second event rejected (idempotent)

        # Verify first event callback was called
        mock_confirm_idempotency_1.assert_called_once()

        # Verify second event callback was not called
        mock_confirm_idempotency_2.assert_not_called()

    async def test_handle_spellcheck_phase_completed_state_consistency_after_duplicates(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_completed: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test that essay state remains consistent after processing duplicate events."""
        # Arrange - Essay already successfully processed
        essay_id = "essay-123"
        batch_id = "batch-456"
        original_storage_id = "storage-original-123"

        # Mock essay state has original storage ID
        mock_essay_state_completed.processing_metadata["spellcheck_result"][
            "corrected_text_storage_id"
        ] = original_storage_id

        mock_essay_repository.get_essay_state.return_value = mock_essay_state_completed

        # Act - Try to process duplicate event with different storage ID
        result = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-duplicate-456",  # Different storage ID
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert
        assert result is False

        # Verify no state change occurred
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()

        # Verify original metadata is preserved (would be checked in actual implementation)
        assert (
            mock_essay_state_completed.processing_metadata["spellcheck_result"][
                "corrected_text_storage_id"
            ]
            == original_storage_id
        )

    async def test_handle_spellcheck_phase_completed_idempotency_key_generation_consistency(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_awaiting: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test that same event parameters generate consistent behavior for idempotency."""
        # Arrange
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-789"
        correlation_id_test = uuid4()

        # Multiple calls with identical parameters should have consistent behavior
        mock_essay_repository.get_essay_state.return_value = mock_essay_state_awaiting
        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS

        # First call setup
        mock_essay_repository.get_essay_state.side_effect = [
            mock_essay_state_awaiting,
            updated_essay_state,
        ]

        # Act - First call
        result_1 = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=correlation_id_test,
        )

        # Store call count
        initial_update_calls = mock_essay_repository.update_essay_status_via_machine.call_count

        # Reset for second call
        mock_essay_repository.reset_mock()
        mock_batch_coordinator.reset_mock()

        # Setup for duplicate call (essay now completed)
        mock_essay_state_already_completed = MagicMock()
        mock_essay_state_already_completed.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.return_value = mock_essay_state_already_completed

        # Act - Second call with identical parameters
        result_2 = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=correlation_id_test,
        )

        # Assert
        assert result_1 is True  # First call succeeded
        assert result_2 is False  # Second call idempotently rejected
        assert initial_update_calls == 1  # Only one actual update occurred

        # Verify second call made no database changes
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()

    async def test_handle_spellcheck_phase_completed_idempotency_with_different_correlation_ids(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        mock_essay_state_completed: MagicMock,
        correlation_id: str,
    ) -> None:
        """Test idempotency behavior with different correlation IDs but same event content."""
        # Arrange - Essay already processed
        essay_id = "essay-123"
        batch_id = "batch-456"
        status = EssayStatus.SPELLCHECKED_SUCCESS
        corrected_text_storage_id = "storage-789"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state_completed

        # Act - Process same event with different correlation IDs
        correlation_id_1 = uuid4()
        correlation_id_2 = uuid4()

        result_1 = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=correlation_id_1,
        )

        result_2 = await handler.handle_spellcheck_phase_completed(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=None,
            correlation_id=correlation_id_2,  # Different correlation ID
        )

        # Assert - Both should be rejected due to essay already being processed
        assert result_1 is False
        assert result_2 is False

        # Verify no database updates occurred for either call
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()
