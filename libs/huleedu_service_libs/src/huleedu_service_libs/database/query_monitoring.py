"""Query performance monitoring for database operations.

This module provides decorators and context managers for tracking
database query performance and operation types.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import TYPE_CHECKING, Callable, Optional

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from .metrics import DatabaseMetricsProtocol

logger = create_service_logger("huleedu.database.query_monitoring")


class QueryPerformanceTracker:
    """Track query performance and operation types."""

    def __init__(self, metrics: DatabaseMetricsProtocol, service_name: str):
        """Initialize query performance tracker."""
        self.metrics = metrics
        self.service_name = service_name

    @asynccontextmanager
    async def track_query(
        self,
        operation: str,
        table: str,
        query_description: Optional[str] = None,
    ):
        """
        Context manager for tracking query performance.

        Args:
            operation: Type of operation (select, insert, update, delete, etc.)
            table: Table name being operated on
            query_description: Optional description for logging

        Usage:
            async with tracker.track_query("select", "batches", "get batch by id"):
                result = await session.execute(select(Batch).where(Batch.id == batch_id))
        """
        start_time = time.time()
        success = True

        try:
            if query_description:
                logger.debug(f"Starting query: {query_description} on table {table}")

            yield

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            logger.error(f"Query failed on table {table}: {error_type}: {e}")

            # Record the error
            self.metrics.record_database_error(error_type, operation)
            raise

        finally:
            duration = time.time() - start_time

            # Record the query duration
            self.metrics.record_query_duration(
                operation=operation,
                table=table,
                duration=duration,
                success=success,
            )

            if query_description:
                logger.debug(
                    f"Query completed: {query_description} on table {table} "
                    f"in {duration:.3f}s ({'success' if success else 'failed'})"
                )

    @asynccontextmanager
    async def track_transaction(
        self,
        operation: str,
        description: Optional[str] = None,
    ):
        """
        Context manager for tracking transaction performance.

        Args:
            operation: Type of transaction (create_batch, update_status, etc.)
            description: Optional description for logging

        Usage:
            async with tracker.track_transaction("create_batch", "Creating new batch"):
                # Your transaction logic here
                batch = await create_batch(...)
                await session.commit()
        """
        start_time = time.time()
        success = True

        try:
            if description:
                logger.debug(f"Starting transaction: {description}")

            yield

        except Exception as e:
            success = False
            error_type = e.__class__.__name__
            logger.error(f"Transaction failed: {error_type}: {e}")

            # Record the error
            self.metrics.record_database_error(error_type, operation)
            raise

        finally:
            duration = time.time() - start_time

            # Record the transaction duration
            self.metrics.record_transaction_duration(
                operation=operation,
                duration=duration,
                success=success,
            )

            if description:
                logger.debug(
                    f"Transaction completed: {description} "
                    f"in {duration:.3f}s ({'success' if success else 'failed'})"
                )

    def wrap_repository_method(
        self,
        operation: str,
        table: str,
        method_name: Optional[str] = None,
    ) -> Callable:
        """
        Decorator for wrapping repository methods with performance tracking.

        Args:
            operation: Type of operation (select, insert, update, delete)
            table: Primary table being operated on
            method_name: Optional method name for logging

        Returns:
            Decorator function

        Usage:
            @tracker.wrap_repository_method("select", "batches", "get_batch_by_id")
            async def get_batch_by_id(self, batch_id: str):
                # Your method implementation
                pass
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                description = method_name or func.__name__

                async with self.track_query(operation, table, description):
                    return await func(*args, **kwargs)

            return wrapper

        return decorator


def query_performance_tracker(
    metrics: DatabaseMetricsProtocol,
    operation: str,
    table: str,
    method_name: Optional[str] = None,
) -> Callable:
    """
    Decorator for tracking query performance on repository methods.

    Args:
        metrics: Database metrics instance
        operation: Type of operation (select, insert, update, delete)
        table: Primary table being operated on
        method_name: Optional method name for logging

    Returns:
        Decorator function

    Usage:
        @query_performance_tracker(metrics, "select", "batches", "get_batch_by_id")
        async def get_batch_by_id(self, batch_id: str):
            # Your method implementation
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            description = method_name or func.__name__

            try:
                logger.debug(f"Starting query: {description} on table {table}")
                result = await func(*args, **kwargs)
                return result

            except Exception as e:
                success = False
                error_type = e.__class__.__name__
                logger.error(f"Query failed on table {table}: {error_type}: {e}")

                # Record the error
                metrics.record_database_error(error_type, operation)
                raise

            finally:
                duration = time.time() - start_time

                # Record the query duration
                metrics.record_query_duration(
                    operation=operation,
                    table=table,
                    duration=duration,
                    success=success,
                )

                logger.debug(
                    f"Query completed: {description} on table {table} "
                    f"in {duration:.3f}s ({'success' if success else 'failed'})"
                )

        return wrapper

    return decorator


def transaction_performance_tracker(
    metrics: DatabaseMetricsProtocol,
    operation: str,
    description: Optional[str] = None,
) -> Callable:
    """
    Decorator for tracking transaction performance on repository methods.

    Args:
        metrics: Database metrics instance
        operation: Type of transaction (create_batch, update_status, etc.)
        description: Optional description for logging

    Returns:
        Decorator function

    Usage:
        @transaction_performance_tracker(metrics, "create_batch", "Creating new batch")
        async def create_batch(self, batch_data: dict):
            # Your transaction implementation
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            method_description = description or func.__name__

            try:
                logger.debug(f"Starting transaction: {method_description}")
                result = await func(*args, **kwargs)
                return result

            except Exception as e:
                success = False
                error_type = e.__class__.__name__
                logger.error(f"Transaction failed: {error_type}: {e}")

                # Record the error
                metrics.record_database_error(error_type, operation)
                raise

            finally:
                duration = time.time() - start_time

                # Record the transaction duration
                metrics.record_transaction_duration(
                    operation=operation,
                    duration=duration,
                    success=success,
                )

                logger.debug(
                    f"Transaction completed: {method_description} "
                    f"in {duration:.3f}s ({'success' if success else 'failed'})"
                )

        return wrapper

    return decorator
