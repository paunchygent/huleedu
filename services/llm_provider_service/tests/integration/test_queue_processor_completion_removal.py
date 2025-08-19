"""
Integration test for queue processor request removal behavior.

Tests that queue processor properly removes completed and failed requests
from the queue to prevent clogging.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core import ErrorCode, EssayComparisonWinner, LLMProviderType, QueueStatus
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail

from services.llm_provider_service.api_models import LLMComparisonRequest
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.queue_models import QueuedRequest


class TestQueueProcessorCompletionRemoval:
    """Test that queue processor removes completed and failed requests."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Test settings with short retry limits."""
        settings = Settings()
        settings.QUEUE_MAX_RETRIES = 1  # Limit retries for faster testing
        settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
        return settings

    @pytest.fixture
    def mock_orchestrator(self) -> AsyncMock:
        """Mock LLM orchestrator."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_manager(self) -> AsyncMock:
        """Mock queue manager that tracks remove() calls."""
        mock = AsyncMock()
        mock.remove_calls = []  # Track remove calls

        # Track remove calls
        async def track_remove(queue_id: Any) -> bool:
            mock.remove_calls.append(queue_id)
            return True

        mock.remove = AsyncMock(side_effect=track_remove)
        mock.update_status = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher."""
        return AsyncMock()

    @pytest.fixture
    def trace_context_manager(self) -> TraceContextManagerImpl:
        """Real trace context manager."""
        return TraceContextManagerImpl()

    @pytest.fixture
    def queue_processor(
        self,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        trace_context_manager: TraceContextManagerImpl,
        settings: Settings,
    ) -> QueueProcessorImpl:
        """Queue processor with mocked dependencies."""
        return QueueProcessorImpl(
            orchestrator=mock_orchestrator,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=trace_context_manager,
            settings=settings,
        )

    @pytest.fixture
    def sample_request(self) -> QueuedRequest:
        """Sample queued request for testing."""
        correlation_id = uuid4()
        return QueuedRequest(
            queue_id=uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="Compare these essays",
                essay_a="Essay A content",
                essay_b="Essay B content",
                callback_topic="test.callback.topic",
                correlation_id=correlation_id,
            ),
            callback_topic="test.callback.topic",
            correlation_id=correlation_id,
            queued_at=datetime.now(timezone.utc),
            ttl=timedelta(hours=1),
            priority=5,
            status=QueueStatus.QUEUED,
            retry_count=0,
            size_bytes=1024,
        )

    @pytest.mark.asyncio
    async def test_successful_request_is_removed_from_queue(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        sample_request: QueuedRequest,
    ) -> None:
        """Test that successfully completed requests are removed from queue."""
        # Configure orchestrator to return success
        mock_result = LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="Test justification",
            confidence=0.8,
            provider=LLMProviderType.MOCK,
            model="test-model",
            correlation_id=sample_request.request_data.correlation_id,
            response_time_ms=100,
            token_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost_estimate=0.001,
            trace_id="test-trace",
        )
        mock_orchestrator.process_queued_request.return_value = mock_result

        # Process the request
        await queue_processor._process_request(sample_request)

        # Verify status was updated to COMPLETED
        mock_queue_manager.update_status.assert_called_with(
            queue_id=sample_request.queue_id,
            status=QueueStatus.COMPLETED,
            result_location=f"cache:{sample_request.queue_id}",
        )

        # CRITICAL: Verify remove was called to prevent queue clogging
        assert sample_request.queue_id in mock_queue_manager.remove_calls

    @pytest.mark.asyncio
    async def test_permanently_failed_request_is_removed_from_queue(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        sample_request: QueuedRequest,
    ) -> None:
        """Test that permanently failed requests are removed from queue."""
        # Set retry count to max to ensure permanent failure
        sample_request.retry_count = queue_processor.settings.QUEUE_MAX_RETRIES

        # Configure orchestrator to raise non-retryable error
        error_detail = create_test_error_detail(
            error_code=ErrorCode.VALIDATION_ERROR,  # Non-retryable
            message="Permanent validation error",
            service="llm_provider_service",
            operation="process_queued_request",
            correlation_id=sample_request.request_data.correlation_id,
            details={"provider": "mock"},
        )
        mock_orchestrator.process_queued_request.side_effect = HuleEduError(error_detail)

        # Process the request
        await queue_processor._process_request(sample_request)

        # Verify status was updated to FAILED
        mock_queue_manager.update_status.assert_called_with(
            queue_id=sample_request.queue_id,
            status=QueueStatus.FAILED,
            message=error_detail.message,
        )

        # CRITICAL: Verify remove was called to prevent queue clogging
        assert sample_request.queue_id in mock_queue_manager.remove_calls

    @pytest.mark.asyncio
    async def test_retryable_request_is_removed_then_requeued(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        sample_request: QueuedRequest,
    ) -> None:
        """Test that retryable requests are removed then re-enqueued."""
        # Set retry count below max to enable retry
        sample_request.retry_count = 0

        # Configure orchestrator to raise retryable error
        error_detail = create_test_error_detail(
            error_code=ErrorCode.RATE_LIMIT,  # Retryable
            message="Rate limit exceeded",
            service="llm_provider_service",
            operation="process_queued_request",
            correlation_id=sample_request.request_data.correlation_id,
            details={"provider": "mock"},
        )
        mock_orchestrator.process_queued_request.side_effect = HuleEduError(error_detail)

        # Process the request
        await queue_processor._process_request(sample_request)

        # Verify remove was called before re-enqueuing
        assert sample_request.queue_id in mock_queue_manager.remove_calls

        # Verify enqueue was called for retry
        mock_queue_manager.enqueue.assert_called_once()

        # Verify the retry count was incremented
        enqueued_request = mock_queue_manager.enqueue.call_args[0][0]
        assert enqueued_request.retry_count == 1

    @pytest.mark.asyncio
    async def test_multiple_completions_dont_clog_queue(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
    ) -> None:
        """Test that multiple completed requests are all removed from queue."""
        # Create multiple requests
        requests = []
        for i in range(5):
            correlation_id = uuid4()
            request = QueuedRequest(
                queue_id=uuid4(),
                request_data=LLMComparisonRequest(
                    user_prompt=f"Compare essays {i}",
                    essay_a=f"Essay A {i}",
                    essay_b=f"Essay B {i}",
                    callback_topic="test.callback.topic",
                    correlation_id=correlation_id,
                ),
                callback_topic="test.callback.topic",
                correlation_id=correlation_id,
                queued_at=datetime.now(timezone.utc),
                ttl=timedelta(hours=1),
                priority=5,
                status=QueueStatus.QUEUED,
                retry_count=0,
                size_bytes=1024,
            )
            requests.append(request)

        # Configure orchestrator to succeed for all requests
        mock_result = LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="Test justification",
            confidence=0.8,
            provider=LLMProviderType.MOCK,
            model="test-model",
            correlation_id=uuid4(),
            response_time_ms=100,
            token_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost_estimate=0.001,
            trace_id="test-trace",
        )
        mock_orchestrator.process_queued_request.return_value = mock_result

        # Process all requests
        for request in requests:
            await queue_processor._process_request(request)

        # CRITICAL: Verify all requests were removed from queue
        for request in requests:
            assert request.queue_id in mock_queue_manager.remove_calls

        # Verify we have exactly 5 remove calls
        assert len(mock_queue_manager.remove_calls) == 5
