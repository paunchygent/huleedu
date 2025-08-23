"""Prometheus metrics for Email Service.

This module provides comprehensive metrics collection for the Email Service,
following established HuleEdu patterns from CJ Assessment Service.
"""

from __future__ import annotations

from typing import Any, Optional

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

logger = create_service_logger("email_service.metrics")

# Global metrics dictionary to avoid re-creation
_metrics: dict[str, Any] = {}


def _create_metrics(database_metrics: Optional[DatabaseMetrics] = None) -> dict[str, Any]:
    """Create Prometheus metrics for the Email Service.

    Returns:
        Dictionary of metric instances keyed by metric name
    """
    try:
        metrics = {
            # HTTP operational metrics
            "request_count": Counter(
                "email_service_http_requests_total",
                "Total HTTP requests",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "request_duration": Histogram(
                "email_service_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=REGISTRY,
            ),
            # Email processing metrics
            "emails_sent_total": Counter(
                "emails_sent_total",
                "Total emails sent successfully",
                ["provider", "category", "template"],
                registry=REGISTRY,
            ),
            "emails_failed_total": Counter(
                "emails_failed_total",
                "Total email failures",
                ["provider", "category", "failure_reason"],
                registry=REGISTRY,
            ),
            "email_processing_duration_seconds": Histogram(
                "email_processing_duration_seconds",
                "Complete email processing duration in seconds",
                buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
                registry=REGISTRY,
            ),
            # Template processing metrics
            "template_render_duration_seconds": Histogram(
                "template_render_duration_seconds",
                "Template rendering duration in seconds",
                buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5),
                registry=REGISTRY,
            ),
            "template_render_total": Counter(
                "template_render_total",
                "Total template renderings",
                ["template_id", "status"],  # success/error
                registry=REGISTRY,
            ),
            # Email provider metrics
            "provider_response_time_seconds": Histogram(
                "provider_response_time_seconds",
                "Email provider API response time in seconds",
                buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
                registry=REGISTRY,
            ),
            "provider_requests_total": Counter(
                "provider_requests_total",
                "Total requests to email providers",
                ["provider", "status"],  # success/error
                registry=REGISTRY,
            ),
            # Queue and processing metrics
            "kafka_message_processing_duration_seconds": Histogram(
                "kafka_message_processing_duration_seconds",
                "Kafka message processing duration in seconds",
                buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
                registry=REGISTRY,
            ),
            "kafka_messages_processed_total": Counter(
                "kafka_messages_processed_total",
                "Total Kafka messages processed",
                ["status"],  # success/error
                registry=REGISTRY,
            ),
            "kafka_queue_latency_seconds": Histogram(
                "kafka_message_queue_latency_seconds",
                "Latency between event timestamp and processing start",
                registry=REGISTRY,
            ),
            # Email status tracking
            "email_status_changes_total": Counter(
                "email_status_changes_total",
                "Total email status changes",
                ["from_status", "to_status"],
                registry=REGISTRY,
            ),
            "pending_emails": Gauge(
                "pending_emails",
                "Number of emails currently pending processing",
                registry=REGISTRY,
            ),
            # Outbox event publishing metrics
            "outbox_events_published_total": Counter(
                "outbox_events_published_total",
                "Total events published via outbox pattern",
                ["event_type", "status"],
                registry=REGISTRY,
            ),
            "outbox_publish_duration_seconds": Histogram(
                "outbox_publish_duration_seconds",
                "Outbox event publishing duration in seconds",
                buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5),
                registry=REGISTRY,
            ),
            # Error and retry metrics
            "email_retries_total": Counter(
                "email_retries_total",
                "Total email retry attempts",
                ["provider", "retry_attempt"],
                registry=REGISTRY,
            ),
            "email_permanent_failures_total": Counter(
                "email_permanent_failures_total",
                "Total emails that failed after all retries",
                ["provider", "failure_reason"],
                registry=REGISTRY,
            ),
            # Business intelligence metrics
            "daily_email_volume": Gauge(
                "daily_email_volume",
                "Daily email volume by category",
                ["category", "status"],  # sent/failed
                registry=REGISTRY,
            ),
            "email_categories_total": Counter(
                "email_categories_total",
                "Total emails by category",
                ["category"],  # verification, password_reset, welcome, etc.
                registry=REGISTRY,
            ),
        }

        # Add database metrics if provided
        if database_metrics:
            db_metrics = database_metrics.get_metrics()
            metrics.update(db_metrics)
            logger.info("Database metrics integrated into Email Service metrics")

        logger.info("Successfully created all Email Service metrics")
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
    """Get existing metrics from the registry.

    Returns:
        Dictionary of existing metric instances
    """
    existing_metrics = {}

    # Get all collectors from the registry
    for collector in list(REGISTRY._collector_to_names.keys()):
        if hasattr(collector, "_name"):
            # Map metric names to their collectors
            metric_name = collector._name
            if "email_service" in metric_name or any(
                pattern in metric_name
                for pattern in [
                    "emails_",
                    "template_",
                    "provider_",
                    "kafka_message",
                    "outbox_",
                    "daily_email",
                ]
            ):
                # Convert metric name to our key format
                key = (
                    metric_name.replace("email_service_", "")
                    .replace("_total", "_total")
                    .replace("_seconds", "_seconds")
                )
                existing_metrics[key] = collector

    logger.info(f"Retrieved {len(existing_metrics)} existing Email Service metrics from registry")
    return existing_metrics


def get_metrics(database_metrics: Optional[DatabaseMetrics] = None) -> dict[str, Any]:
    """Get or create Email Service metrics.

    Args:
        database_metrics: Optional database metrics to include

    Returns:
        Dictionary of all Email Service metrics
    """
    global _metrics

    if not _metrics:
        _metrics = _create_metrics(database_metrics)
    elif database_metrics:
        # Add database metrics if they weren't included before
        db_metrics = database_metrics.get_metrics()
        _metrics.update(db_metrics)

    return _metrics


def get_business_metrics() -> dict[str, Any]:
    """Get business intelligence metrics for Email Service.

    Returns:
        Dictionary containing business metrics
    """
    all_metrics = get_metrics()
    return {
        "emails_sent_total": all_metrics.get("emails_sent_total"),
        "emails_failed_total": all_metrics.get("emails_failed_total"),
        "email_processing_duration_seconds": all_metrics.get("email_processing_duration_seconds"),
        "template_render_duration_seconds": all_metrics.get("template_render_duration_seconds"),
        "provider_response_time_seconds": all_metrics.get("provider_response_time_seconds"),
        "kafka_messages_processed_total": all_metrics.get("kafka_messages_processed_total"),
        "kafka_queue_latency_seconds": all_metrics.get("kafka_queue_latency_seconds"),
        "outbox_events_published_total": all_metrics.get("outbox_events_published_total"),
        "email_retries_total": all_metrics.get("email_retries_total"),
        "email_permanent_failures_total": all_metrics.get("email_permanent_failures_total"),
        "daily_email_volume": all_metrics.get("daily_email_volume"),
        "email_categories_total": all_metrics.get("email_categories_total"),
        "pending_emails": all_metrics.get("pending_emails"),
    }


def setup_email_service_database_monitoring(
    engine: Any, service_name: str = "email_service"
) -> DatabaseMetrics:
    """Set up database monitoring for Email Service.

    Args:
        engine: SQLAlchemy async engine
        service_name: Service name for metrics labeling

    Returns:
        DatabaseMetrics instance for the service
    """
    logger.info(f"Database monitoring setup complete for {service_name}")
    return setup_database_monitoring(engine, service_name)


def get_database_metrics() -> dict[str, Any]:
    """Get database-specific metrics for Email Service.

    Returns:
        Dictionary of database metrics
    """
    all_metrics = get_metrics()
    db_metrics = {}

    # Filter for database-related metrics
    for name, metric in all_metrics.items():
        if any(
            pattern in name
            for pattern in ["database", "connection", "query", "transaction", "pool"]
        ):
            db_metrics[name] = metric

    return db_metrics


def get_http_metrics() -> dict[str, Any]:
    """Get HTTP-specific metrics for Email Service.

    Returns:
        Dictionary of HTTP metrics
    """
    all_metrics = get_metrics()
    return {
        "request_count": all_metrics.get("request_count"),
        "request_duration": all_metrics.get("request_duration"),
    }


# Export main metrics getter for easy import
__all__ = [
    "get_metrics",
    "get_business_metrics",
    "setup_email_service_database_monitoring",
    "get_database_metrics",
    "get_http_metrics",
]
