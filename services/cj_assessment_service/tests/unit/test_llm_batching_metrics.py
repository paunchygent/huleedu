"""Unit tests for CJ LLM batching metrics helper.

Covers request and batch counters for different CJ request types.
"""

from __future__ import annotations

import pytest
from common_core.config_enums import LLMBatchingMode

from services.cj_assessment_service.cj_core_logic import comparison_processing as cp


class DummyCounter:
    """Minimal counter implementation to capture labels and increments."""

    def __init__(self) -> None:
        self.label_calls: list[dict[str, str]] = []
        self.inc_calls: list[int] = []

    def labels(self, **labels: str) -> "DummyCounter":  # pragma: no cover - trivial
        self.label_calls.append(labels)
        return self

    def inc(self, value: int = 1) -> None:  # pragma: no cover - trivial
        self.inc_calls.append(value)


def _make_business_metrics(
    requests_metric: DummyCounter | None,
    batches_metric: DummyCounter | None,
) -> dict[str, DummyCounter]:
    metrics: dict[str, DummyCounter] = {}
    if requests_metric is not None:
        metrics["cj_llm_requests_total"] = requests_metric
    if batches_metric is not None:
        metrics["cj_llm_batches_started_total"] = batches_metric
    return metrics


def test_record_llm_batching_metrics_initial_batch_increments_requests_and_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initial cj_comparison batch should record both request and batch counters."""

    requests_metric = DummyCounter()
    batches_metric = DummyCounter()

    monkeypatch.setattr(
        cp,
        "get_business_metrics",
        lambda: _make_business_metrics(requests_metric, batches_metric),
    )

    cp._record_llm_batching_metrics(  # type: ignore[attr-defined]
        effective_mode=LLMBatchingMode.SERIAL_BUNDLE,
        request_count=5,
        request_type="cj_comparison",
    )

    assert requests_metric.label_calls == [
        {"batching_mode": LLMBatchingMode.SERIAL_BUNDLE.value},
    ]
    assert requests_metric.inc_calls == [5]

    assert batches_metric.label_calls == [
        {"batching_mode": LLMBatchingMode.SERIAL_BUNDLE.value},
    ]
    assert batches_metric.inc_calls == [1]


def test_record_llm_batching_metrics_retry_only_increments_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cj_retry should increment requests but not batches_started counter."""

    requests_metric = DummyCounter()
    batches_metric = DummyCounter()

    monkeypatch.setattr(
        cp,
        "get_business_metrics",
        lambda: _make_business_metrics(requests_metric, batches_metric),
    )

    cp._record_llm_batching_metrics(  # type: ignore[attr-defined]
        effective_mode=LLMBatchingMode.PER_REQUEST,
        request_count=3,
        request_type="cj_retry",
    )

    assert requests_metric.label_calls == [
        {"batching_mode": LLMBatchingMode.PER_REQUEST.value},
    ]
    assert requests_metric.inc_calls == [3]

    # No batch counter updates for retries
    assert batches_metric.label_calls == []
    assert batches_metric.inc_calls == []
