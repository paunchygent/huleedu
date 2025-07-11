"""SQLAlchemy connection pool monitoring with event listeners.

This module provides automatic monitoring of SQLAlchemy connection pools
through event listeners that track connection lifecycle events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

if TYPE_CHECKING:
    from .metrics import DatabaseMetricsProtocol

logger = create_service_logger("huleedu.database.connection_monitoring")


class ConnectionPoolMonitor:
    """Monitor SQLAlchemy connection pools with event listeners."""

    def __init__(self, engine: AsyncEngine, metrics: DatabaseMetricsProtocol):
        """Initialize connection pool monitoring."""
        self.engine = engine
        self.metrics = metrics
        self.service_logger = logger
        self._setup_event_listeners()

    def _setup_event_listeners(self) -> None:
        """Setup SQLAlchemy event listeners for connection pool monitoring."""
        try:
            # Listen for connection events on the pool
            pool = self.engine.pool

            # Connection acquisition events
            event.listen(pool, "connect", self._on_connect)
            event.listen(pool, "checkout", self._on_checkout)
            event.listen(pool, "checkin", self._on_checkin)

            # Connection lifecycle events
            event.listen(pool, "invalidate", self._on_invalidate)
            event.listen(pool, "soft_invalidate", self._on_soft_invalidate)

            self.service_logger.info("Connection pool event listeners configured")

        except Exception as e:
            self.service_logger.error(f"Failed to setup connection pool listeners: {e}")

    def _on_connect(self, dbapi_connection: Any, connection_record: Any) -> None:
        """Called when a new connection is created."""
        # Parameters required by SQLAlchemy event interface
        _ = dbapi_connection, connection_record
        try:
            self.service_logger.debug("New database connection created")
            self._update_pool_metrics()
        except Exception as e:
            self.service_logger.error(f"Error in connection create handler: {e}")

    def _on_checkout(
        self, dbapi_connection: Any, connection_record: Any, connection_proxy: Any
    ) -> None:
        """Called when a connection is checked out from the pool."""
        # Parameters required by SQLAlchemy event interface
        _ = dbapi_connection, connection_record, connection_proxy
        try:
            self.service_logger.debug("Connection checked out from pool")
            self._update_pool_metrics()

            # Record connection acquisition
            pool_status = self._get_pool_status()
            self.metrics.record_connection_acquired(
                pool_size=pool_status["size"], overflow=pool_status["overflow"]
            )

        except Exception as e:
            self.service_logger.error(f"Error in connection checkout handler: {e}")

    def _on_checkin(self, dbapi_connection: Any, connection_record: Any) -> None:
        """Called when a connection is checked back into the pool."""
        # Parameters required by SQLAlchemy event interface
        _ = dbapi_connection, connection_record
        try:
            self.service_logger.debug("Connection checked back into pool")
            self._update_pool_metrics()

            # Record connection release
            pool_status = self._get_pool_status()
            self.metrics.record_connection_released(
                pool_size=pool_status["size"], overflow=pool_status["overflow"]
            )

        except Exception as e:
            self.service_logger.error(f"Error in connection checkin handler: {e}")

    def _on_invalidate(
        self, dbapi_connection: Any, connection_record: Any, exception: Optional[Exception]
    ) -> None:
        """Called when a connection is invalidated."""
        # Parameters required by SQLAlchemy event interface
        _ = dbapi_connection, connection_record
        try:
            self.service_logger.warning(f"Connection invalidated: {exception}")
            self._update_pool_metrics()

            # Record as a database error
            if exception:
                error_type = exception.__class__.__name__
                self.metrics.record_database_error(error_type, "connection_invalidate")

        except Exception as e:
            self.service_logger.error(f"Error in connection invalidate handler: {e}")

    def _on_soft_invalidate(
        self, dbapi_connection: Any, connection_record: Any, exception: Optional[Exception]
    ) -> None:
        """Called when a connection is soft invalidated."""
        # Parameters required by SQLAlchemy event interface
        _ = dbapi_connection, connection_record
        try:
            self.service_logger.debug(f"Connection soft invalidated: {exception}")
            self._update_pool_metrics()

        except Exception as e:
            self.service_logger.error(f"Error in connection soft invalidate handler: {e}")

    def _get_pool_status(self) -> dict[str, int]:
        """Get current pool status information."""
        try:
            pool = self.engine.pool
            return {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
        except Exception as e:
            self.service_logger.error(f"Error getting pool status: {e}")
            return {"size": 0, "checked_in": 0, "checked_out": 0, "overflow": 0}

    def _update_pool_metrics(self) -> None:
        """Update pool metrics with current status."""
        try:
            status = self._get_pool_status()

            # Calculate active and idle connections
            active = status["checked_out"]
            idle = status["checked_in"]
            total = status["size"]
            overflow = status["overflow"]

            # Update metrics
            self.metrics.set_connection_pool_status(
                active=active,
                idle=idle,
                total=total,
                overflow=overflow,
            )

        except Exception as e:
            self.service_logger.error(f"Error updating pool metrics: {e}")

    def get_current_status(self) -> dict[str, Any]:
        """Get current connection pool status for health checks."""
        try:
            status = self._get_pool_status()
            return {
                "pool_size": status["size"],
                "active_connections": status["checked_out"],
                "idle_connections": status["checked_in"],
                "overflow_connections": status["overflow"],
                "pool_usage_percent": (status["checked_out"] / max(status["size"], 1)) * 100,
            }
        except Exception as e:
            self.service_logger.error(f"Error getting current pool status: {e}")
            return {
                "pool_size": 0,
                "active_connections": 0,
                "idle_connections": 0,
                "overflow_connections": 0,
                "pool_usage_percent": 0.0,
            }


def setup_connection_monitoring(
    engine: AsyncEngine,
    metrics: DatabaseMetricsProtocol,
) -> ConnectionPoolMonitor:
    """
    Setup connection pool monitoring for a SQLAlchemy engine.

    Args:
        engine: SQLAlchemy async engine
        metrics: Database metrics instance

    Returns:
        ConnectionPoolMonitor instance
    """
    monitor = ConnectionPoolMonitor(engine, metrics)
    logger.info("Connection pool monitoring enabled")
    return monitor
