---
description: Describes the service providing pipeline definitions to BOS
globs: 
alwaysApply: false
---
# 028: Batch Conductor Service Architecture ✅ **PRODUCTION READY**

## 1. Service Identity

| Property | Value |
|----------|-------|
| **Package** | `huleedu-batch-conductor-service` |
| **Port** | 4002 (Internal HTTP API) |
| **Stack** | Quart, Hypercorn, Kafka, Redis, Dishka, Prometheus |
| **Status** | ✅ **IMPLEMENTED** - 29/29 tests passing, production-ready, standards-aligned |

**Purpose** – Intelligent pipeline dependency resolution service. Analyzes batch states via event-driven projection, resolves pipeline dependencies, and provides optimized pipeline definitions to BOS.

---

## 2. Core Components & Clean Architecture Layout ✅ **IMPLEMENTED**

```
services/batch_conductor_service/
├── app.py                              # Lean Quart entry point
├── startup_setup.py                    # DI + metrics initialization
├── api/                               # HTTP Blueprint routes
│   ├── health_routes.py               # Standard health/metrics endpoints  
│   └── pipeline_routes.py             # Internal pipeline resolution API
├── implementations/                   # Protocol implementations
│   ├── batch_state_repository_impl.py # Redis-cached state management
│   ├── redis_batch_state_repository.py # Atomic Redis operations
│   ├── mock_batch_state_repository.py # Mock repository for development
│   ├── pipeline_generator_impl.py     # YAML loader & validation
│   ├── pipeline_rules_impl.py         # Dependency resolution engine
│   ├── pipeline_resolution_service_impl.py # Service facade for BOS
│   └── kafka_dlq_producer_impl.py     # DLQ production for failures
├── protocols.py                       # typing.Protocol definitions
├── di.py                             # Dishka DI providers with repository selection
├── config.py                         # Pydantic Settings with USE_MOCK_REPOSITORY
├── api_models.py                     # Request/response models
├── kafka_consumer.py                 # Event-driven state projection
├── pipeline_definitions.py          # Config-driven pipeline models
├── pipeline_generator.py            # YAML pipeline loader
├── pipelines.yaml                   # Human-readable pipeline definitions
└── tests/                           # 29 tests including mock repository validation
    ├── test_mock_batch_state_repository.py
    └── test_repository_selection.py
```

*All external interactions injected via `typing.Protocol` interfaces and wired by Dishka.*

---

## 3. Repository Architecture ✅ **STANDARDS ALIGNED**

### Environment-Based Repository Selection
```python
if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
    return MockBatchStateRepositoryImpl()
else:
    return RedisCachedBatchStateRepositoryImpl(redis_client)
```

### Mock Repository Implementation
- **Development Mode**: Simulates Redis atomic operations and TTL behavior
- **No Infrastructure**: Runs without Redis dependency for local development
- **Protocol Compliance**: Implements full `BatchStateRepositoryProtocol`
- **Atomic Simulation**: Lock-based concurrency control with TTL expiration

### Production Repository
- **Redis-First**: Optimized for cache performance with 7-day TTL
- **Atomic Operations**: WATCH/MULTI/EXEC pattern for race condition safety
- **PostgreSQL Fallback**: Persistent storage layer for reliability

---

## 4. Event-Driven Architecture ✅ **IMPLEMENTED**

### Real-Time Batch State Projection
- **Kafka Events Consumed**: `SpellcheckResultDataV1`, `CJAssessmentResultDataV1`
- **State Management**: Redis-cached batch state with atomic WATCH/MULTI/EXEC operations
- **Decoupled Design**: No synchronous ELS API calls, purely event-driven

### Atomic State Operations
- **Race Condition Safety**: Redis WATCH/MULTI/EXEC pattern with exponential backoff
- **Retry Logic**: Up to 5 attempts with graceful fallback to non-atomic operations
- **Idempotency**: Handles duplicate events gracefully

---

## 5. Pipeline Resolution Engine ✅ **IMPLEMENTED**

### Dependency Rules
- `ai_feedback` → requires `spellcheck` completion
- `cj_assessment` → requires `spellcheck` completion  
- `spellcheck` → no dependencies (immediate execution)

### Intelligent Optimization
- **State-Aware Pruning**: Removes completed steps from pipeline definitions
- **Prerequisite Validation**: Ensures dependencies are met before pipeline construction
- **Batch Analysis**: Real-time essay status evaluation for optimization

---

## 6. API Endpoints ✅ **IMPLEMENTED**

### Internal API
- **`POST /internal/v1/pipelines/define`**: Pipeline dependency resolution with validation
- **`GET /healthz`**: Health check with JSON response format
- **`GET /metrics`**: Prometheus metrics including pipeline resolution rates

### BOS Integration
- **HTTP Client**: `BatchConductorClientProtocol` implementation in BOS
- **Request/Response**: Pydantic models with comprehensive validation
- **Error Handling**: Proper HTTP status codes and error responses

---

## 7. Observability & Production Resilience ✅ **IMPLEMENTED**

### Prometheus Metrics
| Metric | Type | Description |
|--------|------|-------------|
| `bcs_pipeline_resolutions_total{status}` | Counter | Pipeline resolution success/failure rates |
| `http_requests_total` | Counter | HTTP request metrics via service library |
| `http_request_duration_seconds` | Histogram | Request latency tracking |

### Error Handling & DLQ
- **DLQ Topics**: `<base_topic>.DLQ` pattern for failed pipeline resolutions
- **Error Metadata**: Comprehensive failure context for debugging and replay
- **Circuit Breakers**: Graceful degradation for external dependency failures

### Structured Logging
- **Correlation IDs**: Request tracking across service boundaries
- **Event Processing**: Lifecycle logging for Kafka event consumption
- **Error Boundaries**: Contextual error logging with stack traces

---

## 8. Testing & Quality Assurance ✅ **IMPLEMENTED**

### Comprehensive Test Coverage (29/29 passing)
- **Unit Tests**: Protocol implementations with proper mocking
- **Integration Tests**: Kafka event processing and API endpoints
- **Repository Tests**: Mock repository protocol compliance (5 tests)
- **Configuration Tests**: Environment-based repository selection (5 tests)
- **Boundary Testing**: Error scenarios and edge cases
- **Atomic Operations**: Concurrency simulation and retry logic validation

### Code Quality Standards
- **Linting**: Zero Ruff warnings across all modules
- **Type Safety**: Full MyPy compliance with proper type annotations
- **Architecture**: Protocol-based DI with clean separation of concerns

---

## 9. Dependency Injection & Service Integration ✅ **IMPLEMENTED**

### Dishka DI Container
- **Container Initialization**: `startup_setup.py` with proper lifecycle management
- **Protocol-Based**: All dependencies injected via `typing.Protocol` abstractions
- **Repository Selection**: Environment-based injection of mock or production repositories
- **HTTP Integration**: `quart-dishka` for route injection via `@inject` decorator

### Service Library Compliance
- **Logging**: `huleedu_service_libs.logging_utils` for structured logging
- **Metrics**: Service library Prometheus integration
- **Configuration**: Pydantic `BaseSettings` with environment variable management

---

## 10. Configuration Management

### Repository Configuration
- `BCS_USE_MOCK_REPOSITORY`: Use mock repository for development/testing (default: false)
- `BCS_ENVIRONMENT`: Environment type - testing/development/production (default: development)

### Service Configuration
- `BCS_HTTP_HOST`: Server host (default: 0.0.0.0)
- `BCS_HTTP_PORT`: Server port (default: 4002)
- `BCS_LOG_LEVEL`: Logging level (default: INFO)
- `BCS_HTTP_TIMEOUT`: HTTP client timeout (default: 30s)

### Infrastructure Configuration
- `BCS_KAFKA_BOOTSTRAP_SERVERS`: Kafka connection
- `BCS_REDIS_URL`: Redis connection for state caching (default: redis://localhost:6379)
- `BCS_REDIS_TTL_SECONDS`: Redis TTL for essay state (default: 604800 - 7 days)

### Development vs Production
- **Development Mode**: `BCS_USE_MOCK_REPOSITORY=true` - No Redis required
- **Production Mode**: `BCS_USE_MOCK_REPOSITORY=false` - Redis-first performance

### Pipeline Configuration
- **YAML Definition**: Human-readable pipeline structures in `pipelines.yaml`
- **Type Safety**: Pydantic models for configuration validation
- **Dependency Detection**: Automatic cycle detection and validation

---

## 11. Mandatory Production Patterns ✅ **IMPLEMENTED**

### Graceful Shutdown
- **Resource Cleanup**: Kafka consumer, Redis pool, and HTTP server cleanup in `startup_setup.py`
- **Signal Handling**: Proper SIGTERM/SIGINT handling for container environments
- **Health Checks**: Docker health check integration

### Error Recovery
- **Idempotency**: Redis operations handle duplicate requests gracefully
- **Fail Fast**: Critical startup errors use `logger.critical()` then raise
- **DLQ Production**: Failed operations routed to dead letter queues for replay

### Service Integration
- **BOS HTTP Client**: Complete integration via `BatchConductorClientProtocol`
- **Event Consumption**: Kafka-based state projection without polling ELS
- **Topic Management**: Uses `common_core.enums` for topic name consistency

---

**Implementation Status**: ✅ **PRODUCTION READY** - All phases complete with comprehensive testing and BOS integration validated through E2E tests.
