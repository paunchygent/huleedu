"""Unit tests for BatchCompletionChecker module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.exceptions import DatabaseOperationError
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import CJRepositoryProtocol


class TestBatchCompletionChecker:
    """Test cases for BatchCompletionChecker class."""

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create mock database protocol."""
        mock_db = AsyncMock(spec=CJRepositoryProtocol)
        mock_session = AsyncMock()
        mock_db.session.return_value.__aenter__.return_value = mock_session
        mock_db.session.return_value.__aexit__.return_value = None
        return mock_db

    @pytest.fixture
    def completion_checker(self, mock_database: AsyncMock) -> BatchCompletionChecker:
        """Create BatchCompletionChecker instance for testing."""
        return BatchCompletionChecker(database=mock_database)

    @pytest.fixture
    def sample_batch_state(self) -> CJBatchState:
        """Create sample batch state."""
        batch_state = CJBatchState()
        batch_state.batch_id = 1
        batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        batch_state.total_comparisons = 100
        batch_state.completed_comparisons = 80
        batch_state.completion_threshold_pct = 95
        return batch_state

    async def test_check_batch_completion_terminal_state_completed(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
    ) -> None:
        """Test completion check when batch is in COMPLETED state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        batch_state = CJBatchState()
        batch_state.state = CJBatchStateEnum.COMPLETED

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is True
            mock_get_batch_state.assert_called_once_with(
                session=mock_session, cj_batch_id=cj_batch_id, correlation_id=correlation_id
            )

    async def test_check_batch_completion_terminal_state_failed(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
    ) -> None:
        """Test completion check when batch is in FAILED state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        batch_state = CJBatchState()
        batch_state.state = CJBatchStateEnum.FAILED

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is True

    async def test_check_batch_completion_terminal_state_cancelled(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
    ) -> None:
        """Test completion check when batch is in CANCELLED state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        batch_state = CJBatchState()
        batch_state.state = CJBatchStateEnum.CANCELLED

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is True

    async def test_check_batch_completion_threshold_reached(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
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

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is True

    async def test_check_batch_completion_threshold_not_reached(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
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

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is False

    async def test_check_batch_completion_with_config_overrides(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
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

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                config_overrides=config_overrides,
            )

            # Assert
            assert result is True  # Should pass with 85% > 80% override threshold

    async def test_check_batch_completion_zero_total_comparisons(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
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

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is False

    async def test_check_batch_completion_batch_state_not_found(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
    ) -> None:
        """Test completion check when batch state is not found."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = None

            with pytest.raises(DatabaseOperationError) as exc_info:
                await completion_checker.check_batch_completion(
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )

            assert "Batch state not found" in str(exc_info.value)
            assert exc_info.value.correlation_id == correlation_id
            assert exc_info.value.details["operation"] == "check_batch_completion"
            assert exc_info.value.details["entity_id"] == str(cj_batch_id)

    async def test_check_batch_completion_database_error(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
    ) -> None:
        """Test completion check when database operation fails."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.side_effect = Exception("Database connection failed")

            with pytest.raises(DatabaseOperationError) as exc_info:
                await completion_checker.check_batch_completion(
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )

            assert "Failed to check batch completion" in str(exc_info.value)
            assert exc_info.value.correlation_id == correlation_id
            assert exc_info.value.details["operation"] == "check_batch_completion"
            assert exc_info.value.details["entity_id"] == str(cj_batch_id)

    async def test_check_batch_completion_existing_database_operation_error(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
    ) -> None:
        """Test completion check when DatabaseOperationError is raised."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        original_error = DatabaseOperationError(
            message="Original database error",
            correlation_id=correlation_id,
            operation="original_operation",
        )

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.side_effect = original_error

            with pytest.raises(DatabaseOperationError) as exc_info:
                await completion_checker.check_batch_completion(
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )

            # Should re-raise the original DatabaseOperationError
            assert exc_info.value is original_error
            assert "Original database error" in str(exc_info.value)

    async def test_check_batch_completion_edge_case_threshold(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check with edge case threshold values."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Test exact threshold match
        sample_batch_state.total_comparisons = 50
        sample_batch_state.completed_comparisons = 48  # 96% exactly
        sample_batch_state.completion_threshold_pct = 96  # 96% threshold
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert - should be True for exactly meeting threshold
            assert result is True

    async def test_check_batch_completion_partial_comparisons(
        self,
        completion_checker: BatchCompletionChecker,
        mock_database: AsyncMock,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test completion check with partial completion scenarios."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Test 90% completion with 85% threshold
        sample_batch_state.total_comparisons = 200
        sample_batch_state.completed_comparisons = 180  # 90%
        sample_batch_state.completion_threshold_pct = 85  # 85% threshold
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS

        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state

            result = await completion_checker.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert - 90% > 85% threshold
            assert result is True
