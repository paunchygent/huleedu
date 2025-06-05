---
trigger: model_decision
description: "Implementation patterns for HuleEdu services. Follow when developing or modifying services to ensure consistency and maintainability."
---

---
description: Read before all work on web framework, I/O, API etc
globs: 
alwaysApply: false
---
# 040: Service Implementation Guidelines

## 1. Core Stack

## 3. Protocols, Dependency Injection, and Metrics

- All service contracts must use `typing.Protocol`. Do not use adapters/wrappers in prototypes.
- Use Dishka DI for all provider wiring. Orchestration maps (e.g., `phase_initiators_map`) must use enums as keys.
- Expose Prometheus metrics for orchestration and state transitions (see README Sec 5).

- **Framework**: Quart for async HTTP services, direct `asyncio` and `aiokafka` for worker services.
- **Dependencies**: PDM exclusively (`pyproject.toml`, `pdm.lock`)
- **Programming**: `async/await` for all I/O operations

## 2. HTTP Service Blueprint Architecture **MANDATORY**

### 2.1. Blueprint Pattern Requirements
**ALL HTTP services (Quart-based) MUST follow this architecture:**

- **app.py MUST** be lean (< 150 lines) and focused on:
  - Quart app initialization
  - Dependency injection setup with Dishka
  - Blueprint registration
  - Global middleware (metrics, logging, error handling)
  - Startup/shutdown hooks
- **FORBIDDEN**: Direct route definitions in app.py

### 2.2. API Directory Structure **REQUIRED**
```python
services/<service_name>/
├── app.py                          # Lean application setup
├── api/                            # **REQUIRED** Blueprint routes directory
│   ├── __init__.py
│   ├── health_routes.py            # **REQUIRED** /healthz, /metrics endpoints
│   └── <domain>_routes.py          # Domain-specific routes (e.g., content_routes.py)
├── config.py                       # Pydantic settings
├── protocols.py                    # Service behavioral contracts
└── di.py                          # Dishka DI providers (if needed)
```

### 2.3. Blueprint Implementation Standards

#### health_routes.py - **REQUIRED** for all HTTP services:
```python
"""Health and metrics routes for [Service Name]."""
from quart import Blueprint, Response, jsonify
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

health_bp = Blueprint('health_routes', __name__)

@health_bp.route("/healthz")
async def health_check() -> Response:
    """Health check endpoint."""
    # Service-specific health validation logic
    return jsonify({"status": "ok", "message": "[Service] is healthy"}), 200

@health_bp.route("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
```

#### Domain-specific route files:
- **MUST** define Blueprint with descriptive name (e.g., `content_bp`, `batch_bp`)
- **MUST** focus on HTTP request/response handling only
- **MUST** delegate business logic to protocol implementations
- **Dependencies MUST** be injected via module functions from app.py

#### app.py Blueprint Registration Pattern:
```python
# Import Blueprints
from .api.health_routes import health_bp
from .api.content_routes import content_bp, set_content_dependencies

# Register Blueprints
app.register_blueprint(health_bp)
app.register_blueprint(content_bp)

# Share dependencies with Blueprints
@app.before_serving
async def startup():
    # Initialize dependencies
    set_content_dependencies(store_root, metrics)
```

## 3. Async Patterns & Structure

### 3.1. Dependency Contracts & Protocols
- **MUST** define internal behavioral contracts using `typing.Protocol` in a `<service_name>/protocols.py` file.
- Business logic components (e.g., in `event_processor.py` or Blueprint route handlers) **MUST** depend on these protocols, not concrete implementations directly.
- Concrete implementations of protocols are provided at the service entry point (e.g., in `worker_main.py` or `app.py`), ideally via a DI framework like Dishka.

### 3.2. Dependency Injection with Dishka
- **MUST** use Dishka DI framework for all services
- **HTTP Services**: Use `quart-dishka` integration with `@inject` decorator and `FromDishka[T]` annotations
- **Worker Services**: Use Dishka container with manual scoping for Kafka message processing

#### HTTP Service Pattern (Quart + quart-dishka):
```python
# app.py
from dishka import make_async_container
from quart_dishka import QuartDishka, inject
from di import ServiceProvider

@app.before_serving
async def startup():
    container = make_async_container(ServiceProvider())
    QuartDishka(app=app, container=container)

# In Blueprint route file
@content_bp.post("/endpoint")
@inject
async def handler(dependency: FromDishka[Protocol]) -> Response:
    # Use dependency directly
    pass
```

#### Worker Service Pattern:
```python
# worker_main.py
from dishka import make_async_container

async def main():
    container = make_async_container(ServiceProvider())
    async with container() as request_container:
        dependency = await request_container.get(Protocol)
        # Use dependency
```

#### DI Provider Pattern:
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

#### Clean DI Architecture Pattern (ELS Model):
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

### 3.3. Worker Service Structure Pattern (Example: Spell Checker)
- **`worker_main.py`**: Handles service lifecycle (startup, shutdown), Kafka client management, signal handling, and the primary message consumption loop. Initializes/injects dependencies.
- **`event_processor.py`**: Contains logic for deserializing messages, implementing defined protocols (often by composing functions from `core_logic.py`), and orchestrating the processing flow for a single message.
- **`core_logic.py`**: Houses fundamental, reusable business logic, algorithms, and direct interactions with external systems (e.g., HTTP calls), implemented as standalone functions or simple classes.
- **`protocols.py`**: Defines `typing.Protocol` interfaces.

### 3.4. Resource Management (e.g., Kafka Clients, HTTP Sessions)
- **MUST** use `asynccontextmanager` for managing resources that require explicit setup and teardown (e.g., Kafka clients, `aiohttp.ClientSession`).
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

## 4. State Management
- Each service owns its primary entities' state
- State changes **MUST** be communicated via events
- Follow state transition logic from Architectural Design Blueprint

## 5. API Design
- RESTful principles
- Pydantic models for request/response schemas
- API versioning (`/v1/...`)
- `ErrorInfoModel` for standardized error responses

## 6. Configuration Management

### 6.1. Standardized Pydantic Settings Pattern
- **MUST** use `pydantic-settings` for all service configuration
- **MUST** create `config.py` at service root with this pattern:

```python
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuration settings for the [Service Name]."""
    LOG_LEVEL: str = "INFO"
    # Add typed fields with defaults
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="[SERVICE_NAME]_",
    )

settings = Settings()
```

### 6.2. Configuration Usage
- Import settings: `from .config import settings`
- Use `settings.FIELD_NAME` instead of `os.getenv()`
- Sensitive info **MUST NEVER** be hardcoded

## 7. Logging

### 7.1. Centralized Logging Utility
- **MUST** use `huleedu_service_libs.logging_utils` for all logging
- **FORBIDDEN**: Standard library `logging` module in services
- **Pattern**:
```python
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

# Service initialization
configure_service_logging("service-name", log_level=settings.LOG_LEVEL)
logger = create_service_logger("component-name")
```

### 7.2. Mandatory Correlation IDs
- For any operation chain (request/event), a `correlation_id` **MUST** be established or propagated
- This `correlation_id` **MUST** be in all log messages across all involved services
- Use `log_event_processing()` for EventEnvelope processing

### 7.3. Consistent Log Levels & Clear Messages
- Use appropriate levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- Log messages **MUST** be clear, concise, and contextual