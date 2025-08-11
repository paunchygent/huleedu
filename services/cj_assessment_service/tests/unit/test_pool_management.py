"""Unit tests for failed comparison pool management functionality."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
    from services.cj_assessment_service.models_api import (
        ComparisonTask,
        FailedComparisonPool,
    )
    from services.cj_assessment_service.models_db import CJBatchState

from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
    FailedComparisonEntry,
    FailedComparisonPool,
    FailedComparisonPoolStatistics,
)

# Import shared fixtures
pytest_plugins = ["services.cj_assessment_service.tests.unit.conftest_pool"]


class TestFailedComparisonPoolAdd:
    """Test adding comparisons to failed pool."""

    @pytest.mark.asyncio
    async def test_add_to_failed_pool_success(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_database: AsyncMock,
        sample_comparison_task: ComparisonTask,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test successfully adding comparison to failed pool."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        failure_reason = "timeout"

        # Mock database session with proper query responses
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        
        # Mock the execute method to return batch state when queried
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=sample_batch_state)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Mock commit for the atomic update
        mock_session.commit = AsyncMock(return_value=None)

        # Act
        await batch_pool_manager.add_to_failed_pool(
            cj_batch_id=cj_batch_id,
            comparison_task=sample_comparison_task,
            failure_reason=failure_reason,
            correlation_id=correlation_id,
        )

        # Assert - Verify database interactions through the mock
        # Should have executed at least 2 queries: one for get_batch_state, one for atomic update
        assert mock_session.execute.call_count >= 2
        
        # Verify commit was called for the atomic operation
        mock_session.commit.assert_called()
        
        # Verify the SQL update contained the expected batch_id
        update_call = None
        for call in mock_session.execute.call_args_list:
            if call.args and hasattr(call.args[0], 'text'):
                # This is the SQL text update call
                update_call = call
                break
        
        if update_call:
            # Verify the batch_id was passed to the SQL update
            assert update_call.kwargs.get('batch_id') == cj_batch_id or \
                   (update_call.args[1] if len(update_call.args) > 1 else {}).get('batch_id') == cj_batch_id

    @pytest.mark.asyncio
    async def test_add_to_failed_pool_no_batch_state(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_database: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test adding to failed pool when batch state not found."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        failure_reason = "timeout"

        # Mock database session to return None for batch state query
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        
        # Mock the execute method to return None when batch state is queried
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)  # No batch state found
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act & Assert
        from huleedu_service_libs.error_handling import HuleEduError

        with pytest.raises(HuleEduError, match="batch_state with ID"):
            await batch_pool_manager.add_to_failed_pool(
                cj_batch_id=cj_batch_id,
                comparison_task=sample_comparison_task,
                failure_reason=failure_reason,
                correlation_id=correlation_id,
            )


class TestFailedComparisonPoolModels:
    """Test failed comparison pool data models."""

    def test_failed_comparison_entry_creation(self, sample_comparison_task: ComparisonTask) -> None:
        """Test creating failed comparison entry."""
        # Arrange
        correlation_id = uuid4()
        failed_at = datetime.now(UTC)

        # Act
        entry = FailedComparisonEntry(
            essay_a_id="essay_a_123",
            essay_b_id="essay_b_456",
            comparison_task=sample_comparison_task,
            failure_reason="timeout",
            failed_at=failed_at,
            retry_count=0,
            original_batch_id="batch_123",
            correlation_id=correlation_id,
        )

        # Assert
        assert entry.essay_a_id == "essay_a_123"
        assert entry.essay_b_id == "essay_b_456"
        assert entry.comparison_task == sample_comparison_task
        assert entry.failure_reason == "timeout"
        assert entry.failed_at == failed_at
        assert entry.retry_count == 0
        assert entry.original_batch_id == "batch_123"
        assert entry.correlation_id == correlation_id

    def test_failed_comparison_pool_statistics_defaults(self) -> None:
        """Test failed comparison pool statistics default values."""
        # Act
        stats = FailedComparisonPoolStatistics()

        # Assert
        assert stats.total_failed == 0
        assert stats.retry_attempts == 0
        assert stats.last_retry_batch is None
        assert stats.successful_retries == 0
        assert stats.permanently_failed == 0

    def test_failed_comparison_pool_creation(self) -> None:
        """Test creating failed comparison pool."""
        # Act
        pool = FailedComparisonPool()

        # Assert
        assert pool.failed_comparison_pool == []
        assert isinstance(pool.pool_statistics, FailedComparisonPoolStatistics)
        assert pool.pool_statistics.total_failed == 0

    def test_failed_comparison_pool_serialization(
        self, sample_comparison_task: ComparisonTask
    ) -> None:
        """Test serializing and deserializing failed comparison pool."""
        # Arrange
        entry = FailedComparisonEntry(
            essay_a_id="essay_a_123",
            essay_b_id="essay_b_456",
            comparison_task=sample_comparison_task,
            failure_reason="timeout",
            failed_at=datetime.now(UTC),
            retry_count=1,
            original_batch_id="batch_123",
            correlation_id=uuid4(),
        )

        pool = FailedComparisonPool(
            failed_comparison_pool=[entry],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=1),
        )

        # Act
        serialized = pool.model_dump()
        deserialized = FailedComparisonPool.model_validate(serialized)

        # Assert
        assert len(deserialized.failed_comparison_pool) == 1
        assert deserialized.pool_statistics.total_failed == 1
        assert deserialized.failed_comparison_pool[0].essay_a_id == "essay_a_123"
        assert deserialized.failed_comparison_pool[0].retry_count == 1


class TestFailedComparisonPoolBasicOperations:
    """Test basic failed comparison pool operations."""

    @pytest.mark.asyncio
    async def test_pool_entry_validation(self) -> None:
        """Test that pool entries are properly validated."""
        # Arrange
        essay_a = EssayForComparison(
            id="essay_a_test",
            text_content="Test essay A content",
            current_bt_score=0.7,
        )
        essay_b = EssayForComparison(
            id="essay_b_test",
            text_content="Test essay B content",
            current_bt_score=0.4,
        )
        comparison_task = ComparisonTask(
            essay_a=essay_a,
            essay_b=essay_b,
            prompt="Test prompt",
        )

        # Act
        entry = FailedComparisonEntry(
            essay_a_id=essay_a.id,
            essay_b_id=essay_b.id,
            comparison_task=comparison_task,
            failure_reason="test_failure",
            failed_at=datetime.now(UTC),
            retry_count=0,
            original_batch_id="test_batch",
            correlation_id=uuid4(),
        )

        # Assert
        assert entry.comparison_task.essay_a.id == essay_a.id
        assert entry.comparison_task.essay_b.id == essay_b.id
        assert entry.comparison_task.prompt == "Test prompt"

    def test_pool_statistics_increment(self) -> None:
        """Test incrementing pool statistics."""
        # Arrange
        stats = FailedComparisonPoolStatistics()

        # Act
        stats.total_failed += 1
        stats.retry_attempts += 1
        stats.successful_retries += 1
        stats.permanently_failed += 1
        stats.last_retry_batch = "test_batch_123"

        # Assert
        assert stats.total_failed == 1
        assert stats.retry_attempts == 1
        assert stats.successful_retries == 1
        assert stats.permanently_failed == 1
        assert stats.last_retry_batch == "test_batch_123"

    def test_empty_pool_behavior(self, empty_failed_pool: FailedComparisonPool) -> None:
        """Test behavior of empty failed comparison pool."""
        # Assert
        assert len(empty_failed_pool.failed_comparison_pool) == 0
        assert empty_failed_pool.pool_statistics.total_failed == 0
        assert empty_failed_pool.pool_statistics.retry_attempts == 0
        assert empty_failed_pool.pool_statistics.successful_retries == 0
        assert empty_failed_pool.pool_statistics.permanently_failed == 0
        assert empty_failed_pool.pool_statistics.last_retry_batch is None

    @pytest.mark.asyncio
    async def test_pool_capacity_and_structure(
        self, sample_comparison_task: ComparisonTask
    ) -> None:
        """Test pool can handle multiple entries correctly."""
        # Arrange
        pool = FailedComparisonPool()
        entries_to_add = 5

        # Act - Add multiple entries
        for i in range(entries_to_add):
            entry = FailedComparisonEntry(
                essay_a_id=f"essay_a_{i}",
                essay_b_id=f"essay_b_{i}",
                comparison_task=sample_comparison_task,
                failure_reason="bulk_test",
                failed_at=datetime.now(UTC),
                retry_count=0,
                original_batch_id="bulk_batch",
                correlation_id=uuid4(),
            )
            pool.failed_comparison_pool.append(entry)
            pool.pool_statistics.total_failed += 1

        # Assert
        assert len(pool.failed_comparison_pool) == entries_to_add
        assert pool.pool_statistics.total_failed == entries_to_add

        # Verify each entry is unique
        essay_a_ids = [entry.essay_a_id for entry in pool.failed_comparison_pool]
        assert len(set(essay_a_ids)) == entries_to_add  # All unique
