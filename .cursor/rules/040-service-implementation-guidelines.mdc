---
description: Read before all work on web framework, I/O, API etc
globs: 
alwaysApply: false
---
# 040: Service Implementation Guidelines

## 1. Purpose
Complete service implementation patterns and requirements for HuleEdu microservices. Contains ALL patterns used across services.

Model service: `@identity_service/`

**Related Rules**:
- [041-http-service-blueprint.mdc](mdc:041-http-service-blueprint.mdc) - HTTP Blueprint patterns
- [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc) - Async/DI patterns
- [043-service-configuration-and-logging.mdc](mdc:043-service-configuration-and-logging.mdc) - Config/logging
- [047-security-configuration-standards.mdc](mdc:047-security-configuration-standards.mdc) - Security patterns
- [048-structured-error-handling-standards.mdc](mdc:048-structured-error-handling-standards.mdc) - Error patterns
- [071.1-prometheus-metrics-patterns.mdc](mdc:071.1-prometheus-metrics-patterns.mdc) - Metrics patterns
- [087-docker-development-container-patterns.mdc](mdc:087-docker-development-container-patterns.mdc) - Docker patterns

## 2. Core Stack
- **Framework**: HuleEduApp (typed Quart) with guaranteed infrastructure
- **Dependencies**: PDM exclusively (`pyproject.toml`, `pdm.lock`)  
- **DI**: Dishka with `APP`/`REQUEST` scopes + QuartDishka integration
- **Config**: SecureServiceSettings base with environment detection → [047](mdc:047-security-configuration-standards.mdc)
- **Errors**: HuleEduError + domain factories → [048](mdc:048-structured-error-handling-standards.mdc)
- **Observability**: Prometheus + OpenTelemetry → [071.1](mdc:071.1-prometheus-metrics-patterns.mdc)

## 3. Mandatory Service Patterns

### 3.1. Application Structure
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

### 3.2. Startup Setup Pattern
```python
# startup_setup.py - Centralized initialization
async def initialize_services(app: HuleEduApp, settings: Settings) -> None:
    container = make_async_container(CoreProvider(), ImplementationsProvider())
    QuartDishka(app=app, container=container)
    
    app.database_engine = database_engine  # REQUIRED
    app.container = container              # REQUIRED
    # Optional: tracer, consumer_task, etc.
```

### 3.3. Configuration Standards
```python
# config.py - Must inherit SecureServiceSettings
from huleedu_service_libs.config import SecureServiceSettings

class Settings(SecureServiceSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICE_", extra="ignore")
    
    SERVICE_NAME: str = "service_name"
    # Environment detection via base class: is_production(), is_development()
```

### 3.4. Error Handling Integration
```python
# Use structured error factories from huleedu_service_libs
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_validation_error,
    raise_user_not_found_error,  # Domain-specific factories
)

try:
    result = await handler.process()
except HuleEduError as e:
    logger.warning(f"Business error: {e.error_detail.message}")
    return jsonify({"error": e.error_detail.model_dump()}), e.error_detail.status_code
```

## 4. Infrastructure Patterns

### 4.1. Protocols and DI
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
    if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
        return MockRepositoryImpl()
    return ProductionRepositoryImpl()
```

### 4.2. Service Libraries Integration
- **MUST** use `huleedu_service_libs.kafka_client.KafkaBus` for Kafka with circuit breakers
- **MUST** use `huleedu_service_libs.redis_client.RedisClient` for Redis with lifecycle management
- **MUST** use `huleedu_service_libs.logging_utils` for structured logging
- **MUST** use `huleedu_service_libs.error_handling` for all exceptions
- **MUST** use `@idempotent_consumer` decorator for ALL Kafka consumers
- **MUST** integrate database monitoring for PostgreSQL services

### 4.3. Circuit Breaker Standards
```python
# MUST wrap external dependencies with circuit breakers
@provide(scope=Scope.APP)
def provide_external_client(
    settings: Settings,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> ExternalClientProtocol:
    base_client = ExternalClientImpl(settings)
    if settings.CIRCUIT_BREAKER_ENABLED:
        breaker = circuit_breaker_registry.get("external_client")
        return CircuitBreakerExternalClient(base_client, breaker)
    return base_client
```

### 4.4. Repository Selection Standards
- **Pattern**: `USE_MOCK_REPOSITORY` flag for development/testing environments
- **Testing**: Always use mock repositories regardless of USE_MOCK_REPOSITORY flag
- **Development**: Mock repositories simulate production behavior (atomic operations, TTL)

### 4.5. Database Integration
```python
# Database monitoring + health checking (startup_setup.py)
db_metrics = setup_database_monitoring(engine, "service_name")
app.extensions["db_metrics"] = db_metrics
app.health_checker = DatabaseHealthChecker(engine, "service_name")
app.database_engine = database_engine  # REQUIRED HuleEduApp attribute
```

### 4.6. Kafka Consumer Integration
```python
# Idempotent consumers with Redis deduplication
@idempotent_consumer(redis_client=redis_client, config=idempotency_config)
async def handle_message(msg: ConsumerRecord):
    # Automatically prevents duplicate processing
    pass

# Background task startup (startup_setup.py)
consumer_task = asyncio.create_task(kafka_consumer.start_consumer())
app.consumer_task = consumer_task  # Optional HuleEduApp attribute
```

### 4.7. App Extensions Pattern
```python
# Standard extension storage in app.extensions dict
app.extensions["metrics"] = metrics
app.extensions["tracer"] = tracer  
app.extensions["relay_worker"] = relay_worker
app.extensions["queue_processor"] = queue_processor  # LLM Provider
app.extensions["dishka_container"] = container  # Alternative storage
```

### 4.8. Outbox Pattern Integration
```python
# EventRelayWorker startup (startup_setup.py) 
relay_worker = await request_container.get(EventRelayWorker)
await relay_worker.start()
app.extensions["relay_worker"] = relay_worker

# Transactional outbox for reliable event publishing
# Shared DB session ensures atomicity with domain operations
```

### 4.9. Observability Middleware Setup
```python  
# Metrics middleware (startup_setup.py)
setup_standard_service_metrics_middleware(app, "service_abbreviation")

# Distributed tracing (startup_setup.py)
tracer = init_tracing("service_name")
app.extensions["tracer"] = tracer
setup_tracing_middleware(app, tracer)
```

### 4.10. Error Handler Patterns
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

### 4.11. Alembic Migration Standards
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

### 4.12. Lifecycle Management
```python
# Startup pattern (app.py)
@app.before_serving
async def startup() -> None:
    await initialize_services(app, settings)
    setup_standard_service_metrics_middleware(app, "abbrev")
    
@app.after_serving
async def shutdown() -> None:
    await shutdown_services()
```

### 4.13. Production Patterns
- **MUST** implement graceful shutdown with proper async resource cleanup
- **MUST** use DI-managed `aiohttp.ClientSession` with configured timeouts  
- **MUST** use manual Kafka commits with error boundaries (no auto-commit)
- **MUST** fail fast on startup errors with `logger.critical()` and `raise`

## 5. Service Types

### 5.1. HTTP Services → [041](mdc:041-http-service-blueprint.mdc)
- HuleEduApp with Blueprint pattern
- `/health` and `/metrics` endpoints mandatory
- `database_engine` and `container` are REQUIRED attributes

### 5.2. Worker Services → [042](mdc:042-async-patterns-and-di.mdc)
- Event processor pattern with background Kafka consumer
- Same DI, error handling, and observability patterns as HTTP services

### 5.3. Hybrid Services
- Combined HTTP + Worker (e.g., CJ Assessment, Essay Lifecycle)
- Single `startup_setup.py` manages both lifecycles
- Shared metrics registry prevents collisions

## 6. Implementation Checklist
- [ ] HuleEduApp with `startup_setup.py` initialization
- [ ] SecureServiceSettings inheritance → [047](mdc:047-security-configuration-standards.mdc)
- [ ] Error handling with HuleEduError factories → [048](mdc:048-structured-error-handling-standards.mdc)
- [ ] Circuit breakers for external dependencies
- [ ] Repository selection with `USE_MOCK_REPOSITORY` support
- [ ] Database monitoring + health checking integration
- [ ] `@idempotent_consumer` for all Kafka consumers
- [ ] Outbox pattern with EventRelayWorker
- [ ] Metrics class + observability middleware → [071.1](mdc:071.1-prometheus-metrics-patterns.mdc)
- [ ] Alembic migration setup for PostgreSQL services
- [ ] Docker multi-stage builds → [087](mdc:087-docker-development-container-patterns.mdc)
