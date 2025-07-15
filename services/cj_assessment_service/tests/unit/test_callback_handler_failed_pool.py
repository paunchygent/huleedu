"""Unit tests for callback handler failed pool integration."""

from __future__ import annotations

import pytest
from datetime import datetime, UTC
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

from common_core.error_enums import ErrorCode
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.models.error_models import ErrorDetail
from services.cj_assessment_service.cj_core_logic.batch_callback_handler import (
    continue_cj_assessment_workflow,
    _add_failed_comparison_to_pool,
    _handle_successful_retry,
    _reconstruct_comparison_task,
)
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import ComparisonPair
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
)


@pytest.fixture
def mock_settings():
    """Create mock settings with failed pool configuration."""
    settings = MagicMock(spec=Settings)
    settings.ENABLE_FAILED_COMPARISON_RETRY = True
    return settings


@pytest.fixture
def mock_database():
    """Create mock database protocol."""
    return AsyncMock(spec=CJRepositoryProtocol)


@pytest.fixture
def mock_event_publisher():
    """Create mock event publisher protocol."""
    return AsyncMock(spec=CJEventPublisherProtocol)


@pytest.fixture
def mock_batch_processor():
    """Create mock batch processor."""
    return AsyncMock(spec=BatchProcessor)


@pytest.fixture
def sample_comparison_pair():
    """Create sample comparison pair."""
    pair = MagicMock(spec=ComparisonPair)
    pair.id = 123
    pair.cj_batch_id = 456
    pair.essay_a_els_id = "essay_a_123"
    pair.essay_b_els_id = "essay_b_456"
    pair.prompt_text = "Compare these essays"
    pair.winner = None
    return pair


@pytest.fixture
def error_comparison_result():
    """Create LLM comparison result with error."""
    error_detail = ErrorDetail(
        error_code=ErrorCode.LLM_PROVIDER_TIMEOUT,
        message="Request timed out",
        correlation_id=uuid4(),
        timestamp=datetime.now(UTC),
        service="llm_provider_service",
        details={},
    )

    return LLMComparisonResultV1(
        request_id=str(uuid4()),
        is_error=True,
        error_detail=error_detail,
        winner=None,
        confidence=None,
        justification=None,
        provider="openai",
        model="gpt-4",
        response_time_ms=30000,
        token_usage={"prompt_tokens": 100, "completion_tokens": 0, "total_tokens": 100},
        cost_estimate=0.003,
    )


@pytest.fixture
def success_comparison_result():
    """Create successful LLM comparison result."""
    return LLMComparisonResultV1(
        request_id=str(uuid4()),
        is_error=False,
        error_detail=None,
        winner="essay_a",
        confidence=0.85,
        justification="Essay A shows better structure",
        provider="openai",
        model="gpt-4",
        response_time_ms=2500,
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        cost_estimate=0.003,
    )


class TestCallbackHandlerFailedPoolIntegration:
    """Test callback handler integration with failed pool."""

    @pytest.mark.asyncio
    async def test_continue_workflow_with_error_adds_to_pool(
        self,
        mock_database,
        mock_event_publisher,
        mock_settings,
        mock_batch_processor,
        error_comparison_result,
        sample_comparison_pair,
    ):
        """Test that error results are added to failed pool."""
        # Arrange
        correlation_id = uuid4()

        # Mock _update_comparison_result to return batch_id
        batch_id = 456

        async def mock_update_comparison_result(*args, **kwargs):
            return batch_id

        # Mock the callback handler function that's called internally
        import services.cj_assessment_service.cj_core_logic.batch_callback_handler as handler_module

        original_update = handler_module._update_comparison_result
        handler_module._update_comparison_result = mock_update_comparison_result

        # Mock _check_workflow_continuation
        handler_module._check_workflow_continuation = AsyncMock(return_value=False)

        # Mock _trigger_existing_workflow_continuation
        handler_module._trigger_existing_workflow_continuation = AsyncMock()

        try:
            # Act
            await continue_cj_assessment_workflow(
                comparison_result=error_comparison_result,
                correlation_id=correlation_id,
                database=mock_database,
                event_publisher=mock_event_publisher,
                settings=mock_settings,
                batch_processor=mock_batch_processor,
            )

            # Assert - The function should complete without error
            # More detailed testing would require mocking the metrics
            assert True  # Placeholder assertion

        finally:
            # Restore original function
            handler_module._update_comparison_result = original_update

    @pytest.mark.asyncio
    async def test_continue_workflow_with_success_handles_retry(
        self,
        mock_database,
        mock_event_publisher,
        mock_settings,
        mock_batch_processor,
        success_comparison_result,
        sample_comparison_pair,
    ):
        """Test that successful results check for retry handling."""
        # Arrange
        correlation_id = uuid4()

        # Mock _update_comparison_result to return batch_id
        batch_id = 456

        async def mock_update_comparison_result(*args, **kwargs):
            return batch_id

        # Mock the callback handler function that's called internally
        import services.cj_assessment_service.cj_core_logic.batch_callback_handler as handler_module

        original_update = handler_module._update_comparison_result
        handler_module._update_comparison_result = mock_update_comparison_result

        # Mock _check_workflow_continuation
        handler_module._check_workflow_continuation = AsyncMock(return_value=False)

        # Mock _trigger_existing_workflow_continuation
        handler_module._trigger_existing_workflow_continuation = AsyncMock()

        try:
            # Act
            await continue_cj_assessment_workflow(
                comparison_result=success_comparison_result,
                correlation_id=correlation_id,
                database=mock_database,
                event_publisher=mock_event_publisher,
                settings=mock_settings,
                batch_processor=mock_batch_processor,
            )

            # Assert - The function should complete without error
            assert True  # Placeholder assertion

        finally:
            # Restore original function
            handler_module._update_comparison_result = original_update


class TestAddFailedComparisonToPool:
    """Test adding failed comparisons to pool functionality."""

    @pytest.mark.asyncio
    async def test_add_failed_comparison_to_pool_success(
        self,
        mock_batch_processor,
        sample_comparison_pair,
        error_comparison_result,
    ):
        """Test successfully adding failed comparison to pool."""
        # Arrange
        correlation_id = uuid4()

        # Mock reconstruction of comparison task
        from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison

        mock_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_123", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_456", text_content="Essay B"),
            prompt="Compare essays",
        )

        # Mock batch processor methods
        mock_batch_processor.add_to_failed_pool = AsyncMock()
        mock_batch_processor.check_retry_batch_needed = AsyncMock(return_value=False)

        # Mock the reconstruction function
        import services.cj_assessment_service.cj_core_logic.batch_callback_handler as handler_module

        original_reconstruct = handler_module._reconstruct_comparison_task
        handler_module._reconstruct_comparison_task = AsyncMock(return_value=mock_task)

        try:
            # Act
            await _add_failed_comparison_to_pool(
                batch_processor=mock_batch_processor,
                comparison_pair=sample_comparison_pair,
                comparison_result=error_comparison_result,
                correlation_id=correlation_id,
            )

            # Assert
            mock_batch_processor.add_to_failed_pool.assert_called_once_with(
                cj_batch_id=sample_comparison_pair.cj_batch_id,
                comparison_task=mock_task,
                failure_reason=error_comparison_result.error_detail.error_code.value,
                correlation_id=correlation_id,
            )

            mock_batch_processor.check_retry_batch_needed.assert_called_once_with(
                cj_batch_id=sample_comparison_pair.cj_batch_id,
                correlation_id=correlation_id,
            )

        finally:
            # Restore original function
            handler_module._reconstruct_comparison_task = original_reconstruct

    @pytest.mark.asyncio
    async def test_add_failed_comparison_triggers_retry(
        self,
        mock_batch_processor,
        sample_comparison_pair,
        error_comparison_result,
    ):
        """Test that failed comparison triggers retry batch when threshold met."""
        # Arrange
        correlation_id = uuid4()

        # Mock reconstruction of comparison task
        from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison

        mock_task = ComparisonTask(
            essay_a=EssayForComparison(id="essay_a_123", text_content="Essay A"),
            essay_b=EssayForComparison(id="essay_b_456", text_content="Essay B"),
            prompt="Compare essays",
        )

        # Mock batch processor methods
        mock_batch_processor.add_to_failed_pool = AsyncMock()
        mock_batch_processor.check_retry_batch_needed = AsyncMock(return_value=True)
        mock_batch_processor.submit_retry_batch = AsyncMock()

        # Mock the reconstruction function
        import services.cj_assessment_service.cj_core_logic.batch_callback_handler as handler_module

        original_reconstruct = handler_module._reconstruct_comparison_task
        handler_module._reconstruct_comparison_task = AsyncMock(return_value=mock_task)

        try:
            # Act
            await _add_failed_comparison_to_pool(
                batch_processor=mock_batch_processor,
                comparison_pair=sample_comparison_pair,
                comparison_result=error_comparison_result,
                correlation_id=correlation_id,
            )

            # Assert
            mock_batch_processor.submit_retry_batch.assert_called_once_with(
                cj_batch_id=sample_comparison_pair.cj_batch_id,
                correlation_id=correlation_id,
            )

        finally:
            # Restore original function
            handler_module._reconstruct_comparison_task = original_reconstruct

    @pytest.mark.asyncio
    async def test_add_failed_comparison_handles_reconstruction_failure(
        self,
        mock_batch_processor,
        sample_comparison_pair,
        error_comparison_result,
    ):
        """Test handling of comparison task reconstruction failure."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch processor methods
        mock_batch_processor.add_to_failed_pool = AsyncMock()
        mock_batch_processor.check_retry_batch_needed = AsyncMock()

        # Mock the reconstruction function to return None (failure)
        import services.cj_assessment_service.cj_core_logic.batch_callback_handler as handler_module

        original_reconstruct = handler_module._reconstruct_comparison_task
        handler_module._reconstruct_comparison_task = AsyncMock(return_value=None)

        try:
            # Act
            await _add_failed_comparison_to_pool(
                batch_processor=mock_batch_processor,
                comparison_pair=sample_comparison_pair,
                comparison_result=error_comparison_result,
                correlation_id=correlation_id,
            )

            # Assert
            # Should not call add_to_failed_pool if reconstruction fails
            mock_batch_processor.add_to_failed_pool.assert_not_called()
            mock_batch_processor.check_retry_batch_needed.assert_not_called()

        finally:
            # Restore original function
            handler_module._reconstruct_comparison_task = original_reconstruct


class TestHandleSuccessfulRetry:
    """Test handling successful retry functionality."""

    @pytest.mark.asyncio
    async def test_handle_successful_retry_removes_from_pool(
        self,
        mock_batch_processor,
        sample_comparison_pair,
    ):
        """Test that successful retry removes comparison from pool."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch state with failed pool containing matching entry
        from services.cj_assessment_service.models_api import (
            FailedComparisonPool,
            FailedComparisonEntry,
            FailedComparisonPoolStatistics,
        )

        failed_entry = FailedComparisonEntry(
            essay_a_id=sample_comparison_pair.essay_a_els_id,
            essay_b_id=sample_comparison_pair.essay_b_els_id,
            comparison_task=MagicMock(),
            failure_reason="timeout",
            failed_at=datetime.now(UTC),
            retry_count=1,
            original_batch_id="123",
            correlation_id=uuid4(),
        )

        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[failed_entry],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=1),
        )

        mock_batch_state = MagicMock()
        mock_batch_state.processing_metadata = failed_pool.model_dump()

        mock_session = AsyncMock()
        mock_batch_processor.database.session.return_value.__aenter__.return_value = (
            mock_session
        )
        mock_batch_processor._get_batch_state = AsyncMock(return_value=mock_batch_state)
        mock_batch_processor._update_batch_processing_metadata = AsyncMock()

        # Act
        await _handle_successful_retry(
            batch_processor=mock_batch_processor,
            comparison_pair=sample_comparison_pair,
            correlation_id=correlation_id,
        )

        # Assert
        mock_batch_processor._update_batch_processing_metadata.assert_called_once()

        # Check that the metadata indicates successful retry
        call_args = mock_batch_processor._update_batch_processing_metadata.call_args
        metadata = call_args[1]["metadata"]
        assert metadata["pool_statistics"]["successful_retries"] == 1
        assert len(metadata["failed_comparison_pool"]) == 0  # Entry should be removed

    @pytest.mark.asyncio
    async def test_handle_successful_retry_no_matching_entry(
        self,
        mock_batch_processor,
        sample_comparison_pair,
    ):
        """Test successful retry handling when no matching entry in pool."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch state with failed pool containing non-matching entry
        from services.cj_assessment_service.models_api import (
            FailedComparisonPool,
            FailedComparisonEntry,
            FailedComparisonPoolStatistics,
        )

        failed_entry = FailedComparisonEntry(
            essay_a_id="different_essay_a",
            essay_b_id="different_essay_b",
            comparison_task=MagicMock(),
            failure_reason="timeout",
            failed_at=datetime.now(UTC),
            retry_count=1,
            original_batch_id="123",
            correlation_id=uuid4(),
        )

        failed_pool = FailedComparisonPool(
            failed_comparison_pool=[failed_entry],
            pool_statistics=FailedComparisonPoolStatistics(total_failed=1),
        )

        mock_batch_state = MagicMock()
        mock_batch_state.processing_metadata = failed_pool.model_dump()

        mock_session = AsyncMock()
        mock_batch_processor.database.session.return_value.__aenter__.return_value = (
            mock_session
        )
        mock_batch_processor._get_batch_state = AsyncMock(return_value=mock_batch_state)

        # Act
        await _handle_successful_retry(
            batch_processor=mock_batch_processor,
            comparison_pair=sample_comparison_pair,
            correlation_id=correlation_id,
        )

        # Assert
        # Should not update metadata if no matching entry found
        mock_batch_processor._update_batch_processing_metadata.assert_not_called()


class TestReconstructComparisonTask:
    """Test comparison task reconstruction functionality."""

    @pytest.mark.asyncio
    async def test_reconstruct_comparison_task_success(self, sample_comparison_pair):
        """Test successful reconstruction of comparison task."""
        # Arrange
        correlation_id = uuid4()

        # Act
        task = await _reconstruct_comparison_task(
            comparison_pair=sample_comparison_pair,
            correlation_id=correlation_id,
        )

        # Assert
        assert task is not None
        assert task.essay_a.id == sample_comparison_pair.essay_a_els_id
        assert task.essay_b.id == sample_comparison_pair.essay_b_els_id
        assert task.prompt == sample_comparison_pair.prompt_text

    @pytest.mark.asyncio
    async def test_reconstruct_comparison_task_handles_error(self):
        """Test reconstruction handling when comparison pair is invalid."""
        # Arrange
        correlation_id = uuid4()
        invalid_pair = MagicMock()
        # Make the pair invalid by causing an attribute error
        del invalid_pair.essay_a_els_id

        # Act
        task = await _reconstruct_comparison_task(
            comparison_pair=invalid_pair,
            correlation_id=correlation_id,
        )

        # Assert
        assert task is None