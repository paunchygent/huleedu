# Type-Safe Quart App

Type-safe Quart application patterns with dependency injection and lifecycle management.

## Overview

The HuleEduApp extends Quart with type-safe patterns, dependency injection integration, and standardized lifecycle management. It provides a foundation for building robust HTTP services with proper resource management and observability.

## HuleEduApp Class

**Module**: `quart_app.py`  
**Purpose**: Enhanced Quart application with type safety and standardized patterns

### Basic Usage

```python
from huleedu_service_libs import HuleEduApp
from huleedu_service_libs.error_handling.quart import register_error_handlers

def create_app() -> HuleEduApp:
    app = HuleEduApp(__name__)
    
    # Configure error handling
    register_error_handlers(app)
    
    return app
```

### Key Features

- **Type-Safe Extensions**: Typed attributes for common infrastructure
- **Lifecycle Management**: Automatic resource startup and cleanup
- **DI Integration**: Built-in Dishka container support
- **Standard Middleware**: Pre-configured observability and metrics
- **Health Check Support**: Integrated health monitoring

## Application Structure

### Recommended App Structure

```python
# app.py - Main application factory
from huleedu_service_libs import HuleEduApp
from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from dishka import make_async_container

def create_app() -> HuleEduApp:
    app = HuleEduApp(__name__)
    
    # IMMEDIATE infrastructure setup - no lazy loading
    app.database_engine = create_async_engine(settings.DATABASE_URL)
    app.container = make_async_container(ServiceProvider())
    
    # Error handling
    register_error_handlers(app)
    
    # Middleware
    setup_standard_service_metrics_middleware(app, settings.SERVICE_NAME)
    
    # Register blueprints
    from api.content_routes import content_bp
    from api.health_routes import health_bp
    
    app.register_blueprint(content_bp)
    app.register_blueprint(health_bp)
    
    return app
```

### Type-Safe Extensions

```python
# HuleEduApp provides typed attributes
class HuleEduApp(Quart):
    # Infrastructure - immediately available
    database_engine: AsyncEngine
    container: AsyncContainer
    
    # Optional components
    tracer: Optional[Tracer] = None
    metrics: Optional[dict] = None
    health_checker: Optional[DatabaseHealthChecker] = None
    
    # Service-specific extensions can be added
    kafka_consumer: Optional[AIOKafkaConsumer] = None
    redis_client: Optional[RedisClient] = None
```

## Dependency Injection Integration

### Route-Level Injection

```python
from quart import Blueprint, request
from dishka.integrations.quart import inject, FromDishka
from huleedu_service_libs.error_handling import raise_validation_error

content_bp = Blueprint("content", __name__)

@content_bp.route("/content", methods=["POST"])
@inject
async def create_content(
    content_service: FromDishka[ContentServiceProtocol]
) -> dict:
    data = await request.get_json()
    
    if not data:
        raise_validation_error(
            service="content_service",
            operation="create_content",
            message="Request body required",
            correlation_id=get_correlation_id()
        )
    
    content = await content_service.create_content(data)
    return {"content_id": content.id}
```

### Service-Level Access

```python
from quart import current_app

async def access_infrastructure():
    # Access guaranteed infrastructure
    engine = current_app.database_engine
    container = current_app.container
    
    # Access optional components (check first)
    if current_app.tracer:
        with trace_operation(current_app.tracer, "operation"):
            pass
```

## Lifecycle Management

### Startup Pattern

```python
# startup_setup.py - Infrastructure initialization
from huleedu_service_libs.logging_utils import configure_service_logging
from huleedu_service_libs.observability import init_tracing, setup_tracing_middleware
from huleedu_service_libs.database import setup_database_monitoring, DatabaseHealthChecker

async def setup_services(app: HuleEduApp, settings: Settings):
    """Complete service initialization."""
    
    # Configure logging first
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL
    )
    
    # Initialize tracing
    app.tracer = init_tracing(settings.SERVICE_NAME)
    setup_tracing_middleware(app, app.tracer)
    
    # Setup database monitoring
    app.metrics = setup_database_monitoring(
        app.database_engine, 
        settings.SERVICE_NAME
    )
    
    # Create health checker
    app.health_checker = DatabaseHealthChecker(
        app.database_engine, 
        settings.SERVICE_NAME
    )
    
    logger.info("Service initialization complete", service=settings.SERVICE_NAME)
```

### Background Tasks

For services with background tasks (like Kafka consumers), store task references in the app:

```python
import asyncio
from aiokafka import AIOKafkaConsumer

async def setup_background_tasks(app: HuleEduApp, settings: Settings):
    """Setup background consumers and tasks."""
    
    # Create and store Kafka consumer
    consumer = AIOKafkaConsumer(
        "content-events",
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"{settings.SERVICE_NAME}-consumer"
    )
    
    app.kafka_consumer = consumer
    
    # Start consumer as background task
    app.consumer_task = asyncio.create_task(run_consumer(consumer))
    
    logger.info("Background tasks started")

@app.after_serving
async def shutdown_background_tasks():
    """Graceful shutdown of background resources."""
    if hasattr(current_app, 'consumer_task'):
        current_app.consumer_task.cancel()
        try:
            await current_app.consumer_task
        except asyncio.CancelledError:
            pass
    
    if hasattr(current_app, 'kafka_consumer'):
        await current_app.kafka_consumer.stop()
    
    logger.info("Background tasks stopped")
```

## Error Handling Integration

### Framework-Specific Error Handlers

```python
from huleedu_service_libs.error_handling.quart import register_error_handlers

# Register in app factory
app = HuleEduApp(__name__)
register_error_handlers(app)

# Use core error factories in routes
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
    raise_authorization_error
)

@content_bp.route("/content/<content_id>")
@inject
async def get_content(
    content_id: str,
    content_service: FromDishka[ContentServiceProtocol]
):
    content = await content_service.get_content(content_id)
    
    if not content:
        raise_resource_not_found(
            service="content_service",
            operation="get_content",
            resource_type="content",
            resource_id=content_id,
            correlation_id=get_correlation_id()
        )
    
    return content.to_dict()
```

## Health Check Integration

### Standard Health Routes

```python
# api/health_routes.py
from quart import Blueprint, current_app, jsonify
from huleedu_service_libs.database import DatabaseHealthChecker

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz")
async def health_check():
    """Comprehensive health check."""
    # Access guaranteed infrastructure
    engine = current_app.database_engine
    
    # Create or use existing health checker
    health_checker = getattr(current_app, 'health_checker', None)
    if not health_checker:
        health_checker = DatabaseHealthChecker(engine, "content_service")
    
    summary = await health_checker.get_health_summary()
    status_code = 200 if summary["overall_status"] == "healthy" else 503
    
    return jsonify(summary), status_code

@health_bp.route("/readiness")
async def readiness_check():
    """Check if service is ready to accept traffic."""
    checks = {
        "database": await _check_database_ready(),
        "dependencies": await _check_dependencies_ready()
    }
    
    all_ready = all(check["status"] == "ready" for check in checks.values())
    status_code = 200 if all_ready else 503
    
    return jsonify({
        "status": "ready" if all_ready else "not_ready",
        "checks": checks
    }), status_code

async def _check_database_ready() -> dict:
    """Check database readiness."""
    try:
        engine = current_app.database_engine
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "message": "Database accessible"}
    except Exception as e:
        return {"status": "not_ready", "message": f"Database error: {e}"}
```

## Middleware Setup

### Standard Middleware Stack

```python
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.observability import setup_tracing_middleware

def setup_middleware(app: HuleEduApp, settings: Settings):
    """Setup standard middleware stack."""
    
    # Metrics middleware
    setup_standard_service_metrics_middleware(app, settings.SERVICE_NAME)
    
    # Tracing middleware (if tracer is available)
    if app.tracer:
        setup_tracing_middleware(app, app.tracer)
    
    # Request ID middleware
    @app.before_request
    async def before_request():
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        g.correlation_id = correlation_id
    
    @app.after_request
    async def after_request(response):
        if hasattr(g, 'correlation_id'):
            response.headers["X-Correlation-ID"] = g.correlation_id
        return response
```

## Configuration Patterns

### Settings Integration

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SERVICE_NAME: str = "content_service"
    ENVIRONMENT: str = "development"
    
    # Database
    DATABASE_URL: str
    
    # Infrastructure
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    REDIS_URL: str = "redis://redis:6379"
    
    # Observability
    LOG_LEVEL: str = "INFO"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4317"
    
    class Config:
        env_file = ".env"

# Use in app factory
settings = Settings()
app = create_app(settings)
```

## Testing Patterns

### Test App Factory

```python
# test_helpers.py
from huleedu_service_libs import HuleEduApp
from unittest.mock import AsyncMock

def create_test_app() -> HuleEduApp:
    """Create app for testing."""
    app = HuleEduApp(__name__)
    app.config['TESTING'] = True
    
    # Mock infrastructure for testing
    app.database_engine = AsyncMock()
    app.container = AsyncMock()
    
    # Register test routes
    from api.content_routes import content_bp
    app.register_blueprint(content_bp)
    
    return app

# Use in tests
@pytest.fixture
async def test_app():
    app = create_test_app()
    async with app.test_app():
        yield app
```

### Route Testing

```python
import pytest
from quart.testing import QuartClient

async def test_create_content(test_app: HuleEduApp):
    """Test content creation endpoint."""
    test_client: QuartClient = test_app.test_client()
    
    # Mock service dependency
    mock_service = AsyncMock()
    mock_service.create_content.return_value = Content(id="123", title="Test")
    
    # Inject mock into DI container
    test_app.container.get.return_value = mock_service
    
    # Test request
    response = await test_client.post("/content", json={"title": "Test Content"})
    
    assert response.status_code == 200
    data = await response.get_json()
    assert data["content_id"] == "123"
```

## Best Practices

1. **Immediate Infrastructure Setup**: Initialize database and DI container in app factory
2. **Type-Safe Access**: Use typed attributes for guaranteed infrastructure
3. **Proper Lifecycle**: Setup startup and shutdown handlers for background tasks
4. **Standard Health Checks**: Include both health and readiness endpoints
5. **Middleware Stack**: Use standard observability and metrics middleware
6. **Error Handling**: Register framework-specific error handlers early
7. **Dependency Injection**: Use @inject decorator for route-level DI
8. **Configuration**: Use Pydantic settings with environment variables

## Anti-Patterns to Avoid

1. **Lazy Infrastructure**: Don't defer critical infrastructure setup
2. **Missing Health Checks**: Always include health monitoring endpoints
3. **Untyped Access**: Use typed attributes rather than generic app.extensions
4. **Resource Leaks**: Properly shutdown background tasks and connections
5. **Missing Error Handling**: Register error handlers before routes
6. **Synchronous Operations**: Keep all operations async throughout
7. **Hardcoded Configuration**: Use environment variables for all config
8. **Testing Shortcuts**: Use proper test app factories and mocking