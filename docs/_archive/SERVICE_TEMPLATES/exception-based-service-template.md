# Exception-Based HuleEdu Service Template

## Overview

This template provides a comprehensive guide for creating new HuleEdu services following the exception-based error handling architecture. Use this template to ensure consistency, maintainability, and adherence to established patterns.

## Quick Start

1. Copy the file structure below to create your new service
2. Replace `<service_name>` and `<Domain>` placeholders with your actual service names
3. Implement protocols first, then implementations
4. Add comprehensive tests
5. Configure DI container
6. Add documentation

## Complete File Structure

```
services/<service_name>/
├── app.py                          # HuleEduApp setup with guaranteed contracts
├── config.py                       # Pydantic settings with environment validation
├── protocols.py                    # All typing.Protocol interfaces
├── di.py                          # Dishka providers with proper lifecycle
├── startup_setup.py               # Database schema and service initialization
├── metrics.py                     # Prometheus metrics with service-specific patterns
├── exceptions.py                  # Service-specific exception definitions (optional)
├── Dockerfile                     # Containerization with proper PYTHONPATH
├── pyproject.toml                 # PDM configuration with dependencies
├── README.md                      # Service documentation
├── alembic.ini                    # Database migration configuration
├── alembic/                       # Database migrations (if applicable)
│   ├── __init__.py
│   ├── env.py
│   └── versions/
├── api/                           # HTTP endpoints (for HTTP services)
│   ├── __init__.py
│   ├── health_routes.py           # Required health endpoints
│   └── <domain>_routes.py         # Domain-specific routes
├── implementations/               # Concrete implementations
│   ├── __init__.py
│   ├── <service>_service_impl.py  # Main business logic implementation
│   ├── <repository>_impl.py       # Database/persistence implementations
│   ├── event_publisher_impl.py    # Event publishing implementation
│   └── <external>_client_impl.py  # External service clients
├── models_db.py                   # SQLAlchemy database models (if applicable)
├── models_api.py                  # API request/response models (if applicable)
├── enums_db.py                    # Database-specific enums (if applicable)
├── core_logic/                    # Pure business logic (if complex)
│   ├── __init__.py
│   └── <domain>_logic.py
├── event_processor.py             # Kafka event processing (for worker services)
├── kafka_consumer.py              # Kafka consumer setup (for worker services)
├── worker_main.py                 # Worker service entry point (for worker services)
└── tests/                         # Comprehensive test suite
    ├── __init__.py
    ├── conftest.py                # Test fixtures and configuration
    ├── test_api_integration.py    # API integration tests
    ├── test_contract_compliance.py # Contract validation tests
    ├── test_core_logic.py         # Business logic unit tests
    ├── test_repository_integration.py # Database integration tests
    ├── unit/                      # Unit tests
    │   ├── __init__.py
    │   ├── test_<service>_impl.py
    │   ├── test_kafka_circuit_breaker_di.py
    │   └── test_resilient_kafka_functionality.py
    ├── integration/               # Integration tests
    │   ├── __init__.py
    │   └── test_<external>_integration.py
    └── performance/               # Performance tests (if applicable)
        ├── __init__.py
        ├── conftest.py
        └── test_<service>_performance.py
```

## Template Files

### 1. Exception-Based Protocols (`protocols.py`)

```python
"""Protocol interfaces for <Service Name>.

All protocols use exception-based error handling with HuleEduError.
NO tuple returns are allowed - all errors are raised as exceptions.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

class <Domain>RepositoryProtocol(Protocol):
    """Protocol for <domain> data persistence operations."""

    async def create_<entity>(
        self, 
        data: <CreateRequest>, 
        correlation_id: UUID
    ) -> <Entity>:
        """Create a new <entity>.

        Args:
            data: Entity creation data
            correlation_id: Request correlation ID for tracing

        Returns:
            The created entity

        Raises:
            HuleEduError: On any failure (validation, database, etc.)
        """
        ...

    async def get_<entity>_by_id(
        self, 
        entity_id: UUID, 
        correlation_id: UUID
    ) -> <Entity>:
        """Retrieve an entity by ID.

        Args:
            entity_id: The entity ID to retrieve
            correlation_id: Request correlation ID for tracing

        Returns:
            The entity

        Raises:
            HuleEduError: On not found or other failures
        """
        ...

class <Domain>ServiceProtocol(Protocol):
    """Protocol for core <domain> business logic."""

    async def process_<operation>(
        self,
        request: <OperationRequest>,
        correlation_id: UUID,
    ) -> <OperationResult>:
        """Process <operation> with full error handling.

        Args:
            request: Operation request data
            correlation_id: Request correlation ID for tracing

        Returns:
            Operation result

        Raises:
            HuleEduError: On any business logic or infrastructure failure
        """
        ...

class <Domain>EventPublisherProtocol(Protocol):
    """Protocol for publishing <domain> events."""

    async def publish_<event_type>(
        self,
        event_data: <EventData>,
        correlation_id: UUID,
    ) -> None:
        """Publish <event_type> event.

        Args:
            event_data: Event payload data
            correlation_id: Request correlation ID for tracing

        Raises:
            HuleEduError: On publishing failure
        """
        ...
```

### 2. Exception-Based Service Implementation (`implementations/<service>_service_impl.py`)

```python
"""Main business logic implementation for <Service Name>.

This implementation follows the exception-based error handling pattern,
raising HuleEduError for all failure conditions.
"""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.error_handling import (
    raise_validation_error,
    raise_resource_not_found,
    raise_processing_error,
    HuleEduError,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.<service_name>.protocols import (
    <Domain>RepositoryProtocol,
    <Domain>ServiceProtocol,
    <Domain>EventPublisherProtocol,
)

logger = create_service_logger("<service_name>.<domain>_service")


class <Domain>ServiceImpl(<Domain>ServiceProtocol):
    """Implementation of <Domain>ServiceProtocol with exception-based error handling."""

    def __init__(
        self,
        repository: <Domain>RepositoryProtocol,
        event_publisher: <Domain>EventPublisherProtocol,
    ) -> None:
        """Initialize service with injected dependencies."""
        self.repository = repository
        self.event_publisher = event_publisher

    async def process_<operation>(
        self,
        request: <OperationRequest>,
        correlation_id: UUID,
    ) -> <OperationResult>:
        """Process <operation> with comprehensive error handling."""
        logger.info(
            "Processing <operation> request",
            extra={
                "correlation_id": str(correlation_id),
                "request_type": type(request).__name__,
            },
        )

        try:
            # Validate request
            if not request.<validation_field>:
                raise_validation_error(
                    service="<service_name>",
                    operation="process_<operation>",
                    field="<validation_field>",
                    message="<Validation failure message>",
                    correlation_id=correlation_id,
                )

            # Business logic processing
            result = await self._execute_business_logic(request, correlation_id)

            # Publish success event
            await self.event_publisher.publish_<event_type>(
                event_data=<EventData>(...),
                correlation_id=correlation_id,
            )

            logger.info(
                "Successfully processed <operation>",
                extra={
                    "correlation_id": str(correlation_id),
                    "result_id": str(result.id),
                },
            )

            return result

        except Exception as e:
            # Re-raise HuleEduError as-is, wrap others
            if isinstance(e, HuleEduError):
                raise
            else:
                raise_processing_error(
                    service="<service_name>",
                    operation="process_<operation>",
                    message=f"Unexpected error during processing: {str(e)}",
                    correlation_id=correlation_id,
                    original_error=str(e),
                )

    async def _execute_business_logic(
        self, 
        request: <OperationRequest>, 
        correlation_id: UUID
    ) -> <OperationResult>:
        """Execute core business logic with error handling."""
        # Example: Repository interaction
        try:
            entity = await self.repository.create_<entity>(request, correlation_id)
            return <OperationResult>(
                id=entity.id,
                status="completed",
                # ... other fields
            )
        except Exception:
            # Repository will raise HuleEduError, let it propagate
            raise
```

### 3. Exception-Based Repository (`implementations/<repository>_impl.py`)

```python
"""Repository implementation with exception-based error handling."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
    raise_database_error,
    HuleEduError,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.<service_name>.models_db import <Entity>
from services.<service_name>.protocols import <Domain>RepositoryProtocol

logger = create_service_logger("<service_name>.<domain>_repository")


class <Domain>RepositoryImpl(<Domain>RepositoryProtocol):
    """PostgreSQL implementation of <Domain>RepositoryProtocol."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize repository with database engine."""
        self.engine = engine
        self.session_factory = async_sessionmaker(
            engine, 
            expire_on_commit=False,
            class_=AsyncSession
        )

    @asynccontextmanager
    async def session_context(self):
        """Provide database session context manager."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_<entity>(
        self, 
        data: <CreateRequest>, 
        correlation_id: UUID
    ) -> <Entity>:
        """Create a new <entity> with comprehensive error handling."""
        logger.info(
            "Creating <entity>",
            extra={
                "correlation_id": str(correlation_id),
                "data_type": type(data).__name__,
            },
        )

        try:
            async with self.session_context() as session:
                entity = <Entity>(
                    **data.model_dump(exclude_unset=True)
                )
                session.add(entity)
                await session.flush()
                await session.refresh(entity)  # Prevent DetachedInstanceError
                await session.commit()

                logger.info(
                    "Successfully created <entity>",
                    extra={
                        "correlation_id": str(correlation_id),
                        "entity_id": str(entity.id),
                    },
                )

                return entity

        except IntegrityError as e:
            raise_validation_error(
                service="<service_name>",
                operation="create_<entity>",
                field="<constraint_field>",
                message="<Entity> creation failed due to constraint violation",
                correlation_id=correlation_id,
                constraint_error=str(e.orig),
            )
        except Exception as e:
            raise_database_error(
                service="<service_name>",
                operation="create_<entity>",
                message=f"Database error during <entity> creation: {str(e)}",
                correlation_id=correlation_id,
                original_error=str(e),
            )

    async def get_<entity>_by_id(
        self, 
        entity_id: UUID, 
        correlation_id: UUID
    ) -> <Entity>:
        """Retrieve an entity by ID with error handling."""
        logger.info(
            "Retrieving <entity> by ID",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": str(entity_id),
            },
        )

        try:
            async with self.session_context() as session:
                entity = await session.get(<Entity>, entity_id)
                
                if entity is None:
                    raise_resource_not_found(
                        service="<service_name>",
                        operation="get_<entity>_by_id",
                        resource_type="<Entity>",
                        resource_id=str(entity_id),
                        correlation_id=correlation_id,
                    )

                await session.refresh(entity)  # Ensure all relationships loaded
                
                logger.info(
                    "Successfully retrieved <entity>",
                    extra={
                        "correlation_id": str(correlation_id),
                        "entity_id": str(entity_id),
                    },
                )

                return entity

        except HuleEduError:
            # Re-raise our own errors
            raise
        except Exception as e:
            raise_database_error(
                service="<service_name>",
                operation="get_<entity>_by_id",
                message=f"Database error during <entity> retrieval: {str(e)}",
                correlation_id=correlation_id,
                entity_id=str(entity_id),
                original_error=str(e),
            )
```

### 4. Exception-Based API Routes (`api/<domain>_routes.py`)

```python
"""API routes for <domain> operations with exception-based error handling."""

from __future__ import annotations

from uuid import UUID, uuid4

from quart import Blueprint, request, jsonify
from quart_dishka import FromDishka, inject
from huleedu_service_libs.error_handling import (
    register_error_handlers,
    extract_correlation_id,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.<service_name>.protocols import <Domain>ServiceProtocol
from services.<service_name>.models_api import <CreateRequest>, <OperationResponse>

# Register error handlers for automatic HuleEduError -> HTTP response conversion
<domain>_bp = Blueprint('<domain>', __name__)
register_error_handlers(<domain>_bp)

logger = create_service_logger("<service_name>.<domain>_routes")


@<domain>_bp.post("/<entities>")
@inject
async def create_<entity>(
    service: FromDishka[<Domain>ServiceProtocol],
) -> tuple[dict, int]:
    """Create a new <entity> with comprehensive error handling."""
    correlation_id = extract_correlation_id() or uuid4()
    
    logger.info(
        "Received create <entity> request",
        extra={
            "correlation_id": str(correlation_id),
            "endpoint": "create_<entity>",
        },
    )

    # Parse request - let Pydantic validation raise exceptions
    request_data = await request.get_json()
    create_request = <CreateRequest>(**request_data)

    # Call service - exceptions are automatically handled by error handlers
    result = await service.process_create_<entity>(
        request=create_request,
        correlation_id=correlation_id,
    )

    # Convert to API response format
    response = <OperationResponse>(
        id=result.id,
        status=result.status,
        # ... other fields
    )

    logger.info(
        "Successfully processed create <entity> request",
        extra={
            "correlation_id": str(correlation_id),
            "entity_id": str(result.id),
        },
    )

    return response.model_dump(), 201


@<domain>_bp.get("/<entities>/<uuid:entity_id>")
@inject
async def get_<entity>(
    entity_id: UUID,
    service: FromDishka[<Domain>ServiceProtocol],
) -> dict:
    """Retrieve an <entity> by ID with error handling."""
    correlation_id = extract_correlation_id() or uuid4()
    
    logger.info(
        "Received get <entity> request",
        extra={
            "correlation_id": str(correlation_id),
            "entity_id": str(entity_id),
        },
    )

    # Service call - exceptions handled automatically
    result = await service.get_<entity>_by_id(
        entity_id=entity_id,
        correlation_id=correlation_id,
    )

    response = <EntityResponse>.from_entity(result)

    return response.model_dump()
```

### 5. Exception-Based Testing Patterns (`tests/unit/test_<service>_impl.py`)

```python
"""Unit tests for <Domain>ServiceImpl with exception-based error handling."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from huleedu_service_libs.error_handling import (
    HuleEduError,
    assert_raises_huleedu_error,
    ErrorDetailMatcher,
    create_test_error_detail,
)
from common_core.error_enums import ErrorCode

from services.<service_name>.implementations.<service>_service_impl import <Domain>ServiceImpl
from services.<service_name>.protocols import (
    <Domain>RepositoryProtocol,
    <Domain>EventPublisherProtocol,
)


class Test<Domain>Service:
    """Test suite for <Domain>ServiceImpl exception-based error handling."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Mock repository following protocol."""
        return AsyncMock(spec=<Domain>RepositoryProtocol)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher following protocol."""
        return AsyncMock(spec=<Domain>EventPublisherProtocol)

    @pytest.fixture
    def service(
        self, 
        mock_repository: AsyncMock, 
        mock_event_publisher: AsyncMock
    ) -> <Domain>ServiceImpl:
        """Service instance with mocked dependencies."""
        return <Domain>ServiceImpl(
            repository=mock_repository,
            event_publisher=mock_event_publisher,
        )

    @pytest.mark.asyncio
    async def test_successful_operation(
        self,
        service: <Domain>ServiceImpl,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test successful operation execution."""
        # Arrange
        correlation_id = uuid4()
        request = <OperationRequest>(...)
        expected_entity = <Entity>(id=uuid4(), ...)
        mock_repository.create_<entity>.return_value = expected_entity

        # Act
        result = await service.process_<operation>(request, correlation_id)

        # Assert
        assert result.id == expected_entity.id
        mock_repository.create_<entity>.assert_called_once_with(request, correlation_id)
        mock_event_publisher.publish_<event_type>.assert_called_once()

    @pytest.mark.asyncio
    async def test_validation_error_handling(
        self,
        service: <Domain>ServiceImpl,
    ) -> None:
        """Test that validation errors are properly raised."""
        # Arrange
        correlation_id = uuid4()
        invalid_request = <OperationRequest>(
            <validation_field>=None  # Invalid data
        )

        # Act & Assert
        with assert_raises_huleedu_error(
            ErrorDetailMatcher(
                error_code=ErrorCode.VALIDATION_FAILED,
                service="<service_name>",
                operation="process_<operation>",
                correlation_id=correlation_id,
            )
        ):
            await service.process_<operation>(invalid_request, correlation_id)

    @pytest.mark.asyncio
    async def test_repository_error_propagation(
        self,
        service: <Domain>ServiceImpl,
        mock_repository: AsyncMock,
    ) -> None:
        """Test that repository errors are properly propagated."""
        # Arrange
        correlation_id = uuid4()
        request = <OperationRequest>(...)
        
        # Configure repository to raise HuleEduError
        mock_repository.create_<entity>.side_effect = HuleEduError(
            error_detail=create_test_error_detail(
                error_code=ErrorCode.DATABASE_ERROR,
                service="<service_name>",
                operation="create_<entity>",
                correlation_id=correlation_id,
            )
        )

        # Act & Assert
        with assert_raises_huleedu_error(
            ErrorDetailMatcher(
                error_code=ErrorCode.DATABASE_ERROR,
                service="<service_name>",
                operation="create_<entity>",
                correlation_id=correlation_id,
            )
        ):
            await service.process_<operation>(request, correlation_id)

    @pytest.mark.asyncio
    async def test_unexpected_error_wrapping(
        self,
        service: <Domain>ServiceImpl,
        mock_repository: AsyncMock,
    ) -> None:
        """Test that unexpected errors are wrapped in HuleEduError."""
        # Arrange
        correlation_id = uuid4()
        request = <OperationRequest>(...)
        mock_repository.create_<entity>.side_effect = ValueError("Unexpected error")

        # Act & Assert
        with assert_raises_huleedu_error(
            ErrorDetailMatcher(
                error_code=ErrorCode.PROCESSING_ERROR,
                service="<service_name>",
                operation="process_<operation>",
                correlation_id=correlation_id,
            )
        ):
            await service.process_<operation>(request, correlation_id)
```

### 6. Dependency Injection Configuration (`di.py`)

```python
"""Dependency injection configuration for <Service Name>."""

from __future__ import annotations

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.<service_name>.config import Settings, settings
from services.<service_name>.implementations.<service>_service_impl import <Domain>ServiceImpl
from services.<service_name>.implementations.<repository>_impl import <Domain>RepositoryImpl
from services.<service_name>.implementations.event_publisher_impl import <Domain>EventPublisherImpl
from services.<service_name>.protocols import (
    <Domain>ServiceProtocol,
    <Domain>RepositoryProtocol,
    <Domain>EventPublisherProtocol,
)


class <Service>Provider(Provider):
    """Provider for <Service Name> dependencies."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide application settings."""
        return settings

    @provide(scope=Scope.APP)
    async def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide database engine with proper configuration."""
        return create_async_engine(
            settings.database_url,
            echo=settings.DATABASE_ECHO,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    @provide(scope=Scope.APP)
    def provide_repository(
        self, 
        engine: AsyncEngine
    ) -> <Domain>RepositoryProtocol:
        """Provide repository implementation."""
        return <Domain>RepositoryImpl(engine)

    @provide(scope=Scope.APP)
    async def provide_event_publisher(
        self, 
        settings: Settings
    ) -> <Domain>EventPublisherProtocol:
        """Provide event publisher implementation."""
        publisher = <Domain>EventPublisherImpl(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            service_name=settings.SERVICE_NAME,
        )
        await publisher.start()
        return publisher

    @provide(scope=Scope.REQUEST)
    def provide_service(
        self,
        repository: <Domain>RepositoryProtocol,
        event_publisher: <Domain>EventPublisherProtocol,
    ) -> <Domain>ServiceProtocol:
        """Provide service implementation."""
        return <Domain>ServiceImpl(
            repository=repository,
            event_publisher=event_publisher,
        )


def create_container() -> AsyncContainer:
    """Create and configure the application's dependency injection container."""
    return make_async_container(
        <Service>Provider(),
    )
```

### 7. Application Setup (`app.py`)

```python
"""Application setup for <Service Name> with HuleEduApp integration."""

from __future__ import annotations

from dishka.integrations.quart import setup_dishka
from huleedu_service_libs.quart_app import HuleEduApp
from sqlalchemy.ext.asyncio import create_async_engine

from services.<service_name>.config import Settings, settings
from services.<service_name>.di import create_container
from services.<service_name>.api.health_routes import health_bp
from services.<service_name>.api.<domain>_routes import <domain>_bp
from services.<service_name>.startup_setup import initialize_services


def create_app(settings_override: Settings | None = None) -> HuleEduApp:
    """Create and configure the <Service Name> application."""
    app_settings = settings_override or settings
    
    # Create HuleEduApp with guaranteed infrastructure
    app = HuleEduApp(__name__)
    
    # Initialize guaranteed infrastructure
    app.container = create_container()
    app.database_engine = create_async_engine(
        app_settings.database_url,
        echo=False,
        future=True,
        pool_size=app_settings.DATABASE_POOL_SIZE,
        max_overflow=app_settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=app_settings.DATABASE_POOL_PRE_PING,
        pool_recycle=app_settings.DATABASE_POOL_RECYCLE,
    )
    app.extensions = {}
    
    # Setup dependency injection
    setup_dishka(container=app.container, app=app)
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(<domain>_bp, url_prefix="/api/v1")
    
    # Initialize services
    app.before_serving(lambda: initialize_services(app, app_settings, app.container))
    
    return app


# Create application instance
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=settings.DEBUG)
```

## Key Principles

### 1. Exception-Based Error Handling
- **NO tuple returns** - all errors are raised as exceptions
- Use `raise_*` factory functions from `huleedu_service_libs.error_handling`
- Propagate `HuleEduError` exceptions, wrap unexpected errors
- Automatic HTTP error conversion in API routes

### 2. Protocol-First Design
- Define all interfaces as `typing.Protocol` first
- Implement concrete classes that follow protocols
- Use protocol types in dependency injection
- Test against protocols, not implementations

### 3. Comprehensive Testing
- Unit tests with protocol-based mocking
- Integration tests for database and external services
- Contract tests for Pydantic models
- Exception handling tests with proper matchers

### 4. HuleEduApp Integration
- Use `HuleEduApp` base class for guaranteed infrastructure
- Initialize database engine in `create_app()`
- Type-safe access to guaranteed attributes
- Proper lifecycle management

### 5. Observability Integration
- Structured logging with correlation IDs
- Prometheus metrics with service-specific patterns
- OpenTelemetry tracing integration
- Health endpoints with proper error handling

## Development Workflow

1. **Design Protocols** - Start with interfaces defining your service contracts
2. **Implement Business Logic** - Create service implementations with proper error handling
3. **Add Persistence** - Implement repository patterns with database integration
4. **Create API Routes** - Add HTTP endpoints with automatic error conversion
5. **Write Comprehensive Tests** - Cover all scenarios with proper exception testing
6. **Configure Dependencies** - Set up Dishka providers with proper scoping
7. **Document Service** - Add README with usage examples and API documentation

## Quality Assurance

### Required Commands
```bash
# Type checking
pdm run typecheck-all

# Code formatting and linting
pdm run format-all
pdm run lint-fix --unsafe-fixes

# Testing
pdm run pytest services/<service_name>/tests/

# Full validation
pdm run test-all
```

### Success Criteria
- ✅ All type checks pass
- ✅ All linting checks pass
- ✅ 100% test pass rate
- ✅ No tuple-based error returns
- ✅ Proper exception-based error handling
- ✅ Protocol-based dependency injection
- ✅ Comprehensive test coverage

This template ensures consistency across all HuleEdu services while maintaining the highest standards of code quality, testability, and maintainability.
