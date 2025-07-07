---
description: Use when defining async patterns, protocols, dependency injection, resource management, and worker service structure.
globs: 
alwaysApply: false
---
# 042: Async Patterns and Dependency Injection

## 1. Purpose
Defines async patterns, protocols, dependency injection, resource management, and worker service structure.

**See also**: [040-service-implementation-guidelines.mdc](mdc:040-service-implementation-guidelines.mdc) for core stack requirements.

## 2. Dependency Contracts & Protocols

### 2.1. Protocol Definition Requirements
- **MUST** define internal behavioral contracts using `typing.Protocol` in a `<service_name>/protocols.py` file.
- Business logic components (e.g., in `event_processor.py` or Blueprint route handlers) **MUST** depend on these protocols, not concrete implementations directly.
- Concrete implementations of protocols are provided at the service entry point (e.g., in `worker_main.py` or `app.py`), ideally via a DI framework like Dishka.

## 3. Dependency Injection with Dishka

### 3.1. Framework Requirements
- **MUST** use Dishka DI framework for all services
- **HTTP Services**: Use `quart-dishka` integration with `@inject` decorator and `FromDishka[T]` annotations
- **Worker Services**: Use Dishka container with manual scoping for Kafka message processing

### 3.2. HTTP Service Pattern (Quart + quart-dishka):
```python
# app.py - Lean setup with startup hooks
from startup_setup import initialize_services, shutdown_services

@app.before_serving
async def startup():
    await initialize_services(app, settings)

@app.after_serving
async def shutdown():
    await shutdown_services()

# startup_setup.py - DI and metrics initialization
async def initialize_services(app: Quart, settings: Settings):
    container = make_async_container(ServiceProvider())
    QuartDishka(app=app, container=container)
    # Create metrics with app context pattern
    app.extensions["metrics"] = _create_metrics(registry)

# In Blueprint route file
@content_bp.post("/endpoint")
@inject
async def handler(dependency: FromDishka[Protocol]) -> Response:
    # Use dependency directly
    pass
```

### 3.3. Worker Service Pattern:
```python
# worker_main.py
from dishka import make_async_container

async def main():
    container = make_async_container(ServiceProvider())
    async with container() as request_container:
        dependency = await request_container.get(Protocol)
        # Use dependency
```

### 3.4. DI Provider Pattern:
- **MUST** create `<service>/di.py` with service-specific `Provider` class
- **MUST** use `@provide` decorator with appropriate scopes (`Scope.APP`, `Scope.REQUEST`)
- **MUST** return protocol interfaces, not concrete classes from business logic
```python
# di.py
from dishka import Provider, Scope, provide

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_protocol(self) -> ProtocolInterface:
        return ConcreteImplementation()
```

### 3.5. Clean DI Architecture Pattern (ELS Model):
- **di.py MUST** be lean (< 150 lines) containing ONLY:
  - Provider class with @provide methods
  - Simple instantiation logic
  - No business logic whatsoever
- **implementations/ directory**: For services with multiple concrete implementations:
  - Contains all business logic implementations following SRP
  - Each implementation file: 50-100 lines (single responsibility)
  - Protocol interfaces remain in protocols.py
  - Import implementations in di.py only for provider methods
```python
# Example clean di.py structure
from implementations.content_client import DefaultContentClient
from implementations.event_publisher import DefaultEventPublisher

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_content_client(self, session: ClientSession) -> ContentClient:
        return DefaultContentClient(session, settings)
```

## 4. Worker Service Structure Pattern

### 4.1. Standard File Structure (Example: Spell Checker)
- **`worker_main.py`**: Handles service lifecycle (startup, shutdown), Kafka client management, signal handling, and the primary message consumption loop. Initializes/injects dependencies.
- **`event_processor.py`**: Contains logic for deserializing messages, implementing defined protocols (often by composing functions from `core_logic.py`), and orchestrating the processing flow for a single message.
- **`core_logic.py`**: Houses fundamental, reusable business logic, algorithms, and direct interactions with external systems (e.g., HTTP calls), implemented as standalone functions or simple classes.
- **`protocols.py`**: Defines `typing.Protocol` interfaces.

## 5. Resource Management

### 5.1. Async Context Manager Requirements
- **MUST** use `asynccontextmanager` for managing resources that require explicit setup and teardown (e.g., Kafka clients, `aiohttp.ClientSession`).

### 5.2. Standard Patterns:
```python
@asynccontextmanager
async def managed_http_session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as session:
        yield session

@asynccontextmanager
async def kafka_clients(
    # ... kafka config args ...
) -> AsyncIterator[tuple[AIOKafkaConsumer, AIOKafkaProducer]]:
    consumer = AIOKafkaConsumer(...)
    producer = AIOKafkaProducer(...)
    await consumer.start()
    await producer.start()
    try:
        yield consumer, producer
    finally:
        await consumer.stop()
        await producer.stop()
```

### 3.6. Database Monitoring Integration Pattern

For services with PostgreSQL persistence:

```python
# di.py
from huleedu_service_libs.database import DatabaseMetrics
from services.<service_name>.metrics import setup_<service>_database_monitoring

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        return create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
        )
    
    @provide(scope=Scope.APP)
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        return setup_<service>_database_monitoring(
            engine=engine, service_name=settings.SERVICE_NAME
        )
```

### 3.7. Health Check Engine Storage Pattern

PostgreSQL services MUST store the database engine on the app instance for health checks:

```python
# startup_setup.py
async def initialize_database_schema(app: Quart, settings: Settings) -> AsyncEngine:
    engine = create_async_engine(settings.DATABASE_URL, ...)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.database_engine = engine  # Required for health checks
    return engine

# app.py
@app.before_serving
async def startup() -> None:
    await startup_setup.initialize_database_schema(app, settings)
```

### 3.8. Route Dependency Injection Patterns

For Quart services using quart-dishka:

```python
# api/routes.py
from dishka import FromDishka
from quart_dishka import inject

@blueprint.route("/endpoint")
@inject  # MUST use @inject decorator
async def handler(
    service: FromDishka[ServiceProtocol],
    settings: FromDishka[Settings],
) -> Response:
    # Dependencies are automatically injected
    result = await service.process()
    return jsonify(result)
```

### 3.9. Metrics Integration Pattern

Services with database metrics integration:

```python
# metrics.py
def setup_<service>_database_monitoring(
    engine: AsyncEngine,
    service_name: str,
    existing_metrics: Optional[Dict[str, Any]] = None,
) -> DatabaseMetrics:
    """Setup comprehensive database monitoring for service."""
    return setup_database_monitoring(engine, service_name, existing_metrics)

# startup_setup.py
async def initialize_services(app: Quart, settings: Settings) -> None:
    # Get database metrics from container
    async with container() as request_container:
        database_metrics = await request_container.get(DatabaseMetrics)
    
    # Initialize metrics with database integration
    metrics = get_metrics(database_metrics)
    app.extensions["metrics"] = metrics
```

### 3.10. Provider Organization Pattern

For complex services, organize providers by domain:

```python
# di.py
class DatabaseProvider(Provider):
    """Database engine, sessions, and metrics."""
    
class RepositoryProvider(Provider):
    """Repository implementations."""
    
class ServiceProvider(Provider):
    """Core service dependencies."""
    
class MetricsProvider(Provider):
    """Prometheus metrics with database integration."""

# app.py or worker_main.py
container = make_async_container(
    DatabaseProvider(),
    RepositoryProvider(),
    ServiceProvider(),
    MetricsProvider(),
)
