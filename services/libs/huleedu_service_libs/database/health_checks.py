"""Database health check utilities for PostgreSQL services.

This module provides comprehensive health checks for database connectivity,
performance, and resource utilization.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, NotRequired, TypedDict

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import Pool

logger = create_service_logger("huleedu.database.health_checks")


class PoolStatus(TypedDict):
    """Type-safe structure for database pool status."""
    status: str
    pool_size: int
    active_connections: int
    idle_connections: int
    overflow_connections: int
    invalid_connections: int
    pool_type: str
    error: NotRequired[str]  # Optional error message for degraded status


def get_pool_status_safe(pool: Pool) -> PoolStatus:
    """
    Get pool status with type safety and graceful degradation.

    This function safely extracts connection pool metrics from SQLAlchemy pools,
    handling different pool implementations (QueuePool, StaticPool, etc.) that
    may have different method signatures.

    Args:
        pool: SQLAlchemy connection pool instance

    Returns:
        Dictionary with pool status metrics
    """
    try:
        # Type-safe attribute access with fallbacks, ensuring int results
        pool_size = int(getattr(pool, "size", lambda: 0)())
        active_connections = int(getattr(pool, "checkedout", lambda: 0)())
        idle_connections = int(getattr(pool, "checkedin", lambda: 0)())
        overflow_connections = int(getattr(pool, "overflow", lambda: 0)())
        invalid_connections = int(getattr(pool, "invalid", lambda: 0)())

        return {
            "status": "healthy",
            "pool_size": pool_size,
            "active_connections": active_connections,
            "idle_connections": idle_connections,
            "overflow_connections": overflow_connections,
            "invalid_connections": invalid_connections,
            "pool_type": pool.__class__.__name__,
        }
    except Exception as e:
        # Graceful degradation when pool methods fail
        return {
            "status": "degraded",
            "pool_size": 0,
            "active_connections": 0,
            "idle_connections": 0,
            "overflow_connections": 0,
            "invalid_connections": 0,
            "error": str(e),
            "pool_type": pool.__class__.__name__,
        }


class DatabaseHealthChecker:
    """Comprehensive database health checking utility."""

    def __init__(self, engine: AsyncEngine, service_name: str):
        """Initialize database health checker."""
        self.engine = engine
        self.service_name = service_name
        self.logger = logger

    async def check_basic_connectivity(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Check basic database connectivity.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            Dictionary with connectivity status and metrics
        """
        start_time = time.time()

        try:
            # Test basic connection
            async with asyncio.timeout(timeout):
                async with self.engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))

            duration = time.time() - start_time

            return {
                "status": "healthy",
                "connectivity": True,
                "response_time_seconds": duration,
                "error": None,
                "timestamp": time.time(),
            }

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            return {
                "status": "unhealthy",
                "connectivity": False,
                "response_time_seconds": duration,
                "error": "Connection timeout",
                "timestamp": time.time(),
            }

        except Exception as e:
            duration = time.time() - start_time
            return {
                "status": "unhealthy",
                "connectivity": False,
                "response_time_seconds": duration,
                "error": str(e),
                "timestamp": time.time(),
            }

    async def check_connection_pool_health(self) -> Dict[str, Any]:
        """
        Check connection pool health and resource utilization.

        Returns:
            Dictionary with pool health status and metrics
        """
        try:
            # Get pool statistics using type-safe method
            pool_stats = get_pool_status_safe(self.engine.pool)

            # Handle degraded pool status
            if pool_stats.get("status") == "degraded":
                return {
                    "status": "error",
                    "error": pool_stats.get("error", "Pool status unavailable"),
                    "pool_type": pool_stats.get("pool_type", "unknown"),
                    "timestamp": time.time(),
                }

            # Extract metrics with type safety
            pool_size = pool_stats["pool_size"]
            checked_out = pool_stats["active_connections"]
            checked_in = pool_stats["idle_connections"]
            overflow = pool_stats["overflow_connections"]
            invalid = pool_stats["invalid_connections"]

            # Calculate utilization
            total_capacity = pool_size + overflow
            utilization_percent = (checked_out / max(total_capacity, 1)) * 100

            # Determine health status
            status = "healthy"
            warnings = []

            # Check for high utilization
            if utilization_percent > 90:
                status = "warning"
                warnings.append(f"High pool utilization: {utilization_percent:.1f}%")

            # Check for invalid connections
            if invalid > 0:
                status = "warning"
                warnings.append(f"Invalid connections detected: {invalid}")

            # Check for overflow usage
            if overflow > 0:
                if overflow > (pool_size * 0.5):  # More than 50% overflow
                    status = "warning"
                    warnings.append(f"High overflow usage: {overflow}")

            return {
                "status": status,
                "pool_size": pool_size,
                "active_connections": checked_out,
                "idle_connections": checked_in,
                "overflow_connections": overflow,
                "invalid_connections": invalid,
                "total_capacity": total_capacity,
                "utilization_percent": utilization_percent,
                "pool_type": pool_stats.get("pool_type", "unknown"),
                "warnings": warnings,
                "timestamp": time.time(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time(),
            }

    async def check_query_performance(self, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Check database query performance with simple benchmarks.

        Args:
            timeout: Query timeout in seconds

        Returns:
            Dictionary with performance metrics
        """
        try:
            # Test simple SELECT performance
            start_time = time.time()
            async with asyncio.timeout(timeout):
                async with self.engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
            simple_query_time = time.time() - start_time

            # Test more complex query (if possible)
            start_time = time.time()
            async with asyncio.timeout(timeout):
                async with self.engine.begin() as conn:
                    await conn.execute(text("SELECT COUNT(*) FROM pg_stat_activity"))
            complex_query_time = time.time() - start_time

            # Determine performance status
            status = "healthy"
            warnings = []

            if simple_query_time > 1.0:
                status = "warning"
                warnings.append(f"Slow simple query: {simple_query_time:.3f}s")

            if complex_query_time > 5.0:
                status = "warning"
                warnings.append(f"Slow complex query: {complex_query_time:.3f}s")

            return {
                "status": status,
                "simple_query_time_seconds": simple_query_time,
                "complex_query_time_seconds": complex_query_time,
                "warnings": warnings,
                "timestamp": time.time(),
            }

        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "error": "Query performance test timeout",
                "timestamp": time.time(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time(),
            }

    async def check_database_resources(self) -> Dict[str, Any]:
        """
        Check database resource utilization (PostgreSQL-specific).

        Returns:
            Dictionary with resource utilization metrics
        """
        try:
            async with self.engine.begin() as conn:
                # Get connection count
                result = await conn.execute(
                    text("""
                    SELECT COUNT(*) as active_connections
                    FROM pg_stat_activity
                    WHERE state = 'active'
                """)
                )
                active_connections = result.scalar()

                # Get database size (if accessible)
                try:
                    result = await conn.execute(
                        text("""
                        SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
                    """)
                    )
                    db_size = result.scalar()
                except:
                    db_size = "unavailable"

                # Get long-running queries
                result = await conn.execute(
                    text("""
                    SELECT COUNT(*) as long_running_queries
                    FROM pg_stat_activity
                    WHERE state = 'active' 
                    AND query_start < NOW() - INTERVAL '5 minutes'
                    AND query != '<IDLE>'
                """)
                )
                long_running_queries = result.scalar()

                # Determine status
                status = "healthy"
                warnings = []

                if long_running_queries > 0:
                    status = "warning"
                    warnings.append(f"Long-running queries detected: {long_running_queries}")

                return {
                    "status": status,
                    "active_connections": active_connections,
                    "database_size": db_size,
                    "long_running_queries": long_running_queries,
                    "warnings": warnings,
                    "timestamp": time.time(),
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time(),
            }

    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive database health check.

        Returns:
            Dictionary with complete health status
        """
        self.logger.info(f"Starting comprehensive database health check for {self.service_name}")

        # Run all health checks concurrently
        connectivity_task = asyncio.create_task(self.check_basic_connectivity())
        pool_task = asyncio.create_task(self.check_connection_pool_health())
        performance_task = asyncio.create_task(self.check_query_performance())
        resources_task = asyncio.create_task(self.check_database_resources())

        # Wait for all checks to complete
        connectivity_result = await connectivity_task
        pool_result = await pool_task
        performance_result = await performance_task
        resources_result = await resources_task

        # Aggregate results
        all_checks = [connectivity_result, pool_result, performance_result, resources_result]

        # Determine overall status
        overall_status = "healthy"
        if any(check.get("status") == "unhealthy" for check in all_checks):
            overall_status = "unhealthy"
        elif any(check.get("status") == "error" for check in all_checks):
            overall_status = "error"
        elif any(check.get("status") == "warning" for check in all_checks):
            overall_status = "warning"

        # Collect all warnings
        all_warnings = []
        for check in all_checks:
            warnings = check.get("warnings", [])
            if warnings:
                all_warnings.extend(warnings)

        result = {
            "service": self.service_name,
            "overall_status": overall_status,
            "checks": {
                "connectivity": connectivity_result,
                "connection_pool": pool_result,
                "query_performance": performance_result,
                "database_resources": resources_result,
            },
            "warnings": all_warnings,
            "timestamp": time.time(),
        }

        self.logger.info(
            f"Database health check completed for {self.service_name}: {overall_status}"
        )

        return result

    async def get_health_summary(self) -> Dict[str, Any]:
        """
        Get a lightweight health summary suitable for frequent polling.

        Returns:
            Dictionary with essential health metrics
        """
        try:
            # Quick connectivity check
            connectivity = await self.check_basic_connectivity(timeout=2.0)

            # Pool status
            pool_status = await self.check_connection_pool_health()

            # Quick status determination
            if not connectivity.get("connectivity", False):
                status = "unhealthy"
            elif pool_status.get("utilization_percent", 0) > 95:
                status = "warning"
            else:
                status = "healthy"

            return {
                "service": self.service_name,
                "status": status,
                "connectivity": connectivity.get("connectivity", False),
                "response_time_seconds": connectivity.get("response_time_seconds", 0),
                "pool_utilization_percent": pool_status.get("utilization_percent", 0),
                "active_connections": pool_status.get("active_connections", 0),
                "timestamp": time.time(),
            }

        except Exception as e:
            return {
                "service": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": time.time(),
            }
