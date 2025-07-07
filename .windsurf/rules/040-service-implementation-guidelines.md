---
description: Read before all work on web framework, I/O, API etc
globs: 
alwaysApply: false
---
# 040: Service Implementation Guidelines

## 1. Purpose
High-level, cross-cutting principles and stack requirements for HuleEdu microservice development.

Model service: `@batch_orchestrator_service/`

**Related Rules**:
- [041-http-service-blueprint.mdc](mdc:041-http-service-blueprint.mdc) - HTTP service architecture patterns
- [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc) - Async patterns, protocols, and DI
- [043-service-configuration-and-logging.mdc](mdc:043-service-configuration-and-logging.mdc) - Configuration and logging standards

## 2. Core Stack
- **Framework**: Quart for async HTTP services, direct `asyncio` and `aiokafka` for worker services.
- **Dependencies**: PDM exclusively (`pyproject.toml`, `pdm.lock`)
- **Programming**: `async/await` for all I/O operations
- **Protocols**: `typing.Protocol` for behavioral contracts and dependency abstraction
- **Dependency Injection**: Dishka framework with clean architecture patterns
- **Metrics**: Prometheus with standardized `/metrics` endpoints

## 3. Service Types Overview

### 3.1. HTTP Services (Quart-based and FastAPI-based)
- **MUST** follow Blueprint/Router pattern architecture → See [041-http-service-blueprint.mdc](mdc:041-http-service-blueprint.mdc) and [041-fastapi-integration-patterns.mdc](mdc:041-fastapi-integration-patterns.mdc)
- **MUST** implement standardized `/healthz` and `/metrics` endpoints
- **MUST** use Dishka DI with framework-specific integration (`quart-dishka` or `dishka[fastapi]`)
- **MUST** separate concerns: lean `main.py`/`app.py` + `startup_setup.py` for DI/metrics initialization
- **Pattern**: Extract DI container creation into `startup_setup.py` with functions like `create_di_container()` and `setup_dependency_injection()`

### 3.2. Worker Services (Kafka-based)
- **MUST** follow event processor pattern → See [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc)
- **Structure**: `worker_main.py`, `event_processor.py`, `core_logic.py`, `protocols.py`
- **MUST** use Dishka DI with manual container scoping

## 4. Cross-Cutting Concerns

### 4.1. Protocols and Dependency Injection
- **MUST** define behavioral contracts using `typing.Protocol` → See [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc)
- Business logic **MUST** depend on protocols, not concrete implementations
- **MUST** use Dishka DI framework with appropriate scoping

### 4.2. HTTP + Worker Metrics pattern
Services with multiple entry points (e.g., HTTP + Worker) **MUST** use a shared metrics module to ensure a single Prometheus registry instance."

### 4.2. Metrics and Monitoring
- **MUST** expose Prometheus metrics via `/metrics` endpoint
- **MUST** use centralized metrics collection patterns
- **MUST** implement service-specific health validation logic
- **MUST** use app context pattern for metrics: `app.extensions["metrics"]` (prevents registry collisions)

### 4.3. State Management
- Each service owns its primary entities' state
- State changes **MUST** be communicated via events
- Follow state transition logic from Architectural Design Blueprint

### 4.4. Configuration Management
- **MUST** use `pydantic-settings` and `enums` with standardized patterns → See [043-service-configuration-and-logging.mdc](mdc:043-service-configuration-and-logging.mdc)
- **FORBIDDEN**: Hardcoded sensitive information
- **MUST** use environment variables with service-specific prefixes

### 4.5. Logging Standards
- **MUST** use `huleedu_service_libs.logging_utils` → See [043-service-configuration-and-logging.mdc](mdc:043-service-configuration-and-logging.mdc)
- **MANDATORY**: Correlation IDs for all operation chains
- **FORBIDDEN**: Standard library `logging` module in services

### 4.6. Kafka Client Standards
- **MUST** use `huleedu_service_libs.kafka_client` utilities
- **FORBIDDEN**: Direct `AIOKafkaProducer`/`AIOKafkaConsumer` imports
- **Producers**: Use `KafkaBus` class

### 4.7. Redis Client Standards
- **MUST** use `huleedu_service_libs.redis_client` utilities
- **FORBIDDEN**: Direct `redis.asyncio.Redis` imports in service code
- **Pattern**: Use `RedisClient` class with protocol-based DI injection
- **Lifecycle**: Managed through DI container with `start()`/`stop()` methods

### 4.8. Repository Selection Standards
- **MUST** use environment-based repository selection for services with persistence
- **Pattern**: `USE_MOCK_REPOSITORY` flag for development/testing environments
- **Implementation**:
  ```python
  if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
      return MockRepositoryImpl()
  else:
      return ProductionRepositoryImpl()
  ```
- **Configuration**: `<SERVICE>_USE_MOCK_REPOSITORY` and `<SERVICE>_ENVIRONMENT` variables
- **Development**: Mock repositories simulate production behavior (atomic operations, TTL)
- **Testing**: Always use mock repositories regardless of USE_MOCK_REPOSITORY flag

### 4.9. Production Patterns (Sprint 1 Hardened)
- **MUST** implement graceful shutdown with proper async resource cleanup
- **MUST** use DI-managed `aiohttp.ClientSession` with configured timeouts
- **MUST** use manual Kafka commits with error boundaries (no auto-commit)
- **MUST** implement `/healthz` with consistent JSON response format

### 4.10. Service Library Usage Patterns
- **MUST** use service libraries for ALL infrastructure interactions:
  - `huleedu_service_libs.kafka_client` for Kafka publishing
  - `huleedu_service_libs.redis_client` for Redis operations
  - `huleedu_service_libs.logging_utils` for structured logging
  - `huleedu_service_libs.database` for PostgreSQL monitoring
- **MUST** implement lifecycle management for all clients:
  ```python
  # Always in DI providers
  client = RedisClient(client_id="service-redis")
  await client.start()  # REQUIRED before use
  # ... use client ...
  await client.stop()   # REQUIRED for cleanup
  ```
- **MUST** use `@idempotent_consumer` decorator for ALL Kafka consumers:
  ```python
  @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
  async def handle_message(msg: ConsumerRecord):
      # Automatically prevents duplicate processing
      pass
  ```
- **MUST** integrate database monitoring for PostgreSQL services:
  ```python
  # In startup_setup.py
  db_metrics = setup_database_monitoring(engine, "service_name")
  app.extensions["db_metrics"] = db_metrics
  app.health_checker = DatabaseHealthChecker(engine, "service_name")
  ```
- **MUST** wrap external dependencies with circuit breakers:
  ```python
  # In di.py
  client = ExternalServiceImpl()
  breaker = CircuitBreaker(name="external_api")
  return make_resilient(client, breaker)
  ```
- **MUST** fail fast on startup errors with `logger.critical()` and `raise`

### 4.11. Observability (Prometheus & Distributed Tracing)
- **Metrics Class**: `MUST` define all service-specific metrics in a dedicated class within `<service>/metrics.py` or `<service>/app/metrics.py`.
- **DI Provider**: `MUST` create a MetricsProvider in `<service>/di.py` to provide the metrics class and `prometheus_client.REGISTRY` with `Scope.APP`.
- **Metrics Endpoint**: `MUST` expose metrics at a `/metrics` endpoint, typically in `routers/health_routes.py`.
- **Instrumentation**: `MUST` instrument API routes by injecting the metrics class. Use `.time()` for latency and `.inc()` for counters within handlers.
- **Distributed Tracing**: `MUST` use `huleedu_service_libs.observability.tracing` utilities for OpenTelemetry integration
- **Trace Propagation**: `MUST` extract and inject trace context for all service-to-service communication (HTTP and Kafka)
- **Exception Handling**: `MUST` use proper exception handling patterns to avoid masking HTTPExceptions:
  ```python
  @inject
  async def my_handler(metrics: FromDishka[MyMetrics]):
      endpoint = "/endpoint"
      with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
          try:
              # ... business logic ...
              metrics.http_requests_total.labels(method="POST", endpoint=endpoint, http_status="200").inc()
              return result
          except HTTPException:
              raise  # CRITICAL: Re-raise HTTPException without wrapping
          except Exception as e:
              metrics.http_requests_total.labels(method="POST", endpoint=endpoint, http_status="500").inc()
              raise HTTPException(status_code=500, detail="Internal server error") from e
  ```

### 4.11. Resilience Patterns (Circuit Breakers)
- **HTTP Clients**: `MUST` wrap all service-to-service HTTP clients with circuit breakers using `huleedu_service_libs.resilience`
- **Kafka Producers**: `SHOULD` protect Kafka publishing with circuit breakers and fallback queues
- **External APIs**: `MUST` use circuit breakers for all third-party API calls (AI providers, external services)
- **Configuration**: `MUST` make circuit breaker thresholds configurable via environment variables
- **DI Integration**: `MUST` integrate circuit breakers through Dishka providers using `make_resilient()` wrapper
- **Pattern**:
  ```python
  @provide(scope=Scope.APP)
  def provide_external_client(
      settings: Settings,
      circuit_breaker_registry: CircuitBreakerRegistry,
  ) -> ExternalClientProtocol:
      base_client = ExternalClientImpl(settings)
      if settings.CIRCUIT_BREAKER_ENABLED:
          breaker = circuit_breaker_registry.get("external_client")
          return make_resilient(base_client, breaker)
      return base_client
  ```

### 4.12. PostgreSQL Database Migration Standards
Services requiring PostgreSQL persistent storage **MUST** implement the consolidated Alembic migration pattern.

**REQUIRED Infrastructure**:
- `alembic.ini` - Service-specific configuration
- `alembic/env.py` - Async SQLAlchemy environment with service configuration integration
- `alembic/versions/` - Migration files following `YYYYMMDD_NNNN_description.py` naming
- `pyproject.toml` - Must include `alembic` dependency and standardized PDM scripts

**REQUIRED Dependencies**:
```toml
dependencies = [
    "sqlalchemy[asyncio]",
    "asyncpg",
    "alembic",  # Required for all PostgreSQL services
]

[tool.pdm.scripts]
# Standardized migration commands (identical across all services)
migrate-upgrade = "alembic upgrade head"
migrate-downgrade = "alembic downgrade -1"
migrate-history = "alembic history"
migrate-current = "alembic current"
migrate-revision = "alembic revision --autogenerate"
migrate-stamp = "alembic stamp head"
```

**REQUIRED Configuration**:
- Service `config.py` **MUST** include `database_url` property for Alembic integration
- Migration environment **MUST** use async SQLAlchemy patterns
- Database URLs **MUST** be dynamically loaded from service configuration

**Implementation Reference**: See [053-sqlalchemy-standards.mdc](mdc:053-sqlalchemy-standards.mdc) for complete migration template patterns.

**Enforcement**: All new PostgreSQL services **MUST** implement this pattern from initial development. Existing services **MUST** be migrated to this pattern during next major database changes.

## 5. Implementation Checklist
Before implementing any service, ensure you have reviewed:
- [ ] This overview for core stack requirements
- [ ] [041-http-service-blueprint.mdc](mdc:041-http-service-blueprint.mdc) for HTTP service patterns
- [ ] [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc) for async patterns and DI
- [ ] [043-service-configuration-and-logging.mdc](mdc:043-service-configuration-and-logging.mdc) for config and logging
