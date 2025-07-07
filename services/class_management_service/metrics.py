"""Metrics definitions for the Class Management Service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("class_management_service.metrics")


class CmsMetrics:
    """A container for all Prometheus metrics for the service."""

    def __init__(self, database_metrics: Optional[DatabaseMetrics] = None) -> None:
        # HTTP and API metrics
        self.http_requests_total = Counter(
            "cms_http_requests_total",
            "Total number of HTTP requests for Class Management Service.",
            ["method", "endpoint", "http_status"],
        )
        self.http_request_duration_seconds = Histogram(
            "cms_http_request_duration_seconds",
            "HTTP request duration in seconds for Class Management Service.",
            ["method", "endpoint"],
        )

        # Business metrics
        self.class_creations_total = Counter(
            "cms_class_creations_total",
            "Total number of classes created successfully.",
        )
        self.student_creations_total = Counter(
            "cms_student_creations_total",
            "Total number of students created successfully.",
        )
        self.api_errors_total = Counter(
            "cms_api_errors_total",
            "Total number of API errors.",
            ["endpoint", "error_type"],
        )

        # Database metrics integration
        self.database_metrics = database_metrics
        if database_metrics:
            logger.info("Database metrics integrated into CmsMetrics")

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics including database metrics."""
        metrics = {
            "http_requests_total": self.http_requests_total,
            "http_request_duration_seconds": self.http_request_duration_seconds,
            "class_creations_total": self.class_creations_total,
            "student_creations_total": self.student_creations_total,
            "api_errors_total": self.api_errors_total,
        }

        # Add database metrics if available
        if self.database_metrics:
            db_metrics = self.database_metrics.get_metrics()
            metrics.update(db_metrics)

        return metrics


def setup_class_management_database_monitoring(
    engine: AsyncEngine,
    service_name: str = "class_management_service",
    existing_metrics: Optional[Dict[str, Any]] = None,
) -> DatabaseMetrics:
    """
    Setup comprehensive database monitoring for Class Management Service.

    Args:
        engine: SQLAlchemy async engine for class management database
        service_name: Service name for metrics labeling
        existing_metrics: Optional existing metrics dictionary to extend

    Returns:
        DatabaseMetrics instance configured for class management operations
    """
    return setup_database_monitoring(engine, service_name, existing_metrics)
