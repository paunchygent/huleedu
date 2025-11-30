"""Unit tests for QueuedRequestExecutor."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from common_core import (
    EssayComparisonWinner,
    LLMComparisonRequest,
    LLMConfigOverridesHTTP,
    LLMProviderType,
    QueueStatus,
)
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_request_executor import (
    QueuedRequestExecutor,
)
from services.llm_provider_service.implementations.queue_tracing_enricher import (
    QueueTracingEnricher,
)
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import ComparisonProcessorProtocol
from services.llm_provider_service.queue_models import QueuedRequest


@pytest.fixture
def mock_comparison_processor() -> AsyncMock:
    return AsyncMock(spec=ComparisonProcessorProtocol)


@pytest.fixture
def mock_queue_manager() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_trace_context_manager() -> Mock:
    trace_manager = Mock(spec=TraceContextManagerImpl)
    mock_span = Mock()
    mock_span.add_event = Mock()
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=mock_span)
    context_manager.__exit__ = Mock(return_value=None)
    trace_manager.restore_trace_context_for_queue_processing.return_value = context_manager
    return trace_manager


@pytest.fixture
def settings() -> Settings:
    settings = Settings()
    settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
    return settings


@pytest.fixture
def mock_metrics() -> Mock:
    return Mock(spec=QueueProcessorMetrics)


@pytest.fixture
def mock_tracing_enricher() -> Mock:
    return Mock(spec=QueueTracingEnricher)


class TestQueuedRequestExecutor:
    @pytest.fixture
    def executor(
        self,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_trace_context_manager: Mock,
        settings: Settings,
        mock_metrics: Mock,
        mock_tracing_enricher: Mock,
    ) -> QueuedRequestExecutor:
        return QueuedRequestExecutor(
            comparison_processor=mock_comparison_processor,
            queue_manager=mock_queue_manager,
            event_publisher=mock_event_publisher,
            trace_context_manager=mock_trace_context_manager,
            settings=settings,
            queue_processing_mode=QueueProcessingMode.PER_REQUEST,
            metrics=mock_metrics,
            tracing_enricher=mock_tracing_enricher,
        )

    @pytest.mark.asyncio
    async def test_execute_request_success(
        self,
        executor: QueuedRequestExecutor,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_metrics: Mock,
    ) -> None:
        # Arrange
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()
        request_data = LLMComparisonRequest(
            user_prompt="test prompt",
            callback_topic="test.topic",
            correlation_id=correlation_id,
        )
        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=100,
            callback_topic="test.topic",
        )

        mock_comparison_processor.process_comparison.return_value = LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="test",
            confidence=0.9,
            provider=LLMProviderType.MOCK,
            model="mock-model",
            correlation_id=correlation_id,
            response_time_ms=100,
            token_usage={},
            cost_estimate=0.0,
        )

        # Act
        outcome = await executor.execute_request(queued_request)

        # Assert
        assert outcome.result == "success"
        assert outcome.provider == LLMProviderType.MOCK
        mock_queue_manager.update_status.assert_any_call(
            queue_id=request_id, status=QueueStatus.PROCESSING
        )
        mock_queue_manager.update_status.assert_any_call(
            queue_id=request_id, status=QueueStatus.COMPLETED, result_location=f"cache:{request_id}"
        )
        mock_event_publisher.publish_llm_request_completed.assert_called_once()
        mock_metrics.record_cache_scope_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_request_hule_error(
        self,
        executor: QueuedRequestExecutor,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        # Arrange
        request_id = uuid.uuid4()
        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=LLMComparisonRequest(
                user_prompt="test", callback_topic="topic", correlation_id=uuid.uuid4()
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=100,
            callback_topic="topic",
        )

        error_detail = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="Test error",
            correlation_id=queued_request.request_data.correlation_id,
            timestamp=datetime.now(timezone.utc),
            service="test",
            operation="test",
        )
        mock_comparison_processor.process_comparison.side_effect = HuleEduError(error_detail)
        queued_request.retry_count = 3  # Max retries

        # Act
        outcome = await executor.execute_request(queued_request)

        # Assert
        assert outcome.result == "failure"
        mock_queue_manager.update_status.assert_any_call(
            queue_id=request_id, status=QueueStatus.FAILED, message="Test error"
        )
        mock_event_publisher.publish_llm_provider_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_serial_bundle_success(
        self,
        executor: QueuedRequestExecutor,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
    ) -> None:
        # Arrange
        executor.queue_processing_mode = QueueProcessingMode.SERIAL_BUNDLE
        request1 = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="1", callback_topic="topic", correlation_id=uuid.uuid4()
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=100,
            callback_topic="topic",
        )
        request2 = QueuedRequest(
            queue_id=uuid.uuid4(),
            request_data=LLMComparisonRequest(
                user_prompt="2", callback_topic="topic", correlation_id=uuid.uuid4()
            ),
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=100,
            callback_topic="topic",
        )

        mock_queue_manager.dequeue.side_effect = [request2, None]
        mock_comparison_processor.process_comparison_batch.return_value = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="1",
                confidence=0.9,
                provider=LLMProviderType.MOCK,
                model="mock",
                correlation_id=request1.queue_id,
                response_time_ms=10,
                token_usage={},
                cost_estimate=0.0,
            ),
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_B,
                justification="2",
                confidence=0.9,
                provider=LLMProviderType.MOCK,
                model="mock",
                correlation_id=request2.queue_id,
                response_time_ms=10,
                token_usage={},
                cost_estimate=0.0,
            ),
        ]

        # Act
        result = await executor.execute_serial_bundle(request1)

        # Assert
        assert len(result.outcomes) == 2

    @pytest.mark.asyncio
    async def test_execute_request_uses_llm_config_overrides(
        self,
        executor: QueuedRequestExecutor,
        mock_comparison_processor: AsyncMock,
        mock_queue_manager: AsyncMock,
    ) -> None:
        """Single-request execution should pass overrides to comparison processor."""
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        request_data = LLMComparisonRequest(
            user_prompt="test prompt",
            callback_topic="test.topic",
            correlation_id=correlation_id,
            llm_config_overrides=LLMConfigOverridesHTTP(
                provider_override=LLMProviderType.ANTHROPIC,
                model_override="claude-sonnet-4-5-20250929",
                temperature_override=0.3,
                system_prompt_override="System override",
                max_tokens_override=4096,
            ),
        )
        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=100,
            callback_topic="test.topic",
        )

        mock_queue_manager.update_status = AsyncMock(return_value=True)
        mock_comparison_processor.process_comparison.return_value = LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="test",
            confidence=0.9,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-sonnet-4-5-20250929",
            correlation_id=correlation_id,
            response_time_ms=100,
            token_usage={},
            cost_estimate=0.0,
        )

        await executor.execute_request(queued_request)

        mock_comparison_processor.process_comparison.assert_awaited_once()
        _, kwargs = mock_comparison_processor.process_comparison.await_args
        assert kwargs["provider"] == LLMProviderType.ANTHROPIC
        assert kwargs["model_override"] == "claude-sonnet-4-5-20250929"
        assert kwargs["temperature_override"] == 0.3
        assert kwargs["system_prompt_override"] == "System override"
        assert kwargs["max_tokens_override"] == 4096
