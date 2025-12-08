"""Unit tests for retry logic and batch formation functionality."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.models_api import ComparisonTask

from services.cj_assessment_service.cj_core_logic.batch_submission import (
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


class TestFailedComparisonPoolRetryCheck:
    """Test checking if retry batch is needed."""

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_disabled(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_settings: Settings,
    ) -> None:
        """Test retry check when retry is disabled."""
        # Arrange
        mock_settings.ENABLE_FAILED_COMPARISON_RETRY = False
        cj_batch_id = 123
        correlation_id = uuid4()

        # Act
        result = await batch_pool_manager.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_threshold_met(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_batch_repo: AsyncMock,
    ) -> None:
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

        mock_batch_repo.get_batch_state_for_update.return_value = batch_state

        result = await batch_pool_manager.check_retry_batch_needed(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_check_retry_batch_needed_threshold_not_met(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_batch_repo: AsyncMock,
    ) -> None:
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

        mock_batch_repo.get_batch_state_for_update.return_value = batch_state

        result = await batch_pool_manager.check_retry_batch_needed(
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
        batch_pool_manager: BatchPoolManager,
        mock_batch_repo: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
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

        mock_batch_repo.get_batch_state_for_update.return_value = batch_state

        retry_tasks = await batch_pool_manager.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert retry_tasks is not None
        assert len(retry_tasks) == 6  # All eligible failures should be included
        assert all(isinstance(task, ComparisonTask) for task in retry_tasks)

    @pytest.mark.asyncio
    async def test_form_retry_batch_max_retry_reached(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_batch_repo: AsyncMock,
        sample_comparison_task: ComparisonTask,
        mock_settings: Settings,
    ) -> None:
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

        mock_batch_repo.get_batch_state_for_update.return_value = batch_state

        retry_tasks = await batch_pool_manager.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert retry_tasks is None  # No eligible failures

    @pytest.mark.asyncio
    async def test_form_retry_batch_partial_eligibility(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_batch_repo: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test forming retry batch when some comparisons are ineligible."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Create mixed batch state: some eligible, some at max retries
        sample_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_1", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_1", text_content="Essay B"),
            prompt="Compare essays",
        )

        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[
                # Eligible entries (retry_count < MAX_RETRY_ATTEMPTS)
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_{i}",
                    essay_b_id=f"essay_b_{i}",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=1,  # Eligible
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(4)
            ]
            + [
                # Ineligible entries (at max retry count)
                FailedComparisonEntry(
                    essay_a_id=f"essay_a_max_{i}",
                    essay_b_id=f"essay_b_max_{i}",
                    comparison_task=sample_task,
                    failure_reason="timeout",
                    failed_at=datetime.now(UTC),
                    retry_count=mock_settings.MAX_RETRY_ATTEMPTS,  # Ineligible
                    original_batch_id="123",
                    correlation_id=uuid4(),
                )
                for i in range(3)
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=7),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        mock_batch_repo.get_batch_state_for_update.return_value = batch_state

        # Should return None because only 4 eligible (below threshold of 5)
        retry_tasks = await batch_pool_manager.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert retry_tasks is None  # Below threshold despite total count > 5


class TestFailedComparisonPoolSubmitRetry:
    """Test submitting retry batches."""

    @pytest.mark.asyncio
    async def test_submit_retry_batch_success(
        self,
        batch_retry_processor: BatchRetryProcessor,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test successfully submitting retry batch."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock form_retry_batch to return tasks
        retry_tasks = [sample_comparison_task]
        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        with (
            patch.object(
                batch_retry_processor.pool_manager, "form_retry_batch", new_callable=AsyncMock
            ) as mock_form_retry,
            patch.object(
                batch_retry_processor.batch_submitter,
                "submit_comparison_batch",
                new_callable=AsyncMock,
            ) as mock_submit,
            patch(
                "services.cj_assessment_service.metrics.get_business_metrics"
            ) as mock_get_metrics,
        ):
            mock_form_retry.return_value = retry_tasks
            mock_submit.return_value = submission_result
            mock_metric = MagicMock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            with patch.object(
                batch_retry_processor,
                "_load_processing_metadata",
                AsyncMock(return_value={"llm_overrides": {}, "original_request": {}}),
            ):
                # Act
                result = await batch_retry_processor.submit_retry_batch(
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )

            # Assert
            assert result is not None
            assert result.total_submitted == 1
            mock_form_retry.assert_called_once()
            mock_submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_retry_batch_disabled(
        self,
        batch_retry_processor: BatchRetryProcessor,
        mock_settings: Settings,
    ) -> None:
        """Test submitting retry batch when retry is disabled."""
        # Arrange
        mock_settings.ENABLE_FAILED_COMPARISON_RETRY = False
        cj_batch_id = 123
        correlation_id = uuid4()

        # Act
        result = await batch_retry_processor.submit_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_submit_retry_batch_no_tasks(
        self,
        batch_retry_processor: BatchRetryProcessor,
    ) -> None:
        """Test submitting retry batch when no tasks are available."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Mock form_retry_batch to return None (no tasks)
        with patch.object(
            batch_retry_processor.pool_manager, "form_retry_batch", new_callable=AsyncMock
        ) as mock_form_retry:
            mock_form_retry.return_value = None

            # Act
            result = await batch_retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is None
            mock_form_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_retry_batch_with_overrides(
        self,
        batch_retry_processor: BatchRetryProcessor,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test submitting retry batch with model overrides."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        model_override = "test-model"
        temperature_override = 0.7
        max_tokens_override = 1000

        # Mock dependencies
        retry_tasks = [sample_comparison_task]
        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        with (
            patch.object(
                batch_retry_processor.pool_manager, "form_retry_batch", new_callable=AsyncMock
            ) as mock_form_retry,
            patch.object(
                batch_retry_processor.batch_submitter,
                "submit_comparison_batch",
                new_callable=AsyncMock,
            ) as mock_submit,
            patch(
                "services.cj_assessment_service.metrics.get_business_metrics"
            ) as mock_get_metrics,
        ):
            mock_form_retry.return_value = retry_tasks
            mock_submit.return_value = submission_result
            mock_metric = MagicMock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            with patch.object(
                batch_retry_processor,
                "_load_processing_metadata",
                AsyncMock(return_value={"llm_overrides": {}, "original_request": {}}),
            ):
                # Act
                result = await batch_retry_processor.submit_retry_batch(
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                    model_override=model_override,
                    temperature_override=temperature_override,
                    max_tokens_override=max_tokens_override,
                )

            # Assert
            assert result is not None
            mock_submit.assert_called_once()

            # Verify overrides were passed
            call_args = mock_submit.call_args
            assert call_args is not None
            kwargs = call_args[1]
            assert kwargs["model_override"] == model_override
            assert kwargs["temperature_override"] == temperature_override
            assert kwargs["max_tokens_override"] == max_tokens_override
            assert kwargs["system_prompt_override"] is None

    @pytest.mark.asyncio
    async def test_retry_batch_metadata_includes_capped_preferred_bundle_size(
        self,
        batch_retry_processor: BatchRetryProcessor,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Retry batch metadata should carry capped preferred_bundle_size hint."""
        cj_batch_id = 123
        correlation_id = uuid4()

        # Large retry wave size that should be capped at 64 in metadata.
        retry_tasks = [sample_comparison_task] * 80
        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=len(retry_tasks),
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        with (
            patch.object(
                batch_retry_processor.pool_manager,
                "form_retry_batch",
                new_callable=AsyncMock,
            ) as mock_form_retry,
            patch.object(
                batch_retry_processor.batch_submitter,
                "submit_comparison_batch",
                new_callable=AsyncMock,
            ) as mock_submit,
            patch(
                "services.cj_assessment_service.metrics.get_business_metrics"
            ) as mock_get_metrics,
            patch.object(
                batch_retry_processor,
                "_load_processing_metadata",
                AsyncMock(
                    return_value={
                        "llm_overrides": {},
                        "original_request": {"cj_source": "els"},
                    }
                ),
            ),
        ):
            mock_form_retry.return_value = retry_tasks
            mock_submit.return_value = submission_result
            mock_metric = MagicMock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Ensure metadata hints are enabled so preferred_bundle_size is emitted.
            batch_retry_processor.settings.ENABLE_LLM_BATCHING_METADATA_HINTS = True

            result = await batch_retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            assert result is not None
            call_args = mock_submit.call_args
            assert call_args is not None
            metadata_context = call_args[1]["metadata_context"]
            assert metadata_context["preferred_bundle_size"] == 64


class TestRetryBatchSizing:
    """Test retry batch sizing logic."""

    @pytest.mark.asyncio
    async def test_retry_batch_respects_size_limit(
        self,
        batch_pool_manager: BatchPoolManager,
        mock_batch_repo: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test that retry batch respects the RETRY_BATCH_SIZE setting."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Set up many eligible failures (more than RETRY_BATCH_SIZE)
        many_failures = 15  # More than RETRY_BATCH_SIZE (10)
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
                for i in range(many_failures)
            ],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=many_failures),
        )

        batch_state = MagicMock(spec=CJBatchState)
        batch_state.processing_metadata = failed_pool.model_dump()

        mock_batch_repo.get_batch_state_for_update.return_value = batch_state

        retry_tasks = await batch_pool_manager.form_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert retry_tasks is not None
        assert len(retry_tasks) == mock_settings.RETRY_BATCH_SIZE  # Limited by RETRY_BATCH_SIZE
        assert len(retry_tasks) < many_failures  # Not all failures processed
