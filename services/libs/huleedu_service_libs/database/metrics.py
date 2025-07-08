"""Core database metrics implementation for PostgreSQL observability.

This module provides the core database metrics collection infrastructure
following HuleEdu's established patterns for Prometheus integration.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("huleedu.database.metrics")


class DatabaseMetricsProtocol(Protocol):
    """Protocol for database metrics collection."""

    def record_query_duration(
        self,
        operation: str,
        table: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record query execution duration."""
        ...

    def record_connection_acquired(self, pool_size: int, overflow: int) -> None:
        """Record connection acquisition from pool."""
        ...

    def record_connection_released(self, pool_size: int, overflow: int) -> None:
        """Record connection release to pool."""
        ...

    def record_transaction_duration(
        self,
        operation: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record transaction duration."""
        ...

    def record_database_error(self, error_type: str, operation: str) -> None:
        """Record database error occurrence."""
        ...

    def set_connection_pool_status(
        self,
        active: int,
        idle: int,
        total: int,
        overflow: int,
    ) -> None:
        """Set current connection pool status."""
        ...


class PrometheusDatabaseMetrics:
    """Prometheus implementation of database metrics collection."""

    def __init__(self, service_name: str, metrics_dict: Optional[Dict[str, Any]] = None):
        """Initialize with service name and optional existing metrics dictionary."""
        self.service_name = service_name
        self.metrics = metrics_dict or {}
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize all database metrics."""
        try:
            # Query performance metrics
            self.metrics["database_query_duration_seconds"] = Histogram(
                f"{self.service_name}_database_query_duration_seconds",
                "Database query duration in seconds",
                ["operation", "table", "result"],
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
                registry=REGISTRY,
            )

            # Connection pool metrics
            self.metrics["database_connections_active"] = Gauge(
                f"{self.service_name}_database_connections_active",
                "Number of active database connections",
                registry=REGISTRY,
            )

            self.metrics["database_connections_idle"] = Gauge(
                f"{self.service_name}_database_connections_idle",
                "Number of idle database connections",
                registry=REGISTRY,
            )

            self.metrics["database_connections_total"] = Gauge(
                f"{self.service_name}_database_connections_total",
                "Total database connections in pool",
                registry=REGISTRY,
            )

            self.metrics["database_connections_overflow"] = Gauge(
                f"{self.service_name}_database_connections_overflow",
                "Number of overflow database connections",
                registry=REGISTRY,
            )

            # Connection lifecycle metrics
            self.metrics["database_connections_acquired_total"] = Counter(
                f"{self.service_name}_database_connections_acquired_total",
                "Total database connections acquired",
                registry=REGISTRY,
            )

            self.metrics["database_connections_released_total"] = Counter(
                f"{self.service_name}_database_connections_released_total",
                "Total database connections released",
                registry=REGISTRY,
            )

            # Transaction metrics
            self.metrics["database_transactions_total"] = Counter(
                f"{self.service_name}_database_transactions_total",
                "Total database transactions",
                ["operation", "result"],
                registry=REGISTRY,
            )

            self.metrics["database_transaction_duration_seconds"] = Histogram(
                f"{self.service_name}_database_transaction_duration_seconds",
                "Database transaction duration in seconds",
                ["operation", "result"],
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
                registry=REGISTRY,
            )

            # Error tracking
            self.metrics["database_errors_total"] = Counter(
                f"{self.service_name}_database_errors_total",
                "Total database errors",
                ["error_type", "operation"],
                registry=REGISTRY,
            )

            logger.info(f"Initialized database metrics for service: {self.service_name}")

        except ValueError as e:
            if "Duplicated timeseries" in str(e):
                logger.warning(
                    f"Database metrics already registered for {self.service_name}: {e} "
                    "– reusing existing collectors from REGISTRY."
                )
                self.metrics = self._get_existing_metrics()
            else:
                raise

    def _get_existing_metrics(self) -> Dict[str, Any]:
        """Retrieve existing metrics from registry."""
        name_map = {
            "database_query_duration_seconds": (
                f"{self.service_name}_database_query_duration_seconds"
            ),
            "database_connections_active": f"{self.service_name}_database_connections_active",
            "database_connections_idle": f"{self.service_name}_database_connections_idle",
            "database_connections_total": f"{self.service_name}_database_connections_total",
            "database_connections_overflow": f"{self.service_name}_database_connections_overflow",
            "database_connections_acquired_total": (
                f"{self.service_name}_database_connections_acquired_total"
            ),
            "database_connections_released_total": (
                f"{self.service_name}_database_connections_released_total"
            ),
            "database_transactions_total": f"{self.service_name}_database_transactions_total",
            "database_transaction_duration_seconds": (
                f"{self.service_name}_database_transaction_duration_seconds"
            ),
            "database_errors_total": f"{self.service_name}_database_errors_total",
        }

        existing = {}
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
                logger.error(f"Error retrieving database metric '{metric_name}': {exc}")

        return existing

    def record_query_duration(
        self,
        operation: str,
        table: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record query execution duration."""
        try:
            if "database_query_duration_seconds" in self.metrics:
                result = "success" if success else "error"
                self.metrics["database_query_duration_seconds"].labels(
                    operation=operation,
                    table=table,
                    result=result,
                ).observe(duration)
        except Exception as e:
            logger.error(f"Failed to record query duration: {e}")

    def record_connection_acquired(self, pool_size: int, overflow: int) -> None:
        """Record connection acquisition from pool."""
        try:
            if "database_connections_acquired_total" in self.metrics:
                self.metrics["database_connections_acquired_total"].inc()
        except Exception as e:
            logger.error(f"Failed to record connection acquired: {e}")

    def record_connection_released(self, pool_size: int, overflow: int) -> None:
        """Record connection release to pool."""
        try:
            if "database_connections_released_total" in self.metrics:
                self.metrics["database_connections_released_total"].inc()
        except Exception as e:
            logger.error(f"Failed to record connection released: {e}")

    def record_transaction_duration(
        self,
        operation: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record transaction duration."""
        try:
            result = "success" if success else "error"

            if "database_transactions_total" in self.metrics:
                self.metrics["database_transactions_total"].labels(
                    operation=operation,
                    result=result,
                ).inc()

            if "database_transaction_duration_seconds" in self.metrics:
                self.metrics["database_transaction_duration_seconds"].labels(
                    operation=operation,
                    result=result,
                ).observe(duration)
        except Exception as e:
            logger.error(f"Failed to record transaction duration: {e}")

    def record_database_error(self, error_type: str, operation: str) -> None:
        """Record database error occurrence."""
        try:
            if "database_errors_total" in self.metrics:
                self.metrics["database_errors_total"].labels(
                    error_type=error_type,
                    operation=operation,
                ).inc()
        except Exception as e:
            logger.error(f"Failed to record database error: {e}")

    def set_connection_pool_status(
        self,
        active: int,
        idle: int,
        total: int,
        overflow: int,
    ) -> None:
        """Set current connection pool status."""
        try:
            if "database_connections_active" in self.metrics:
                self.metrics["database_connections_active"].set(active)
            if "database_connections_idle" in self.metrics:
                self.metrics["database_connections_idle"].set(idle)
            if "database_connections_total" in self.metrics:
                self.metrics["database_connections_total"].set(total)
            if "database_connections_overflow" in self.metrics:
                self.metrics["database_connections_overflow"].set(overflow)
        except Exception as e:
            logger.error(f"Failed to set connection pool status: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get the metrics dictionary for integration with service metrics."""
        return self.metrics


class NoOpDatabaseMetrics:
    """No-op implementation for testing or when metrics are disabled."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    def record_query_duration(
        self,
        operation: str,
        table: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """No-op query duration recording."""
        # Parameters unused by design for no-op implementation
        _ = operation, table, duration, success

    def record_connection_acquired(self, pool_size: int, overflow: int) -> None:
        """No-op connection acquisition recording."""
        # Parameters unused by design for no-op implementation
        _ = pool_size, overflow

    def record_connection_released(self, pool_size: int, overflow: int) -> None:
        """No-op connection release recording."""
        # Parameters unused by design for no-op implementation
        _ = pool_size, overflow

    def record_transaction_duration(
        self,
        operation: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """No-op transaction duration recording."""
        # Parameters unused by design for no-op implementation
        _ = operation, duration, success

    def record_database_error(self, error_type: str, operation: str) -> None:
        """No-op database error recording."""
        # Parameters unused by design for no-op implementation
        _ = error_type, operation

    def set_connection_pool_status(
        self,
        active: int,
        idle: int,
        total: int,
        overflow: int,
    ) -> None:
        """No-op connection pool status setting."""
        # Parameters unused by design for no-op implementation
        _ = active, idle, total, overflow

    def get_metrics(self) -> Dict[str, Any]:
        """Return empty metrics dictionary."""
        return {}


# Type alias for convenience
DatabaseMetrics = PrometheusDatabaseMetrics


def setup_database_monitoring(
    engine: AsyncEngine,
    service_name: str,
    metrics_dict: Optional[Dict[str, Any]] = None,
) -> DatabaseMetrics:
    """
    Setup comprehensive database monitoring for a service.

    Args:
        engine: SQLAlchemy async engine
        service_name: Name of the service (used for metric naming)
        metrics_dict: Optional existing metrics dictionary to extend

    Returns:
        DatabaseMetrics instance configured for the service
    """
    from .connection_monitoring import setup_connection_monitoring

    # Create metrics instance
    db_metrics = DatabaseMetrics(service_name, metrics_dict)

    # Setup connection monitoring
    setup_connection_monitoring(engine, db_metrics)

    logger.info(f"Database monitoring setup complete for service: {service_name}")
    return db_metrics
