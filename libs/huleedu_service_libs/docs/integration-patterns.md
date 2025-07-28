# Integration Patterns

Service setup and dependency injection patterns for HuleEdu microservices.

## Overview

This guide demonstrates how to integrate HuleEdu Service Libraries into microservices using dependency injection, proper lifecycle management, and architectural patterns that align with HuleEdu's protocol-first design.

## Basic Service Integration

### Dependency Injection Setup

```python
# In di.py
from dishka import Provider, Scope, provide
from huleedu_service_libs import KafkaBus, RedisClient
from huleedu_service_libs.protocols import KafkaPublisherProtocol, RedisClientProtocol

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaPublisherProtocol:
        kafka_bus = KafkaBus(client_id=f"{settings.SERVICE_NAME}-producer")
        await kafka_bus.start()
        return kafka_bus
    
    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL
        )
        await redis_client.start()
        return redis_client
```

### Service Startup Pattern

```python
# In startup_setup.py
from huleedu_service_libs.logging_utils import configure_service_logging
from huleedu_service_libs.database import setup_database_monitoring
from huleedu_service_libs.observability import init_tracing

async def setup_services(app: Quart, settings: Settings):
    # Configure logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL
    )
    
    # Initialize tracing
    tracer = init_tracing(settings.SERVICE_NAME)
    app.tracer = tracer
    
    # Setup database
    engine = create_async_engine(settings.DATABASE_URL)
    db_metrics = setup_database_monitoring(engine, settings.SERVICE_NAME)
    
    # Setup middleware
    setup_standard_service_metrics_middleware(app, settings.SERVICE_NAME)
    setup_tracing_middleware(app, tracer)
```

## HTTP Service Pattern (Quart)

### Complete App Setup

```python
# In app.py
from huleedu_service_libs import HuleEduApp
from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware

def create_app() -> HuleEduApp:
    app = HuleEduApp(__name__)
    
    # IMMEDIATE infrastructure initialization
    app.database_engine = create_async_engine(settings.DATABASE_URL)
    app.container = make_async_container(ServiceProvider())
    
    # Error handling
    register_error_handlers(app)
    
    # Middleware
    setup_standard_service_metrics_middleware(app, settings.SERVICE_NAME)
    
    # Register blueprints
    from api.content_routes import content_bp
    app.register_blueprint(content_bp)
    
    return app
```

### Route Implementation

```python
# In api/content_routes.py
from quart import Blueprint, request, current_app
from dishka.integrations.quart import inject, FromDishka
from huleedu_service_libs.error_handling import raise_validation_error, raise_resource_not_found

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

@content_bp.route("/content/<content_id>")
@inject
async def get_content(
    content_id: str,
    content_service: FromDishka[ContentServiceProtocol]
) -> dict:
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

## Worker Service Pattern (Kafka)

### Event Processor Setup

```python
# In event_processor.py
from huleedu_service_libs.idempotency_v2 import idempotent_consumer, IdempotencyConfig

class EventProcessor:
    def __init__(
        self,
        redis_client: RedisClientProtocol,
        content_service: ContentServiceProtocol,
        service_name: str
    ):
        self.redis_client = redis_client
        self.content_service = content_service
        self.config = IdempotencyConfig(
            service_name=service_name,
            enable_debug_logging=True
        )
    
    @idempotent_consumer(redis_client=self.redis_client, config=self.config)
    async def process_content_event(self, msg: ConsumerRecord):
        with trace_operation(self.tracer, "process_content_event"):
            envelope = EventEnvelope.model_validate_json(msg.value)
            
            # Extract trace context
            with use_trace_context(envelope.metadata):
                await self._handle_event(envelope)
    
    async def _handle_event(self, envelope: EventEnvelope):
        if envelope.event_type == "CONTENT_VALIDATION_REQUESTED":
            await self._handle_validation_request(envelope.data)
        elif envelope.event_type == "CONTENT_INDEXING_REQUESTED":
            await self._handle_indexing_request(envelope.data)
        else:
            logger.warning(f"Unknown event type: {envelope.event_type}")
```

### Worker Main Setup

```python
# In worker_main.py
import asyncio
from aiokafka import AIOKafkaConsumer
from dishka import make_async_container

async def main():
    # Setup DI container
    container = make_async_container(ServiceProvider())
    
    async with container() as request_container:
        # Get dependencies
        event_processor = await request_container.get(EventProcessor)
        settings = await request_container.get(Settings)
        
        # Setup Kafka consumer
        consumer = AIOKafkaConsumer(
            "content-events",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=f"{settings.SERVICE_NAME}-consumer",
            auto_offset_reset="earliest"
        )
        
        await consumer.start()
        try:
            async for msg in consumer:
                await event_processor.process_content_event(msg)
        finally:
            await consumer.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Service Implementation Patterns

### Repository Pattern with Monitoring

```python
# In implementations/content_repository_impl.py
from huleedu_service_libs.database import query_performance_tracker

class ContentRepositoryImpl:
    def __init__(self, engine: AsyncEngine, metrics: dict):
        self.engine = engine
        self.metrics = metrics
    
    @query_performance_tracker(operation="get_content", table="content")
    async def get_content(self, content_id: str) -> Content | None:
        async with self.engine.begin() as conn:
            result = await conn.execute(
                select(Content).where(Content.id == content_id)
            )
            return result.scalar_one_or_none()
    
    @query_performance_tracker(operation="create_content", table="content")
    async def create_content(self, data: dict) -> Content:
        async with self.engine.begin() as conn:
            content = Content(**data)
            conn.add(content)
            await conn.commit()
            return content
```

### Service Layer with Event Publishing

```python
# In implementations/content_service_impl.py
class ContentServiceImpl:
    def __init__(
        self,
        repository: ContentRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        redis_client: RedisClientProtocol
    ):
        self.repository = repository
        self.kafka_bus = kafka_bus
        self.redis_client = redis_client
    
    async def create_content(self, data: dict) -> Content:
        # Idempotency check
        idempotency_key = f"content_creation:{data['user_id']}:{hash(data['title'])}"
        is_first = await self.redis_client.set_if_not_exists(
            idempotency_key, "1", ttl_seconds=3600
        )
        
        if not is_first:
            existing = await self.repository.get_content_by_title(data['title'])
            return existing
        
        # Create content
        content = await self.repository.create_content(data)
        
        # Publish event
        envelope = EventEnvelope(
            event_type="CONTENT_CREATED",
            source_service="content_service",
            data=ContentCreatedEvent(
                content_id=content.id,
                user_id=content.user_id,
                title=content.title
            )
        )
        await self.kafka_bus.publish("content-events", envelope)
        
        return content
```

## Health Check Integration

### Database Health Monitoring

```python
# In api/health_routes.py
from huleedu_service_libs.database import DatabaseHealthChecker

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz")
async def health_check():
    # Access guaranteed infrastructure
    engine = current_app.database_engine
    
    # Comprehensive health check
    health_checker = DatabaseHealthChecker(engine, "content_service")
    summary = await health_checker.get_health_summary()
    
    status_code = 200 if summary["overall_status"] == "healthy" else 503
    return jsonify(summary), status_code

@health_bp.route("/readiness")
async def readiness_check():
    """Check if service is ready to accept traffic."""
    checks = {
        "database": await _check_database(),
        "redis": await _check_redis(),
        "kafka": await _check_kafka()
    }
    
    all_ready = all(check["status"] == "ready" for check in checks.values())
    status_code = 200 if all_ready else 503
    
    return jsonify({
        "status": "ready" if all_ready else "not_ready",
        "checks": checks
    }), status_code
```

## Background Task Management

For services with background tasks, store task references in app for graceful shutdown:

```python
# Store background tasks in app
app.consumer_task = asyncio.create_task(consumer.start())
app.kafka_consumer = consumer

@app.after_serving
async def shutdown_background_tasks():
    if app.consumer_task:
        app.consumer_task.cancel()
    if app.kafka_consumer:
        await app.kafka_consumer.stop()
```

## Configuration

Use Pydantic settings for configuration with environment variables for all infrastructure dependencies and service-specific TTL mappings.

## Testing Integration

### Protocol-Based Testing

```python
# Use AsyncMock with protocols for clean testing
mock_redis = AsyncMock(spec=RedisClientProtocol)
mock_kafka = AsyncMock(spec=KafkaPublisherProtocol)

# Inject mocks into service
service = ContentServiceImpl(repository=mock_repo, kafka_bus=mock_kafka, redis_client=mock_redis)
```

## Best Practices

1. **Protocol-First Design**: Always depend on protocols, not implementations
2. **Lifecycle Management**: Properly start/stop all infrastructure clients
3. **Graceful Shutdown**: Handle background tasks and connections properly
4. **Health Monitoring**: Include comprehensive health checks
5. **Error Handling**: Use framework-specific error handlers
6. **Structured Logging**: Configure logging early in startup
7. **Idempotency**: Protect all event processing with idempotency
8. **Tracing Context**: Propagate trace context across service boundaries
9. **Configuration**: Use environment variables for all configuration
10. **Testing**: Mock protocols for unit tests, use integration tests for workflows

## Anti-Patterns to Avoid

1. **Direct Instantiation**: Don't create clients directly in handlers
2. **Missing Lifecycle**: Always start/stop infrastructure clients
3. **Framework Coupling**: Keep business logic independent of web frameworks
4. **Hardcoded Values**: Use configuration for all external dependencies
5. **Synchronous Operations**: Use async throughout the stack
6. **Missing Error Handling**: Handle infrastructure failures gracefully
7. **Resource Leaks**: Ensure proper cleanup in all code paths
8. **Testing Shortcuts**: Don't skip protocol-based mocking