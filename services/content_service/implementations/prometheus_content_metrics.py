"""Prometheus-based content metrics implementation."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter

from services.content_service.protocols import ContentMetricsProtocol

logger = create_service_logger("content.metrics.prometheus")


class PrometheusContentMetrics(ContentMetricsProtocol):
    """Prometheus-based implementation of content metrics collection."""

    def __init__(self, content_operations_counter: Counter) -> None:
        """
        Initialize Prometheus content metrics.

        Args:
            content_operations_counter: Prometheus counter for content operations
        """
        self.content_operations = content_operations_counter

    def record_operation(self, operation: str, status: str) -> None:
        """
        Record a content operation metric.

        Args:
            operation: Operation type ('upload', 'download')
            status: Operation status ('success', 'failed', 'error', 'not_found')
        """
        try:
            self.content_operations.labels(operation=operation, status=status).inc()
        except Exception as e:
            logger.error(f"Error recording content operation metric: {e}")
