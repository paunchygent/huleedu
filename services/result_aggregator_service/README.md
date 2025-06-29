# Result Aggregator Service

The Result Aggregator Service acts as a materialized view layer for the HuleEdu platform, consuming completion events from processing services and providing fast, query-optimized access to aggregated results for the API Gateway.

## Overview

This service implements a CQRS (Command Query Responsibility Segregation) pattern where:

- **Write operations** occur via Kafka event consumption
- **Read operations** occur via internal REST API queries

The service maintains a normalized PostgreSQL database that aggregates results from:

- Essay Lifecycle Service (batch phase outcomes)
- Spell Checker Service (correction results)
- CJ Assessment Service (ranking and scores)
- Future services (NLP, AI Feedback) with placeholders

## Architecture

### Service Type

- **Hybrid**: Kafka consumer + HTTP API service
- **Pattern**: Event sourcing with materialized views
- **Database**: PostgreSQL with normalized schema
- **Cache**: Redis for query optimization

### Key Components

1. **Kafka Consumer**
   - Subscribes to completion events from all processing services
   - Implements idempotency via Redis
   - Includes DLQ (Dead Letter Queue) support
   - Manual commit pattern for reliability

2. **Internal API**
   - Provides `/internal/v1/batches/{batch_id}/status` endpoint
   - Service-to-service authentication via API keys
   - Includes user_id for API Gateway security checks
   - Prometheus metrics on separate port

3. **Database Schema**
   - `batch_results` table: Batch-level aggregation
   - `essay_results` table: Essay-level results per phase
   - Optimized indexes for common query patterns
   - Support for future service integration

## API Endpoints

### Health & Metrics

- `GET /healthz` - Health check endpoint
- `GET /metrics` - Prometheus metrics (port 9096)

### Internal Query API

- `GET /internal/v1/batches/{batch_id}/status` - Get comprehensive batch status
- `GET /internal/v1/batches/user/{user_id}` - Get all batches for a user

### Authentication

All internal API requests require:

- `X-Internal-API-Key` header
- `X-Service-ID` header
- `X-Correlation-ID` header (optional but recommended)

## Configuration

Key environment variables:

```bash
# Service configuration
SERVICE_NAME=result-aggregator-service
HOST=0.0.0.0
PORT=4003
METRICS_PORT=9096

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/result_aggregator

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP_ID=result-aggregator-group

# Redis
REDIS_URL=redis://localhost:6379

# Security
INTERNAL_API_KEY=your-secret-key
ALLOWED_SERVICE_IDS=["api-gateway-service", "admin-dashboard-service"]
```

## Development

### Import Pattern

**CRITICAL**: This service uses full module paths for ALL imports to avoid conflicts with other services:

```python
# CORRECT - Always use full paths
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.protocols import BatchRepositoryProtocol
from services.result_aggregator_service.di import ServiceProvider

# WRONG - Will cause import errors
from metrics import ResultAggregatorMetrics
from protocols import BatchRepositoryProtocol
from di import ServiceProvider
```

This is necessary because all service directories are in PYTHONPATH in both Docker and test environments. See `.cursor/rules/055-import-resolution-patterns.mdc` for details.

### Running Locally

```bash
# From monorepo root
pdm run -p services/result_aggregator_service dev

# Or run both HTTP and Kafka consumer
pdm run -p services/result_aggregator_service start
```

### Running Tests

```bash
# Unit tests
pdm run -p services/result_aggregator_service test-unit

# Integration tests
pdm run -p services/result_aggregator_service test-integration
```

### Docker

```bash
# Build and run with docker-compose
pdm run dc-build result_aggregator_service
pdm run dc-up result_aggregator_service

# View logs
pdm run dc-logs-service result_aggregator_service
```

## Database Migrations

The service automatically creates tables on startup. For production deployments, use Alembic migrations (to be implemented).

## Monitoring

### Metrics

The service exposes Prometheus metrics on port 9096:

- `ras_api_requests_total` - API request count
- `ras_api_request_duration_seconds` - Request latency
- `ras_messages_processed_total` - Kafka messages processed
- `ras_invalid_messages_total` - Invalid/malformed messages by topic and error type
- `ras_cache_hits_total` / `ras_cache_misses_total` - Cache performance
- `ras_consumer_errors_total` - Consumer error count

### Logging

Structured logging with correlation IDs for request tracing.

## Integration Points

### Consumes Events From

- Essay Lifecycle Service: `huleedu.els.batch.phase.outcome.v1`
- Spell Checker Service: `huleedu.essay.spellcheck.completed.v1`
- CJ Assessment Service: `huleedu.cj_assessment.completed.v1`

### Consumed By

- API Gateway Service (primary consumer)
- Future: Admin Dashboard Service

## Security Considerations

1. **Internal API**: Service-to-service authentication only
2. **User Isolation**: All queries include user_id for ownership verification
3. **No Direct External Access**: Only accessible via API Gateway
4. **Audit Trail**: All operations logged with correlation IDs

## Performance Optimization

1. **Database**:
   - Composite indexes on (user_id, batch_id)
   - Separate indexes on status fields
   - Connection pooling configured

2. **Caching**:
   - Redis cache with 5-minute TTL
   - Cache invalidation on updates
   - Fail-open strategy (serves stale on cache failure)

3. **Event Processing**:
   - Batch processing for efficiency
   - Async I/O throughout
   - Configurable consumer batch size

## Implementation Status

### Completed Features

- ✅ Kafka consumer with idempotency
- ✅ Event processing for all current services
- ✅ Batch registration event handling (creates initial batch records)
- ✅ PostgreSQL repository implementation with common_core enums
- ✅ Redis state store and caching with proper JSON abstraction
- ✅ Internal API with service-to-service authentication
- ✅ Prometheus metrics for all operations
- ✅ Docker configuration for deployment

### Recent Improvements

1. **Batch Creation**: Now subscribes to `BatchEssaysRegistered` events to create initial records
2. **Enum Alignment**: Uses `BatchStatus` and `ProcessingStage` from common_core
3. **Cache Abstraction**: Properly encapsulated caching with JSON string protocol
4. **Error Handling**: Production-resilient Kafka consumer with poison pill storage and metrics
5. **Active Cache Invalidation**: Redis SET-based tracking for immediate cache consistency
6. **Test Organization**: Split test files following <400 LOC rule for maintainability

### Completed Major Enhancements

1. **Kafka Consumer Resilience** (CONSOLIDATION_TASK refactor):
   - Production-grade error handling with graceful degradation
   - Poison pill detection and storage in Redis for inspection
   - Comprehensive metrics for invalid messages by topic and error type
   - Test-configurable behavior via `RAISE_ON_DESERIALIZATION_ERROR` flag
   - Fixed integration tests to validate resilient behavior instead of expecting failures

2. **Active Cache Invalidation** (CONSOLIDATION_TASK_2):
   - Redis SET-based tracking system for user cache keys
   - Atomic cache operations using Redis pipelines
   - Immediate invalidation on `BatchEssaysRegistered` events
   - Performance-optimized (no KEYS/SCAN operations)
   - Proper TTL management for tracking sets

### Known Limitations

- Database migrations not yet implemented (uses auto-create for now)

## Future Enhancements

1. **Additional Event Sources**:
   - NLP Analysis results
   - AI Feedback results
   - Student parsing events

2. **Enhanced Queries**:
   - Batch comparison endpoints
   - Aggregate statistics by time period
   - Export functionality

3. **Performance**:
   - Materialized views for complex queries
   - Event replay capability
   - Horizontal scaling support
