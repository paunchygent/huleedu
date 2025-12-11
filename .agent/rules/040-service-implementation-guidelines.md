---
id: "040-service-implementation-guidelines"
type: "implementation"
created: 2025-05-25
last_updated: 2025-11-17
scope: "backend"
---

# 040: Service Implementation Guidelines

## Core Stack
- **Framework**: HuleEduApp (typed Quart) with guaranteed infrastructure
- **Dependencies**: PDM exclusively (`pyproject.toml`, `pdm.lock`)  
- **DI**: Dishka with `APP`/`REQUEST` scopes + QuartDishka integration
- **Config**: SecureServiceSettings base with environment detection
- **Errors**: HuleEduError + domain factories from `huleedu_service_libs.error_handling`
- **Observability**: Prometheus + OpenTelemetry

## Mandatory Service Patterns

### Application Structure
```python
# app.py - Application initialization (<150 LoC)
from huleedu_service_libs import HuleEduApp
from .startup_setup import initialize_services, shutdown_services

app = HuleEduApp(__name__)

@app.before_serving
async def startup() -> None:
    await initialize_services(app, settings)

@app.after_serving  
async def shutdown() -> None:
    await shutdown_services()
```

### Startup Setup Pattern
```python
# startup_setup.py - Centralized initialization
async def initialize_services(app: HuleEduApp, settings: Settings) -> None:
    container = make_async_container(CoreProvider(), ImplementationsProvider())
    QuartDishka(app=app, container=container)
    
    app.database_engine = database_engine  # REQUIRED
    app.container = container              # REQUIRED
    # Optional: tracer, consumer_task, etc.
```

### Configuration Standards
```python
# config.py - Must inherit SecureServiceSettings
from huleedu_service_libs.config import SecureServiceSettings

class Settings(SecureServiceSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICE_", extra="ignore")
    SERVICE_NAME: str = "service_name"
    # Environment detection via base class: is_production(), is_development()
```

## Infrastructure Integration Requirements

### Service Libraries Integration
- **MUST** use `huleedu_service_libs.kafka_client.KafkaBus` for Kafka with circuit breakers
- **MUST** use `huleedu_service_libs.redis_client.RedisClient` for Redis with lifecycle management
- **MUST** use `huleedu_service_libs.logging_utils` for structured logging
- **MUST** use `huleedu_service_libs.error_handling` for all exceptions
- **MUST** use `@idempotent_consumer` decorator for ALL Kafka consumers
- **MUST** integrate database monitoring for PostgreSQL services

### Protocols and DI Pattern
```python
# protocols.py - Behavioral contracts
class Repository(Protocol):
    async def get_by_id(self, id: str) -> Entity | None: ...

# di.py - Dishka providers with circuit breakers
@provide(scope=Scope.APP)
def provide_circuit_breaker_registry(settings: Settings) -> CircuitBreakerRegistry:
    registry = CircuitBreakerRegistry()
    if settings.CIRCUIT_BREAKER_ENABLED:
        registry.register("kafka_producer", CircuitBreaker(...))
    return registry

@provide(scope=Scope.REQUEST)  # Per-operation instances  
def provide_repository(session: AsyncSession, settings: Settings) -> Repository:
    return MockRepositoryImpl() if settings.USE_MOCK_REPOSITORY else ProductionRepositoryImpl()
```

### Circuit Breaker Standards
```python
# Shared protocols: Use service library wrappers
@provide(scope=Scope.APP)
def provide_http_client(base_client: HttpClientProtocol, circuit_breaker_registry: CircuitBreakerRegistry) -> HttpClientProtocol:
    from huleedu_service_libs.resilience import CircuitBreakerHttpClient
    breaker = circuit_breaker_registry.get("http_client")
    return CircuitBreakerHttpClient(base_client, breaker)

# Service-specific protocols: Create service-specific wrappers
@provide(scope=Scope.APP)
def provide_service_client(base_client: ServiceSpecificProtocol, circuit_breaker_registry: CircuitBreakerRegistry) -> ServiceSpecificProtocol:
    from .implementations.circuit_breaker_service_client import CircuitBreakerServiceClient
    breaker = circuit_breaker_registry.get("service_client")
    return CircuitBreakerServiceClient(base_client, breaker)
```

## Required Integrations

### Database Integration
```python
# Database monitoring + health checking (startup_setup.py)
db_metrics = setup_database_monitoring(engine, "service_name")
app.extensions["db_metrics"] = db_metrics
app.health_checker = DatabaseHealthChecker(engine, "service_name")
app.database_engine = database_engine  # REQUIRED HuleEduApp attribute
```

### Kafka Consumer Integration
```python
# Idempotent consumers with Redis deduplication
@idempotent_consumer(redis_client=redis_client, config=idempotency_config)
async def handle_message(msg: ConsumerRecord):
    # Automatically prevents duplicate processing
    # Header-first processing: Complete headers skip JSON parsing
    pass

# Background task startup (startup_setup.py)
consumer_task = asyncio.create_task(kafka_consumer.start_consumer())
app.consumer_task = consumer_task  # Optional HuleEduApp attribute
```

### Outbox Pattern Integration
```python
# EventRelayWorker startup (startup_setup.py) 
relay_worker = await request_container.get(EventRelayWorker)
await relay_worker.start()
app.extensions["relay_worker"] = relay_worker

# Transactional outbox for reliable event publishing
# Shared DB session ensures atomicity with domain operations
# OutboxManager automatically adds Kafka headers (event_id, event_type, trace_id, source_service)
```

### Observability Middleware Setup
```python  
# Metrics middleware (startup_setup.py)
setup_standard_service_metrics_middleware(app, "service_abbreviation")

# Distributed tracing (startup_setup.py)
tracer = init_tracing("service_name")
app.extensions["tracer"] = tracer
setup_tracing_middleware(app, tracer)
```

## Error Handler Patterns
```python
# Global error handlers (app.py)
@app.errorhandler(HuleEduError)
async def handle_huleedu_error(error: HuleEduError) -> Response:
    return create_error_response(error.error_detail)

@app.errorhandler(ValidationError) 
async def handle_validation_error(error: ValidationError) -> Response:
    raise_validation_error(service="service", operation="validation", ...)

@app.errorhandler(Exception)
async def handle_general_error(error: Exception) -> Response:
    raise_processing_error(service="service", operation="processing", ...)
```

## Service Types

| Service Type | Characteristics | Required Attributes |
|-------------|----------------|-------------------|
| HTTP Services | HuleEduApp + Blueprint pattern | `database_engine`, `container`, `/health`, `/metrics` |
| Worker Services | Event processor + background Kafka consumer | Same DI, error handling, observability |
| Hybrid Services | Combined HTTP + Worker | Single `startup_setup.py`, shared metrics registry |

## Production Requirements
- **MUST** implement graceful shutdown with proper async resource cleanup
- **MUST** use DI-managed `aiohttp.ClientSession` with configured timeouts  
- **MUST** use manual Kafka commits with error boundaries (no auto-commit)
- **MUST** fail fast on startup errors with `logger.critical()` and `raise`

## Repository Selection Standards
- **Pattern**: `USE_MOCK_REPOSITORY` flag for development/testing environments
- **Testing**: Always use mock repositories regardless of USE_MOCK_REPOSITORY flag
- **Development**: Mock repositories simulate production behavior (atomic operations, TTL)

## App Extensions Pattern
```python
# Standard extension storage in app.extensions dict
app.extensions["metrics"] = metrics
app.extensions["tracer"] = tracer  
app.extensions["relay_worker"] = relay_worker
app.extensions["queue_processor"] = queue_processor  # LLM Provider
app.extensions["dishka_container"] = container  # Alternative storage
```

## Alembic Migration Standards
```python
# config.py - REQUIRED for Alembic
@property
def database_url(self) -> str:
    # Environment-aware database URL construction
    # Production: HULEEDU_PROD_DB_* variables
    # Development: localhost with service-specific port
    
# pyproject.toml - Standardized scripts
[tool.pdm.scripts]
migrate-upgrade = "alembic upgrade head"
migrate-downgrade = "alembic downgrade -1" 
migrate-revision = "alembic revision --autogenerate"
```

## Implementation Checklist
- [ ] HuleEduApp with `startup_setup.py` initialization
- [ ] SecureServiceSettings inheritance
- [ ] Error handling with HuleEduError factories
- [ ] Circuit breakers for external dependencies
- [ ] Repository selection with `USE_MOCK_REPOSITORY` support
- [ ] Database monitoring + health checking integration
- [ ] `@idempotent_consumer` for all Kafka consumers
- [ ] Outbox pattern with EventRelayWorker
- [ ] Metrics class + observability middleware
- [ ] Alembic migration setup for PostgreSQL services
- [ ] Docker multi-stage builds
