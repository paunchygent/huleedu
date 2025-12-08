"""Focused unit tests for SerialBundleStrategy bundling semantics.

Covers:
- preferred_bundle_size hint below SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL
- preferred_bundle_size capped by SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core import (
    EssayComparisonWinner,
    LLMComparisonRequest,
    LLMProviderType,
    QueueStatus,
)
from common_core import LLMConfigOverridesHTTP as LLMConfigOverrides

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.implementations.callback_event_publisher import (
    CallbackEventPublisher,
)
from services.llm_provider_service.implementations.execution_result_handler import (
    ExecutionResultHandler,
)
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_tracing_enricher import (
    QueueTracingEnricher,
)
from services.llm_provider_service.implementations.request_strategies import (
    SerialBundleStrategy,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import (
    ComparisonProcessorProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest


def _make_strategy(
    *,
    comparison_processor: AsyncMock,
    queue_manager: AsyncMock,
    settings: Settings,
) -> SerialBundleStrategy:
    """Construct SerialBundleStrategy with lightweight dependencies."""

    tracing_enricher = QueueTracingEnricher(QueueProcessingMode.SERIAL_BUNDLE)

    metrics = QueueProcessorMetrics(
        queue_metrics={},
        llm_metrics={},
        queue_processing_mode=QueueProcessingMode.SERIAL_BUNDLE,
    )
    callback_publisher = CallbackEventPublisher(
        event_publisher=AsyncMock(),
        settings=settings,
    )
    result_handler = ExecutionResultHandler(
        queue_manager=queue_manager,
        event_publisher=AsyncMock(),
        callback_publisher=callback_publisher,
        metrics=metrics,
        settings=settings,
    )

    return SerialBundleStrategy(
        comparison_processor=comparison_processor,
        result_handler=result_handler,
        trace_context_manager=Mock(),
        settings=settings,
        metrics=metrics,
        tracing_enricher=tracing_enricher,
    )


def _make_request(
    *,
    preferred_bundle_size: int | None,
    provider: LLMProviderType = LLMProviderType.MOCK,
) -> QueuedRequest:
    """Helper to construct a queued request with optional bundle hint."""

    metadata: dict[str, Any] = {"cj_llm_batching_mode": "serial_bundle"}
    if preferred_bundle_size is not None:
        metadata["preferred_bundle_size"] = preferred_bundle_size

    request_data = LLMComparisonRequest(
        user_prompt="prompt",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(
            provider_override=provider,
            model_override="mock-model",
        ),
        metadata=metadata,
    )
    return QueuedRequest(
        queue_id=uuid4(),
        request_data=request_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(request_data.model_dump_json()),
        callback_topic="topic",
    )


@pytest.mark.asyncio
async def test_serial_bundle_uses_preferred_bundle_size_when_below_cap() -> None:
    """preferred_bundle_size hint below cap should limit bundle size."""

    settings = Settings()
    settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE
    settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 4

    mock_comparison_processor: AsyncMock = AsyncMock(spec=ComparisonProcessorProtocol)
    mock_queue_manager: AsyncMock = AsyncMock(spec=QueueManagerProtocol)

    strategy = _make_strategy(
        comparison_processor=mock_comparison_processor,
        queue_manager=mock_queue_manager,
        settings=settings,
    )

    first_request = _make_request(preferred_bundle_size=2)
    second_request = _make_request(preferred_bundle_size=2)

    mock_queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])
    mock_queue_manager.update_status = AsyncMock()

    mock_comparison_processor.process_comparison_batch.return_value = [
        LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="A",
            confidence=0.5,
            provider=LLMProviderType.MOCK,
            model="mock-model",
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
            model="mock-model",
            correlation_id=second_request.queue_id,
            response_time_ms=12,
            token_usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            cost_estimate=0.0,
            metadata={"prompt_sha256": "def"},
        ),
    ]

    result = await strategy.execute(first_request)

    mock_comparison_processor.process_comparison_batch.assert_awaited_once()
    call = mock_comparison_processor.process_comparison_batch.await_args
    batch_items = call.args[0]
    assert len(batch_items) == 2
    assert result.pending_request is None


@pytest.mark.asyncio
async def test_serial_bundle_caps_preferred_bundle_size_at_config_limit() -> None:
    """preferred_bundle_size above cap should be limited by config."""

    settings = Settings()
    settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE
    settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 4

    mock_comparison_processor: AsyncMock = AsyncMock(spec=ComparisonProcessorProtocol)
    mock_queue_manager: AsyncMock = AsyncMock(spec=QueueManagerProtocol)

    strategy = _make_strategy(
        comparison_processor=mock_comparison_processor,
        queue_manager=mock_queue_manager,
        settings=settings,
    )

    first_request = _make_request(preferred_bundle_size=10)
    extra_requests = [_make_request(preferred_bundle_size=None) for _ in range(3)]

    mock_queue_manager.dequeue = AsyncMock(side_effect=[*extra_requests, None])
    mock_queue_manager.update_status = AsyncMock()

    mock_comparison_processor.process_comparison_batch.return_value = [
        LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="A",
            confidence=0.5,
            provider=LLMProviderType.MOCK,
            model="mock-model",
            correlation_id=first_request.queue_id,
            response_time_ms=10,
            token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            cost_estimate=0.0,
            metadata={"prompt_sha256": "a"},
        )
    ] + [
        LLMOrchestratorResponse(
            winner=EssayComparisonWinner.ESSAY_B,
            justification="B",
            confidence=0.6,
            provider=LLMProviderType.MOCK,
            model="mock-model",
            correlation_id=req.queue_id,
            response_time_ms=12,
            token_usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            cost_estimate=0.0,
            metadata={"prompt_sha256": "b"},
        )
        for req in extra_requests
    ]

    result = await strategy.execute(first_request)

    mock_comparison_processor.process_comparison_batch.assert_awaited_once()
    call = mock_comparison_processor.process_comparison_batch.await_args
    batch_items = call.args[0]
    assert len(batch_items) == settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL
    assert result.pending_request is None
