"""Repository integration middleware for database metrics.

This module provides middleware and decorators for seamless integration
of database metrics with existing repository patterns.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import TYPE_CHECKING, Callable, Dict, Optional, Type

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from .connection_monitoring import ConnectionPoolMonitor
    from .metrics import DatabaseMetricsProtocol

logger = create_service_logger("huleedu.database.middleware")


class DatabaseMetricsMiddleware:
    """Middleware for integrating database metrics with repository patterns."""

    def __init__(
        self,
        engine: AsyncEngine,
        metrics: DatabaseMetricsProtocol,
        connection_monitor: Optional[ConnectionPoolMonitor] = None,
    ):
        """Initialize database metrics middleware."""
        self.engine = engine
        self.metrics = metrics
        self.connection_monitor = connection_monitor
        self.logger = logger

    @asynccontextmanager
    async def session_with_metrics(
        self,
        session_factory: Callable,
        operation_name: str = "database_operation",
    ):
        """
        Context manager for database sessions with automatic metrics collection.

        Args:
            session_factory: Factory function that creates database sessions
            operation_name: Name of the operation for metrics labeling

        Usage:
            async with middleware.session_with_metrics(
                db_infrastructure.session,
                "create_batch"
            ) as session:
                # Your database operations here
                batch = Batch(...)
                session.add(batch)
                await session.commit()
        """
        start_time = time.time()
        success = True

        try:
            async with session_factory() as session:
                yield session

        except Exception as e:
            success = False
            error_type = e.__class__.__name__

            # Record the error
            self.metrics.record_database_error(error_type, operation_name)

            self.logger.error(f"Database operation failed: {operation_name}: {error_type}: {e}")
            raise

        finally:
            duration = time.time() - start_time

            # Record transaction duration
            self.metrics.record_transaction_duration(
                operation=operation_name,
                duration=duration,
                success=success,
            )

    def wrap_repository_class(
        self,
        repository_class: Type,
        table_mapping: Optional[Dict[str, str]] = None,
    ) -> Type:
        """
        Class decorator for wrapping repository classes with metrics.

        Args:
            repository_class: Repository class to wrap
            table_mapping: Optional mapping of method names to table names

        Returns:
            Wrapped repository class with metrics

        Usage:
            @middleware.wrap_repository_class(
                table_mapping={
                    "get_batch_by_id": "batches",
                    "create_batch": "batches",
                    "update_batch_status": "batches",
                }
            )
            class BatchRepository:
                async def get_batch_by_id(self, batch_id: str):
                    # Implementation
                    pass
        """
        if table_mapping is None:
            table_mapping = {}

        class WrappedRepository(repository_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._metrics = self.metrics
                self._table_mapping = table_mapping

            def __getattribute__(self, name):
                attr = super().__getattribute__(name)

                # Only wrap async methods that aren't private
                if (
                    callable(attr)
                    and not name.startswith("_")
                    and hasattr(attr, "__code__")
                    and attr.__code__.co_flags & 0x0080  # CO_COROUTINE flag
                ):
                    return self._wrap_method(attr, name)

                return attr

            def _wrap_method(self, method: Callable, method_name: str) -> Callable:
                """Wrap individual repository methods with metrics."""

                @wraps(method)
                async def wrapper(*args, **kwargs):
                    # Determine operation type from method name
                    operation = self._determine_operation_type(method_name)

                    # Get table name from mapping or infer from method name
                    table = self._table_mapping.get(method_name, "unknown")

                    start_time = time.time()
                    success = True

                    try:
                        result = await method(*args, **kwargs)
                        return result

                    except Exception as e:
                        success = False
                        error_type = e.__class__.__name__

                        # Record the error
                        self._metrics.record_database_error(error_type, operation)

                        logger.error(f"Repository method failed: {method_name}: {error_type}: {e}")
                        raise

                    finally:
                        duration = time.time() - start_time

                        # Record query duration
                        self._metrics.record_query_duration(
                            operation=operation,
                            table=table,
                            duration=duration,
                            success=success,
                        )

                return wrapper

            def _determine_operation_type(self, method_name: str) -> str:
                """Determine operation type from method name."""
                method_lower = method_name.lower()

                if any(
                    word in method_lower for word in ["get", "find", "fetch", "select", "retrieve"]
                ):
                    return "select"
                elif any(word in method_lower for word in ["create", "insert", "add", "store"]):
                    return "insert"
                elif any(word in method_lower for word in ["update", "modify", "change", "set"]):
                    return "update"
                elif any(word in method_lower for word in ["delete", "remove", "drop"]):
                    return "delete"
                else:
                    return "unknown"

        return WrappedRepository

    def repository_method_tracker(
        self,
        operation: str,
        table: str,
        method_name: Optional[str] = None,
    ) -> Callable:
        """
        Method decorator for tracking repository method performance.

        Args:
            operation: Type of operation (select, insert, update, delete)
            table: Primary table being operated on
            method_name: Optional method name for logging

        Returns:
            Decorator function

        Usage:
            @middleware.repository_method_tracker("select", "batches", "get_batch_by_id")
            async def get_batch_by_id(self, batch_id: str):
                # Implementation
                pass
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                description = method_name or func.__name__

                try:
                    logger.debug(f"Starting repository method: {description}")
                    result = await func(*args, **kwargs)
                    return result

                except Exception as e:
                    success = False
                    error_type = e.__class__.__name__

                    # Record the error
                    self.metrics.record_database_error(error_type, operation)

                    logger.error(f"Repository method failed: {description}: {error_type}: {e}")
                    raise

                finally:
                    duration = time.time() - start_time

                    # Record query duration
                    self.metrics.record_query_duration(
                        operation=operation,
                        table=table,
                        duration=duration,
                        success=success,
                    )

                    logger.debug(
                        f"Repository method completed: {description} "
                        f"in {duration:.3f}s ({'success' if success else 'failed'})"
                    )

            return wrapper

        return decorator


class DatabaseInfrastructureEnhancer:
    """Enhancer for existing database infrastructure classes."""

    def __init__(self, metrics: DatabaseMetricsProtocol):
        """Initialize database infrastructure enhancer."""
        self.metrics = metrics
        self.logger = logger

    def enhance_session_factory(
        self,
        original_session_factory: Callable,
        operation_name: str = "database_session",
    ) -> Callable:
        """
        Enhance an existing session factory with metrics collection.

        Args:
            original_session_factory: Original session factory function
            operation_name: Name for metrics labeling

        Returns:
            Enhanced session factory

        Usage:
            # In your database infrastructure class
            self.enhanced_session = enhancer.enhance_session_factory(
                self.async_session_maker,
                "batch_operations"
            )
        """

        @asynccontextmanager
        async def enhanced_session():
            start_time = time.time()
            success = True

            try:
                async with original_session_factory() as session:
                    yield session

            except Exception as e:
                success = False
                error_type = e.__class__.__name__

                # Record the error
                self.metrics.record_database_error(error_type, operation_name)

                self.logger.error(f"Database session failed: {operation_name}: {error_type}: {e}")
                raise

            finally:
                duration = time.time() - start_time

                # Record transaction duration
                self.metrics.record_transaction_duration(
                    operation=operation_name,
                    duration=duration,
                    success=success,
                )

        return enhanced_session


def create_repository_middleware(
    engine: AsyncEngine,
    metrics: DatabaseMetricsProtocol,
    connection_monitor: Optional[ConnectionPoolMonitor] = None,
) -> DatabaseMetricsMiddleware:
    """
    Create database metrics middleware for repository integration.

    Args:
        engine: SQLAlchemy async engine
        metrics: Database metrics instance
        connection_monitor: Optional connection monitor

    Returns:
        DatabaseMetricsMiddleware instance
    """
    return DatabaseMetricsMiddleware(engine, metrics, connection_monitor)


def create_infrastructure_enhancer(
    metrics: DatabaseMetricsProtocol,
) -> DatabaseInfrastructureEnhancer:
    """
    Create database infrastructure enhancer.

    Args:
        metrics: Database metrics instance

    Returns:
        DatabaseInfrastructureEnhancer instance
    """
    return DatabaseInfrastructureEnhancer(metrics)
