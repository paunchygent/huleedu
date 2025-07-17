"""Prometheus-based content metrics implementation."""

from __future__ import annotations

from common_core.observability_enums import OperationType
from common_core.status_enums import OperationStatus
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

    def record_operation(self, operation: OperationType, status: OperationStatus) -> None:
        """
        Record a content operation metric.

        Args:
            operation: Operation type (OperationType enum)
            status: Operation status (OperationStatus enum)
        """
        try:
            self.content_operations.labels(operation=operation.value, status=status.value).inc()
        except Exception as e:
            logger.error(f"Error recording content operation metric: {e}")
