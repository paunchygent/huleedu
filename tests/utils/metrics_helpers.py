"""
Shared Prometheus metrics helpers for docker-backed tests.

These helpers are designed to be reused by ENG5 CJ docker semantics
tests and ENG5 mock parity tests. They provide a thin async wrapper
around fetching `/metrics` and parsing the Prometheus text exposition
format into a simple in-memory structure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Dict, List, Tuple

import httpx

from tests.utils.metrics_validation import iter_metric_samples

MetricLabels = Dict[str, str]
MetricSample = Tuple[MetricLabels, float]
MetricMap = Dict[str, List[MetricSample]]

DEFAULT_METRICS_TIMEOUT_SECONDS = 5.0


async def fetch_metrics_text(
    metrics_url: str, timeout_seconds: float = DEFAULT_METRICS_TIMEOUT_SECONDS
) -> str:
    """Fetch raw Prometheus metrics text from a given metrics URL."""
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(metrics_url)
        response.raise_for_status()
        return response.text


async def fetch_and_parse_metrics(
    *,
    base_url: str | None = None,
    metrics_url: str | None = None,
    timeout_seconds: float = DEFAULT_METRICS_TIMEOUT_SECONDS,
) -> MetricMap:
    """Fetch and parse Prometheus metrics into a simple mapping.

    Args:
        base_url: Service base URL (e.g. ``http://localhost:9095``). When provided,
            ``/metrics`` will be appended.
        metrics_url: Explicit metrics URL. If provided, this takes precedence
            over ``base_url``.
        timeout_seconds: Request timeout when fetching metrics.

    Returns:
        Mapping from metric name to a list of ``(labels, value)`` tuples.
    """
    if metrics_url is None:
        if base_url is None:
            raise ValueError("Either base_url or metrics_url must be provided")
        metrics_url = base_url.rstrip("/") + "/metrics"

    metrics_text = await fetch_metrics_text(metrics_url, timeout_seconds=timeout_seconds)

    metrics: MetricMap = {}
    for name, labels, value in iter_metric_samples(metrics_text):
        metrics.setdefault(name, []).append((labels, value))
    return metrics


def find_metric_values_in_map(
    metrics: MetricMap,
    metric_name: str,
    labels_subset: Mapping[str, str] | None = None,
) -> list[float]:
    """Extract values for a metric from a parsed metrics map.

    Args:
        metrics: Parsed metrics map returned by :func:`fetch_and_parse_metrics`.
        metric_name: Name of the metric to search for.
        labels_subset: Optional subset of labels that must match.

    Returns:
        List of metric values matching the name and label subset.
    """
    samples = metrics.get(metric_name, [])
    if not labels_subset:
        return [value for _labels, value in samples]

    values: list[float] = []
    for labels, value in samples:
        if all(labels.get(k) == v for k, v in labels_subset.items()):
            values.append(value)
    return values
