"""Unit tests for queue processor error handling with mock provider."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from common_core import LLMProviderType, QueueStatus
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail

from services.llm_provider_service.api_models import LLMComparisonRequest, LLMConfigOverrides
from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.queue_models import QueuedRequest


class TestQueueProcessorErrorHandling:
    """Tests for queue processor error handling."""

    @pytest.fixture
    def mock_orchestrator(self) -> AsyncMock:
        """Create mock orchestrator."""
        return AsyncMock()

    @pytest.fixture
    def mock_queue_manager(self) -> AsyncMock:
        """Create mock queue manager."""
        return AsyncMock()

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock()

    @pytest.fixture
    def mock_trace_context_manager(self) -> Mock:
        """Create mock trace context manager."""
        trace_manager = Mock(spec=TraceContextManagerImpl)
        # Create a mock context manager for restore_trace_context_for_queue_processing
        mock_span = Mock()
        mock_span.add_event = Mock()
        context_manager = Mock()
        context_manager.__enter__ = Mock(return_value=mock_span)
        context_manager.__exit__ = Mock(return_value=None)
        trace_manager.restore_trace_context_for_queue_processing.return_value = context_manager
        return trace_manager

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        settings = Settings()
        settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
        return settings

    @pytest.fixture
    def queue_processor(
        self,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
        settings: Settings,
    ) -> QueueProcessorImpl:
        """Create queue processor with mocked dependencies."""
        return QueueProcessorImpl(
            orchestrator=mock_orchestrator,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_process_request_handles_huleedu_error(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that queue processor handles HuleEduError without re-raising."""
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="Compare these essays",
            essay_a="Essay A content",
            essay_b="Essay B content",
            callback_topic="llm.comparison.callback",
            correlation_id=correlation_id,
            llm_config_overrides=LLMConfigOverrides(
                provider_override=LLMProviderType.MOCK,
            ),
        )

        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="llm.comparison.callback",
            trace_context={},
        )

        # Configure orchestrator to raise HuleEduError (simulating mock provider error)
        error_detail = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="Mock provider simulated error for testing",
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc),
            service="llm_provider_service",
            operation="mock_comparison_generation",
            details={"provider": "mock", "error_simulation": True},
        )

        mock_orchestrator.process_queued_request.side_effect = HuleEduError(error_detail)

        # Set retry count to max so next error causes immediate failure
        queued_request.retry_count = 3

        # Act - This should not raise an exception
        await queue_processor._process_request(queued_request)

        # Assert
        # Verify that the error was handled by updating status to FAILED
        mock_queue_manager.update_status.assert_any_call(
            queue_id=request_id,
            status=QueueStatus.FAILED,
            message="Mock provider simulated error for testing",
        )

        # Verify that a failure event was published
        mock_event_publisher.publish_llm_provider_failure.assert_called_once()
        call_args = mock_event_publisher.publish_llm_provider_failure.call_args
        assert call_args.kwargs["provider"] == "mock"
        assert call_args.kwargs["error_details"] == "Mock provider simulated error for testing"

    @pytest.mark.asyncio
    async def test_process_request_handles_unexpected_exception(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that queue processor handles unexpected exceptions without re-raising."""
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="Compare these essays",
            essay_a="Essay A content",
            essay_b="Essay B content",
            callback_topic="llm.comparison.callback",
            correlation_id=correlation_id,
        )

        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="llm.comparison.callback",
            trace_context={"traceparent": "00-1234567890abcdef-1234567890abcdef-01"},
        )

        # Configure orchestrator to raise unexpected exception
        mock_orchestrator.process_queued_request.side_effect = RuntimeError("Unexpected error")

        # Set retry count to max so next error causes immediate failure
        queued_request.retry_count = 3

        # Act - This should not raise an exception
        await queue_processor._process_request(queued_request)

        # Assert
        # Verify that the error was handled by updating status to FAILED
        mock_queue_manager.update_status.assert_any_call(
            queue_id=request_id,
            status=QueueStatus.FAILED,
            message="Processing failed: Unexpected error",
        )

        # Verify that a failure event was published
        mock_event_publisher.publish_llm_provider_failure.assert_called_once()
        call_args = mock_event_publisher.publish_llm_provider_failure.call_args
        assert call_args.kwargs["provider"] == "openai"  # Default provider for unexpected errors
        assert call_args.kwargs["error_details"] == "Processing failed: Unexpected error"

    @pytest.mark.asyncio
    async def test_process_request_successful_processing(
        self,
        queue_processor: QueueProcessorImpl,
        mock_orchestrator: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test successful request processing."""
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="Compare these essays",
            essay_a="Essay A content",
            essay_b="Essay B content",
            callback_topic="llm.comparison.callback",
            correlation_id=correlation_id,
        )

        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="llm.comparison.callback",
            trace_context={},
        )

        # Configure orchestrator to return successful response
        mock_orchestrator.process_queued_request.return_value = LLMOrchestratorResponse(
            winner="Essay A",
            justification="Essay A is better",
            confidence=0.85,
            provider=LLMProviderType.MOCK,
            model="mock-model-v1",
            correlation_id=correlation_id,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_estimate=0.01,
            response_time_ms=100,
        )

        # Act
        await queue_processor._process_request(queued_request)

        # Assert
        # Verify status was updated to PROCESSING then COMPLETED
        assert mock_queue_manager.update_status.call_count >= 2

        # Check for PROCESSING status
        mock_queue_manager.update_status.assert_any_call(
            queue_id=request_id,
            status=QueueStatus.PROCESSING,
        )

        # Check for COMPLETED status
        completed_calls = [
            call
            for call in mock_queue_manager.update_status.call_args_list
            if call.kwargs.get("status") == QueueStatus.COMPLETED
        ]
        assert len(completed_calls) == 1

        # Verify success event was published
        mock_event_publisher.publish_llm_request_completed.assert_called_once()
        call_args = mock_event_publisher.publish_llm_request_completed.call_args
        assert call_args.kwargs["success"] is True
