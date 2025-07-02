"""Shared metrics module for LLM Provider Service."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

logger = create_service_logger("llm_provider.metrics")

_metrics: dict[str, Any] | None = None


def get_metrics() -> dict[str, Any]:
    """Get or create shared metrics instances (Singleton Pattern)."""
    global _metrics
    if _metrics is None:
        logger.info("Initializing shared LLM Provider Service metrics registry.")
        _metrics = _create_metrics()
    return _metrics


def _create_metrics() -> dict[str, Any]:
    """Create all Prometheus metrics for LLM Provider Service."""
    try:
        metrics = {
            # Standard HTTP Metrics
            "http_requests_total": Counter(
                "llm_provider_http_requests_total",
                "Total HTTP requests to LLM Provider Service",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "http_request_duration_seconds": Histogram(
                "llm_provider_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=REGISTRY,
            ),
            # LLM-specific Metrics
            "llm_requests_total": Counter(
                "llm_provider_requests_total",
                "Total LLM API requests",
                ["provider", "model", "request_type", "status"],
                registry=REGISTRY,
            ),
            "llm_response_duration_seconds": Histogram(
                "llm_provider_response_duration_seconds",
                "LLM API response time in seconds",
                ["provider", "model", "cached"],
                buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
                registry=REGISTRY,
            ),
            "llm_tokens_used_total": Counter(
                "llm_provider_tokens_used_total",
                "Total tokens used by LLM providers",
                ["provider", "model", "token_type"],
                registry=REGISTRY,
            ),
            "llm_cost_dollars_total": Counter(
                "llm_provider_cost_dollars_total",
                "Total estimated cost in USD",
                ["provider", "model"],
                registry=REGISTRY,
            ),
            "llm_cache_hits_total": Counter(
                "llm_provider_cache_hits_total",
                "Total cache hits for LLM responses",
                ["provider"],
                registry=REGISTRY,
            ),
            "llm_circuit_breaker_state": Gauge(
                "llm_provider_circuit_breaker_state",
                "Circuit breaker state (0=closed, 1=open, 2=half_open)",
                ["provider"],
                registry=REGISTRY,
            ),
            "llm_concurrent_requests": Gauge(
                "llm_provider_concurrent_requests",
                "Current number of concurrent LLM requests",
                ["provider"],
                registry=REGISTRY,
            ),
        }
        return metrics
    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(
                f"Metrics already registered: {e} – reusing existing collectors from REGISTRY.",
            )
            return _get_existing_metrics()
        raise


def get_http_metrics() -> dict[str, Any]:
    """Get metrics required by the HTTP API component."""
    all_metrics = get_metrics()
    return {
        "http_requests_total": all_metrics.get("http_requests_total"),
        "http_request_duration_seconds": all_metrics.get("http_request_duration_seconds"),
    }


def get_llm_metrics() -> dict[str, Any]:
    """Get metrics required by LLM operations."""
    all_metrics = get_metrics()
    return {
        "llm_requests_total": all_metrics.get("llm_requests_total"),
        "llm_response_duration_seconds": all_metrics.get("llm_response_duration_seconds"),
        "llm_tokens_used_total": all_metrics.get("llm_tokens_used_total"),
        "llm_cost_dollars_total": all_metrics.get("llm_cost_dollars_total"),
        "llm_cache_hits_total": all_metrics.get("llm_cache_hits_total"),
        "llm_circuit_breaker_state": all_metrics.get("llm_circuit_breaker_state"),
        "llm_concurrent_requests": all_metrics.get("llm_concurrent_requests"),
    }


def _get_existing_metrics() -> dict[str, Any]:
    """Return already-registered collectors from the global REGISTRY.

    Falling back to an empty dict disables metrics entirely. This helper looks up the
    collectors by their canonical metric names so middleware and services keep
    working even when the module is imported more than once (common during tests).
    """
    from prometheus_client import REGISTRY

    name_map = {
        "http_requests_total": "llm_provider_http_requests_total",
        "http_request_duration_seconds": "llm_provider_http_request_duration_seconds",
        "llm_requests_total": "llm_provider_requests_total",
        "llm_response_duration_seconds": "llm_provider_response_duration_seconds",
        "llm_tokens_used_total": "llm_provider_tokens_used_total",
        "llm_cost_dollars_total": "llm_provider_cost_dollars_total",
        "llm_cache_hits_total": "llm_provider_cache_hits_total",
        "llm_circuit_breaker_state": "llm_provider_circuit_breaker_state",
        "llm_concurrent_requests": "llm_provider_concurrent_requests",
    }

    existing: dict[str, Any] = {}
    registry_collectors = getattr(REGISTRY, "_names_to_collectors", None)
    for logical_key, metric_name in name_map.items():
        try:
            if registry_collectors and metric_name in registry_collectors:
                existing[logical_key] = registry_collectors[metric_name]
            else:
                for collector in REGISTRY.collect():
                    if collector.name == metric_name:
                        existing[logical_key] = collector
                        break
        except Exception as exc:
            logger.error("Error retrieving LLM metric '%s': %s", metric_name, exc)

    return existing
