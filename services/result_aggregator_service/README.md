# Result Aggregator Service

## Service Identity
- **Port**: 4003 (API), 9096 (metrics)
- **Purpose**: Materialized view layer for aggregated results
- **Pattern**: CQRS - write via Kafka, read via REST API
- **Stack**: HuleEduApp, PostgreSQL, Kafka consumer, Redis cache

## Architecture

```
app.py                  # HuleEduApp + Kafka consumer setup
api/
  health_routes.py      # /healthz, /metrics
  batch_routes.py       # Batch query endpoints
worker_main.py         # Kafka consumer entry point
event_processor.py     # Message processing logic
protocols.py           # BatchRepositoryProtocol, CacheManagerProtocol
di.py                  # Dishka providers
models_db.py          # SQLAlchemy models
```

## API Endpoints

**Base**: `/internal/v1` (requires `X-Internal-API-Key`, `X-Service-ID`)

- `GET /batches/{batch_id}/status`: Comprehensive batch status
- `GET /batches/user/{user_id}`: User's batches with pagination

## Database Schema

- `batch_results`: Batch-level aggregation
- `essay_results`: Essay-level results per phase
- Optimized indexes: (user_id, batch_id), status fields

## Kafka Consumer

**Subscribes to**:
- `huleedu.els.batch.registered.v1`: Creates initial batch
- `huleedu.els.batch.phase.outcome.v1`: Phase completions
- `huleedu.essay.spellcheck.completed.v1`: Spell check results
- `huleedu.cj_assessment.completed.v1`: CJ rankings

**Features**:
- Redis idempotency
- DLQ support
- Manual commit pattern

## Cache Strategy

**Redis Cache**:
- 5-minute TTL
- SET-based tracking: `ras:user:{user_id}:cache_keys`
- Atomic invalidation on updates
- Fail-open pattern

## Key Patterns

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

✅ Production ready with:
- Type-safe HuleEduApp contract
- Resilient Kafka consumer
- Active cache invalidation
- 78/78 tests passing
- 0 MyPy errors