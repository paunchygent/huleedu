"""Shared metrics module for NLP Service.

This module ensures metrics are created once and shared between components,
preventing duplicate registration errors while maintaining unified metrics endpoint.
"""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Histogram

logger = create_service_logger("nlp_service.metrics")

# Global metrics instances (created once, shared by worker)
_metrics: dict[str, Any] | None = None


def get_metrics() -> dict[str, Any]:
    """Get or create shared metrics instances.

    Returns:
        Dictionary of metric instances keyed by metric name

    Thread-safe singleton pattern for metrics initialization.
    """
    global _metrics

    if _metrics is None:
        _metrics = _create_metrics()
        logger.info("Shared metrics initialized")
        logger.info(f"Available metrics: {list(_metrics.keys())}")

    return _metrics


def _create_metrics() -> dict[str, Any]:
    """Create Prometheus metrics for the NLP Service.

    Returns:
        Dictionary of metric instances keyed by metric name
    """
    try:
        metrics = {
            "nlp_operations_total": Counter(
                "nlp_operations_total",
                "Total NLP analysis operations performed",
                ["operation_type", "status"],
                registry=REGISTRY,
            ),
            "nlp_processing_duration_seconds": Histogram(
                "nlp_processing_duration_seconds",
                "NLP processing duration in seconds",
                ["operation_type"],
                registry=REGISTRY,
            ),
            "student_matches_found": Histogram(
                "nlp_student_matches_found",
                "Distribution of student matches found per analysis",
                buckets=(0, 1, 2, 5, 10, 20, 50, 100),
                registry=REGISTRY,
            ),
            "kafka_queue_latency_seconds": Histogram(
                "nlp_kafka_message_queue_latency_seconds",
                "Latency between event timestamp and processing start",
                registry=REGISTRY,
            ),
            "nlp_batch_size": Histogram(
                "nlp_batch_size",
                "Size of batches processed by NLP service",
                buckets=(1, 5, 10, 25, 50, 100, 250, 500),
                registry=REGISTRY,
            ),
        }

        logger.info("Successfully created all metrics")
        return metrics

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(f"Metrics already exist in registry: {e} – reusing existing collectors.")
            return _get_existing_metrics()
        else:
            raise


def _get_existing_metrics() -> dict[str, Any]:
    """Return already-registered collectors from the global Prometheus REGISTRY."""

    from prometheus_client import REGISTRY

    name_map: dict[str, str] = {
        "nlp_operations_total": "nlp_operations_total",
        "nlp_processing_duration_seconds": "nlp_processing_duration_seconds",
        "student_matches_found": "nlp_student_matches_found",
        "kafka_queue_latency_seconds": "nlp_kafka_message_queue_latency_seconds",
        "nlp_batch_size": "nlp_batch_size",
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
            logger.error("Error retrieving NLP metric '%s': %s", metric_name, exc)

    return existing


def get_business_metrics() -> dict[str, Any]:
    """Get business intelligence metrics for worker components.

    Returns:
        Dictionary containing business metrics
    """
    all_metrics = get_metrics()
    return {
        "student_matches_found": all_metrics.get("student_matches_found"),
        "kafka_queue_latency_seconds": all_metrics.get("kafka_queue_latency_seconds"),
        "nlp_batch_size": all_metrics.get("nlp_batch_size"),
    }
