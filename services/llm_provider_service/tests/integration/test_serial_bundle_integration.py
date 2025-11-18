"""Integration tests for serial bundle behaviour in QueueProcessor.

These tests exercise the serial-bundle path in `QueueProcessorImpl` using a
mocked queue manager and event publisher, focusing on:

- Happy-path bundling of compatible requests and serial-bundle metrics
- Fairness behaviour via `_pending_request` for incompatible requests
- Expired + active mixes and expiry metrics
- Regression coverage for per-request mode (no serial-bundle metrics)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import (
    ComparisonProcessorProtocol,
    LLMEventPublisherProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest


@pytest.mark.asyncio
async def test_serial_bundle_happy_path_bundles_requests_and_records_metrics() -> None:
    """Happy-path: compatible requests are bundled and metrics reflect bundle.

    This test exercises `_process_request_serial_bundle` directly with a mocked
    `QueueManagerProtocol`, verifying that:

    - Two compatible requests are bundled into a single `process_comparison_batch` call
    - Both requests transition to COMPLETED and are removed from the queue
    - Serial-bundle metrics record exactly one call and bundle size of 2
    """

    settings = Settings()
    settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE
    settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 4

    mock_comparison_processor: AsyncMock = AsyncMock(spec=ComparisonProcessorProtocol)
    mock_queue_manager: AsyncMock = AsyncMock(spec=QueueManagerProtocol)
    mock_event_publisher: AsyncMock = AsyncMock(spec=LLMEventPublisherProtocol)
    trace_context_manager = TraceContextManagerImpl()

    queue_processor = QueueProcessorImpl(
        comparison_processor=mock_comparison_processor,
        queue_manager=mock_queue_manager,
        event_publisher=mock_event_publisher,
        trace_context_manager=trace_context_manager,
        settings=settings,
        queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
    )

    # Attach only the serial-bundle metrics – other queue metrics are unit-tested separately.
    queue_processor.queue_metrics = {
        "llm_serial_bundle_calls_total": Mock(),
        "llm_serial_bundle_items_per_call": Mock(),
    }

    calls_counter = queue_processor.queue_metrics["llm_serial_bundle_calls_total"]
    items_hist = queue_processor.queue_metrics["llm_serial_bundle_items_per_call"]
    calls_counter.labels.return_value = Mock()
    items_hist.labels.return_value = Mock()

    # Create two compatible queued requests (same provider, same overrides, same batching hint).
    first_req_data = LLMComparisonRequest(
        user_prompt="prompt-a",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(
            provider_override=LLMProviderType.MOCK,
            model_override="mock-model-v1",
        ),
        metadata={"cj_llm_batching_mode": "serial_bundle"},
    )
    first_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=first_req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(first_req_data.model_dump_json()),
        callback_topic="topic",
    )

    second_req_data = LLMComparisonRequest(
        user_prompt="prompt-b",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(
            provider_override=LLMProviderType.MOCK,
            model_override="mock-model-v1",
        ),
        metadata={"cj_llm_batching_mode": "serial_bundle"},
    )
    second_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=second_req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(second_req_data.model_dump_json()),
        callback_topic="topic",
    )

    # Serial-bundle helper pulls additional items from the queue manager.
    mock_queue_manager.dequeue = AsyncMock(side_effect=[second_request, None])
    mock_queue_manager.update_status = AsyncMock(return_value=True)
    mock_queue_manager.remove = AsyncMock(return_value=True)

    # Comparison processor returns two results, one per bundled request.
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

    # One batch call with two items.
    mock_comparison_processor.process_comparison_batch.assert_awaited_once()
    batch_call_args = mock_comparison_processor.process_comparison_batch.await_args
    assert len(batch_call_args.args[0]) == 2

    # Both requests transition to COMPLETED and are removed from the queue.
    completed_statuses: dict[Any, list[QueueStatus]] = {}
    for args, kwargs in mock_queue_manager.update_status.call_args_list:
        # update_status is called with keyword arguments in QueueProcessorImpl.
        queue_id = kwargs.get("queue_id") or (args[0] if args else None)
        status = kwargs.get("status")
        completed_statuses.setdefault(queue_id, []).append(status)

    assert QueueStatus.COMPLETED in completed_statuses.get(first_request.queue_id, [])
    assert QueueStatus.COMPLETED in completed_statuses.get(second_request.queue_id, [])

    # remove() is invoked positionally: remove(queue_id).
    removed_ids = {args[0] for args, _ in mock_queue_manager.remove.call_args_list}
    assert first_request.queue_id in removed_ids
    assert second_request.queue_id in removed_ids

    # Serial-bundle metrics: exactly one call with bundle size 2.
    calls_counter.labels.assert_called_once_with(provider="mock", model="mock-model-v1")
    calls_counter.labels.return_value.inc.assert_called_once_with()

    items_hist.labels.assert_called_once_with(provider="mock", model="mock-model-v1")
    items_hist.labels.return_value.observe.assert_called_once_with(2)


@pytest.mark.asyncio
async def test_serial_bundle_defers_incompatible_request_to_pending() -> None:
    """Fairness: incompatible request is not bundled and becomes `_pending_request`.

    The first request should be processed as a single-item bundle, while the first
    incompatible request is stored on `_pending_request` for a later iteration.
    """

    settings = Settings()
    settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE

    mock_comparison_processor: AsyncMock = AsyncMock(spec=ComparisonProcessorProtocol)
    mock_queue_manager: AsyncMock = AsyncMock(spec=QueueManagerProtocol)
    mock_event_publisher: AsyncMock = AsyncMock(spec=LLMEventPublisherProtocol)
    trace_context_manager = TraceContextManagerImpl()

    queue_processor = QueueProcessorImpl(
        comparison_processor=mock_comparison_processor,
        queue_manager=mock_queue_manager,
        event_publisher=mock_event_publisher,
        trace_context_manager=trace_context_manager,
        settings=settings,
        queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
    )

    first_req_data = LLMComparisonRequest(
        user_prompt="prompt-a",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
    )
    first_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=first_req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(first_req_data.model_dump_json()),
        callback_topic="topic",
    )

    incompatible_req_data = LLMComparisonRequest(
        user_prompt="prompt-b",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.OPENAI),
    )
    incompatible_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=incompatible_req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(incompatible_req_data.model_dump_json()),
        callback_topic="topic",
    )

    mock_queue_manager.dequeue = AsyncMock(side_effect=[incompatible_request])
    mock_queue_manager.update_status = AsyncMock(return_value=True)
    mock_queue_manager.remove = AsyncMock(return_value=True)

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

    # Only the first request is processed in this bundle.
    mock_comparison_processor.process_comparison_batch.assert_awaited_once()
    awaited_call = mock_comparison_processor.process_comparison_batch.await_args
    assert len(awaited_call.args[0]) == 1

    # Incompatible request is stored for later processing.
    assert queue_processor._pending_request is incompatible_request


@pytest.mark.asyncio
async def test_serial_bundle_skips_expired_requests_and_records_expiry_metrics() -> None:
    """Expired requests are skipped from bundles and tracked via expiry metrics.

    When a subsequent dequeued request is already expired, the queue processor
    should:

    - Mark it as EXPIRED using the queue manager
    - Record `llm_queue_expiry_*` metrics with reason `ttl`
    - Exclude it from the bundle and serial-bundle metrics
    """

    settings = Settings()
    settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.SERIAL_BUNDLE

    mock_comparison_processor: AsyncMock = AsyncMock(spec=ComparisonProcessorProtocol)
    mock_queue_manager: AsyncMock = AsyncMock(spec=QueueManagerProtocol)
    mock_event_publisher: AsyncMock = AsyncMock(spec=LLMEventPublisherProtocol)
    trace_context_manager = TraceContextManagerImpl()

    queue_processor = QueueProcessorImpl(
        comparison_processor=mock_comparison_processor,
        queue_manager=mock_queue_manager,
        event_publisher=mock_event_publisher,
        trace_context_manager=trace_context_manager,
        settings=settings,
        queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
    )

    expiry_counter = Mock()
    expiry_age_hist = Mock()
    calls_counter = Mock()
    items_hist = Mock()

    expiry_counter.labels.return_value = Mock()
    expiry_age_hist.labels.return_value = Mock()
    calls_counter.labels.return_value = Mock()
    items_hist.labels.return_value = Mock()

    queue_processor.queue_metrics = {
        "llm_queue_expiry_total": expiry_counter,
        "llm_queue_expiry_age_seconds": expiry_age_hist,
        "llm_serial_bundle_calls_total": calls_counter,
        "llm_serial_bundle_items_per_call": items_hist,
    }

    # Non-expired first request.
    first_req_data = LLMComparisonRequest(
        user_prompt="prompt-a",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
    )
    first_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=first_req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(first_req_data.model_dump_json()),
        callback_topic="topic",
    )

    # Expired request based on TTL + queued_at.
    expired_req_data = LLMComparisonRequest(
        user_prompt="prompt-expired",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
    )
    expired_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=expired_req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc) - timedelta(hours=5),
        size_bytes=len(expired_req_data.model_dump_json()),
        callback_topic="topic",
    )

    mock_queue_manager.dequeue = AsyncMock(side_effect=[expired_request, None])
    mock_queue_manager.update_status = AsyncMock(return_value=True)
    mock_queue_manager.remove = AsyncMock(return_value=True)

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

    # Expired request marked as EXPIRED by queue manager.
    mock_queue_manager.update_status.assert_any_call(
        queue_id=expired_request.queue_id,
        status=QueueStatus.EXPIRED,
        message="Request expired before processing",
    )

    # Expiry metrics recorded exactly once for the expired request.
    expiry_counter.labels.assert_called_once()
    expiry_counter.labels.return_value.inc.assert_called_once_with()

    expiry_age_hist.labels.assert_called_once()
    expiry_age_hist.labels.return_value.observe.assert_called_once()

    # Serial-bundle metrics recorded for the single active request only.
    calls_counter.labels.assert_called_once()
    items_hist.labels.assert_called_once()
    items_hist.labels.return_value.observe.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_per_request_mode_does_not_emit_serial_bundle_metrics() -> None:
    """Regression: per-request mode should never touch serial-bundle metrics.

    This ensures that when `QUEUE_PROCESSING_MODE=per_request`, normal request
    processing via `_process_request` behaves as before and does not emit any
    serial-bundle metrics, even if those collectors are attached.
    """

    settings = Settings()
    settings.QUEUE_PROCESSING_MODE = QueueProcessingMode.PER_REQUEST

    mock_comparison_processor: AsyncMock = AsyncMock(spec=ComparisonProcessorProtocol)
    mock_queue_manager: AsyncMock = AsyncMock(spec=QueueManagerProtocol)
    mock_event_publisher: AsyncMock = AsyncMock(spec=LLMEventPublisherProtocol)
    trace_context_manager = TraceContextManagerImpl()

    queue_processor = QueueProcessorImpl(
        comparison_processor=mock_comparison_processor,
        queue_manager=mock_queue_manager,
        event_publisher=mock_event_publisher,
        trace_context_manager=trace_context_manager,
        settings=settings,
        queue_processing_mode=settings.QUEUE_PROCESSING_MODE,
    )

    calls_counter = Mock()
    items_hist = Mock()
    calls_counter.labels.return_value = Mock()
    items_hist.labels.return_value = Mock()

    # Attach serial-bundle metrics, but they should remain unused in per-request mode.
    queue_processor.queue_metrics = {
        "llm_serial_bundle_calls_total": calls_counter,
        "llm_serial_bundle_items_per_call": items_hist,
    }

    req_data = LLMComparisonRequest(
        user_prompt="prompt-a",
        callback_topic="topic",
        correlation_id=uuid4(),
        llm_config_overrides=LLMConfigOverrides(provider_override=LLMProviderType.MOCK),
    )
    request = QueuedRequest(
        queue_id=uuid4(),
        request_data=req_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(req_data.model_dump_json()),
        callback_topic="topic",
    )

    mock_queue_manager.update_status = AsyncMock(return_value=True)
    mock_queue_manager.remove = AsyncMock(return_value=True)

    mock_comparison_processor.process_comparison.return_value = LLMOrchestratorResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="A",
        confidence=0.5,
        provider=LLMProviderType.MOCK,
        model="mock",
        correlation_id=request.queue_id,
        response_time_ms=10,
        token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        cost_estimate=0.0,
        metadata={"prompt_sha256": "abc"},
    )

    await queue_processor._process_request(request)

    # Comparison was processed via per-request path.
    mock_comparison_processor.process_comparison.assert_awaited_once()

    # Serial-bundle metrics must not be touched in per-request mode.
    calls_counter.labels.assert_not_called()
    items_hist.labels.assert_not_called()
