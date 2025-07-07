"""Shared metrics module for CJ Assessment Service.

This module ensures metrics are created once and shared between HTTP and worker components,
preventing duplicate registration errors while maintaining unified metrics endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

from common_core.observability_enums import MetricName

logger = create_service_logger("cj_assessment_service.metrics")

# Global metrics instances (created once, shared by HTTP and worker)
_metrics: dict[str, Any] | None = None


def get_metrics(database_metrics: Optional[DatabaseMetrics] = None) -> dict[str, Any]:
    """Get or create shared metrics instances.

    Returns:
        Dictionary of metric instances keyed by metric name

    Thread-safe singleton pattern for metrics initialization.
    """
    global _metrics

    if _metrics is None:
        _metrics = _create_metrics(database_metrics)
        logger.info("Shared metrics initialized")
        logger.info(f"Available metrics: {list(_metrics.keys())}")

    return _metrics


def _create_metrics(database_metrics: Optional[DatabaseMetrics] = None) -> dict[str, Any]:
    """Create Prometheus metrics for the CJ Assessment Service.

    Returns:
        Dictionary of metric instances keyed by metric name
    """
    try:
        metrics = {
            # HTTP operational metrics
            "request_count": Counter(
                "cj_assessment_http_requests_total",
                "Total HTTP requests",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "request_duration": Histogram(
                "cj_assessment_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=REGISTRY,
            ),
            # CJ Assessment business metrics using standardized names
            "cj_assessment_operations": Counter(
                "cj_assessment_operations_total",
                "Total CJ assessment operations",
                ["operation", "status"],
                registry=REGISTRY,
            ),
            "llm_api_calls": Counter(
                "cj_assessment_llm_api_calls_total",
                "Total LLM API calls",
                ["provider", "model", "status"],
                registry=REGISTRY,
            ),
            # Business intelligence metrics using MetricName enum
            MetricName.PIPELINE_EXECUTION_TIME.value: Histogram(
                "huleedu_cj_comparisons_made",
                "Distribution of comparisons made per CJ assessment batch",
                buckets=(0, 10, 25, 50, 100, 200, 500, 1000),
                registry=REGISTRY,
            ),
            "cj_assessment_duration_seconds": Histogram(
                "huleedu_cj_assessment_duration_seconds",
                "Duration of complete CJ assessment workflows",
                buckets=(10, 30, 60, 120, 300, 600, 1200),
                registry=REGISTRY,
            ),
            "kafka_queue_latency_seconds": Histogram(
                "kafka_message_queue_latency_seconds",
                "Latency between event timestamp and processing start",
                registry=REGISTRY,
            ),
        }

        # Add database metrics if provided
        if database_metrics:
            db_metrics = database_metrics.get_metrics()
            metrics.update(db_metrics)
            logger.info("Database metrics integrated into CJ Assessment Service metrics")

        logger.info("Successfully created all CJ Assessment metrics")
        return metrics

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(f"Metrics already exist in registry: {e}")
            # Return existing metrics from registry
            existing = _get_existing_metrics()
            # Add database metrics to existing if provided
            if database_metrics:
                db_metrics = database_metrics.get_metrics()
                existing.update(db_metrics)
            return existing
        else:
            raise


def _get_existing_metrics() -> dict[str, Any]:
    """Retrieve existing metric collectors from the global Prometheus REGISTRY.

    Returning an empty dict disables metrics after duplicated-registration errors.
    Instead, we re-hydrate the collectors so the service and middleware can
    continue to record metrics even when the module is imported multiple times
    (common in test runners or when both the worker and HTTP app import it).
    """

    from prometheus_client import REGISTRY  # local import to avoid circular deps

    name_map: dict[str, str] = {
        "request_count": "cj_assessment_http_requests_total",
        "request_duration": "cj_assessment_http_request_duration_seconds",
        "cj_assessment_operations": "cj_assessment_operations_total",
        "llm_api_calls": "cj_assessment_llm_api_calls_total",
        MetricName.PIPELINE_EXECUTION_TIME.value: "huleedu_cj_comparisons_made",
        "cj_assessment_duration_seconds": "huleedu_cj_assessment_duration_seconds",
        "kafka_queue_latency_seconds": "kafka_message_queue_latency_seconds",
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
        except Exception as exc:  # pragma: no cover
            logger.error("Error retrieving CJ metric '%s': %s", metric_name, exc)

    return existing


def get_business_metrics() -> dict[str, Any]:
    """Get business intelligence metrics for worker components.

    Returns:
        Dictionary containing business metrics
    """
    all_metrics = get_metrics()
    return {
        MetricName.PIPELINE_EXECUTION_TIME.value: all_metrics.get(
            MetricName.PIPELINE_EXECUTION_TIME.value
        ),
        "cj_assessment_duration_seconds": all_metrics.get("cj_assessment_duration_seconds"),
        "kafka_queue_latency_seconds": all_metrics.get("kafka_queue_latency_seconds"),
        "llm_api_calls": all_metrics.get("llm_api_calls"),
    }


def setup_cj_assessment_database_monitoring(
    engine: AsyncEngine,
    service_name: str = "cj_assessment_service",
    existing_metrics: Optional[Dict[str, Any]] = None,
) -> DatabaseMetrics:
    """
    Setup comprehensive database monitoring for CJ Assessment Service.

    Args:
        engine: SQLAlchemy async engine for CJ assessment database
        service_name: Service name for metrics labeling
        existing_metrics: Optional existing metrics dictionary to extend

    Returns:
        DatabaseMetrics instance configured for CJ assessment operations
    """
    return setup_database_monitoring(engine, service_name, existing_metrics)


def get_database_metrics() -> dict[str, Any]:
    """Get database metrics dictionary for integration with DatabaseMetrics.

    Returns:
        Dictionary containing database-related metrics from the service
    """
    all_metrics = get_metrics()
    return {
        "cj_assessment_operations": all_metrics.get("cj_assessment_operations"),
        "llm_api_calls": all_metrics.get("llm_api_calls"),
        "cj_assessment_duration_seconds": all_metrics.get("cj_assessment_duration_seconds"),
        "kafka_queue_latency_seconds": all_metrics.get("kafka_queue_latency_seconds"),
    }


def get_http_metrics() -> dict[str, Any]:
    """Get HTTP operational metrics for web components.

    Returns:
        Dictionary containing HTTP metrics
    """
    all_metrics = get_metrics()
    return {
        "request_count": all_metrics.get("request_count"),
        "request_duration": all_metrics.get("request_duration"),
        "cj_assessment_operations": all_metrics.get("cj_assessment_operations"),
        "llm_api_calls": all_metrics.get("llm_api_calls"),
    }
