"""Integration tests for BATCH_API queue metrics scaffolding.

These tests exercise QueueProcessorMetrics with real Prometheus collectors to
ensure that QueueProcessingMode.BATCH_API produces metrics labelled with
queue_processing_mode="batch_api" for wait-time and callbacks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from common_core import LLMComparisonRequest, LLMProviderType, QueueStatus

from services.llm_provider_service.config import QueueProcessingMode
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.metrics import get_queue_metrics
from services.llm_provider_service.queue_models import QueuedRequest


def test_batch_api_completion_metrics_use_batch_api_label_in_histogram() -> None:
    """record_completion_metrics should emit samples with queue_processing_mode='batch_api'."""
    queue_metrics = get_queue_metrics()
    metrics = QueueProcessorMetrics(
        queue_metrics=queue_metrics,
        llm_metrics=None,
        queue_processing_mode=QueueProcessingMode.BATCH_API,
    )

    request_data = LLMComparisonRequest(
        user_prompt="prompt",
        callback_topic="topic",
    )
    queued_request = QueuedRequest(
        queue_id=uuid4(),
        request_data=request_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        size_bytes=len(request_data.model_dump_json()),
        callback_topic="topic",
    )

    metrics.record_completion_metrics(
        provider=LLMProviderType.MOCK,
        result="success",
        request=queued_request,
        processing_started=datetime.now(timezone.utc).timestamp(),
    )

    wait_hist = queue_metrics["llm_queue_wait_time_seconds"]
    collected_metric = None
    for metric in wait_hist.collect():
        if metric.name == "llm_provider_queue_wait_time_seconds":
            collected_metric = metric
            break

    assert collected_metric is not None

    modes = {
        sample.labels.get("queue_processing_mode")
        for sample in collected_metric.samples
        # Only consider count / bucket / sum samples that carry the label.
        if "queue_processing_mode" in sample.labels
    }
    assert "batch_api" in modes
