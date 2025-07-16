---
inclusion: always
---

# Architectural Standards

## Service Implementation Requirements

### MANDATORY Service Structure
Every service MUST follow this structure:
```
service_name/
├── app.py              # HTTP service entry point
├── worker.py           # Kafka worker entry point (if applicable)
├── config.py           # Pydantic BaseSettings configuration
├── protocols.py        # Protocol interfaces (abstractions)
├── di.py              # Dependency injection container
├── startup_setup.py    # Service initialization
├── api/               # HTTP endpoints (if applicable)
├── implementations/   # Concrete implementations
└── tests/            # Comprehensive test suite
```

### Service Library Compliance (ZERO TOLERANCE)
- **FORBIDDEN**: `import logging` or `from logging import`
- **MUST**: Use `huleedu_service_libs.logging_utils` for all logging
- **FORBIDDEN**: Direct `aiokafka` imports
- **MUST**: Use service library's `KafkaBus` class for Kafka operations
- **MUST**: Declare `huleedu-service-libs` in `pyproject.toml`

### Dependency Injection Patterns
- All business logic depends on protocols (abstractions) in `protocols.py`
- Concrete implementations in `implementations/` directory
- DI container configuration in `di.py` using Dishka
- Protocol-based testing with mock implementations

### Event-Driven Communication
- All events use `EventEnvelope` wrapper from `common_core`
- Event data models are versioned Pydantic models in `common_core`
- Deterministic event ID generation based on business data only
- Idempotency handling with Redis-based deduplication

### Error Handling Standards
- Structured error responses with correlation IDs
- Circuit breaker patterns for external service calls
- Graceful degradation and fallback mechanisms
- Comprehensive logging with context preservation

### Observability Requirements
- Prometheus metrics endpoints (`/metrics`)
- Health check endpoints (`/healthz`) with dependency checks
- Distributed tracing with correlation ID propagation
- Structured logging with JSON format for production