# Result Aggregator Service

## Service Identity
- **Port**: 4003 (API), 9096 (metrics)
- **Purpose**: Event aggregation, publishing, and materialized view layer
- **Pattern**: Event aggregation with transactional outbox and notification projection
- **Stack**: HuleEduApp, PostgreSQL, Kafka consumer + publisher, Redis cache

## Architecture

```
app.py                  # HuleEduApp + Kafka consumer setup
api/
  health_routes.py      # /healthz, /metrics
  batch_routes.py       # Batch query endpoints
worker_main.py         # Kafka consumer entry point
event_processor.py     # Message processing logic
notification_projector.py # Teacher notification projections
protocols.py           # BatchRepositoryProtocol, CacheManagerProtocol
di.py                  # Dishka providers with outbox pattern
models_db.py          # SQLAlchemy models + event_outbox
```

## API Endpoints

**Base**: `/internal/v1` (requires `X-Internal-API-Key`, `X-Service-ID`)

- `GET /batches/{batch_id}/status`: Comprehensive batch status with internal `BatchStatus` enum values
- `GET /batches/user/{user_id}`: User's batches with pagination

### Status Integration

Provides detailed internal status tracking using 12-value `BatchStatus` enum. API Gateway consumes these endpoints and maps internal statuses to client-facing `BatchClientStatus` values for frontend consistency.

## Database Schema

- `batch_results`: Batch-level aggregation
- `essay_results`: Essay-level results per phase
- Optimized indexes: (user_id, batch_id), status fields

## Kafka Integration

**Subscribes to**:
- `huleedu.els.batch.registered.v1`: Creates initial batch
- `huleedu.els.batch.phase.outcome.v1`: Phase completions
- `huleedu.essay.spellcheck.completed.v1`: Spell check results
- `huleedu.cj_assessment.completed.v1`: CJ rankings

**Publishes**:
- `huleedu.batch.results.ready.v1`: All processing phases complete (HIGH priority)
- `huleedu.batch.assessment.completed.v1`: CJ assessment done (STANDARD priority)
- `huleedu.notification.teacher.requested.v1`: Via notification projector

**Features**:
- Transactional outbox pattern for reliable event publishing
- Redis idempotency with 24-hour TTL
- Direct notification projector invocation (no Kafka round-trip)
- DLQ support with manual commit pattern

## Cache Strategy

**Redis Cache**:
- 5-minute TTL
- SET-based tracking: `ras:user:{user_id}:cache_keys`
- Atomic invalidation on updates
- Fail-open pattern

## Key Patterns

**Outbox with Notification Projection**:
```python
# Canonical pattern: Store first, then direct invocation
async def publish_batch_results_ready(event, correlation_id):
    await self.outbox_manager.publish_to_outbox(...)  # Store first
    if self.notification_projector:  # Direct invocation, no Kafka round-trip
        await self.notification_projector.handle_batch_results_ready(event, correlation_id)
```

**HuleEduApp with Kafka**:
```python
app = HuleEduApp(__name__)
app.container = container
app.database_engine = engine
app.consumer_task = asyncio.create_task(kafka_consumer())
```

**Import Pattern** (CRITICAL):
```python
# ALWAYS use full paths
from services.result_aggregator_service.protocols import BatchRepositoryProtocol
# NEVER relative imports
```

**Cache Invalidation**:
```python
async def invalidate_user_batches(self, user_id: str):
    keys = await self.redis_set_ops.smembers(f"ras:user:{user_id}:cache_keys")
    async with self.redis_set_ops.pipeline() as pipe:
        for key in keys:
            pipe.delete(key)
        pipe.delete(f"ras:user:{user_id}:cache_keys")
        await pipe.execute()
```

## Configuration

Environment prefix: `RESULT_AGGREGATOR_SERVICE_`
- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_CONSUMER_GROUP_ID`
- `REDIS_URL`
- `INTERNAL_API_KEY`
- `ALLOWED_SERVICE_IDS`

## Metrics

- `ras_api_requests_total`
- `ras_api_request_duration_seconds`
- `ras_messages_processed_total`
- `ras_invalid_messages_total`
- `ras_cache_hits_total` / `ras_cache_misses_total`

## Development

```bash
# Run both HTTP + Kafka
pdm run -p services/result_aggregator_service start

# Tests
pdm run pytest services/result_aggregator_service/tests/

# Type check
pdm run mypy services/result_aggregator_service/
```

## Status

✅ Production ready with event publishing capabilities:
- Event aggregation and republishing via transactional outbox
- Teacher notification projector with direct invocation pattern
- Type-safe HuleEduApp contract with Kafka consumer + publisher
- Resilient event processing with Redis idempotency
- Active cache invalidation via Redis SETs
- 78/78 tests passing with outbox pattern validation
- 0 MyPy errors