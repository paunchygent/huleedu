# HuleEdu Service Libraries

A comprehensive collection of shared utilities and infrastructure components for HuleEdu microservices, providing consistent patterns for distributed system concerns including event-driven communication, observability, resilience, and data persistence.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Core Modules](#core-modules)
  - [Kafka Client](#kafka-client)
  - [Redis Client](#redis-client)
  - [Database Utilities](#database-utilities)
  - [Logging Utilities](#logging-utilities)
  - [Observability](#observability)
  - [Resilience Patterns](#resilience-patterns)
  - [Middleware](#middleware)
  - [Event Utilities](#event-utilities)
  - [Idempotency](#idempotency)
  - [Type-Safe Quart App](#type-safe-quart-app)
- [Integration Patterns](#integration-patterns)
- [Testing Guidelines](#testing-guidelines)
- [Migration Guide](#migration-guide)

## Overview

The HuleEdu Service Libraries (`huleedu_service_libs`) package provides battle-tested, production-ready utilities that enforce architectural consistency across all HuleEdu microservices. These libraries embody our core principles of event-driven architecture, protocol-based design, and comprehensive observability.

### Design Philosophy

1. **Protocol-First**: All major components expose protocols for clean dependency injection and testing
2. **Lifecycle Management**: Explicit `start()` and `stop()` methods for resource management
3. **Observability Built-In**: Metrics, tracing, and structured logging are first-class concerns
4. **Resilience by Default**: Circuit breakers, retries, and graceful degradation patterns
5. **Type Safety**: Full type hints and protocol definitions for compile-time safety

### Package Structure

```
huleedu_service_libs/
├── __init__.py              # Main exports
├── kafka_client.py          # Kafka event publishing
├── redis_client.py          # Redis operations & transactions
├── redis_pubsub.py          # Redis pub/sub for real-time
├── logging_utils.py         # Structured logging with context
├── metrics_middleware.py    # HTTP metrics collection
├── event_utils.py           # Event processing utilities
├── idempotency.py          # Idempotent message processing
├── protocols.py            # Shared protocol definitions
├── database/               # Database monitoring & health
├── middleware/             # Framework-specific middleware
├── observability/          # Distributed tracing
├── resilience/             # Circuit breakers & resilience
└── error_handling/         # Enhanced error context
```

## Installation

The service libraries are installed as part of the HuleEdu monorepo setup:

```python
# In service pyproject.toml dependencies
dependencies = [
    "-e file:///${PROJECT_ROOT}/services/libs",
    # ... other dependencies
]
```

## Core Modules

### Kafka Client

**Module**: `kafka_client.py`  
**Protocol**: `KafkaPublisherProtocol`  
**Purpose**: Simplified async Kafka producer with lifecycle management

#### Key Features
- Automatic EventEnvelope serialization
- Connection pooling and graceful shutdown
- Idempotent message delivery (`enable_idempotence=True`)
- Type-safe event publishing with generics

#### API Reference

```python
class KafkaBus:
    def __init__(self, *, client_id: str, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS)
    async def start(self) -> None
    async def stop(self) -> None
    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope[T_EventPayload],
        key: str | None = None,
    ) -> None
```

#### Usage Example

```python
from huleedu_service_libs import KafkaBus
from common_core.events.envelope import EventEnvelope

# Initialize with explicit client ID
kafka_bus = KafkaBus(client_id="content-service-producer")

# Lifecycle management
await kafka_bus.start()
try:
    # Publish events
    envelope = EventEnvelope(
        event_type="CONTENT_CREATED",
        source_service="content_service",
        data=ContentCreatedEvent(...)
    )
    await kafka_bus.publish("content-events", envelope)
finally:
    await kafka_bus.stop()
```

#### Configuration
- `KAFKA_BOOTSTRAP_SERVERS`: Default `"kafka:9092"`
- Acks: `"all"` (wait for all replicas)
- Idempotence: Enabled by default

### Redis Client

**Module**: `redis_client.py`  
**Protocol**: `RedisClientProtocol`, `AtomicRedisClientProtocol`  
**Purpose**: Redis operations with transaction support and pub/sub delegation

#### Key Features
- Atomic operations for idempotency (`SET NX`)
- WATCH/MULTI/EXEC transaction support
- Pattern scanning for bulk operations
- Integrated pub/sub via `RedisPubSub`
- Explicit lifecycle management

#### API Reference

```python
class RedisClient:
    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL)
    async def start(self) -> None
    async def stop(self) -> None
    
    # Basic operations
    async def set_if_not_exists(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool
    async def get(self, key: str) -> str | None
    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool
    async def delete_key(self, key: str) -> int
    async def ping(self) -> bool
    
    # Transactions
    async def watch(self, *keys: str) -> bool
    async def multi(self) -> bool
    async def exec(self) -> list[Any] | None
    async def unwatch(self) -> bool
    
    # Pattern operations
    async def scan_pattern(self, pattern: str) -> list[str]
    
    # Pub/Sub (delegated)
    async def publish(self, channel: str, message: str) -> int
    async def subscribe(self, channel: str) -> AsyncGenerator
    def get_user_channel(self, user_id: str) -> str
    async def publish_user_notification(self, user_id: str, event_type: str, data: dict) -> int
```

#### Usage Examples

**Idempotency Pattern**:
```python
redis_client = RedisClient(client_id="cj-assessment-redis")
await redis_client.start()

# Check for duplicate processing
key = f"processed:{event_id}"
is_first = await redis_client.set_if_not_exists(key, "1", ttl_seconds=86400)
if not is_first:
    logger.warning(f"Duplicate event {event_id}")
    return
```

**Transaction Pattern**:
```python
# Atomic counter increment
await redis_client.watch("counter")
current = await redis_client.get("counter")
await redis_client.multi()
await redis_client.setex("counter", 3600, str(int(current or 0) + 1))
result = await redis_client.exec()
if result is None:  # Transaction failed
    logger.warning("Counter update conflict")
```

**Pub/Sub Pattern**:
```python
# Publish to user channel
await redis_client.publish_user_notification(
    user_id="user123",
    event_type="essay_graded",
    data={"essay_id": "essay456", "score": 85}
)

# Subscribe to channel
async with redis_client.subscribe("ws:user123") as pubsub:
    async for msg in pubsub.listen():
        if msg["type"] == "message":
            data = json.loads(msg["data"])
            # Process notification
```

#### Configuration
- `REDIS_URL`: Default `"redis://redis:6379"`
- Connection timeout: 5 seconds
- Socket timeout: 5 seconds

### Database Utilities

**Module**: `database/`  
**Purpose**: PostgreSQL monitoring, health checks, and metrics collection

#### Components

##### DatabaseHealthChecker
Comprehensive health monitoring for PostgreSQL databases.

```python
class DatabaseHealthChecker:
    def __init__(self, engine: AsyncEngine, service_name: str)
    
    async def check_basic_connectivity(self, timeout: float = 5.0) -> Dict[str, Any]
    async def check_connection_pool_health(self) -> Dict[str, Any]
    async def check_query_performance(self, timeout: float = 10.0) -> Dict[str, Any]
    async def check_database_resources(self) -> Dict[str, Any]
    async def comprehensive_health_check(self) -> Dict[str, Any]
    async def get_health_summary(self) -> Dict[str, Any]
```

**Health Check Response Example**:
```json
{
  "service": "content_service",
  "overall_status": "healthy",
  "checks": {
    "connectivity": {
      "status": "healthy",
      "response_time_seconds": 0.012
    },
    "connection_pool": {
      "status": "healthy",
      "pool_size": 10,
      "active_connections": 3,
      "utilization_percent": 30.0
    },
    "query_performance": {
      "status": "healthy",
      "simple_query_time_seconds": 0.001,
      "complex_query_time_seconds": 0.045
    },
    "database_resources": {
      "status": "healthy",
      "active_connections": 15,
      "database_size": "125 MB"
    }
  }
}
```

##### Database Metrics
Prometheus metrics for database observability.

```python
# Setup database monitoring
from huleedu_service_libs.database import setup_database_monitoring

db_metrics = setup_database_monitoring(
    engine=engine,
    service_name="content_service",
    metrics_dict=existing_metrics  # Optional
)
```

**Collected Metrics**:
- `{service}_database_query_duration_seconds`: Query execution time histogram
- `{service}_database_connections_active`: Active connection gauge
- `{service}_database_connections_idle`: Idle connection gauge
- `{service}_database_connections_total`: Total pool size gauge
- `{service}_database_connections_overflow`: Overflow connections gauge
- `{service}_database_connections_acquired_total`: Connection acquisition counter
- `{service}_database_connections_released_total`: Connection release counter
- `{service}_database_transactions_total`: Transaction counter
- `{service}_database_transaction_duration_seconds`: Transaction duration histogram
- `{service}_database_errors_total`: Error counter by type and operation

##### Query Performance Tracking
Decorator for tracking query performance.

```python
from huleedu_service_libs.database import query_performance_tracker

class ContentRepository:
    @query_performance_tracker(metrics, operation="create", table="content")
    async def create_content(self, content_data: dict) -> Content:
        # Database operation
        pass
```

#### Integration Example

```python
# In startup_setup.py
async def setup_database(app: Quart, settings: Settings) -> AsyncEngine:
    engine = create_async_engine(settings.DATABASE_URL)
    
    # Setup monitoring
    db_metrics = setup_database_monitoring(engine, "content_service")
    app.extensions["db_metrics"] = db_metrics
    
    # Store health checker
    app.health_checker = DatabaseHealthChecker(engine, "content_service")
    
    return engine

# In health routes
@health_bp.route("/healthz")
async def health_check():
    health_checker = current_app.health_checker
    summary = await health_checker.get_health_summary()
    return jsonify(summary), 200 if summary["status"] == "healthy" else 503
```

### Logging Utilities

**Module**: `logging_utils.py`  
**Purpose**: Structured logging with service context using structlog

#### Key Features
- JSON formatting in production, colored console in development
- Automatic context binding with contextvars
- Event-specific logging with correlation IDs
- Service name and environment injection

#### API Reference

```python
def configure_service_logging(
    service_name: str,
    environment: str | None = None,
    log_level: str = "INFO",
) -> None

def create_service_logger(name: str | None = None) -> structlog.stdlib.BoundLogger

def log_event_processing(
    logger: structlog.stdlib.BoundLogger,
    message: str,
    envelope: EventEnvelope,
    **additional_context: Any,
) -> None
```

#### Usage Example

```python
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

# Configure once at startup
configure_service_logging(
    service_name="content-service",
    environment="production",
    log_level="INFO"
)

# Create loggers
logger = create_service_logger("content.api")

# Log with context
logger.info("Creating content", content_id=content_id, user_id=user_id)

# Log event processing
log_event_processing(
    logger,
    "Processing content update",
    envelope,
    content_id=content_id
)
```

#### Log Output Examples

**Development**:
```
2024-01-15T10:30:45.123Z [INFO    ] content.api:routes.py:create_content:45 Creating content content_id=c123 user_id=u456
```

**Production** (JSON):
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger_name": "content.api",
  "filename": "routes.py",
  "func_name": "create_content",
  "lineno": 45,
  "message": "Creating content",
  "content_id": "c123",
  "user_id": "u456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Observability

**Module**: `observability/tracing.py`  
**Purpose**: Distributed tracing with OpenTelemetry and Jaeger

#### Key Features
- W3C Trace Context propagation
- Automatic span creation with context
- Error recording and status management
- Trace ID extraction for correlation

#### API Reference

```python
def init_tracing(service_name: str) -> trace.Tracer
def get_tracer(service_name: str) -> trace.Tracer

@contextmanager
def trace_operation(
    tracer: trace.Tracer, 
    operation_name: str, 
    attributes: Optional[Dict[str, Any]] = None
)

def get_current_trace_id() -> Optional[str]
def inject_trace_context(carrier: Dict[str, Any]) -> None
def extract_trace_context(carrier: Dict[str, Any]) -> Any

@contextmanager
def use_trace_context(carrier: Dict[str, Any])
```

#### Usage Example

```python
from huleedu_service_libs.observability import init_tracing, trace_operation

# Initialize at startup
tracer = init_tracing("content_service")

# Trace operations
async def create_content(data: dict):
    with trace_operation(tracer, "create_content", {"content_type": data["type"]}):
        # Perform database operation
        content = await repository.create(data)
        
        # Add event to span
        current_span = trace.get_current_span()
        current_span.add_event("content_created", {"content_id": content.id})
        
        return content

# Propagate trace context in events
envelope = EventEnvelope(...)
inject_trace_context(envelope.metadata)
await kafka_bus.publish("content-events", envelope)

# Extract trace context from events
with use_trace_context(envelope.metadata):
    # Child spans will be linked to parent trace
    with trace_operation(tracer, "process_event"):
        await process_content_event(envelope)
```

#### Configuration
- `OTEL_EXPORTER_OTLP_ENDPOINT`: Default `"http://localhost:4317"`
- `SERVICE_VERSION`: Default `"1.0.0"`
- `ENVIRONMENT`: Default `"development"`

### Resilience Patterns

**Module**: `resilience/`  
**Purpose**: Circuit breakers and resilient wrappers for fault tolerance

#### Circuit Breaker

Prevents cascading failures by monitoring failure rates and temporarily blocking calls to failing services.

```python
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: timedelta = timedelta(seconds=60),
        success_threshold: int = 2,
        expected_exception: Type[Exception] = Exception,
        name: Optional[str] = None,
        tracer: Optional[trace.Tracer] = None,
        metrics: Optional[CircuitBreakerMetrics] = None,
        service_name: Optional[str] = None,
    )
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T
    def get_state(self) -> Dict[str, Any]
    def reset(self) -> None
```

**States**:
- `CLOSED`: Normal operation, requests pass through
- `OPEN`: Too many failures, requests blocked
- `HALF_OPEN`: Testing recovery, limited requests allowed

#### Usage Examples

**Direct Usage**:
```python
from huleedu_service_libs.resilience import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=timedelta(seconds=30),
    name="external_api"
)

try:
    result = await breaker.call(external_api.fetch_data, user_id)
except CircuitBreakerError:
    logger.error("Circuit breaker open for external API")
    return cached_data
```

**Decorator Pattern**:
```python
from huleedu_service_libs.resilience import circuit_breaker

@circuit_breaker(failure_threshold=3, recovery_timeout=timedelta(seconds=30))
async def call_external_service(data: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.example.com", json=data)
        return response.json()
```

**With Dependency Injection**:
```python
from huleedu_service_libs.resilience import make_resilient

# In di.py
@provide(scope=Scope.APP)
async def provide_external_client(
    settings: Settings,
    metrics: ServiceMetrics
) -> ExternalServiceProtocol:
    client = ExternalServiceImpl(settings.API_KEY)
    breaker = CircuitBreaker(
        name="external_service",
        metrics=metrics.circuit_breaker
    )
    return make_resilient(client, breaker)
```

#### Metrics Integration

Circuit breaker metrics are automatically collected when a metrics bridge is provided:

- `circuit_breaker_state`: Current state gauge (0=closed, 1=open, 2=half-open)
- `circuit_breaker_calls_total`: Call counter by result (success/failure/blocked)
- `circuit_breaker_state_transitions_total`: State transition counter

### Middleware

**Module**: `middleware/` and `metrics_middleware.py`  
**Purpose**: Framework-specific middleware for metrics and tracing

#### HTTP Metrics Middleware

Automatic request/response metrics collection for Quart services.

```python
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware

# In app.py
def create_app():
    app = Quart(__name__)
    
    # Setup metrics
    metrics = _create_metrics()
    app.extensions["metrics"] = metrics
    
    # Apply middleware
    setup_standard_service_metrics_middleware(app, "content_service")
    
    return app
```

**Collected Metrics**:
- `request_count`: Request counter by method, endpoint, status
- `request_duration`: Request duration histogram by method, endpoint

#### Tracing Middleware

Distributed tracing for HTTP requests.

```python
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from huleedu_service_libs.observability import init_tracing

# In app.py
tracer = init_tracing("content_service")
setup_tracing_middleware(app, tracer)
```

**Features**:
- Automatic span creation for requests
- W3C Trace Context propagation
- Correlation ID management
- Response time tracking

### Event Utilities

**Module**: `event_utils.py`  
**Purpose**: Event processing helpers for idempotency and user notifications

#### API Reference

```python
def extract_user_id_from_event_data(event_data: Any) -> str | None
def extract_correlation_id_as_string(correlation_id: Any) -> str | None
def generate_deterministic_event_id(msg_value: bytes) -> str
def extract_correlation_id_from_event(msg_value: bytes) -> str | None
```

#### Usage Example

```python
from huleedu_service_libs.event_utils import (
    generate_deterministic_event_id,
    extract_user_id_from_event_data
)

# Generate deterministic ID for idempotency
event_id = generate_deterministic_event_id(kafka_message.value)
idempotency_key = f"processed:{event_id}"

# Extract user for notifications
user_id = extract_user_id_from_event_data(envelope.data)
if user_id:
    await redis_client.publish_user_notification(
        user_id=user_id,
        event_type="essay_processed",
        data={"essay_id": envelope.data.essay_id}
    )
```

### Idempotency

**Module**: `idempotency.py`  
**Purpose**: Decorator for idempotent Kafka message processing

#### Features
- Deterministic event ID generation
- Atomic Redis SET NX operations
- Automatic lock release on failure
- Fail-open on Redis errors

#### Usage Example

```python
from huleedu_service_libs.idempotency import idempotent_consumer

@idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
async def handle_essay_submitted(msg: ConsumerRecord) -> None:
    envelope = EventEnvelope.model_validate_json(msg.value)
    
    # This will only execute once per unique event
    await process_essay(envelope.data)
    
    # If processing fails, the idempotency key is released
    # allowing natural retry on the next Kafka poll
```

### Type-Safe Quart App

**Module**: `quart_app.py`  
**Purpose**: Type-safe Quart application class that replaces setattr/getattr anti-patterns

#### Problem Statement

HuleEdu services historically used `setattr()`/`getattr()` for dynamic app attributes, violating DDD principles and type safety:

```python
# Anti-pattern (FORBIDDEN)
setattr(app, "database_engine", engine)
engine = getattr(current_app, "database_engine", None)
```

**Architectural Violations:**
- **Global State Container**: Using Quart app as service locator
- **Hidden Dependencies**: Business logic accesses framework internals without declaration
- **Type System Bypass**: Runtime string-based access with no compile-time verification
- **Poor Development Experience**: No IDE support, autocomplete, or refactoring safety

#### Solution: HuleEduApp Class

The `HuleEduApp` class provides type-safe infrastructure attributes with compile-time verification and IDE support.

#### API Reference

```python
class HuleEduApp(Quart):
    """Type-safe Quart application with guaranteed HuleEdu infrastructure."""
    
    # GUARANTEED INFRASTRUCTURE (Non-Optional) - All services MUST provide these
    database_engine: AsyncEngine
    container: AsyncContainer
    extensions: dict[str, Any]
    
    # OPTIONAL INFRASTRUCTURE (Service-Specific) - May be absent
    tracer: Optional[Tracer] = None
    consumer_task: Optional[asyncio.Task[None]] = None
    kafka_consumer: Optional[Any] = None
    
    def __init__(self, import_name: str, *args, **kwargs) -> None
```

#### Infrastructure Attributes

##### Guaranteed Infrastructure (All Services)

**`database_engine: AsyncEngine`**
- **Purpose**: SQLAlchemy async engine for database operations
- **Usage**: MUST be set during service initialization, accessed in health checks
- **Type**: `sqlalchemy.ext.asyncio.AsyncEngine`
- **Contract**: NON-OPTIONAL - All services must provide this

**`container: AsyncContainer`**
- **Purpose**: Dishka async container for dependency injection
- **Usage**: MUST be set during service initialization for protocol-based dependency resolution
- **Type**: `dishka.AsyncContainer`
- **Contract**: NON-OPTIONAL - All services must provide this

**`extensions: dict[str, Any]`**  
- **Purpose**: Standard Quart extensions dictionary
- **Usage**: Store app-level objects like metrics, tracer instances
- **Type**: `dict[str, Any]`
- **Contract**: GUARANTEED PRESENT - Initialized to empty dict

##### Optional Infrastructure (Service-Specific)

**`tracer: Optional[Tracer] = None`**
- **Purpose**: OpenTelemetry tracer for distributed tracing
- **Usage**: Services participating in distributed tracing
- **Type**: `opentelemetry.trace.Tracer`
- **Contract**: OPTIONAL - May be absent

##### Background Processing (Service-Specific)

**`consumer_task: Optional[asyncio.Task[None]]`**
- **Purpose**: Asyncio task for background Kafka consumer processing
- **Usage**: Services with background Kafka consumers, graceful shutdown
- **Type**: `asyncio.Task[None]`

**`kafka_consumer: Optional[Any]`**
- **Purpose**: Service-specific Kafka consumer instances
- **Usage**: Custom Kafka consumer implementations
- **Type**: `Any` (intentionally generic for service-specific consumer classes)

#### Usage Examples

##### Guaranteed Initialization Pattern

```python
from huleedu_service_libs import HuleEduApp
from dishka import make_async_container
from sqlalchemy.ext.asyncio import create_async_engine

def create_app() -> HuleEduApp:
    """Create app with guaranteed infrastructure initialization."""
    app = HuleEduApp(__name__)
    
    # IMMEDIATE initialization - satisfies non-optional contract
    app.database_engine = create_async_engine(DATABASE_URL)
    app.container = make_async_container(ServiceProvider())
    
    # Extensions already initialized to empty dict
    app.extensions["metrics"] = setup_metrics()
    
    return app

# Type-safe access (no None checks needed)
app = create_app()
engine = app.database_engine  # ✅ Guaranteed to exist
async with app.container() as request_container:  # ✅ No None check needed
    # Access dependencies
    pass
```

##### Migration from Optional Pattern

```python
# OLD (defensive programming with Optional types):
if current_app.database_engine is not None:
    engine = current_app.database_engine
    # Use engine...

if current_app.container is not None:
    async with current_app.container() as request_container:
        # Use container...

# NEW (confident access with guaranteed types):
engine = current_app.database_engine  # No None check needed
async with current_app.container() as request_container:  # No None check needed
    # Use container...
```

##### Health Check Pattern

```python
# health_routes.py - TYPE-SAFE WITH GUARANTEED INFRASTRUCTURE
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huleedu_service_libs import HuleEduApp
    current_app: HuleEduApp  # Type hint for IDE support

@health_bp.route("/healthz")
async def health_check():
    """Type-safe health check with guaranteed infrastructure."""
    
    # OLD (anti-pattern with getattr):
    # engine = getattr(current_app, "database_engine", None)
    # if engine is None: return error
    
    # OLD (defensive programming with Optional):
    # if current_app.database_engine is not None:
    #     engine = current_app.database_engine
    
    # NEW (confident access with guaranteed types):
    engine = current_app.database_engine  # ✅ Guaranteed to exist
    
    # Use typed engine for health check (no None check needed)
    health_checker = DatabaseHealthChecker(engine, "service_name")
    summary = await health_checker.get_health_summary()
    
    status_code = 200 if summary["overall_status"] == "healthy" else 503
    return jsonify(summary), status_code
```

##### Background Task Management

```python
# app.py - Worker service pattern
async def setup_background_tasks(app: HuleEduApp, settings: Settings) -> None:
    """Setup background Kafka consumer with lifecycle management."""
    
    # Start consumer task
    consumer = SpellCheckerKafkaConsumer(settings)
    consumer_task = asyncio.create_task(consumer.start())
    
    # Store for graceful shutdown
    app.consumer_task = consumer_task
    app.kafka_consumer = consumer

@app.after_serving
async def shutdown_background_tasks():
    """Graceful shutdown of background tasks."""
    if app.consumer_task is not None:
        app.consumer_task.cancel()
        try:
            await app.consumer_task
        except asyncio.CancelledError:
            pass
    
    if app.kafka_consumer is not None:
        await app.kafka_consumer.stop()
```

#### Migration Guide

##### From Optional to Guaranteed Types

**Step 1: Update App Creation to Guaranteed Initialization**

```python
# Before (Optional pattern)
from huleedu_service_libs import HuleEduApp
def create_app() -> HuleEduApp:
    app = HuleEduApp(__name__)
    # ... setup code ...
    app.database_engine = engine  # Set later
    app.container = container     # Set later
    return app

# After (guaranteed initialization)
def create_app() -> HuleEduApp:
    app = HuleEduApp(__name__)
    
    # IMMEDIATE initialization - satisfies non-optional contract
    app.database_engine = create_async_engine(DATABASE_URL)
    app.container = make_async_container(ServiceProvider())
    
    return app
```

**Step 2: Remove Defensive None Checks**

```python
# Before (Optional pattern - defensive programming)
if current_app.database_engine is not None:
    engine = current_app.database_engine
    # Use engine...

if current_app.container is not None:
    async with current_app.container() as request_container:
        # Use container...

# After (guaranteed types - confident access)
engine = current_app.database_engine  # No None check needed
async with current_app.container() as request_container:  # No None check needed
    # Use container...
```

**Step 3: Update Health Checks**

```python
# Before (defensive programming)
@health_bp.route("/healthz")
async def health_check():
    engine = current_app.database_engine
    if engine is None:
        return jsonify({"status": "error", "database": "not configured"}), 500
    # Use engine...

# After (guaranteed contract)
@health_bp.route("/healthz")
async def health_check():
    engine = current_app.database_engine  # Guaranteed to exist
    # Use engine directly...
```

**Step 4: Add Type Hints for IDE Support**

```python
# In route files for enhanced IDE support
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huleedu_service_libs import HuleEduApp
    current_app: HuleEduApp
```

##### Service-by-Service Migration Order

Based on task document analysis:

1. **Class Management Service** (Pilot - simple infrastructure)
2. **Result Aggregator Service** (Simple app.py structure)
3. **Essay Lifecycle Service** (Standard startup pattern)
4. **CJ Assessment Service** (DI container complexity)
5. **Batch Orchestrator Service** (Most complex - metrics, tracer, consumer tasks)

#### Benefits

##### Type Safety & Reliability
- **Compile-time verification**: MyPy catches attribute access errors before runtime
- **Guaranteed infrastructure**: No `None` checks needed for core components
- **IDE autocomplete**: Full IntelliSense support for app attributes
- **Refactoring safety**: Rename operations work across entire codebase

##### Development Experience
- **No more AttributeError**: Runtime errors become compile-time errors
- **No defensive programming**: Eliminate `if x is not None:` checks
- **Self-documenting**: Attribute types and contracts are explicit in class definition
- **Debugging efficiency**: Clear attribute names and types in debugger

##### Architectural Compliance
- **DDD Principle Alignment**: Infrastructure dependencies explicitly declared
- **Clean Code Standards**: No magic strings or runtime attribute access
- **Protocol-Based Design**: Clear interfaces for all infrastructure components
- **Explicit Contracts**: Non-optional infrastructure enforces architectural discipline

#### Best Practices

1. **Guaranteed initialization in create_app()**: Set database_engine and container immediately
2. **No defensive programming**: Don't check for None on guaranteed infrastructure
3. **Use TYPE_CHECKING imports**: Add type hints for `current_app` in route files
4. **Follow startup patterns**: Initialize infrastructure in dedicated `startup_setup.py`
5. **Graceful shutdown**: Always clean up background tasks and resources
6. **Keep attributes focused**: Only cross-cutting infrastructure, no service-specific state

#### Anti-Patterns to Avoid

1. **Don't add service-specific attributes**: HuleEduApp is for cross-cutting concerns only
2. **Don't bypass type system**: No `setattr()/getattr()` on HuleEduApp instances
3. **Don't forget TYPE_CHECKING**: Add type hints for optimal IDE support
4. **Don't skip guaranteed initialization**: Always set database_engine and container immediately
5. **Don't use defensive programming**: No `if x is not None:` checks on guaranteed infrastructure
6. **Don't store business logic**: Infrastructure only, no domain-specific objects

#### Architectural Discipline

**CRITICAL**: The HuleEduApp class must NOT become a global dumping ground. Attributes are strictly limited to cross-cutting, application-level infrastructure components like:

- Database engines and connection pools
- Distributed tracing infrastructure
- Dependency injection containers
- Background processing tasks
- Standard Quart extensions

Service-specific business logic, domain objects, or temporary state does NOT belong in HuleEduApp.

## Integration Patterns

### Dependency Injection Setup

```python
# In di.py
from dishka import Provider, Scope, provide
from huleedu_service_libs import KafkaBus, RedisClient

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

### Worker Service Pattern

```python
# In worker_main.py
from huleedu_service_libs.idempotency import idempotent_consumer

class EventProcessor:
    def __init__(self, redis_client: RedisClientProtocol, ...):
        self.redis_client = redis_client
    
    @idempotent_consumer(redis_client=self.redis_client)
    async def process_message(self, msg: ConsumerRecord):
        with trace_operation(self.tracer, "process_event"):
            envelope = EventEnvelope.model_validate_json(msg.value)
            
            # Extract trace context
            with use_trace_context(envelope.metadata):
                await self._handle_event(envelope)
```

## Testing Guidelines

### Protocol-Based Mocking

```python
from unittest.mock import AsyncMock
from huleedu_service_libs.protocols import RedisClientProtocol, KafkaPublisherProtocol

# Mock Redis client
mock_redis = AsyncMock(spec=RedisClientProtocol)
mock_redis.set_if_not_exists.return_value = True
mock_redis.get.return_value = "cached_value"

# Mock Kafka publisher
mock_kafka = AsyncMock(spec=KafkaPublisherProtocol)
mock_kafka.publish.return_value = None

# Inject mocks
service = MyService(redis_client=mock_redis, kafka_bus=mock_kafka)
```

### Integration Testing

```python
import pytest
from testcontainers.redis import RedisContainer
from testcontainers.kafka import KafkaContainer

@pytest.fixture
async def redis_client():
    with RedisContainer() as redis:
        client = RedisClient(
            client_id="test-redis",
            redis_url=redis.get_connection_url()
        )
        await client.start()
        yield client
        await client.stop()

@pytest.fixture
async def kafka_bus():
    with KafkaContainer() as kafka:
        bus = KafkaBus(
            client_id="test-kafka",
            bootstrap_servers=kafka.get_bootstrap_server()
        )
        await bus.start()
        yield bus
        await bus.stop()
```

### Circuit Breaker Testing

```python
async def test_circuit_breaker_opens_on_failures():
    breaker = CircuitBreaker(failure_threshold=2)
    failing_func = AsyncMock(side_effect=Exception("Service down"))
    
    # First failure
    with pytest.raises(Exception):
        await breaker.call(failing_func)
    
    # Second failure opens circuit
    with pytest.raises(Exception):
        await breaker.call(failing_func)
    
    # Circuit is now open
    with pytest.raises(CircuitBreakerError):
        await breaker.call(failing_func)
    
    assert breaker.state == CircuitBreakerState.OPEN
```

## Migration Guide

### Migrating from Direct Redis/Kafka Clients

**Before**:
```python
# Direct aiokafka usage
producer = AIOKafkaProducer(...)
await producer.start()
await producer.send_and_wait(topic, value=json.dumps(data))
```

**After**:
```python
# Using service libraries
kafka_bus = KafkaBus(client_id="my-service")
await kafka_bus.start()
envelope = EventEnvelope(...)
await kafka_bus.publish(topic, envelope)
```

### Migrating to Structured Logging

**Before**:
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"Processing event {event_id}")
```

**After**:
```python
from huleedu_service_libs.logging_utils import create_service_logger
logger = create_service_logger("my_service.processor")
logger.info("Processing event", event_id=event_id, user_id=user_id)
```

### Adding Database Monitoring

**Before**:
```python
engine = create_async_engine(DATABASE_URL)
# No monitoring
```

**After**:
```python
from huleedu_service_libs.database import setup_database_monitoring

engine = create_async_engine(DATABASE_URL)
db_metrics = setup_database_monitoring(engine, "my_service")
# Automatic connection pool and query metrics
```

## Dependencies and Version Requirements

- Python >= 3.11
- aiokafka >= 0.10.0
- redis >= 5.0.0
- structlog >= 25.3.0
- opentelemetry-api >= 1.20.0
- opentelemetry-sdk >= 1.20.0
- opentelemetry-exporter-otlp >= 1.20.0
- prometheus-client >= 0.19.0
- SQLAlchemy >= 2.0.0
- Pydantic >= 2.0.0

## Environment Variables

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses (default: `"kafka:9092"`)
- `REDIS_URL`: Redis connection URL (default: `"redis://redis:6379"`)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OpenTelemetry collector endpoint (default: `"http://localhost:4317"`)
- `ENVIRONMENT`: Deployment environment (default: `"development"`)
- `SERVICE_VERSION`: Service version for tracing (default: `"1.0.0"`)

## Best Practices

1. **Always use lifecycle management**: Call `start()` and `stop()` on clients
2. **Use protocols for dependency injection**: Depend on `RedisClientProtocol`, not `RedisClient`
3. **Configure logging early**: Call `configure_service_logging()` in startup
4. **Use idempotency decorator**: Wrap all Kafka consumers with `@idempotent_consumer`
5. **Add circuit breakers**: Protect external service calls with circuit breakers
6. **Propagate trace context**: Use `inject_trace_context()` and `extract_trace_context()`
7. **Monitor database health**: Use `DatabaseHealthChecker` in health endpoints
8. **Structured logging**: Always use keyword arguments for context
9. **Test with mocks**: Use `AsyncMock(spec=Protocol)` for unit tests
10. **Graceful degradation**: Design for Redis/Kafka unavailability

## Common Anti-Patterns to Avoid

1. **Direct client instantiation in handlers**: Use dependency injection
2. **Forgetting lifecycle management**: Always start/stop clients properly
3. **Synchronous Redis operations**: All operations are async
4. **Ignoring circuit breaker state**: Handle `CircuitBreakerError`
5. **Unstructured logging**: Avoid f-strings, use keyword arguments
6. **Missing correlation IDs**: Always propagate trace context
7. **Hardcoded configuration**: Use environment variables
8. **Skipping idempotency**: Every consumer needs idempotency
9. **Blocking in async code**: Use async clients throughout
10. **Ignoring metrics**: Monitor all critical operations