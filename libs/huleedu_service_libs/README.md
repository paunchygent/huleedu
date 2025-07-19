# HuleEdu Service Libraries

A comprehensive collection of shared utilities and infrastructure components for HuleEdu microservices, providing consistent patterns for distributed system concerns including event-driven communication, observability, resilience, and data persistence.

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
├── idempotency_v2.py        # Advanced idempotent message processing
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
    "-e file:///${PROJECT_ROOT}/libs/huleedu_service_libs",
    # ... other dependencies
]
```

## Documentation Structure

This library documentation is organized into focused areas for better navigation and maintainability. Each document adheres to the <400 line architectural standard:

### Core Infrastructure
- **[Kafka & Redis](docs/kafka-redis.md)** - Event publishing and distributed caching patterns
- **[Database Utilities](docs/database.md)** - PostgreSQL monitoring, health checks, and metrics
- **[Error Handling](docs/error-handling.md)** - Structured error handling with framework separation

### Observability & Reliability
- **[Observability](docs/observability.md)** - Logging, tracing, and metrics collection
- **[Resilience Patterns](docs/resilience.md)** - Circuit breakers and fault tolerance
- **[Idempotency](docs/idempotency.md)** - Advanced message processing patterns

### Application Framework
- **[Type-Safe Quart App](docs/quart-app.md)** - Type-safe Quart application patterns
- **[Integration Patterns](docs/integration-patterns.md)** - Service setup and DI patterns
- **[Testing Guidelines](docs/testing.md)** - Protocol-based mocking and test patterns
- **[Migration Guide](docs/migration-guide.md)** - Upgrading from legacy patterns

## Quick Start

### Basic Service Integration

```python
# In your service's di.py
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
        redis_client = RedisClient(client_id=f"{settings.SERVICE_NAME}-redis")
        await redis_client.start()
        return redis_client
```

### Error Handling Setup

```python
# FastAPI services
from huleedu_service_libs.error_handling.fastapi import register_error_handlers
app = FastAPI()
register_error_handlers(app)

# Quart services  
from huleedu_service_libs.error_handling.quart import register_error_handlers
app = Quart(__name__)
register_error_handlers(app)

# Use core error factories (framework-agnostic)
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
    raise_authentication_error
)
```

### Idempotent Event Processing

```python
from huleedu_service_libs.idempotency_v2 import idempotent_consumer_v2, IdempotencyConfig

config = IdempotencyConfig(
    service_name="your-service-name",
    enable_debug_logging=True
)

@idempotent_consumer_v2(redis_client=redis_client, config=config)
async def handle_event(msg: ConsumerRecord) -> None:
    envelope = EventEnvelope.model_validate_json(msg.value)
    # Process event - guaranteed to run only once per unique event
    await process_event(envelope.data)
```

## Import Patterns

### WORKING Patterns (use these)

```python
# Core exception and utilities
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.error_handling.error_detail_factory import create_error_detail_with_context

# Framework-specific handlers (explicit)
from huleedu_service_libs.error_handling.fastapi import register_error_handlers  # FastAPI
from huleedu_service_libs.error_handling.quart import register_error_handlers    # Quart

# Generic error factories (these work from main module)
from huleedu_service_libs.error_handling import (
    raise_validation_error,
    raise_resource_not_found,
    raise_authentication_error,
    raise_authorization_error
)

# Infrastructure clients
from huleedu_service_libs import KafkaBus, RedisClient, HuleEduApp
```

### BROKEN Patterns (avoid these)

```python
# ❌ These imports will fail in container environments
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling import create_error_detail_with_context

# ❌ Mixed framework imports cause dependency issues
from huleedu_service_libs.error_handling import register_error_handlers
```

## Key Protocols

All infrastructure components implement protocols for dependency injection:

```python
from huleedu_service_libs.protocols import (
    KafkaPublisherProtocol,      # Event publishing
    RedisClientProtocol,         # Redis operations
    AtomicRedisClientProtocol,   # Redis transactions
)
```

## Environment Variables

Core configuration variables used across all services:

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses (default: `"kafka:9092"`)
- `REDIS_URL`: Redis connection URL (default: `"redis://redis:6379"`)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OpenTelemetry collector endpoint (default: `"http://localhost:4317"`)
- `ENVIRONMENT`: Deployment environment (default: `"development"`)
- `SERVICE_VERSION`: Service version for tracing (default: `"1.0.0"`)

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

## Best Practices

1. **Always use lifecycle management**: Call `start()` and `stop()` on clients
2. **Use protocols for dependency injection**: Depend on protocols, not concrete classes
3. **Configure logging early**: Call `configure_service_logging()` in startup
4. **Use idempotency decorator**: Wrap all Kafka consumers with `@idempotent_consumer_v2`
5. **Add circuit breakers**: Protect external service calls with circuit breakers
6. **Propagate trace context**: Use `inject_trace_context()` and `extract_trace_context()`
7. **Monitor database health**: Use `DatabaseHealthChecker` in health endpoints
8. **Structured logging**: Always use keyword arguments for context
9. **Test with mocks**: Use `AsyncMock(spec=Protocol)` for unit tests
10. **Graceful degradation**: Design for Redis/Kafka unavailability

## Anti-Patterns to Avoid

1. **Direct client instantiation in handlers**: Use dependency injection
2. **Forgetting lifecycle management**: Always start/stop clients properly
3. **Synchronous Redis operations**: All operations are async
4. **Ignoring circuit breaker state**: Handle `CircuitBreakerError`
5. **Unstructured logging**: Avoid f-strings, use keyword arguments
6. **Missing correlation IDs**: Always propagate trace context
7. **Hardcoded configuration**: Use environment variables
8. **Skipping idempotency**: Every consumer needs idempotency protection
9. **Blocking in async code**: Use async clients throughout
10. **Ignoring metrics**: Monitor all critical operations

## Contributing

When contributing to these libraries:

1. **Follow architectural patterns**: Maintain protocol-first design
2. **Update documentation**: Keep all docs current with API changes
3. **Add tests**: Protocol-based mocking and integration tests
4. **Version compatibility**: Maintain backward compatibility where possible
5. **Import pattern validation**: Verify all examples work in container environments

For detailed implementation guides and examples, see the individual documentation files linked above.