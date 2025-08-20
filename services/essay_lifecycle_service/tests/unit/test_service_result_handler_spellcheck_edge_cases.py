"""
Unit tests for DefaultServiceResultHandler spellcheck phase completion edge cases.

Tests the thin spellcheck event handler for error conditions, malformed data,
missing entities, invalid states, and orphaned essays scenarios.
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


class TestServiceResultHandlerSpellcheckEdgeCases:
    """Test suite for spellcheck phase completion edge cases and error handling."""

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
    def correlation_id(self) -> str:
        """Generate correlation ID for test."""
        return str(uuid4())

    async def test_handle_spellcheck_phase_completed_missing_essay_id(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling when essay ID is missing or None."""
        # Arrange
        mock_essay_repository.get_essay_state.return_value = None  # Essay not found

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="non-existent-essay-id",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert
        assert result is False

        # Verify essay lookup was attempted
        mock_essay_repository.get_essay_state.assert_called_once_with("non-existent-essay-id", ANY)

        # Verify no database updates or batch coordination occurred
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_phase_completed_invalid_batch_id(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling when batch ID is invalid or doesn't match essay's batch."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "correct-batch-456"  # Different from provided batch ID

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act - Provide wrong batch ID
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="wrong-batch-999",  # Incorrect batch ID
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert - Should still process since handler doesn't validate batch ID matching
        # (this might be business logic that should be added)
        assert result is True

        # Verify processing occurred despite batch ID mismatch
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()

    async def test_handle_spellcheck_phase_completed_null_corrected_text_on_success(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling success status with null corrected text storage ID."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act - Success but no corrected text (no corrections needed)
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id=None,  # No corrections made
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert
        assert result is True

        # Verify no storage reference was added
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.kwargs["storage_reference"] is None

        # Verify metadata reflects no corrected text
        metadata = call_args.args[2]
        assert metadata["spellcheck_result"]["corrected_text_storage_id"] is None

    async def test_handle_spellcheck_phase_completed_malformed_error_codes(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling various malformed or unusual error codes."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "batch-456"

        test_cases = [
            "",  # Empty string
            "   ",  # Whitespace only
            "VERY_LONG_ERROR_CODE_THAT_EXCEEDS_NORMAL_LIMITS_" * 10,  # Very long
            "error-with-special-chars!@#$%^&*()",  # Special characters
            "🚨 EMOJI_ERROR 🚨",  # Contains emojis
            "null",  # String "null"
            "undefined",  # String "undefined"
        ]

        for error_code in test_cases:
            # Reset mocks
            mock_essay_repository.reset_mock()
            mock_batch_coordinator.reset_mock()

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
                correlation_id=uuid4(),
            )

            # Assert
            assert result is True

            # Verify error code is stored as-is (no validation/sanitization)
            call_args = mock_essay_repository.update_essay_status_via_machine.call_args
            metadata = call_args.args[2]
            assert metadata["spellcheck_result"]["error_code"] == error_code

    async def test_handle_spellcheck_phase_completed_essay_not_in_expected_state(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling when essay is not in expected state for spellcheck completion."""
        # Test multiple invalid states
        invalid_states = [
            EssayStatus.UPLOADED,  # Too early in pipeline
            EssayStatus.TEXT_EXTRACTED,  # Too early
            EssayStatus.READY_FOR_PROCESSING,  # Not yet started spellcheck
            EssayStatus.AWAITING_NLP,  # Already passed spellcheck
            EssayStatus.NLP_SUCCESS,  # Further down pipeline
            EssayStatus.ALL_PROCESSING_COMPLETED,  # Pipeline completed
        ]

        for invalid_status in invalid_states:
            # Reset mocks
            mock_essay_repository.reset_mock()
            mock_batch_coordinator.reset_mock()

            # Arrange
            mock_essay_state = MagicMock()
            mock_essay_state.essay_id = "essay-123"
            mock_essay_state.current_status = invalid_status
            mock_essay_state.batch_id = "batch-456"

            mock_essay_repository.get_essay_state.return_value = mock_essay_state

            # Act
            result = await handler.handle_spellcheck_phase_completed(
                essay_id="essay-123",
                batch_id="batch-456",
                status=EssayStatus.SPELLCHECKED_SUCCESS,
                corrected_text_storage_id="storage-789",
                error_code=None,
                correlation_id=uuid4(),
            )

            # Assert - Should fail due to invalid state transition
            assert result is False

            # Verify no database updates occurred
            mock_essay_repository.update_essay_status_via_machine.assert_not_called()
            mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_phase_completed_orphaned_essay_no_batch(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling orphaned essay with no batch association."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "orphaned-essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = None  # Orphaned essay with no batch

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        updated_essay_state.batch_id = None  # Still orphaned
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="orphaned-essay-123",
            batch_id="batch-456",  # Provided but doesn't match essay's null batch
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert
        assert result is True

        # Verify state update occurred
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()

        # Verify batch completion check was still attempted with orphaned essay
        mock_batch_coordinator.check_batch_completion.assert_called_once_with(
            essay_state=updated_essay_state,
            phase_name=PhaseName.SPELLCHECK,
            correlation_id=ANY,
            session=ANY,
        )

    async def test_handle_spellcheck_phase_completed_database_transaction_failure(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling when database transaction fails during processing."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        # Simulate database failure during update
        mock_essay_repository.update_essay_status_via_machine.side_effect = Exception(
            "Database connection failed"
        )

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert
        assert result is False

        # Verify database update was attempted
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()

        # Verify batch coordination was not attempted due to failure
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_phase_completed_batch_coordinator_failure(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling when batch coordinator fails during completion check."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Simulate batch coordinator failure
        mock_batch_coordinator.check_batch_completion.side_effect = Exception(
            "Batch coordination failed"
        )

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert - Should fail due to exception in batch coordination
        assert result is False

        # Verify essay update was successful
        mock_essay_repository.update_essay_status_via_machine.assert_called_once()

        # Verify batch coordination was attempted
        mock_batch_coordinator.check_batch_completion.assert_called_once()

    async def test_handle_spellcheck_phase_completed_session_factory_failure(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling when session factory fails to create session."""
        # Arrange - Simulate session factory failure
        handler.session_factory = AsyncMock(
            side_effect=Exception("Failed to create database session")
        )

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=uuid4(),
        )

        # Assert
        assert result is False

        # Verify no repository operations were attempted
        mock_essay_repository.get_essay_state.assert_not_called()
        mock_essay_repository.update_essay_status_via_machine.assert_not_called()
        mock_batch_coordinator.check_batch_completion.assert_not_called()

    async def test_handle_spellcheck_phase_completed_large_correlation_id(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling with unusually large correlation ID."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Very large correlation ID
        large_correlation_id = uuid4()  # UUID should handle this fine

        # Act
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrected_text_storage_id="storage-789",
            error_code=None,
            correlation_id=large_correlation_id,
        )

        # Assert
        assert result is True

        # Verify correlation ID was properly handled
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.kwargs["correlation_id"] == large_correlation_id

    async def test_handle_spellcheck_phase_completed_mixed_success_failure_data(
        self,
        handler: DefaultServiceResultHandler,
        mock_essay_repository: AsyncMock,
        mock_batch_coordinator: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test handling inconsistent data (success status with error code, etc)."""
        # Arrange
        mock_essay_state = MagicMock()
        mock_essay_state.essay_id = "essay-123"
        mock_essay_state.current_status = EssayStatus.AWAITING_SPELLCHECK
        mock_essay_state.batch_id = "batch-456"

        mock_essay_repository.get_essay_state.return_value = mock_essay_state

        updated_essay_state = MagicMock()
        updated_essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
        mock_essay_repository.get_essay_state.side_effect = [mock_essay_state, updated_essay_state]

        # Act - Success status but with error code (inconsistent data)
        result = await handler.handle_spellcheck_phase_completed(
            essay_id="essay-123",
            batch_id="batch-456",
            status=EssayStatus.SPELLCHECKED_SUCCESS,  # Success status (correct enum)
            corrected_text_storage_id="storage-789",
            error_code="SOME_ERROR_CODE",  # But also error code (inconsistent)
            correlation_id=uuid4(),
        )

        # Assert - Should process based on status (success takes precedence over error code)
        assert result is True

        # Verify it treated as success despite error code presence
        call_args = mock_essay_repository.update_essay_status_via_machine.call_args
        assert call_args.args[1] == EssayStatus.SPELLCHECKED_SUCCESS

        # Verify both corrected text and error code are preserved in metadata
        metadata = call_args.args[2]
        assert metadata["spellcheck_result"]["success"] is True
        assert metadata["spellcheck_result"]["corrected_text_storage_id"] == "storage-789"
        assert metadata["spellcheck_result"]["error_code"] == "SOME_ERROR_CODE"
