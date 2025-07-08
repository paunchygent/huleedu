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
    """Type-safe Quart application with HuleEdu infrastructure.
    
    This class extends Quart to provide typed attributes for all
    cross-cutting infrastructure components used across HuleEdu services.
    It replaces the anti-pattern of using setattr()/getattr() with
    compile-time verified attributes.
    
    Core Infrastructure:
        database_engine: SQLAlchemy async engine for database operations
        extensions: Standard Quart extensions dictionary
        
    Distributed Tracing:
        tracer: OpenTelemetry tracer for distributed tracing
        
    Dependency Injection:
        container: Dishka async container for dependency injection
        
    Background Processing:
        consumer_task: Asyncio task for background Kafka consumers
        kafka_consumer: Service-specific Kafka consumer instances
        
    Note:
        This class is designed to be strict in what attributes it accepts.
        It should NOT become a global dumping ground. Attributes are
        limited to cross-cutting, application-level infrastructure
        components only.
        
    Examples:
        Basic usage:
            >>> from huleedu_service_libs.quart_app import HuleEduApp
            >>> app = HuleEduApp(__name__)
            >>> app.database_engine = create_async_engine(...)
            >>> engine = app.database_engine  # Type-safe access
            
        Health check usage:
            >>> def health_check():
            ...     engine = current_app.database_engine
            ...     if engine is None:
            ...         return {"status": "error", "database": "not configured"}
            ...     return {"status": "healthy"}
            
        Migration from setattr/getattr:
            >>> # OLD (anti-pattern):
            >>> setattr(app, "database_engine", engine)
            >>> engine = getattr(current_app, "database_engine", None)
            >>> 
            >>> # NEW (type-safe):
            >>> app.database_engine = engine
            >>> engine = current_app.database_engine
    """

    # Core Infrastructure (all services)
    database_engine: Optional[AsyncEngine]
    """SQLAlchemy async engine for database operations.
    
    Used by services requiring database persistence. Set during
    service initialization and accessed in health checks and
    database operations.
    """

    extensions: dict[str, Any]
    """Standard Quart extensions dictionary.
    
    Used to store app-level objects like metrics, tracer instances,
    and other infrastructure components. Follows the standard Quart
    pattern for extension registration.
    """

    # Distributed Tracing
    tracer: Optional[Tracer]
    """OpenTelemetry tracer for distributed tracing.
    
    Used by services that participate in distributed tracing.
    Enables correlation of requests across service boundaries.
    """

    # Dependency Injection
    container: Optional[AsyncContainer]
    """Dishka async container for dependency injection.
    
    Used by services implementing dependency injection patterns.
    Provides protocol-based dependency resolution and lifecycle
    management.
    """

    # Background Processing (service-specific)
    consumer_task: Optional[asyncio.Task[None]]
    """Asyncio task for background Kafka consumer processing.
    
    Used by services that run background Kafka consumers.
    Enables graceful shutdown and task lifecycle management.
    """

    kafka_consumer: Optional[Any]
    """Service-specific Kafka consumer instances.
    
    Used by services with custom Kafka consumer implementations.
    Type is intentionally generic to accommodate different
    service-specific consumer classes.
    """

    def __init__(self, import_name: str, *args, **kwargs) -> None:
        """Initialize HuleEduApp with type-safe infrastructure attributes.
        
        Args:
            import_name: The name of the application package
            *args: Additional positional arguments passed to Quart
            **kwargs: Additional keyword arguments passed to Quart
        """
        super().__init__(import_name, *args, **kwargs)

        # Initialize all infrastructure attributes to None
        # This ensures they are always present and properly typed
        self.database_engine = None
        self.extensions = {}
        self.tracer = None
        self.container = None
        self.consumer_task = None
        self.kafka_consumer = None
