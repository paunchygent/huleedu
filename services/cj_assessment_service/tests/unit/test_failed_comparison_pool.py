"""Unit tests for failed comparison pool functionality."""

from __future__ import annotations

import pytest
from datetime import datetime, UTC
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
    FailedComparisonEntry,
    FailedComparisonPool,
    FailedComparisonPoolStatistics,
)
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)


@pytest.fixture
def mock_settings():
    """Create mock settings with failed pool configuration."""
    settings = MagicMock(spec=Settings)
    settings.ENABLE_FAILED_COMPARISON_RETRY = True
    settings.FAILED_COMPARISON_RETRY_THRESHOLD = 5
    settings.MAX_RETRY_ATTEMPTS = 3
    settings.RETRY_BATCH_SIZE = 10
    return settings


@pytest.fixture
def mock_database():
    """Create mock database protocol."""
    return AsyncMock(spec=CJRepositoryProtocol)


@pytest.fixture
def mock_llm_interaction():
    """Create mock LLM interaction protocol."""
    return AsyncMock(spec=LLMInteractionProtocol)


@pytest.fixture
def batch_processor(mock_database, mock_llm_interaction, mock_settings):
    """Create BatchProcessor instance with mocks."""
    return BatchProcessor(
        database=mock_database,
        llm_interaction=mock_llm_interaction,
        settings=mock_settings,
    )


@pytest.fixture
def sample_comparison_task():
    """Create sample comparison task."""
    essay_a = EssayForComparison(
        id="essay_a_123",
        text_content="This is essay A content",
        current_bt_score=0.5,
    )
    essay_b = EssayForComparison(
        id="essay_b_456",
        text_content="This is essay B content",
        current_bt_score=0.3,
    )
    return ComparisonTask(
        essay_a=essay_a,
        essay_b=essay_b,
        prompt="Compare these essays",
    )


@pytest.fixture
def empty_failed_pool():
    """Create empty failed comparison pool."""
    return FailedComparisonPool(
        failed_comparison_pool=[],
        pool_statistics=FailedComparisonPoolStatistics(),
    )


@pytest.fixture
def sample_batch_state(empty_failed_pool):
    """Create sample batch state with empty failed pool."""
    batch_state = MagicMock(spec=CJBatchState)
    batch_state.batch_id = 123
    batch_state.processing_metadata = empty_failed_pool.model_dump()
    return batch_state


class TestFailedComparisonPoolAdd:
    """Test adding comparisons to failed pool."""

    @pytest.mark.asyncio
    async def test_add_to_failed_pool_success(
        self,
        batch_processor,
        mock_database,
        sample_comparison_task,
        sample_batch_state,
    ):
        """Test successfully adding comparison to failed pool."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        failure_reason = "timeout"

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=sample_batch_state)
        batch_processor._update_batch_processing_metadata = AsyncMock()

        # Act
        await batch_processor.add_to_failed_pool(
            cj_batch_id=cj_batch_id,
            comparison_task=sample_comparison_task,
            failure_reason=failure_reason,
            correlation_id=correlation_id,
        )

        # Assert
        batch_processor._get_batch_state.assert_called_once_with(
            session=mock_session,
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )
        batch_processor._update_batch_processing_metadata.assert_called_once()

        # Check that metadata contains the failed comparison
        call_args = batch_processor._update_batch_processing_metadata.call_args
        metadata = call_args[1]["metadata"]
        assert "failed_comparison_pool" in metadata
        assert len(metadata["failed_comparison_pool"]) == 1
        assert metadata["pool_statistics"]["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_add_to_failed_pool_no_batch_state(
        self,
        batch_processor,
        mock_database,
        sample_comparison_task,
    ):
        """Test adding to failed pool when batch state not found."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        failure_reason = "timeout"

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=None)

        # Act & Assert
        from services.cj_assessment_service.exceptions import DatabaseOperationError

        with pytest.raises(DatabaseOperationError, match="Batch state not found"):
            await batch_processor.add_to_failed_pool(
                cj_batch_id=cj_batch_id,
                comparison_task=sample_comparison_task,
                failure_reason=failure_reason,
                correlation_id=correlation_id,
            )


class TestFailedComparisonPoolRetryCheck:
    """Test checking if retry batch is needed."""

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_disabled(
        self,
        batch_processor,
        mock_settings,
    ):
        """Test retry check when retry is disabled."""
        # Arrange
        mock_settings.ENABLE_FAILED_COMPARISON_RETRY = False
        cj_batch_id = 123
        correlation_id = uuid4()

        # Act
        result = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_threshold_met(
        self,
        batch_processor,
        mock_database,
    ):
        """Test retry check when threshold is met."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with enough failures
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_{i}",
                    essay_b_id=f"essay_b_{i}",
                    comparison_task=ComparisonTask(
                        essay_a=EssayForComparison(id=f"essay_a_{i}", text_content="Essay A"),
                        essay_b=EssayForComparison(id=f"essay_b_{i}", text_content="Essay B"),
                        prompt="Compare essays",
                    ),
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(6)  # More than threshold of 5
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=6),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)

        # Act
        result = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_threshold_not_met(
        self,
        batch_processor,
        mock_database,
    ):
        """Test retry check when threshold is not met."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with insufficient failures
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_{i}",
                    essay_b_id=f"essay_b_{i}",
                    comparison_task=ComparisonTask(
                        essay_a=EssayForComparison(id=f"essay_a_{i}", text_content="Essay A"),
                        essay_b=EssayForComparison(id=f"essay_b_{i}", text_content="Essay B"),
                        prompt="Compare essays",
                    ),
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(3)  # Less than threshold of 5
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=3),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)

        # Act
        result = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is False


class TestFailedComparisonPoolRetryBatch:
    """Test forming retry batches from failed pool."""

    @pytest.mark.asyncio
    async def test_form_retry_batch_success(
        self,
        batch_processor,
        mock_database,
        sample_comparison_task,
    ):
        """Test successfully forming retry batch."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with enough failures
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_{i}",
                    essay_b_id=f"essay_b_{i}",
                    comparison_task=sample_comparison_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(6)  # More than threshold of 5
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=6),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)
        batch_processor._update_batch_processing_metadata = AsyncMock()

        # Act
        retry_tasks = await batch_processor.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert retry_tasks is not None
        assert len(retry_tasks) == 6  # All eligible failures should be included
        assert all(isinstance(task, ComparisonTask) for task in retry_tasks)

        # Check that metadata was updated
        batch_processor._update_batch_processing_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_form_retry_batch_max_retry_reached(
        self,
        batch_processor,
        mock_database,
        sample_comparison_task,
        mock_settings,
    ):
        """Test forming retry batch with comparisons at max retry limit."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with failures at max retry count
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_{i}",
                    essay_b_id=f"essay_b_{i}",
                    comparison_task=ComparisonTask(
                        essay_a=EssayForComparison(id=f"essay_a_{i}", text_content="Essay A"),
                        essay_b=EssayForComparison(id=f"essay_b_{i}", text_content="Essay B"),
                        prompt="Compare essays",
                    ),
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=mock_settings.MAX_RETRY_ATTEMPTS,  # At max retries
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(6)
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=6),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)

        # Act
        retry_tasks = await batch_processor.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert retry_tasks is None  # No eligible failures


class TestFailedComparisonPoolSubmitRetry:
    """Test submitting retry batches."""

    @pytest.mark.asyncio
    async def test_submit_retry_batch_success(
        self,
        batch_processor,
        sample_comparison_task,
    ):
        """Test successfully submitting retry batch."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock form_retry_batch to return tasks
        retry_tasks = [sample_comparison_task]
        batch_processor.form_retry_batch = AsyncMock(return_value=retry_tasks)

        # Mock submit_comparison_batch
        from services.cj_assessment_service.cj_core_logic.batch_processor import (
            BatchSubmissionResult,
        )

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )
        batch_processor.submit_comparison_batch = AsyncMock(return_value=submission_result)

        # Act
        result = await batch_processor.submit_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is not None
        assert result.total_submitted == 1
        batch_processor.form_retry_batch.assert_called_once()
        batch_processor.submit_comparison_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_retry_batch_disabled(
        self,
        batch_processor,
        mock_settings,
    ):
        """Test submitting retry batch when retry is disabled."""
        # Arrange
        mock_settings.ENABLE_FAILED_COMPARISON_RETRY = False
        cj_batch_id = 123
        correlation_id = uuid4()

        # Act
        result = await batch_processor.submit_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_submit_retry_batch_no_tasks(
        self,
        batch_processor,
    ):
        """Test submitting retry batch when no tasks are available."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock form_retry_batch to return None (no tasks)
        batch_processor.form_retry_batch = AsyncMock(return_value=None)

        # Act
        result = await batch_processor.submit_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None
        batch_processor.form_retry_batch.assert_called_once()


class TestFailedComparisonPoolModels:
    """Test failed comparison pool data models."""

    def test_failed_comparison_entry_creation(self, sample_comparison_task):
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

    def test_failed_comparison_pool_statistics_defaults(self):
        """Test failed comparison pool statistics default values."""
        # Act
        stats = FailedComparisonPoolStatistics()

        # Assert
        assert stats.total_failed == 0
        assert stats.retry_attempts == 0
        assert stats.last_retry_batch is None
        assert stats.successful_retries == 0
        assert stats.permanently_failed == 0

    def test_failed_comparison_pool_creation(self):
        """Test creating failed comparison pool."""
        # Act
        pool = FailedComparisonPool()

        # Assert
        assert pool.failed_comparison_pool == []
        assert isinstance(pool.pool_statistics, FailedComparisonPoolStatistics)
        assert pool.pool_statistics.total_failed == 0

    def test_failed_comparison_pool_serialization(self, sample_comparison_task):
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


class TestDualModeRetryLogic:
    """Test dual-mode retry logic for fairness."""

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_force_retry_all_with_failures(
        self,
        batch_processor,
        mock_database,
    ):
        """Test force_retry_all=True processes any eligible failures."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with few failures (less than threshold)
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id="essay_a_1",
                    essay_b_id="essay_b_1",
                    comparison_task=ComparisonTask(
                        essay_a=EssayForComparison(id="essay_a_1", text_content="Essay A"),
                        essay_b=EssayForComparison(id="essay_b_1", text_content="Essay B"),
                        prompt="Compare essays",
                    ),
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
            ],  # Only 1 failure (less than threshold of 5)
            pool_statistics=FailedComparisonPoolStatistics(total_failed=1),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)

        # Act - Test force_retry_all=True
        result = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,
        )

        # Assert - Should return True even with only 1 failure
        assert result is True

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_force_retry_all_no_failures(
        self,
        batch_processor,
        mock_database,
        empty_failed_pool,
    ):
        """Test force_retry_all=True with no eligible failures."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = empty_failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)

        # Act
        result = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,
        )

        # Assert - Should return False with no failures
        assert result is False

    @pytest.mark.asyncio
    async def test_form_retry_batch_force_retry_all_with_failures(
        self,
        batch_processor,
        mock_database,
    ):
        """Test form_retry_batch with force_retry_all=True processes any eligible failures."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with few failures (less than threshold)
        sample_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_1", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_1", text_content="Essay B"),
            prompt="Compare essays",
        )

        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id="essay_a_1",
                    essay_b_id="essay_b_1",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
                FailedComparisonEntry(
                    essay_a_id="essay_a_2",
                    essay_b_id="essay_b_2",
                    comparison_task=sample_task,
                    failure_reason="error",
                    failed_at=datetime.now(UTC),
                    retry_count=1,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
            ],  # Only 2 failures (less than threshold of 5)
            pool_statistics=FailedComparisonPoolStatistics(total_failed=2),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)
        batch_processor._update_batch_processing_metadata = AsyncMock()

        # Act - Test force_retry_all=True
        retry_tasks = await batch_processor.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,
        )

        # Assert - Should process all 2 failures despite being below threshold
        assert retry_tasks is not None
        assert len(retry_tasks) == 2
        assert all(isinstance(task, ComparisonTask) for task in retry_tasks)

    @pytest.mark.asyncio
    async def test_form_retry_batch_normal_mode_below_threshold(
        self,
        batch_processor,
        mock_database,
    ):
        """Test form_retry_batch with force_retry_all=False below threshold."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create batch state with few failures (less than threshold)
        sample_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_1", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_1", text_content="Essay B"),
            prompt="Compare essays",
        )

        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id="essay_a_1",
                    essay_b_id="essay_b_1",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
            ],  # Only 1 failure (less than threshold of 5)
            pool_statistics=FailedComparisonPoolStatistics(total_failed=1),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)

        # Act - Test normal mode (force_retry_all=False)
        retry_tasks = await batch_processor.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=False,
        )

        # Assert - Should return None due to threshold not met
        assert retry_tasks is None

    @pytest.mark.asyncio
    async def test_process_remaining_failed_comparisons_success(
        self,
        batch_processor,
    ):
        """Test process_remaining_failed_comparisons method."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock submit_retry_batch to return a result
        from services.cj_assessment_service.cj_core_logic.batch_processor import (
            BatchSubmissionResult,
        )

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=3,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )
        batch_processor.submit_retry_batch = AsyncMock(return_value=submission_result)

        # Act
        result = await batch_processor.process_remaining_failed_comparisons(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is not None
        assert result.total_submitted == 3
        batch_processor.submit_retry_batch.assert_called_once_with(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,  # KEY: Should force retry all
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
        )

    @pytest.mark.asyncio
    async def test_process_remaining_failed_comparisons_no_failures(
        self,
        batch_processor,
    ):
        """Test process_remaining_failed_comparisons when no failures remain."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock submit_retry_batch to return None (no tasks to process)
        batch_processor.submit_retry_batch = AsyncMock(return_value=None)

        # Act
        result = await batch_processor.process_remaining_failed_comparisons(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None
        batch_processor.submit_retry_batch.assert_called_once_with(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
        )


class TestEndOfBatchFairnessScenarios:
    """Test end-of-batch fairness scenarios."""

    @pytest.mark.asyncio
    async def test_fairness_scenario_few_remaining_failures(
        self,
        batch_processor,
        mock_database,
    ):
        """Test fairness when only a few failures remain at batch end."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create scenario: batch ending with 3 remaining failures
        # (below normal threshold of 5, but should be processed for fairness)
        sample_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_1", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_1", text_content="Essay B"),
            prompt="Compare essays",
        )

        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_{i}",
                    essay_b_id=f"essay_b_{i}",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(3)  # 3 remaining failures
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=3),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        batch_processor._get_batch_state = AsyncMock(return_value=batch_state)
        batch_processor._update_batch_processing_metadata = AsyncMock()

        # Act - Simulate end-of-batch processing
        # 1. Normal check should return False (below threshold)
        normal_check = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=False,
        )

        # 2. End-of-batch check should return True (fairness mode)
        fairness_check = await batch_processor.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,
        )

        # 3. Form retry batch in fairness mode
        retry_tasks = await batch_processor.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
            force_retry_all=True,
        )

        # Assert
        assert normal_check is False  # Normal mode: below threshold
        assert fairness_check is True  # Fairness mode: process all remaining
        assert retry_tasks is not None
        assert len(retry_tasks) == 3  # All 3 remaining failures processed