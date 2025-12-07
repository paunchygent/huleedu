"""Unit tests for BatchCompletionChecker module."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.error_enums import ErrorCode
from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import (
    HuleEduError,
    create_error_detail_with_context,
)

from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    SessionProviderProtocol,
)


class TestBatchCompletionChecker:
    """Test cases for BatchCompletionChecker class."""

    @pytest.fixture
    def mock_session_provider(self) -> AsyncMock:
        """Create mock session provider protocol."""
        mock_provider = AsyncMock(spec=SessionProviderProtocol)
        mock_session = AsyncMock()
        mock_provider.session.return_value.__aenter__.return_value = mock_session
        mock_provider.session.return_value.__aexit__.return_value = None
        return mock_provider

    @pytest.fixture
    def mock_batch_repo(self) -> AsyncMock:
        """Create mock batch repository protocol."""
        return AsyncMock(spec=CJBatchRepositoryProtocol)

    @pytest.fixture
    def completion_checker(
        self, mock_session_provider: AsyncMock, mock_batch_repo: AsyncMock
    ) -> BatchCompletionChecker:
        """Create BatchCompletionChecker instance for testing."""
        return BatchCompletionChecker(
            session_provider=mock_session_provider, batch_repo=mock_batch_repo
        )

    @pytest.fixture
    def sample_batch_state(self) -> CJBatchState:
        """Create sample batch state."""
        batch_state = CJBatchState()
        batch_state.batch_id = 1
        batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        batch_state.total_budget = 100  # Required for completion_denominator()
        batch_state.total_comparisons = 100
        batch_state.completed_comparisons = 80
        batch_state.completion_threshold_pct = 95
        return batch_state

    async def test_check_batch_completion_terminal_state_completed(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test completion check when batch is in COMPLETED state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        batch_state = CJBatchState()
        batch_state.state = CJBatchStateEnum.COMPLETED

        mock_batch_repo.get_batch_state.return_value = batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is True
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_terminal_state_failed(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test completion check when batch is in FAILED state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        batch_state = CJBatchState()
        batch_state.state = CJBatchStateEnum.FAILED

        mock_batch_repo.get_batch_state.return_value = batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is True
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_terminal_state_cancelled(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test completion check when batch is in CANCELLED state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        batch_state = CJBatchState()
        batch_state.state = CJBatchStateEnum.CANCELLED

        mock_batch_repo.get_batch_state.return_value = batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is True
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_threshold_reached(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check when completion threshold is reached."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Set up batch state with 95% completion (reaching 95% threshold)
        sample_batch_state.total_comparisons = 100
        sample_batch_state.completed_comparisons = 95
        sample_batch_state.completion_threshold_pct = 95
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_batch_repo.get_batch_state.return_value = sample_batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is True
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_threshold_not_reached(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check when completion threshold is not reached."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Set up batch state with 80% completion (below 95% threshold)
        sample_batch_state.total_comparisons = 100
        sample_batch_state.completed_comparisons = 80
        sample_batch_state.completion_threshold_pct = 95
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_batch_repo.get_batch_state.return_value = sample_batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is False
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_with_config_overrides(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check with configuration overrides."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        config_overrides = BatchConfigOverrides(
            partial_completion_threshold=0.8  # 80% threshold override
        )

        # Set up batch state with 85% completion (should reach 80% override threshold)
        sample_batch_state.total_comparisons = 100
        sample_batch_state.completed_comparisons = 85
        sample_batch_state.completion_threshold_pct = 95  # Original threshold
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_batch_repo.get_batch_state.return_value = sample_batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            config_overrides=config_overrides,
        )

        # Assert
        assert result is True  # Should pass with 85% > 80% override threshold
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_zero_total_comparisons(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check when total_comparisons is zero."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Set up batch state with zero total comparisons
        sample_batch_state.total_comparisons = 0
        sample_batch_state.completed_comparisons = 0
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_batch_repo.get_batch_state.return_value = sample_batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is False
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_batch_state_not_found(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test completion check when batch state is not found."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        mock_batch_repo.get_batch_state.return_value = None

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        assert "Batch state not found" in str(exc_info.value)
        assert exc_info.value.correlation_id == str(correlation_id)
        assert exc_info.value.operation == "check_batch_completion"
        assert exc_info.value.error_detail.details["entity_id"] == str(cj_batch_id)
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_database_error(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test completion check when database operation fails."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        mock_batch_repo.get_batch_state.side_effect = Exception("Database connection failed")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        assert "Failed to check batch completion" in str(exc_info.value)
        assert exc_info.value.correlation_id == str(correlation_id)
        assert exc_info.value.operation == "check_batch_completion"
        assert exc_info.value.error_detail.details["entity_id"] == str(cj_batch_id)
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_existing_database_operation_error(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test completion check when HuleEduError is raised."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Original database error",
            service="cj_assessment_service",
            operation="original_operation",
            correlation_id=correlation_id,
        )
        original_error = HuleEduError(error_detail)

        mock_batch_repo.get_batch_state.side_effect = original_error

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        # Should re-raise the original HuleEduError
        assert exc_info.value is original_error
        assert "Original database error" in str(exc_info.value)
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_edge_case_threshold(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check with edge case threshold values."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Test exact threshold match
        sample_batch_state.total_budget = 50  # Use total_budget for completion_denominator()
        sample_batch_state.total_comparisons = 50
        sample_batch_state.completed_comparisons = 48  # 96% exactly
        sample_batch_state.completion_threshold_pct = 96  # 96% threshold
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_batch_repo.get_batch_state.return_value = sample_batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert - should be True for exactly meeting threshold
        assert result is True
        mock_batch_repo.get_batch_state.assert_called_once()

    async def test_check_batch_completion_partial_comparisons(
        self,
        completion_checker: BatchCompletionChecker,
        mock_batch_repo: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check with partial completion scenarios."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Test 90% completion with 85% threshold
        sample_batch_state.total_budget = 200  # Use total_budget for completion_denominator()
        sample_batch_state.total_comparisons = 200
        sample_batch_state.completed_comparisons = 180  # 90%
        sample_batch_state.completion_threshold_pct = 85  # 85% threshold
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_batch_repo.get_batch_state.return_value = sample_batch_state

        # Act
        result = await completion_checker.check_batch_completion(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert - 90% > 85% threshold
        assert result is True
        mock_batch_repo.get_batch_state.assert_called_once()
