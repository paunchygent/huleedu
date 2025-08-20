# Batch Conductor Service (BCS)

## Overview **Internal pipeline dependency resolution and intelligent pipeline generation**

The Batch Conductor Service (BCS) is an internal Quart-based microservice responsible for analyzing batch states and resolving pipeline dependencies. It provides intelligent pipeline construction based on essay lifecycle states and processing requirements.

## Implementation Status ✅ **FULLY IMPLEMENTED**

**Phase 2 & 2B Complete**: BCS is production-ready with event-driven architecture, atomic Redis operations, comprehensive testing (24/24 tests passing), and full BOS integration via HTTP API.

## Architecture

- **Framework**: Quart + Hypercorn (internal service consistency)
- **Communication**: Internal HTTP API for BOS integration
- **Event-Driven**: Real-time batch state projection via Kafka events (spellcheck/CJ assessment completion)
- **Persistence**: Redis-cached state management with atomic WATCH/MULTI/EXEC operations
- **Port**: 4002 (internal only)

## Key Responsibilities

1. **Pipeline Dependency Resolution**: Intelligent dependency analysis with prerequisite validation
2. **Event-Driven State Projection**: Real-time batch state tracking via Kafka event consumption
3. **Atomic State Management**: Race condition-safe Redis operations with exponential backoff retry
4. **Error Isolation**: DLQ production for pipeline resolution failures with comprehensive metadata
5. **Observability**: Prometheus metrics for pipeline resolution success/failure rates

## Core Features ✅ **IMPLEMENTED**

### Event-Driven Architecture

- **Spellcheck Completion**: Consumes `SpellcheckPhaseCompletedV1` thin events for state tracking
- **CJ Assessment Completion**: Consumes completion events from CJ assessment service  
- Maintains real-time batch/phase state via Redis + PostgreSQL persistence
- Publishes `PhaseSkippedV1` events for pruned phases

### Intelligent Pipeline Resolution & Phase Pruning

- **Dynamic Phase Pruning**: Removes already-completed phases from pipelines
- **Cross-Pipeline Optimization**: Tracks completions across multiple pipeline runs
- **Cache Persistence**: Redis cache persists across pipeline completions (7-day TTL) for cross-pipeline pruning
- **Phase Skipped Events**: Publishes events for observability when phases are pruned
- **Dependency Rules**: ai_feedback/cj_assessment → requires spellcheck

### Production Resilience

- Atomic Redis operations with WATCH/MULTI/EXEC pattern
- DLQ production for failed pipeline resolutions with replay capability
- Exponential backoff retry logic (up to 5 attempts)
- Graceful fallback to non-atomic operations when retries exhausted

### Comprehensive Testing

- 24/24 tests passing including boundary testing, event processing, API validation
- Atomic operation testing with concurrency simulation
- Business logic validation and error scenario coverage

## API Endpoints

### Internal API

- `POST /internal/v1/pipelines/define` - Pipeline dependency resolution with request/response validation
- `GET /healthz` - Health check with JSON response format
- `GET /metrics` - Prometheus metrics including `bcs_pipeline_resolutions_total{status}`

## Service Integration ✅ **COMPLETE**

**Integration with BOS**: HTTP client integration complete with `BatchConductorClientProtocol` and implementation. BOS calls BCS internal API for pipeline resolution and stores resolved pipeline for execution.

**Event Sources**: Consumes completion events from specialized services to maintain current batch state without synchronous ELS API calls.

## Event Consumption Patterns

### Spellchecker Integration
BCS consumes **thin events** from the spellchecker service optimized for state tracking:

- **Event**: `SpellcheckPhaseCompletedV1`
- **Topic**: `huleedu.batch.spellcheck.phase.completed.v1`
- **Purpose**: Phase completion tracking for pipeline pruning (~300 bytes)
- **Handler**: `_handle_spellcheck_phase_completed()` in Kafka consumer
- **Data**: entity_id, batch_id, status, processing_duration_ms

This thin event pattern allows BCS to track phase completions efficiently for intelligent pipeline pruning without processing unnecessary business data.

## Configuration

Environment variables (prefix: `BCS_`):

### Service Configuration

- `BCS_HTTP_HOST`: Server host (default: 0.0.0.0)
- `BCS_HTTP_PORT`: Server port (default: 4002)
- `BCS_LOG_LEVEL`: Logging level (default: INFO)
- `BCS_HTTP_TIMEOUT`: HTTP client timeout (default: 30s)

### Repository Configuration

- `BCS_USE_MOCK_REPOSITORY`: Use mock repository for development/testing (default: false)
- `BCS_ENVIRONMENT`: Environment type - testing/development/production (default: development)

### Infrastructure Configuration

- `BCS_KAFKA_BOOTSTRAP_SERVERS`: Kafka connection (default: kafka:9092)
- `BCS_REDIS_URL`: Redis connection for state caching (default: redis://localhost:6379)
- `BCS_REDIS_TTL_SECONDS`: Redis TTL for essay state (default: 604800 - 7 days)

### Development Mode

Set `BCS_USE_MOCK_REPOSITORY=true` to run without Redis infrastructure. Mock repository simulates atomic operations and TTL behavior for local development.

### Production Mode

Default configuration uses Redis-first state management with atomic WATCH/MULTI/EXEC operations for race condition safety.

## Pipeline Rules Engine

### Dependency Resolution

- `ai_feedback` → requires `spellcheck` completion
- `cj_assessment` → requires `spellcheck` completion  
- `spellcheck` → no dependencies (can run immediately)

### Phase Pruning Examples

- NLP pipeline runs: `[spellcheck, nlp]`
- Subsequent CJ pipeline: `[cj_assessment]` (spellcheck pruned)
- Result: ~50% reduction in redundant processing

## Development

### Requirements

- Python 3.11+
- PDM for dependency management
- Docker for containerization
- Redis for state caching (not required with USE_MOCK_REPOSITORY=true)
- Kafka for event consumption

### Local Development

```bash
# Install dependencies
pdm install

# Run service locally (from monorepo root)
pdm run dev-bcs

# Run tests (29/29 passing)
pdm run pytest services/batch_conductor_service/ -v

# Lint and format
pdm run lint-all
pdm run format-all
```

### Docker

```bash
# Build image
docker build -t huleedu/batch-conductor-service .

# Run container
docker run -p 4002:4002 huleedu/batch-conductor-service
```

## Monitoring & Observability

### Prometheus Metrics

- `bcs_pipeline_resolutions_total{status="success"|"failure"}`: Pipeline resolution outcomes
- Standard HTTP request metrics via service library integration
- Health check availability via `/healthz` endpoint

### Structured Logging

- Correlation ID tracking across requests and events
- Event processing lifecycle logging
- Error boundary logging with context preservation
- DLQ production logging with failure reasons

### Error Handling

- DLQ topics: `<base_topic>.DLQ` pattern for replay capability
- Comprehensive error metadata in DLQ messages
- Circuit breaker patterns for external dependency failures

---

**Status**: ✅ **PRODUCTION READY** - All implementation phases complete with comprehensive testing and BOS integration validated through E2E tests
