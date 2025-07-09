"""
Type-safe Quart application class for HuleEdu microservices.

This module provides the HuleEduApp class that replaces the anti-pattern
of using setattr()/getattr() for app-level infrastructure attributes.
It provides compile-time type safety and IDE support for all
cross-cutting infrastructure components.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from dishka import AsyncContainer
from opentelemetry.trace import Tracer
from quart import Quart
from sqlalchemy.ext.asyncio import AsyncEngine


class HuleEduApp(Quart):
    """Type-safe Quart application with guaranteed HuleEdu infrastructure.

    This class extends Quart to provide typed attributes for all
    cross-cutting infrastructure components used across HuleEdu services.
    It replaces the anti-pattern of using setattr()/getattr() with
    compile-time verified attributes.

    GUARANTEED INFRASTRUCTURE (Non-Optional):
        database_engine: SQLAlchemy async engine for database operations
        container: Dishka async container for dependency injection
        extensions: Standard Quart extensions dictionary

    OPTIONAL INFRASTRUCTURE (Service-Specific):
        tracer: OpenTelemetry tracer for distributed tracing
        consumer_task: Asyncio task for background Kafka consumers
        kafka_consumer: Service-specific Kafka consumer instances

    Note:
        This class enforces a stricter contract. All HuleEdu services MUST
        provide the non-optional attributes during initialization in their
        create_app factory function. This ensures type safety and eliminates
        runtime AttributeError exceptions.

    Examples:
        Guaranteed initialization pattern:
            >>> from huleedu_service_libs.quart_app import HuleEduApp
            >>> def create_app() -> HuleEduApp:
            ...     app = HuleEduApp(__name__)
            ...     app.database_engine = create_async_engine(...)
            ...     app.container = make_async_container(...)
            ...     return app

        Type-safe access (no None checks needed):
            >>> # In health_routes.py
            >>> engine = current_app.database_engine  # Guaranteed to exist
            >>> async with current_app.container() as request_container:
            ...     # No None check needed - container is guaranteed

        Migration from Optional pattern:
            >>> # OLD (defensive programming):
            >>> if current_app.container is not None:
            ...     async with current_app.container() as request_container:
            ...         # ...
            >>>
            >>> # NEW (confident access):
            >>> async with current_app.container() as request_container:
            ...     # No None check needed
    """

    # GUARANTEED INFRASTRUCTURE (Non-Optional) - All services MUST provide these
    database_engine: AsyncEngine
    """SQLAlchemy async engine for database operations.

    GUARANTEED PRESENT: All HuleEdu services must provide this during
    initialization. Used for database persistence, health checks, and
    connection monitoring.
    """

    container: AsyncContainer
    """Dishka async container for dependency injection.

    GUARANTEED PRESENT: All HuleEdu services must provide this during
    initialization. Provides protocol-based dependency resolution and
    lifecycle management.
    """

    extensions: dict[str, Any]
    """Standard Quart extensions dictionary.

    GUARANTEED PRESENT: Initialized to empty dict. Used to store app-level
    objects like metrics, tracer instances, and other infrastructure
    components. Follows the standard Quart pattern for extension registration.
    """

    # OPTIONAL INFRASTRUCTURE (Service-Specific) - May be absent
    tracer: Optional[Tracer] = None
    """OpenTelemetry tracer for distributed tracing.

    OPTIONAL: Used by services that participate in distributed tracing.
    Enables correlation of requests across service boundaries.
    """

    consumer_task: Optional[asyncio.Task[None]] = None
    """Asyncio task for background Kafka consumer processing.

    OPTIONAL: Used by services that run background Kafka consumers.
    Enables graceful shutdown and task lifecycle management.
    """

    kafka_consumer: Optional[Any] = None
    """Service-specific Kafka consumer instances.

    OPTIONAL: Used by services with custom Kafka consumer implementations.
    Type is intentionally generic to accommodate different
    service-specific consumer classes.
    """

    def __init__(self, import_name: str, *args, **kwargs) -> None:
        """Initialize HuleEduApp with type-safe infrastructure attributes.

        IMPORTANT: The guaranteed infrastructure attributes (database_engine,
        container) are NOT initialized here. They MUST be set immediately
        in the service's create_app factory function to satisfy the
        non-optional contract.

        Args:
            import_name: The name of the application package
            *args: Additional positional arguments passed to Quart
            **kwargs: Additional keyword arguments passed to Quart
        """
        super().__init__(import_name, *args, **kwargs)

        # Initialize only the guaranteed-present extensions dict
        # database_engine and container MUST be set in create_app()
        self.extensions = {}

        # Optional infrastructure starts as None
        self.tracer = None
        self.consumer_task = None
        self.kafka_consumer = None
