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
            "llm_provider_api_errors_total": Counter(
                "llm_provider_api_errors_total",
                "Total API errors by provider, error_type, and HTTP status",
                ["provider", "error_type", "http_status_code"],
                registry=REGISTRY,
            ),
            "llm_provider_errors_total": Counter(
                "llm_provider_errors_total",
                "Total provider errors by provider, model, and error type",
                ["provider", "model", "error_type"],
                registry=REGISTRY,
            ),
            "llm_response_duration_seconds": Histogram(
                "llm_provider_response_duration_seconds",
                "LLM API response time in seconds",
                ["provider", "model"],
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
            "circuit_breaker_state": Gauge(
                "llm_provider_circuit_breaker_state",
                "Circuit breaker state (0=closed, 1=open, 2=half_open)",
                ["service", "circuit_name"],
                registry=REGISTRY,
            ),
            "llm_concurrent_requests": Gauge(
                "llm_provider_concurrent_requests",
                "Current number of concurrent LLM requests",
                ["provider"],
                registry=REGISTRY,
            ),
            # Enhanced Performance Metrics - Phase 7
            "llm_response_time_percentiles": Histogram(
                "llm_provider_response_time_percentiles",
                "LLM response time percentiles optimized for sub-500ms tracking",
                ["provider", "model", "request_type"],
                buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
                registry=REGISTRY,
            ),
            "llm_validation_duration_seconds": Histogram(
                "llm_provider_validation_duration_seconds",
                "JSON schema validation duration in seconds",
                ["provider", "validation_type"],
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
                registry=REGISTRY,
            ),
            "llm_queue_depth": Gauge(
                "llm_provider_queue_depth",
                "Current number of requests in queue",
                ["queue_type"],
                registry=REGISTRY,
            ),
            "llm_queue_processing_time_seconds": Histogram(
                "llm_provider_queue_processing_time_seconds",
                "Time spent processing queue requests",
                ["provider", "status"],
                buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
                registry=REGISTRY,
            ),
            "llm_queue_wait_time_seconds": Histogram(
                "llm_provider_queue_wait_time_seconds",
                "Time requests spend waiting in the queue before processing",
                ["queue_processing_mode", "result"],
                buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
                registry=REGISTRY,
            ),
            "llm_comparison_callbacks_total": Counter(
                "llm_provider_comparison_callbacks_total",
                "Total callbacks published by the queue processor",
                ["queue_processing_mode", "result"],
                registry=REGISTRY,
            ),
            "llm_queue_expiry_total": Counter(
                "llm_provider_queue_expiry_total",
                "Total expired queue requests",
                ["provider", "queue_processing_mode", "expiry_reason"],
                registry=REGISTRY,
            ),
            "llm_queue_expiry_age_seconds": Histogram(
                "llm_provider_queue_expiry_age_seconds",
                "Age of requests at expiry in seconds",
                ["provider", "queue_processing_mode"],
                buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
                registry=REGISTRY,
            ),
            "llm_serial_bundle_calls_total": Counter(
                "llm_provider_serial_bundle_calls_total",
                "Total serial-bundle comparison calls",
                ["provider", "model"],
                registry=REGISTRY,
            ),
            "llm_serial_bundle_items_per_call": Histogram(
                "llm_provider_serial_bundle_items_per_call",
                "Number of items per serial-bundle call",
                ["provider", "model"],
                buckets=(1, 2, 4, 8, 16, 32, 64),
                registry=REGISTRY,
            ),
            # Batch API job-level metrics (Phase 2)
            "llm_batch_api_jobs_total": Counter(
                "llm_provider_batch_api_jobs_total",
                "Total batch API jobs by provider, model, and status",
                ["provider", "model", "status"],
                registry=REGISTRY,
            ),
            "llm_batch_api_items_per_job": Histogram(
                "llm_provider_batch_api_items_per_job",
                "Number of items per batch API job",
                ["provider", "model"],
                buckets=(1, 2, 4, 8, 16, 32, 64, 128),
                registry=REGISTRY,
            ),
            "llm_batch_api_job_duration_seconds": Histogram(
                "llm_provider_batch_api_job_duration_seconds",
                "Duration of batch API jobs in seconds",
                ["provider", "model"],
                buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
                registry=REGISTRY,
            ),
            "circuit_breaker_state_changes": Counter(
                "llm_provider_circuit_breaker_state_changes_total",
                "Total circuit breaker state changes",
                ["service", "circuit_name", "from_state", "to_state"],
                registry=REGISTRY,
            ),
            "circuit_breaker_calls_total": Counter(
                "llm_provider_circuit_breaker_calls_total",
                "Total circuit breaker calls",
                ["service", "circuit_name", "result"],
                registry=REGISTRY,
            ),
            "llm_provider_connection_pool_size": Gauge(
                "llm_provider_connection_pool_size",
                "Current connection pool size per provider",
                ["provider"],
                registry=REGISTRY,
            ),
            "llm_provider_connection_pool_active": Gauge(
                "llm_provider_connection_pool_active",
                "Active connections in pool per provider",
                ["provider"],
                registry=REGISTRY,
            ),
            "llm_queue_overflow_total": Counter(
                "llm_provider_queue_overflow_total",
                "Total queue overflow events",
                ["queue_type"],
                registry=REGISTRY,
            ),
            "llm_request_lifecycle_duration_seconds": Histogram(
                "llm_provider_request_lifecycle_duration_seconds",
                "Complete request lifecycle duration (queue -> processing -> response)",
                ["provider", "lifecycle_stage"],
                buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
                registry=REGISTRY,
            ),
            "llm_provider_availability_percentage": Gauge(
                "llm_provider_availability_percentage",
                "Provider availability percentage (0-100)",
                ["provider"],
                registry=REGISTRY,
            ),
            "llm_provider_prompt_cache_events_total": Counter(
                "llm_provider_prompt_cache_events_total",
                "Prompt cache events by provider/model/result (hit, miss, bypass)",
                ["provider", "model", "result"],
                registry=REGISTRY,
            ),
            "llm_provider_prompt_cache_tokens_total": Counter(
                "llm_provider_prompt_cache_tokens_total",
                "Prompt cache token accounting (read/write) by provider and model",
                ["provider", "model", "direction"],
                registry=REGISTRY,
            ),
            "llm_provider_prompt_blocks_total": Counter(
                "llm_provider_prompt_blocks_total",
                "Prompt blocks observed by provider, model, target, cacheability, and ttl.",
                ["provider", "model", "target", "cacheable", "ttl"],
                registry=REGISTRY,
            ),
            "llm_provider_prompt_tokens_histogram": Histogram(
                "llm_provider_prompt_tokens_histogram",
                "Approximate token counts per prompt section (cacheable vs dynamic).",
                ["provider", "model", "section"],
                buckets=(16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192),
                registry=REGISTRY,
            ),
            "llm_provider_cache_scope_total": Counter(
                "llm_provider_cache_scope_total",
                "Prompt cache outcomes by scope (assignment/ad-hoc) and result.",
                ["provider", "model", "scope", "result"],
                registry=REGISTRY,
            ),
            "llm_provider_prompt_ttl_violations_total": Counter(
                "llm_provider_prompt_ttl_violations_total",
                "TTL ordering validation failures detected while building provider payloads.",
                ["provider", "model", "stage"],
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
        "llm_provider_api_errors_total": all_metrics.get("llm_provider_api_errors_total"),
        "llm_provider_errors_total": all_metrics.get("llm_provider_errors_total"),
        "llm_response_duration_seconds": all_metrics.get("llm_response_duration_seconds"),
        "llm_tokens_used_total": all_metrics.get("llm_tokens_used_total"),
        "llm_cost_dollars_total": all_metrics.get("llm_cost_dollars_total"),
        "circuit_breaker_state": all_metrics.get("circuit_breaker_state"),
        "llm_concurrent_requests": all_metrics.get("llm_concurrent_requests"),
        # Enhanced Performance Metrics - Phase 7
        "llm_response_time_percentiles": all_metrics.get("llm_response_time_percentiles"),
        "llm_validation_duration_seconds": all_metrics.get("llm_validation_duration_seconds"),
        "circuit_breaker_state_changes": all_metrics.get("circuit_breaker_state_changes"),
        "circuit_breaker_calls_total": all_metrics.get("circuit_breaker_calls_total"),
        "llm_provider_connection_pool_size": all_metrics.get("llm_provider_connection_pool_size"),
        "llm_provider_connection_pool_active": all_metrics.get(
            "llm_provider_connection_pool_active"
        ),
        "llm_request_lifecycle_duration_seconds": all_metrics.get(
            "llm_request_lifecycle_duration_seconds"
        ),
        "llm_provider_availability_percentage": all_metrics.get(
            "llm_provider_availability_percentage"
        ),
        "llm_provider_prompt_cache_events_total": all_metrics.get(
            "llm_provider_prompt_cache_events_total"
        ),
        "llm_provider_prompt_cache_tokens_total": all_metrics.get(
            "llm_provider_prompt_cache_tokens_total"
        ),
        "llm_provider_prompt_blocks_total": all_metrics.get("llm_provider_prompt_blocks_total"),
        "llm_provider_prompt_tokens_histogram": all_metrics.get(
            "llm_provider_prompt_tokens_histogram"
        ),
        "llm_provider_cache_scope_total": all_metrics.get("llm_provider_cache_scope_total"),
        "llm_provider_prompt_ttl_violations_total": all_metrics.get(
            "llm_provider_prompt_ttl_violations_total"
        ),
    }


def get_queue_metrics() -> dict[str, Any]:
    """Get metrics required by queue operations."""
    all_metrics = get_metrics()
    return {
        "llm_queue_depth": all_metrics.get("llm_queue_depth"),
        "llm_queue_processing_time_seconds": all_metrics.get("llm_queue_processing_time_seconds"),
        "llm_queue_overflow_total": all_metrics.get("llm_queue_overflow_total"),
        "llm_request_lifecycle_duration_seconds": all_metrics.get(
            "llm_request_lifecycle_duration_seconds"
        ),
        "llm_queue_wait_time_seconds": all_metrics.get("llm_queue_wait_time_seconds"),
        "llm_comparison_callbacks_total": all_metrics.get("llm_comparison_callbacks_total"),
        "llm_queue_expiry_total": all_metrics.get("llm_queue_expiry_total"),
        "llm_queue_expiry_age_seconds": all_metrics.get("llm_queue_expiry_age_seconds"),
        "llm_serial_bundle_calls_total": all_metrics.get("llm_serial_bundle_calls_total"),
        "llm_serial_bundle_items_per_call": all_metrics.get("llm_serial_bundle_items_per_call"),
        "llm_batch_api_jobs_total": all_metrics.get("llm_batch_api_jobs_total"),
        "llm_batch_api_items_per_job": all_metrics.get("llm_batch_api_items_per_job"),
        "llm_batch_api_job_duration_seconds": all_metrics.get("llm_batch_api_job_duration_seconds"),
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
        "llm_provider_api_errors_total": "llm_provider_api_errors_total",
        "llm_provider_errors_total": "llm_provider_errors_total",
        "llm_response_duration_seconds": "llm_provider_response_duration_seconds",
        "llm_tokens_used_total": "llm_provider_tokens_used_total",
        "llm_cost_dollars_total": "llm_provider_cost_dollars_total",
        "circuit_breaker_state": "llm_provider_circuit_breaker_state",
        "llm_concurrent_requests": "llm_provider_concurrent_requests",
        # Enhanced Performance Metrics - Phase 7
        "llm_response_time_percentiles": "llm_provider_response_time_percentiles",
        "llm_validation_duration_seconds": "llm_provider_validation_duration_seconds",
        "llm_queue_depth": "llm_provider_queue_depth",
        "llm_queue_processing_time_seconds": "llm_provider_queue_processing_time_seconds",
        "circuit_breaker_state_changes": "llm_provider_circuit_breaker_state_changes_total",
        "circuit_breaker_calls_total": "llm_provider_circuit_breaker_calls_total",
        "llm_provider_connection_pool_size": "llm_provider_connection_pool_size",
        "llm_provider_connection_pool_active": "llm_provider_connection_pool_active",
        "llm_queue_overflow_total": "llm_provider_queue_overflow_total",
        "llm_request_lifecycle_duration_seconds": "llm_provider_request_lifecycle_duration_seconds",
        "llm_provider_availability_percentage": "llm_provider_availability_percentage",
        "llm_queue_wait_time_seconds": "llm_provider_queue_wait_time_seconds",
        "llm_comparison_callbacks_total": "llm_provider_comparison_callbacks_total",
        "llm_queue_expiry_total": "llm_provider_queue_expiry_total",
        "llm_queue_expiry_age_seconds": "llm_provider_queue_expiry_age_seconds",
        "llm_serial_bundle_calls_total": "llm_provider_serial_bundle_calls_total",
        "llm_serial_bundle_items_per_call": "llm_provider_serial_bundle_items_per_call",
        "llm_batch_api_jobs_total": "llm_provider_batch_api_jobs_total",
        "llm_batch_api_items_per_job": "llm_provider_batch_api_items_per_job",
        "llm_batch_api_job_duration_seconds": "llm_provider_batch_api_job_duration_seconds",
        "llm_provider_prompt_cache_events_total": "llm_provider_prompt_cache_events_total",
        "llm_provider_prompt_cache_tokens_total": "llm_provider_prompt_cache_tokens_total",
        "llm_provider_prompt_blocks_total": "llm_provider_prompt_blocks_total",
        "llm_provider_prompt_tokens_histogram": "llm_provider_prompt_tokens_histogram",
        "llm_provider_cache_scope_total": "llm_provider_cache_scope_total",
        "llm_provider_prompt_ttl_violations_total": "llm_provider_prompt_ttl_violations_total",
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


def get_circuit_breaker_metrics() -> dict[str, Any]:
    """Get metrics required by circuit breaker components."""
    all_metrics = get_llm_metrics()
    return {
        "circuit_breaker_state": all_metrics.get("circuit_breaker_state"),
        "circuit_breaker_state_changes": all_metrics.get("circuit_breaker_state_changes"),
        "circuit_breaker_calls_total": all_metrics.get("circuit_breaker_calls_total"),
    }
