"""Focused unit tests for BatchApiStrategy."""

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

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.implementations.batch_api_strategy import (
    BatchApiStrategy,
)
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_tracing_enricher import (
    QueueTracingEnricher,
)
from services.llm_provider_service.internal_models import (
    BatchJobItemStatus,
    LLMOrchestratorResponse,
)
from services.llm_provider_service.queue_models import QueuedRequest, QueueStats


class _MinimalResultHandler:
    """Minimal result handler facade for BatchApiStrategy tests."""

    def __init__(self, queue_manager: AsyncMock) -> None:
        self.queue_manager = queue_manager
        self.handle_expired_request = AsyncMock()
        self.handle_request_success = AsyncMock()
        self.handle_request_hule_error = AsyncMock()


@pytest.fixture
def settings() -> Settings:
    s = Settings()
    s.QUEUE_PROCESSING_MODE = QueueProcessingMode.BATCH_API
    s.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 4
    return s


@pytest.fixture
def queue_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.update_status = AsyncMock()
    manager.dequeue = AsyncMock()
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
def metrics(settings: Settings) -> QueueProcessorMetrics:
    # Use no-op metrics collectors for unit tests.
    return QueueProcessorMetrics(
        queue_metrics=None,
        llm_metrics=None,
        queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
    )


@pytest.fixture
def tracing_enricher(settings: Settings) -> QueueTracingEnricher:
    return QueueTracingEnricher(settings.QUEUE_PROCESSING_MODE)


@pytest.fixture
def comparison_processor() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def batch_job_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.schedule_job = AsyncMock()
    manager.collect_results = AsyncMock()
    return manager


def _make_request(
    provider: LLMProviderType,
    model: str | None = None,
    batching_mode: str | None = None,
) -> QueuedRequest:
    correlation_id = uuid.uuid4()
    metadata: dict[str, object] = {}
    if batching_mode is not None:
        metadata["cj_llm_batching_mode"] = batching_mode
    request_data = LLMComparisonRequest(
        user_prompt="prompt",
        callback_topic="topic",
        correlation_id=correlation_id,
        llm_config_overrides=None,
        metadata=metadata,
    )
    queued_request = QueuedRequest(
        queue_id=uuid.uuid4(),
        request_data=request_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        size_bytes=len(request_data.model_dump_json()),
        callback_topic="topic",
    )
    # Inject provider/model via an overrides-like object that matches the
    # attributes accessed by build_override_kwargs.
    attrs: dict[str, object] = {
        "provider_override": provider,
        "model_override": model,
        "temperature_override": None,
        "system_prompt_override": None,
        "max_tokens_override": None,
    }
    request_data.llm_config_overrides = type("Overrides", (), attrs)()
    return queued_request


@pytest.mark.asyncio
async def test_batch_api_strategy_groups_compatible_requests_and_invokes_job_manager(
    settings: Settings,
    queue_manager: AsyncMock,
    metrics: QueueProcessorMetrics,
    tracing_enricher: QueueTracingEnricher,
    comparison_processor: AsyncMock,
    batch_job_manager: AsyncMock,
) -> None:
    """Compatible requests should be bundled into a single batch job."""
    # Arrange
    first_request = _make_request(
        provider=LLMProviderType.MOCK,
        model="mock-model",
        batching_mode="provider_batch_api",
    )
    second_request = _make_request(
        provider=LLMProviderType.MOCK,
        model="mock-model",
        batching_mode="provider_batch_api",
    )

    # Second request is returned once, then queue is empty.
    queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])

    result_handler = _MinimalResultHandler(queue_manager)

    # Batch job manager returns one result per item.
    job_ref = Mock()
    batch_job_manager.schedule_job.return_value = job_ref
    batch_job_manager.collect_results.return_value = [
        type(
            "JobResult",
            (),
            {
                "queue_id": first_request.queue_id,
                "provider": LLMProviderType.MOCK,
                "model": "mock-model",
                "status": BatchJobItemStatus.SUCCESS,
                "response": LLMOrchestratorResponse(
                    winner=EssayComparisonWinner.ESSAY_A,
                    justification="A",
                    confidence=0.5,
                    provider=LLMProviderType.MOCK,
                    model="mock-model",
                    correlation_id=first_request.request_data.correlation_id
                    or first_request.queue_id,
                    response_time_ms=10,
                    token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    cost_estimate=0.0,
                    metadata={"prompt_sha256": "abc"},
                ),
                "error_message": None,
            },
        )(),
        type(
            "JobResult",
            (),
            {
                "queue_id": second_request.queue_id,
                "provider": LLMProviderType.MOCK,
                "model": "mock-model",
                "status": BatchJobItemStatus.SUCCESS,
                "response": LLMOrchestratorResponse(
                    winner=EssayComparisonWinner.ESSAY_B,
                    justification="B",
                    confidence=0.6,
                    provider=LLMProviderType.MOCK,
                    model="mock-model",
                    correlation_id=second_request.request_data.correlation_id
                    or second_request.queue_id,
                    response_time_ms=12,
                    token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    cost_estimate=0.0,
                    metadata={"prompt_sha256": "def"},
                ),
                "error_message": None,
            },
        )(),
    ]

    strategy = BatchApiStrategy(
        comparison_processor=cast(AsyncMock, comparison_processor),
        result_handler=result_handler,  # type: ignore[arg-type]
        trace_context_manager=Mock(),
        settings=settings,
        metrics=metrics,
        tracing_enricher=tracing_enricher,
        batch_job_manager=batch_job_manager,
    )

    # Act
    result = await strategy.execute(first_request)

    # Assert bundling and job manager interaction
    batch_job_manager.schedule_job.assert_awaited_once()
    scheduled_call = batch_job_manager.schedule_job.await_args
    assert scheduled_call.kwargs["provider"] == LLMProviderType.MOCK
    assert scheduled_call.kwargs["model"] == "mock-model"
    items = scheduled_call.kwargs["items"]
    assert len(items) == 2
    assert {item.queue_id for item in items} == {
        first_request.queue_id,
        second_request.queue_id,
    }

    batch_job_manager.collect_results.assert_awaited_once_with(job_ref)

    # Assert result handler used for both items
    assert result_handler.handle_request_success.await_count == 2
    assert len(result.outcomes) == 2
    assert {o.request.queue_id for o in result.outcomes} == {
        first_request.queue_id,
        second_request.queue_id,
    }


@pytest.mark.asyncio
async def test_batch_api_strategy_defers_incompatible_request_as_pending(
    settings: Settings,
    queue_manager: AsyncMock,
    metrics: QueueProcessorMetrics,
    tracing_enricher: QueueTracingEnricher,
    comparison_processor: AsyncMock,
    batch_job_manager: AsyncMock,
) -> None:
    """Incompatible requests should not be included in the batch and become pending."""
    first_request = _make_request(
        provider=LLMProviderType.MOCK,
        model="mock-model",
        batching_mode="provider_batch_api",
    )
    incompatible_request = _make_request(
        provider=LLMProviderType.OPENAI,  # Different provider ⇒ incompatible
        model="gpt-5.1",
        batching_mode="provider_batch_api",
    )
    queue_manager.dequeue = AsyncMock(side_effect=[incompatible_request, None])

    result_handler = _MinimalResultHandler(queue_manager)
    batch_job_manager.schedule_job = AsyncMock()
    batch_job_manager.collect_results = AsyncMock(return_value=[])

    strategy = BatchApiStrategy(
        comparison_processor=cast(AsyncMock, comparison_processor),
        result_handler=result_handler,  # type: ignore[arg-type]
        trace_context_manager=Mock(),
        settings=settings,
        metrics=metrics,
        tracing_enricher=tracing_enricher,
        batch_job_manager=batch_job_manager,
    )

    result = await strategy.execute(first_request)

    # Only the first (compatible) request should be scheduled; incompatible is deferred.
    scheduled_items = batch_job_manager.schedule_job.await_args.kwargs["items"]
    assert len(scheduled_items) == 1
    assert scheduled_items[0].queue_id == first_request.queue_id

    assert result.pending_request is incompatible_request


@pytest.mark.asyncio
async def test_batch_api_strategy_handles_failed_item_via_error_handler(
    settings: Settings,
    queue_manager: AsyncMock,
    metrics: QueueProcessorMetrics,
    tracing_enricher: QueueTracingEnricher,
    comparison_processor: AsyncMock,
    batch_job_manager: AsyncMock,
) -> None:
    """Failed job items route through handle_request_hule_error and mark outcomes as failure."""
    failing_request = _make_request(
        provider=LLMProviderType.MOCK,
        model="mock-model",
        batching_mode="provider_batch_api",
    )
    queue_manager.dequeue = AsyncMock(return_value=None)

    result_handler = _MinimalResultHandler(queue_manager)

    job_ref = Mock()
    batch_job_manager.schedule_job.return_value = job_ref
    batch_job_manager.collect_results.return_value = [
        type(
            "JobResult",
            (),
            {
                "queue_id": failing_request.queue_id,
                "provider": LLMProviderType.MOCK,
                "model": "mock-model",
                "status": BatchJobItemStatus.FAILED,
                "response": None,
                "error_message": "provider-level failure",
            },
        )(),
    ]

    strategy = BatchApiStrategy(
        comparison_processor=cast(AsyncMock, comparison_processor),
        result_handler=result_handler,  # type: ignore[arg-type]
        trace_context_manager=Mock(),
        settings=settings,
        metrics=metrics,
        tracing_enricher=tracing_enricher,
        batch_job_manager=batch_job_manager,
    )

    result = await strategy.execute(failing_request)

    # No successes expected, failure path should be used exactly once.
    assert result_handler.handle_request_success.await_count == 0
    assert result_handler.handle_request_hule_error.await_count == 1
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.request.queue_id == failing_request.queue_id
    assert outcome.result == "failure"


@pytest.mark.asyncio
async def test_batch_api_strategy_handles_collect_results_exception(
    settings: Settings,
    queue_manager: AsyncMock,
    metrics: QueueProcessorMetrics,
    tracing_enricher: QueueTracingEnricher,
    comparison_processor: AsyncMock,
    batch_job_manager: AsyncMock,
) -> None:
    """Exceptions from collect_results should fail all bundled requests."""
    first_request = _make_request(
        provider=LLMProviderType.MOCK,
        model="mock-model",
        batching_mode="provider_batch_api",
    )
    second_request = _make_request(
        provider=LLMProviderType.MOCK,
        model="mock-model",
        batching_mode="provider_batch_api",
    )

    # Second compatible request is dequeued once, then queue is empty.
    queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])

    result_handler = _MinimalResultHandler(queue_manager)

    job_ref = Mock()
    batch_job_manager.schedule_job.return_value = job_ref
    batch_job_manager.collect_results.side_effect = RuntimeError("collect failed")

    strategy = BatchApiStrategy(
        comparison_processor=cast(AsyncMock, comparison_processor),
        result_handler=result_handler,  # type: ignore[arg-type]
        trace_context_manager=Mock(),
        settings=settings,
        metrics=metrics,
        tracing_enricher=tracing_enricher,
        batch_job_manager=batch_job_manager,
    )

    result = await strategy.execute(first_request)

    batch_job_manager.schedule_job.assert_awaited_once()
    batch_job_manager.collect_results.assert_awaited_once_with(job_ref)

    # All bundled requests should be routed through the error handler.
    assert result_handler.handle_request_success.await_count == 0
    assert result_handler.handle_request_hule_error.await_count == 2

    assert len(result.outcomes) == 2
    assert {outcome.result for outcome in result.outcomes} == {"failure"}
    assert {outcome.request.queue_id for outcome in result.outcomes} == {
        first_request.queue_id,
        second_request.queue_id,
    }
    # Batch API bundling should not leave a pending request when all items are compatible.
    assert result.pending_request is None
