"""Shared metrics module for Batch Conductor Service.

This module ensures metrics are created once and shared between HTTP and Kafka consumer components,
preventing duplicate registration errors while maintaining unified metrics endpoint.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("bcs.metrics")

# Global metrics instances (created once, shared by HTTP and Kafka consumer)
_metrics: dict[str, Any] | None = None


def get_metrics() -> dict[str, Any]:
    """Get or create shared metrics instances.

    Returns:
        Dictionary of metric instances keyed by metric name

    Thread-safe singleton pattern for metrics initialization.
    """
    global _metrics

    if _metrics is None:
        logger.info("Initializing shared BCS metrics registry")
        _metrics = _create_metrics()
        logger.info(f"BCS metrics initialized: {list(_metrics.keys())}")

    return _metrics


def _create_metrics() -> dict[str, Any]:
    """Create Prometheus metrics for the Batch Conductor Service.

    Returns:
        Dictionary of metric instances keyed by metric name
    """
    try:
        metrics = {
            # Standard HTTP Metrics
            "http_requests_total": Counter(
                "bcs_http_requests_total",
                "Total HTTP requests to Batch Conductor Service",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "http_request_duration_seconds": Histogram(
                "bcs_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=REGISTRY,
            ),
            # CRITICAL BUSINESS INTELLIGENCE METRICS
            "pipeline_resolutions_total": Counter(
                "huleedu_bcs_pipeline_resolutions_total",
                "Total pipeline resolutions processed by BCS",
                ["requested_pipeline", "outcome"],  # e.g., 'ai_feedback', 'success'/'failure'
                registry=REGISTRY,
            ),
            "pipeline_resolution_duration_seconds": Histogram(
                "huleedu_bcs_pipeline_resolution_duration_seconds",
                "Time taken for BCS to resolve a pipeline request",
                ["requested_pipeline"],
                buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60),  # Meaningful buckets
                registry=REGISTRY,
            ),
            "events_processed_total": Counter(
                "huleedu_bcs_events_processed_total",
                "Total events processed by the BCS Kafka consumer to build state",
                ["event_type", "outcome"],  # e.g., 'spellcheck_completed', 'success'
                registry=REGISTRY,
            ),
            # Legacy metrics for backward compatibility
            "els_requests": Counter(
                "bcs_els_requests_total",
                "Total ELS HTTP requests",
                ["operation", "status"],
                registry=REGISTRY,
            ),
        }

        logger.info("Successfully created all BCS metrics")
        return metrics

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(f"BCS metrics already exist in registry: {e}")
            # Return existing metrics from registry
            return _get_existing_metrics()
        else:
            raise


def _get_existing_metrics() -> dict[str, Any]:
    """Retrieve existing metrics from the global Prometheus registry.

    This is called when `_create_metrics()` detects a duplicated time-series error,
    meaning the metrics were already registered elsewhere (e.g. another thread or
    a reloaded module).  We look them up by their *real* metric names so we can
    return proper collector references instead of an empty dict – otherwise
    downstream code such as the HTTP middleware will silently receive `None` and
    no metrics will ever be recorded, causing E2E tests to fail.
    """

    logger.warning(
        "BCS metrics already exist – reusing existing collectors from REGISTRY",
    )

    from prometheus_client import REGISTRY  # local import to avoid cycles

    # Mapping of logical keys used throughout the service to real metric names
    name_map = {
        "http_requests_total": "bcs_http_requests_total",
        "http_request_duration_seconds": "bcs_http_request_duration_seconds",
        "pipeline_resolutions_total": "huleedu_bcs_pipeline_resolutions_total",
        "pipeline_resolution_duration_seconds": "huleedu_bcs_pipeline_resolution_duration_seconds",
        "events_processed_total": "huleedu_bcs_events_processed_total",
        "els_requests": "bcs_els_requests_total",
    }

    existing: dict[str, Any] = {}
    # REGISTRY._names_to_collectors is considered internal but is stable and
    # avoids expensive iteration over collectors.  Fallback to iteration if the
    # attribute is missing (unlikely).
    registry_collectors = getattr(REGISTRY, "_names_to_collectors", None)
    for logical_key, metric_name in name_map.items():
        try:
            if registry_collectors is not None and metric_name in registry_collectors:
                existing[logical_key] = registry_collectors[metric_name]
            else:
                # Fallback: iterate over all collectors
                for collector in REGISTRY.collect():
                    if collector.name == metric_name:
                        existing[logical_key] = collector
                        break
        except Exception as exc:  # pragma: no cover – defensive
            logger.error("Error retrieving metric '%s': %s", metric_name, exc)

    return existing


def get_http_metrics() -> dict[str, Any]:
    """Get HTTP operational metrics for web components.

    Returns:
        Dictionary containing HTTP and pipeline resolution metrics
    """
    all_metrics = get_metrics()
    return {
        "http_requests_total": all_metrics.get("http_requests_total"),
        "http_request_duration_seconds": all_metrics.get("http_request_duration_seconds"),
        "pipeline_resolutions_total": all_metrics.get("pipeline_resolutions_total"),
        "pipeline_resolution_duration_seconds": all_metrics.get(
            "pipeline_resolution_duration_seconds"
        ),
        "els_requests": all_metrics.get("els_requests"),
    }


def get_kafka_consumer_metrics() -> dict[str, Any]:
    """Get business intelligence metrics for Kafka consumer components.

    Returns:
        Dictionary containing event processing metrics
    """
    all_metrics = get_metrics()
    return {
        "events_processed_total": all_metrics.get("events_processed_total"),
    }


def get_pipeline_service_metrics() -> dict[str, Any]:
    """Get metrics for pipeline resolution service implementation.

    Returns:
        Dictionary containing pipeline resolution business metrics
    """
    all_metrics = get_metrics()
    return {
        "pipeline_resolutions_total": all_metrics.get("pipeline_resolutions_total"),
        "pipeline_resolution_duration_seconds": all_metrics.get(
            "pipeline_resolution_duration_seconds"
        ),
    }
