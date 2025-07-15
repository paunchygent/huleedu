"""Unit tests for failed comparison pool integration scenarios and fairness logic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.models_api import ComparisonTask
    from services.cj_assessment_service.models_db import CJBatchState

from services.cj_assessment_service.cj_core_logic.batch_processor import (
    BatchSubmissionResult,
)
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
    FailedComparisonEntry,
    FailedComparisonPool,
    FailedComparisonPoolStatistics,
)
from services.cj_assessment_service.models_db import CJBatchState

# Import shared fixtures
pytest_plugins = ["services.cj_assessment_service.tests.unit.conftest_pool"]


class TestDualModeRetryLogic:
    """Test dual-mode retry logic for fairness."""

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_force_retry_all_with_failures(
        self,
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
    ) -> None:
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
        mock_database.session.return_value.__aexit__.return_value = None

        # Act - Test force_retry_all=True
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state
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
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
        empty_failed_pool: FailedComparisonPool,
    ) -> None:
        """Test force_retry_all=True with no eligible failures."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = empty_failed_pool.model_dump()

        # Mock database session and batch state retrieval
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        mock_database.session.return_value.__aexit__.return_value = None

        # Act
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state
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
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
    ) -> None:
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
        mock_database.session.return_value.__aexit__.return_value = None

        # Act - Test force_retry_all=True
        with (
            patch(
                "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state"
            ) as mock_get_batch_state,
            patch(
                "services.cj_assessment_service.cj_core_logic.batch_pool_manager.update_batch_processing_metadata"
            ) as mock_update_metadata,
        ):
            mock_get_batch_state.return_value = batch_state
            retry_tasks = await batch_processor.form_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,
            )

        # Assert - Should process all 2 failures despite being below threshold
        assert retry_tasks is not None
        assert len(retry_tasks) == 2
        assert all(isinstance(task, ComparisonTask) for task in retry_tasks)

        # Verify metadata was updated during batch formation
        mock_update_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_form_retry_batch_normal_mode_below_threshold(
        self,
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
    ) -> None:
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
        mock_database.session.return_value.__aexit__.return_value = None

        # Act - Test normal mode (force_retry_all=False)
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state
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
        batch_processor: BatchProcessor,
    ) -> None:
        """Test process_remaining_failed_comparisons method."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock submit_retry_batch to return a result
        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=3,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        with patch.object(
            batch_processor, "submit_retry_batch", new_callable=AsyncMock
        ) as mock_submit_retry:
            mock_submit_retry.return_value = submission_result

            # Act
            result = await batch_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is not None
            assert result.total_submitted == 3
            mock_submit_retry.assert_called_once_with(
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
        batch_processor: BatchProcessor,
    ) -> None:
        """Test process_remaining_failed_comparisons when no failures remain."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock submit_retry_batch to return None (no tasks to process)
        with patch.object(
            batch_processor, "submit_retry_batch", new_callable=AsyncMock
        ) as mock_submit_retry:
            mock_submit_retry.return_value = None

            # Act
            result = await batch_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is None
            mock_submit_retry.assert_called_once_with(
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
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
    ) -> None:
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
        mock_database.session.return_value.__aexit__.return_value = None

        # Act - Simulate end-of-batch processing
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = batch_state

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

    @pytest.mark.asyncio
    async def test_comprehensive_fairness_workflow(
        self,
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
    ) -> None:
        """Test complete fairness workflow from detection to processing."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create sample task
        sample_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_test", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_test", text_content="Essay B"),
            prompt="Compare these essays for fairness test",
        )

        # Scenario: 2 remaining failures at end of batch
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                FailedComparisonEntry(
                    essay_a_id="essay_a_test_1",
                    essay_b_id="essay_b_test_1",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=1,  # Has been retried once
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
                FailedComparisonEntry(
                    essay_a_id="essay_a_test_2",
                    essay_b_id="essay_b_test_2",
                    comparison_task=sample_task,
                    failure_reason="rate_limit",
                    failed_at=datetime.now(UTC),
                    retry_count=0,  # First failure
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
            ],
            pool_statistics=FailedComparisonPoolStatistics(
                total_failed=2,
                retry_attempts=1,
                successful_retries=0,
                permanently_failed=0,
            ),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database and batch processor methods
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        mock_database.session.return_value.__aexit__.return_value = None

        # Mock submission result
        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=2,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )
        # Mock submit_comparison_batch will be done within context manager

        # Act - Execute complete fairness workflow
        with (
            patch(
                "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state",
                new_callable=AsyncMock,
            ) as mock_get_batch_state,
            patch(
                "services.cj_assessment_service.cj_core_logic.batch_pool_manager.update_batch_processing_metadata",
                new_callable=AsyncMock,
            ) as mock_update_metadata,
            patch.object(
                batch_processor, "submit_comparison_batch", new_callable=AsyncMock
            ) as mock_submit_comparison,
        ):
            mock_get_batch_state.return_value = batch_state
            mock_submit_comparison.return_value = submission_result

            # 1. Check that normal mode would skip
            normal_result = await batch_processor.check_retry_batch_needed(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=False,
            )

            # 2. Execute fairness processing
            fairness_result = await batch_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert normal_result is False  # Would be skipped in normal processing
            assert fairness_result is not None
            assert fairness_result.total_submitted == 2  # Both failures processed
            assert fairness_result.all_submitted is True

            # Verify submission was called with force_retry_all
            mock_submit_comparison.assert_called_once()

            # Verify metadata was updated during batch formation
            mock_update_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_retry_count_fairness_scenario(
        self,
        batch_processor: BatchProcessor,
        mock_database: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test fairness scenario with mixed retry counts and max attempts."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        sample_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_mixed", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_mixed", text_content="Essay B"),
            prompt="Compare essays",
        )

        # Mixed scenario: some eligible, some at max retries
        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                # Eligible for retry
                FailedComparisonEntry(
                    essay_a_id="essay_a_eligible_1",
                    essay_b_id="essay_b_eligible_1",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=1,  # Below max
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
                # At max retry attempts - should be marked as permanently failed
                FailedComparisonEntry(
                    essay_a_id="essay_a_max_retries",
                    essay_b_id="essay_b_max_retries",
                    comparison_task=sample_task,
                    failure_reason="persistent_error",
                    failed_at=datetime.now(UTC),
                    retry_count=mock_settings.MAX_RETRY_ATTEMPTS,  # At max
                    original_batch_id="123",
                    correlation_id=uuid4(),
                ),
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=2),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        # Mock database
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        mock_database.session.return_value.__aexit__.return_value = None

        # Act - Test fairness mode with mixed retry counts
        with (
            patch(
                "services.cj_assessment_service.cj_core_logic.batch_pool_manager.get_batch_state"
            ) as mock_get_batch_state,
            patch(
                "services.cj_assessment_service.cj_core_logic.batch_pool_manager.update_batch_processing_metadata"
            ) as mock_update_metadata,
        ):
            mock_get_batch_state.return_value = batch_state
            retry_tasks = await batch_processor.form_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,
            )

            # Assert
            assert retry_tasks is not None
            assert len(retry_tasks) == 1  # Only 1 eligible (other at max retries)

            # Verify metadata update was called (for permanently failed tracking)
            mock_update_metadata.assert_called_once()
