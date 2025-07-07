"""Service-specific metrics for Result Aggregator Service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("result_aggregator_service.metrics")


class ResultAggregatorMetrics:
    """Service-specific metrics with database monitoring integration."""

    def __init__(self, database_metrics: Optional[DatabaseMetrics] = None) -> None:
        # API metrics
        self.api_requests_total = Counter(
            "ras_api_requests_total", "Total API requests", ["endpoint", "method", "status_code"]
        )

        self.api_request_duration = Histogram(
            "ras_api_request_duration_seconds", "API request duration", ["endpoint", "method"]
        )

        self.api_errors_total = Counter(
            "ras_api_errors_total", "Total API errors", ["endpoint", "error_type"]
        )

        # Kafka consumer metrics
        self.messages_processed = Counter(
            "ras_messages_processed_total", "Total messages processed"
        )

        self.message_processing_time = Histogram(
            "ras_message_processing_duration_seconds", "Message processing duration"
        )

        self.consumer_errors = Counter("ras_consumer_errors_total", "Total consumer errors")

        self.dlq_messages_sent = Counter("ras_dlq_messages_sent_total", "Messages sent to DLQ")

        # Database metrics
        self.db_operations = Counter(
            "ras_db_operations_total", "Total database operations", ["operation", "status"]
        )

        self.db_operation_duration = Histogram(
            "ras_db_operation_duration_seconds", "Database operation duration", ["operation"]
        )

        # Cache metrics
        self.cache_hits_total = Counter("ras_cache_hits_total", "Cache hits", ["cache_type"])

        self.cache_misses_total = Counter("ras_cache_misses_total", "Cache misses", ["cache_type"])

        # Business metrics
        self.batches_aggregated = Counter(
            "ras_batches_aggregated_total", "Total batches aggregated"
        )

        self.essays_aggregated = Counter(
            "ras_essays_aggregated_total", "Total essays aggregated", ["phase"]
        )

        # Data quality metrics
        self.invalid_messages_total = Counter(
            "ras_invalid_messages_total",
            "Total messages that failed deserialization or validation",
            ["topic", "error_type"],  # error_type can be 'JSONDecodeError' or 'ValidationError'
        )

        # Database metrics integration
        self.database_metrics = database_metrics
        if database_metrics:
            logger.info("Database metrics integrated into ResultAggregatorMetrics")

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics including database metrics."""
        metrics = {
            "api_requests_total": self.api_requests_total,
            "api_request_duration": self.api_request_duration,
            "api_errors_total": self.api_errors_total,
            "messages_processed": self.messages_processed,
            "message_processing_time": self.message_processing_time,
            "consumer_errors": self.consumer_errors,
            "dlq_messages_sent": self.dlq_messages_sent,
            "db_operations": self.db_operations,
            "db_operation_duration": self.db_operation_duration,
            "cache_hits_total": self.cache_hits_total,
            "cache_misses_total": self.cache_misses_total,
            "batches_aggregated": self.batches_aggregated,
            "essays_aggregated": self.essays_aggregated,
            "invalid_messages_total": self.invalid_messages_total,
        }

        # Add database metrics if available
        if self.database_metrics:
            db_metrics = self.database_metrics.get_metrics()
            metrics.update(db_metrics)

        return metrics


def setup_result_aggregator_database_monitoring(
    engine: AsyncEngine,
    service_name: str = "result_aggregator_service",
    existing_metrics: Optional[Dict[str, Any]] = None,
) -> DatabaseMetrics:
    """
    Setup comprehensive database monitoring for Result Aggregator Service.

    Args:
        engine: SQLAlchemy async engine for result aggregator database
        service_name: Service name for metrics labeling
        existing_metrics: Optional existing metrics dictionary to extend

    Returns:
        DatabaseMetrics instance configured for result aggregation operations
    """
    return setup_database_monitoring(engine, service_name, existing_metrics)
