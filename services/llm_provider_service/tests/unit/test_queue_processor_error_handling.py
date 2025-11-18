"""Unit tests for queue processor error handling with mock provider."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from common_core import (
    EssayComparisonWinner,
    LLMComparisonRequest,
    LLMProviderType,
    QueueStatus,
)
from common_core import (
    LLMConfigOverridesHTTP as LLMConfigOverrides,
)
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.exceptions import HuleEduError, raise_processing_error
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import ComparisonProcessorProtocol
from services.llm_provider_service.queue_models import QueuedRequest, QueueStats


@pytest.fixture
def mock_comparison_processor() -> AsyncMock:
    """Create mock comparison processor."""
    return AsyncMock(spec=ComparisonProcessorProtocol)


@pytest.fixture
def mock_queue_manager() -> AsyncMock:
    """Create mock queue manager."""
    manager = AsyncMock()
    manager.get_queue_stats = AsyncMock(
        return_value=QueueStats(
            current_size=0,
            max_size=1000,
            memory_usage_mb=0.0,
            max_memory_mb=100.0,
            usage_percent=0.0,
            queued_count=0,
            is_accepting_requests=True,
        )
    )
    return manager


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create mock event publisher."""
    return AsyncMock()


@pytest.fixture
def mock_trace_context_manager() -> Mock:
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
def settings() -> Settings:
    """Create test settings."""
    settings = Settings()
    settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
    return settings


class TestQueueProcessorErrorHandling:
    """Tests for queue processor error handling."""

    @pytest.fixture
    def queue_processor(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
        settings: Settings,
    ) -> QueueProcessorImpl:
        """Create queue processor with mocked dependencies."""
        return QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_process_request_handles_huleedu_error(
        self,
        queue_processor: QueueProcessorImpl,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that queue processor handles HuleEduError without re-raising."""
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
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

        mock_comparison_processor.process_comparison.side_effect = HuleEduError(error_detail)

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
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that queue processor handles unexpected exceptions without re-raising."""
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
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
        mock_comparison_processor.process_comparison.side_effect = RuntimeError("Unexpected error")

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
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test successful request processing."""
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
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

        # Configure comparison processor to return successful response
        mock_comparison_processor.process_comparison.return_value = LLMOrchestratorResponse(
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

    @pytest.mark.asyncio
    async def test_serial_bundle_mode_uses_batch_api(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
    ) -> None:
        """Serial bundle helper should call process_comparison_batch for bundled work."""
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE
        settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1

        queue_processor = QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
        )

        request_data = LLMComparisonRequest(
            user_prompt="prompt",
            callback_topic="topic",
            correlation_id=uuid.uuid4(),
            llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
        )
        queued_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="topic",
        )

        mock_queue_manager.update_status = AsyncMock()
        mock_queue_manager.remove = AsyncMock()
        mock_queue_manager.dequeue = AsyncMock(return_value=None)
        mock_comparison_processor.process_comparison_batch.return_value = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="A",
                confidence=0.5,
                provider=LLMProviderType.MOCK,
                model="mock",
                correlation_id=queued_request.queue_id,
                response_time_ms=10,
                token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "abc"},
            )
        ]
        setattr(queue_processor, "_publish_callback_event", AsyncMock())

        await queue_processor._process_request_serial_bundle(queued_request)

        mock_comparison_processor.process_comparison_batch.assert_called_once()
        mock_comparison_processor.process_comparison.assert_not_called()


class TestSerialBundleProcessing:
    """Focused tests for the serial bundle helper."""

    @pytest.mark.asyncio
    async def test_serial_bundle_collects_multiple_requests(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
    ) -> None:
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE
        settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 3

        queue_processor = QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
        )

        first_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-a",
                callback_topic="topic",
                correlation_id=uuid.uuid4(),
                llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
                metadata={"cj_llm_batching_mode": "serial_bundle"},
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        second_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-b",
                callback_topic="topic",
                correlation_id=uuid.uuid4(),
                llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
                metadata={"cj_llm_batching_mode": "serial_bundle"},
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        mock_queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])
        mock_queue_manager.update_status = AsyncMock()
        mock_queue_manager.remove = AsyncMock()
        setattr(queue_processor, "_publish_callback_event", AsyncMock())
        setattr(queue_processor, "_handle_request_success", AsyncMock())
        setattr(queue_processor, "_record_completion_metrics", Mock())

        mock_comparison_processor.process_comparison_batch.return_value = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="A",
                confidence=0.5,
                provider=LLMProviderType.MOCK,
                model="mock",
                correlation_id=first_request.queue_id,
                response_time_ms=10,
                token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "abc"},
            ),
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_B,
                justification="B",
                confidence=0.6,
                provider=LLMProviderType.MOCK,
                model="mock",
                correlation_id=second_request.queue_id,
                response_time_ms=12,
                token_usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "def"},
            ),
        ]

        await queue_processor._process_request_serial_bundle(first_request)

        mock_comparison_processor.process_comparison_batch.assert_awaited_once()
        assert queue_processor._pending_request is None
        handle_success_mock = cast(AsyncMock, getattr(queue_processor, "_handle_request_success"))
        assert handle_success_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_serial_bundle_defers_incompatible_request(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
    ) -> None:
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE

        queue_processor = QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
        )

        first_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-a",
                callback_topic="topic",
                llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )
        incompatible_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-b",
                callback_topic="topic",
                llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.OPENAI),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        mock_queue_manager.dequeue = AsyncMock(side_effect=[incompatible_request])
        mock_queue_manager.update_status = AsyncMock()
        mock_queue_manager.remove = AsyncMock()
        setattr(queue_processor, "_publish_callback_event", AsyncMock())
        setattr(queue_processor, "_handle_request_success", AsyncMock())
        setattr(queue_processor, "_record_completion_metrics", Mock())

        mock_comparison_processor.process_comparison_batch.return_value = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="A",
                confidence=0.5,
                provider=LLMProviderType.MOCK,
                model="mock",
                correlation_id=first_request.queue_id,
                response_time_ms=10,
                token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "abc"},
            )
        ]

        await queue_processor._process_request_serial_bundle(first_request)

        assert queue_processor._pending_request is incompatible_request
        mock_comparison_processor.process_comparison_batch.assert_awaited_once()
        awaited_call = mock_comparison_processor.process_comparison_batch.await_args
        assert len(awaited_call.args[0]) == 1

    @pytest.mark.asyncio
    async def test_serial_bundle_handles_batch_errors_per_request(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
    ) -> None:
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE

        queue_processor = QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
        )

        first_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-a",
                callback_topic="topic",
                llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )
        second_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-b",
                callback_topic="topic",
                llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        mock_queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])
        mock_queue_manager.update_status = AsyncMock()
        setattr(queue_processor, "_record_completion_metrics", Mock())
        setattr(queue_processor, "_handle_request_hule_error", AsyncMock())

        try:
            raise_processing_error(
                service="llm_provider_service",
                operation="serial_bundle_processing",
                message="provider error",
                correlation_id=first_request.queue_id,
            )
        except HuleEduError as error:
            mock_comparison_processor.process_comparison_batch.side_effect = error

        await queue_processor._process_request_serial_bundle(first_request)

        handle_error_mock = cast(AsyncMock, getattr(queue_processor, "_handle_request_hule_error"))
        assert handle_error_mock.await_count == 2


class TestQueueProcessorMetrics:
    """Tests for queue processor metrics semantics."""

    def test_expired_request_records_expiry_metrics_not_processing_or_callbacks(
        self,
    ) -> None:
        settings = Settings()
        settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
        queue_processor = QueueProcessorImpl(
            comparison_processor=AsyncMock(spec=ComparisonProcessorProtocol),
            queue_manager=AsyncMock(),
            event_publisher=AsyncMock(),
            trace_context_manager=Mock(spec=TraceContextManagerImpl),
            settings=settings,
        )

        queue_processor.queue_metrics = {
            "llm_queue_expiry_total": Mock(),
            "llm_queue_expiry_age_seconds": Mock(),
            "llm_queue_wait_time_seconds": Mock(),
            "llm_queue_processing_time_seconds": Mock(),
            "llm_comparison_callbacks_total": Mock(),
        }

        expiry_counter = queue_processor.queue_metrics["llm_queue_expiry_total"]
        expiry_age_hist = queue_processor.queue_metrics["llm_queue_expiry_age_seconds"]
        wait_hist = queue_processor.queue_metrics["llm_queue_wait_time_seconds"]
        proc_hist = queue_processor.queue_metrics["llm_queue_processing_time_seconds"]
        callbacks_counter = queue_processor.queue_metrics["llm_comparison_callbacks_total"]

        expiry_counter.labels.return_value = Mock()
        expiry_age_hist.labels.return_value = Mock()
        wait_hist.labels.return_value = Mock()
        proc_hist.labels.return_value = Mock()
        callbacks_counter.labels.return_value = Mock()

        request_data = LLMComparisonRequest(
            user_prompt="prompt",
            callback_topic="topic",
            correlation_id=uuid.uuid4(),
        )
        queued_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc) - timedelta(seconds=30),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="topic",
        )

        provider = LLMProviderType.MOCK

        queue_processor._record_expiry_metrics(
            request=queued_request,
            provider=provider,
            expiry_reason="ttl",
        )
        queue_processor._record_completion_metrics(
            provider=provider,
            result="expired",
            request=queued_request,
            processing_started=None,
        )

        expiry_counter.labels.assert_called_once_with(
            provider=provider.value,
            queue_processing_mode=queue_processor.queue_processing_mode.value,
            expiry_reason="ttl",
        )
        expiry_counter.labels.return_value.inc.assert_called_once_with()

        expiry_age_hist.labels.assert_called_once_with(
            provider=provider.value,
            queue_processing_mode=queue_processor.queue_processing_mode.value,
        )
        age_call = expiry_age_hist.labels.return_value.observe.call_args
        assert age_call is not None
        assert age_call.args[0] >= 0.0

        wait_hist.labels.assert_called_once_with(
            queue_processing_mode=queue_processor.queue_processing_mode.value,
            result="expired",
        )
        wait_hist.labels.return_value.observe.assert_called_once_with(  # type: ignore[call-arg]
            pytest.approx(wait_hist.labels.return_value.observe.call_args.args[0])
        )

        proc_hist.labels.return_value.observe.assert_not_called()
        callbacks_counter.labels.return_value.inc.assert_not_called()

    def test_success_request_records_processing_and_callbacks_metrics(
        self,
    ) -> None:
        settings = Settings()
        settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
        queue_processor = QueueProcessorImpl(
            comparison_processor=AsyncMock(spec=ComparisonProcessorProtocol),
            queue_manager=AsyncMock(),
            event_publisher=AsyncMock(),
            trace_context_manager=Mock(spec=TraceContextManagerImpl),
            settings=settings,
        )

        queue_processor.queue_metrics = {
            "llm_queue_expiry_total": Mock(),
            "llm_queue_expiry_age_seconds": Mock(),
            "llm_queue_wait_time_seconds": Mock(),
            "llm_queue_processing_time_seconds": Mock(),
            "llm_comparison_callbacks_total": Mock(),
        }

        wait_hist = queue_processor.queue_metrics["llm_queue_wait_time_seconds"]
        proc_hist = queue_processor.queue_metrics["llm_queue_processing_time_seconds"]
        callbacks_counter = queue_processor.queue_metrics["llm_comparison_callbacks_total"]

        wait_hist.labels.return_value = Mock()
        proc_hist.labels.return_value = Mock()
        callbacks_counter.labels.return_value = Mock()

        request_data = LLMComparisonRequest(
            user_prompt="prompt",
            callback_topic="topic",
            correlation_id=uuid.uuid4(),
        )
        queued_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="topic",
        )

        provider = LLMProviderType.MOCK

        queue_processor._record_completion_metrics(
            provider=provider,
            result="success",
            request=queued_request,
            processing_started=0.0,
        )

        wait_hist.labels.assert_called_once_with(
            queue_processing_mode=queue_processor.queue_processing_mode.value,
            result="success",
        )
        wait_hist.labels.return_value.observe.assert_called_once()

        proc_hist.labels.assert_called_once_with(provider=provider.value, status="success")
        proc_hist.labels.return_value.observe.assert_called_once()

        callbacks_counter.labels.assert_called_once_with(
            queue_processing_mode=queue_processor.queue_processing_mode.value,
            result="success",
        )
        callbacks_counter.labels.return_value.inc.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_serial_bundle_metrics_emitted_for_serial_mode(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
    ) -> None:
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE

        queue_processor = QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
        )

        queue_processor.queue_metrics = {
            "llm_serial_bundle_calls_total": Mock(),
            "llm_serial_bundle_items_per_call": Mock(),
        }

        calls_counter = queue_processor.queue_metrics["llm_serial_bundle_calls_total"]
        items_hist = queue_processor.queue_metrics["llm_serial_bundle_items_per_call"]

        calls_counter.labels.return_value = Mock()
        items_hist.labels.return_value = Mock()

        first_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-a",
                callback_topic="topic",
                correlation_id=uuid.uuid4(),
                llm_config_overrides=LLMConfigOverrides(
                    provider_override=LLMProviderType.MOCK,
                    model_override="mock-model-v1",
                ),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        second_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-b",
                callback_topic="topic",
                correlation_id=uuid.uuid4(),
                llm_config_overrides=LLMConfigOverrides(
                    provider_override=LLMProviderType.MOCK,
                    model_override="mock-model-v1",
                ),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        mock_queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])
        mock_queue_manager.update_status = AsyncMock()
        mock_queue_manager.remove = AsyncMock()
        setattr(queue_processor, "_publish_callback_event", AsyncMock())
        setattr(queue_processor, "_handle_request_success", AsyncMock())
        setattr(queue_processor, "_record_completion_metrics", Mock())

        mock_comparison_processor.process_comparison_batch.return_value = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="A",
                confidence=0.5,
                provider=LLMProviderType.MOCK,
                model="mock-model-v1",
                correlation_id=first_request.queue_id,
                response_time_ms=10,
                token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "abc"},
            ),
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_B,
                justification="B",
                confidence=0.6,
                provider=LLMProviderType.MOCK,
                model="mock-model-v1",
                correlation_id=second_request.queue_id,
                response_time_ms=12,
                token_usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "def"},
            ),
        ]

        await queue_processor._process_request_serial_bundle(first_request)

        calls_counter.labels.assert_called_once_with(
            provider="mock",
            model="mock-model-v1",
        )
        calls_counter.labels.return_value.inc.assert_called_once_with()

        items_hist.labels.assert_called_once_with(
            provider="mock",
            model="mock-model-v1",
        )
        items_hist.labels.return_value.observe.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_serial_bundle_metrics_not_emitted_for_per_request_mode(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
    ) -> None:
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.PER_REQUEST

        queue_processor = QueueProcessorImpl(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
        )

        queue_processor.queue_metrics = {
            "llm_serial_bundle_calls_total": Mock(),
            "llm_serial_bundle_items_per_call": Mock(),
        }

        calls_counter = queue_processor.queue_metrics["llm_serial_bundle_calls_total"]
        items_hist = queue_processor.queue_metrics["llm_serial_bundle_items_per_call"]

        calls_counter.labels.return_value = Mock()
        items_hist.labels.return_value = Mock()

        first_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="prompt-a",
                callback_topic="topic",
                correlation_id=uuid.uuid4(),
                llm_config_overrides=LLMConfigOverrides(
                    provider_override=LLMProviderType.MOCK,
                    model_override="mock-model-v1",
                ),
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=10,
            callback_topic="topic",
        )

        mock_queue_manager.dequeue = AsyncMock(return_value=None)
        mock_queue_manager.update_status = AsyncMock()
        mock_queue_manager.remove = AsyncMock()
        setattr(queue_processor, "_publish_callback_event", AsyncMock())
        setattr(queue_processor, "_handle_request_success", AsyncMock())
        setattr(queue_processor, "_record_completion_metrics", Mock())

        mock_comparison_processor.process_comparison_batch.return_value = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="A",
                confidence=0.5,
                provider=LLMProviderType.MOCK,
                model="mock-model-v1",
                correlation_id=first_request.queue_id,
                response_time_ms=10,
                token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                cost_estimate=0.0,
                metadata={"prompt_sha256": "abc"},
            ),
        ]

        await queue_processor._process_request_serial_bundle(first_request)

        calls_counter.labels.assert_not_called()
        items_hist.labels.assert_not_called()


class TestQueueProcessorMetadataEnrichment:
    """Tests for provider-side metadata enrichment on queued requests."""

    def _create_queue_processor(
        self,
        *,
        mode: QueueProcessingMode,
    ) -> QueueProcessorImpl:
        settings = Settings()
        settings.QUEUE_PROCESSING_MODE = mode
        return QueueProcessorImpl(
            comparison_processor=AsyncMock(spec=ComparisonProcessorProtocol),
            queue_manager=AsyncMock(),
            event_publisher=AsyncMock(),
            trace_context_manager=Mock(spec=TraceContextManagerImpl),
            settings=settings,
            queue_processing_mode=mode,
        )

    def test_enrich_request_metadata_preserves_existing_keys_and_adds_provider_model_and_mode(
        self,
    ) -> None:
        queue_processor = self._create_queue_processor(
            mode=QueueProcessingMode.PER_REQUEST,
        )

        base_metadata = {
            "essay_a_id": "essay-a",
            "essay_b_id": "essay-b",
            "bos_batch_id": "bos-123",
            "cj_batch_id": "42",
            "cj_source": "eng5_runner",
            "cj_request_type": "cj_comparison",
            "cj_llm_batching_mode": "serial_bundle",
        }

        request_data = LLMComparisonRequest(
            user_prompt="prompt",
            callback_topic="topic",
            correlation_id=uuid.uuid4(),
            llm_config_overrides=LLMConfigOverrides(
                provider_override=LLMProviderType.MOCK,
                model_override="mock-model-v1",
            ),
            metadata=base_metadata.copy(),
        )

        queued_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="topic",
        )

        queue_processor._enrich_request_metadata(
            queued_request,
            provider=LLMProviderType.MOCK,
            model="mock-model-v1",
        )

        metadata = queued_request.request_data.metadata or {}

        # Existing keys preserved
        for key, value in base_metadata.items():
            assert metadata[key] == value

        # Additive provider-side keys
        assert metadata["resolved_provider"] == LLMProviderType.MOCK.value
        assert metadata["queue_processing_mode"] == queue_processor.queue_processing_mode.value
        assert metadata["resolved_model"] == "mock-model-v1"

    def test_enrich_request_metadata_omits_resolved_model_when_not_provided_and_uses_mode_label(
        self,
    ) -> None:
        queue_processor = self._create_queue_processor(
            mode=QueueProcessingMode.SERIAL_BUNDLE,
        )

        request_data = LLMComparisonRequest(
            user_prompt="prompt",
            callback_topic="topic",
            correlation_id=uuid.uuid4(),
        )

        queued_request = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="topic",
        )

        queue_processor._enrich_request_metadata(
            queued_request,
            provider=LLMProviderType.OPENAI,
            model=None,
        )

        metadata = queued_request.request_data.metadata or {}

        assert metadata["resolved_provider"] == LLMProviderType.OPENAI.value
        assert metadata["queue_processing_mode"] == queue_processor.queue_processing_mode.value
        assert "resolved_model" not in metadata
