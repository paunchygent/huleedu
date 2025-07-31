"""
Shared metrics module for Essay Lifecycle Service.

This module implements the singleton pattern to prevent registry conflicts
between HTTP and worker components, following the proven pattern from
CJ Assessment Service and Spell Checker Service.
"""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("essay_lifecycle_service.metrics")

# Global metrics instances (created once, shared by HTTP and worker)
_metrics: dict[str, Any] | None = None


def get_http_metrics() -> dict[str, Any]:
    """
    Get HTTP-focused metrics for startup_setup.py integration.

    Thread-safe singleton pattern ensures consistent metric instances
    across HTTP and worker components.
    """
    return get_metrics()


def get_business_metrics() -> dict[str, Any]:
    """
    Get business intelligence metrics for worker components.

    Returns subset of metrics focused on business intelligence
    and operational visibility for worker component usage.
    """
    all_metrics = get_metrics()
    return {
        "essay_state_transitions": all_metrics.get("essay_state_transitions"),
        "batch_processing_duration": all_metrics.get("batch_processing_duration"),
        "batch_coordination_events": all_metrics.get("batch_coordination_events"),
        "kafka_queue_latency": all_metrics.get("kafka_queue_latency"),
    }


def get_metrics(database_metrics: DatabaseMetrics | None = None) -> dict[str, Any]:
    """Thread-safe singleton pattern for metrics initialization."""
    global _metrics
    if _metrics is None:
        _metrics = _create_metrics(database_metrics)
    return _metrics


def _create_metrics(database_metrics: DatabaseMetrics | None = None) -> dict[str, Any]:
    """
    Create all metrics instances with shared registry.

    Creates both HTTP service metrics and business intelligence metrics
    for Essay Lifecycle Service observability.
    """
    registry = REGISTRY

    metrics = {
        # HTTP Service Metrics (existing functionality)
        "request_count": Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry,
        ),
        "request_duration": Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
        "essay_operations": Counter(
            "essay_operations_total",
            "Total essay operations",
            ["operation", "status"],
            registry=registry,
        ),
        # Business Intelligence Metrics (new for worker visibility)
        "essay_state_transitions": Counter(
            "huleedu_essay_state_transitions_total",
            "Essay state transitions by type and batch",
            ["from_state", "to_state", "batch_id"],
            registry=registry,
        ),
        "batch_processing_duration": Histogram(
            "huleedu_batch_processing_duration_seconds",
            "Batch processing duration from registration to completion",
            buckets=[30, 60, 300, 600, 1800, 3600],  # 30s to 1hr
            labelnames=["batch_id", "processing_phase"],
            registry=registry,
        ),
        "batch_coordination_events": Counter(
            "huleedu_batch_coordination_events_total",
            "Batch coordination events (readiness, completion)",
            ["event_type", "batch_id"],
            registry=registry,
        ),
        "kafka_queue_latency": Histogram(
            "kafka_message_queue_latency_seconds",
            "Kafka message queue latency",
            buckets=[0.1, 0.5, 1, 5, 10, 30],  # 100ms to 30s
            labelnames=["topic", "service"],
            registry=registry,
        ),
        # Consumer Health Monitoring Metrics
        "kafka_consumer_last_message_time": Gauge(
            "kafka_consumer_last_message_timestamp",
            "Timestamp of last processed Kafka message",
            ["consumer_group", "topic"],
            registry=registry,
        ),
        "kafka_consumer_messages_processed": Counter(
            "kafka_consumer_messages_processed_total",
            "Total messages processed by Kafka consumer",
            ["consumer_group", "topic", "status"],
            registry=registry,
        ),
        "kafka_consumer_health_status": Gauge(
            "kafka_consumer_health_status",
            "Current health status of Kafka consumer (1=healthy, 0=unhealthy)",
            ["consumer_group", "topic"],
            registry=registry,
        ),
        "kafka_consumer_consecutive_failures": Gauge(
            "kafka_consumer_consecutive_failures",
            "Number of consecutive processing failures",
            ["consumer_group", "topic"],
            registry=registry,
        ),
        "kafka_consumer_idle_seconds": Gauge(
            "kafka_consumer_idle_seconds",
            "Seconds since last message was processed",
            ["consumer_group", "topic"],
            registry=registry,
        ),
    }

    # Add database metrics if provided
    if database_metrics:
        db_metrics = database_metrics.get_metrics()
        metrics.update(db_metrics)
        logger.info("Database metrics integrated into Essay Lifecycle Service metrics")

    return metrics


def setup_essay_lifecycle_database_monitoring(
    engine: AsyncEngine,
    service_name: str = "essay_lifecycle_service",
    existing_metrics: dict[str, Any] | None = None,
) -> DatabaseMetrics:
    """
    Setup comprehensive database monitoring for Essay Lifecycle Service.

    Args:
        engine: SQLAlchemy async engine for essay lifecycle database
        service_name: Service name for metrics labeling
        existing_metrics: Optional existing metrics dictionary to extend

    Returns:
        DatabaseMetrics instance configured for essay lifecycle operations
    """
    return setup_database_monitoring(engine, service_name, existing_metrics)
