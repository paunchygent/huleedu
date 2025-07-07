"""Database metrics library for PostgreSQL observability in HuleEdu services.

This module provides comprehensive database metrics collection, connection monitoring,
query performance tracking, and health checks for PostgreSQL services.

Key Components:
- DatabaseMetrics: Core metrics collection protocol and implementations
- ConnectionMonitoring: SQLAlchemy event listeners for connection pool monitoring
- QueryMonitoring: Performance tracking for database operations
- HealthChecks: Database health verification utilities
- RepositoryMiddleware: Integration with existing repository patterns

Usage:
    from huleedu_service_libs.database import (
        DatabaseMetrics,
        setup_database_monitoring,
        DatabaseHealthChecker,
        query_performance_tracker,
    )

    # Setup database monitoring for a service
    metrics = setup_database_monitoring(engine, service_name="content_service")

    # Use query performance tracking
    @query_performance_tracker(metrics, operation="create")
    async def create_content(self, content_data: dict):
        # Your database operation here
        pass
"""

from .health_checks import DatabaseHealthChecker
from .metrics import (
    DatabaseMetrics,
    DatabaseMetricsProtocol,
    PrometheusDatabaseMetrics,
    setup_database_monitoring,
)
from .query_monitoring import (
    QueryPerformanceTracker,
    query_performance_tracker,
)

__all__ = [
    "DatabaseMetrics",
    "DatabaseMetricsProtocol",
    "PrometheusDatabaseMetrics",
    "setup_database_monitoring",
    "DatabaseHealthChecker",
    "QueryPerformanceTracker",
    "query_performance_tracker",
]
