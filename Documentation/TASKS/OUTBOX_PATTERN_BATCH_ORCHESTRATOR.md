# Outbox Pattern Implementation for Batch Orchestrator Service

## Overview
This document provides a comprehensive guide for implementing the Transactional Outbox Pattern in Batch Orchestrator Service, based on the patterns established in File Service and Essay Lifecycle Service.

## Pattern Analysis

### Shared Outbox Library Components
The shared library (`libs/huleedu_service_libs/src/huleedu_service_libs/outbox/`) provides:
- `OutboxRepositoryProtocol`: Interface for outbox storage operations
- `EventOutbox`: SQLAlchemy model for the event_outbox table
- `PostgreSQLOutboxRepository`: Default PostgreSQL implementation
- `EventRelayWorker`: Background worker that polls and publishes events
- `OutboxProvider`: Dishka provider for dependency injection
- `OutboxMetrics`: Prometheus metrics for monitoring

### Implementation Patterns Discovered

#### 1. Database Migration Pattern
Both services create similar migrations with slight variations:

**File Service Pattern**:
```python
# Uses standard SQLAlchemy column definitions
sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)
# No default value for ID
```

**Essay Lifecycle Service Pattern**:
```python
# Uses gen_random_uuid() for ID generation
sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, 
          server_default=sa.text("gen_random_uuid()"))
```

**Common elements**:
- Table name: `event_outbox`
- Columns: id, aggregate_id, aggregate_type, event_type, event_data, event_key, created_at, published_at, retry_count, last_error
- Three indexes:
  - `ix_event_outbox_unpublished`: Partial index for polling unpublished events
  - `ix_event_outbox_aggregate`: For aggregate lookups
  - `ix_event_outbox_event_type`: For monitoring/debugging

#### 2. Event Publisher Modification Pattern

**Common Pattern**:
1. Inject `OutboxRepositoryProtocol` into event publisher constructor
2. Create EventEnvelope with all required data
3. Use `model_dump(mode="json")` for proper UUID/datetime serialization
4. Store entire envelope in outbox with topic information
5. Maintain existing Redis publishing for real-time updates (if applicable)

**File Service Implementation**:
```python
# Direct implementation in each publish method
await self.outbox_repository.add_event(
    aggregate_id=event_data.file_upload_id,
    aggregate_type="file_upload",
    event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
    event_data=envelope.model_dump(mode="json"),
    topic=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
    event_key=event_data.file_upload_id,
)
```

**Essay Lifecycle Service Implementation**:
```python
# Centralized publish_to_outbox method
async def publish_to_outbox(self, aggregate_type: str, aggregate_id: str, 
                          event_type: str, event_data: Any, topic: str) -> None:
    serialized_data = event_data.model_dump(mode="json")
    serialized_data["topic"] = topic
    # ... implementation
```

#### 3. DI Configuration Pattern

Both services follow similar patterns:
1. Provide `OutboxSettings` with custom configuration
2. Add `OutboxProvider` to the DI container
3. Inject `OutboxRepositoryProtocol` into event publishers

**File Service**:
```python
@provide(scope=Scope.APP)
def provide_outbox_settings(self, settings: Settings) -> OutboxSettings:
    return OutboxSettings(
        poll_interval_seconds=settings.OUTBOX_POLL_INTERVAL_SECONDS,
        batch_size=settings.OUTBOX_BATCH_SIZE,
        max_retries=settings.OUTBOX_MAX_RETRIES,
        error_retry_interval_seconds=settings.OUTBOX_ERROR_RETRY_INTERVAL_SECONDS,
        enable_metrics=True,
    )
```

#### 4. Worker Startup Pattern

**File Service**: Starts EventRelayWorker in API startup
```python
# In startup_setup.py
async with container() as request_container:
    relay_worker = await request_container.get(EventRelayWorker)
    await relay_worker.start()
    app.extensions["relay_worker"] = relay_worker
```

**Essay Lifecycle Service**: Starts EventRelayWorker in worker process
```python
# In worker_main.py
event_relay_worker = await request_container.get(EventRelayWorker)
# Started as part of worker lifecycle
```

## Implementation Plan for Batch Orchestrator Service

### 1. Create Alembic Migration
File: `services/batch_orchestrator_service/alembic/versions/YYYYMMDD_0001_add_event_outbox_table.py`

Follow the File Service pattern but use `gen_random_uuid()` for ID generation (ELS pattern):
- Create event_outbox table with all standard columns
- Add the three standard indexes
- Include proper comments for each column

### 2. Update Service Configuration
File: `services/batch_orchestrator_service/config.py`

Add outbox configuration settings:
```python
# Outbox Pattern Settings
OUTBOX_POLL_INTERVAL_SECONDS: float = 5.0
OUTBOX_BATCH_SIZE: int = 100
OUTBOX_MAX_RETRIES: int = 5
OUTBOX_ERROR_RETRY_INTERVAL_SECONDS: float = 30.0
```

### 3. Modify Event Publisher
File: `services/batch_orchestrator_service/implementations/batch_event_publisher.py`

Pattern to follow:
1. Add `outbox_repository: OutboxRepositoryProtocol` to constructor
2. Replace direct Kafka publishing with outbox storage
3. Use centralized `publish_to_outbox` method (ELS pattern)
4. Ensure proper error handling with structured errors

### 4. Update DI Configuration
File: `services/batch_orchestrator_service/di.py`

1. Import `OutboxProvider` from shared library
2. Add custom `OutboxSettings` provider
3. Update event publisher provider to inject `OutboxRepositoryProtocol`
4. Add `OutboxProvider()` to container creation

### 5. Configure Worker Startup
Since Batch Orchestrator Service runs as a worker (similar to ELS), follow the ELS pattern:
- Start EventRelayWorker in the worker's main process
- Ensure graceful shutdown handling

### 6. Create Integration Tests
Follow the test patterns from File Service:
- Test outbox repository integration
- Test event relay worker functionality
- Test failure scenarios and recovery
- Test metrics collection

### 7. Testing Strategy
1. Unit tests for modified event publisher
2. Integration tests for outbox pattern
3. End-to-end tests verifying event flow
4. Performance tests for relay worker

## Key Considerations

### Transaction Boundaries
- Ensure event storage happens within the same transaction as business operations
- Use shared session when available (repository pattern)

### Error Handling
- Use structured error handling (`raise_kafka_publish_error`, `raise_external_service_error`)
- Maintain correlation IDs throughout
- Log with appropriate context

### Monitoring
- Prometheus metrics are automatically collected by the shared library
- Monitor queue depth, publish rates, and errors
- Set up alerts for failed events exceeding max retries

### Migration Path
- The outbox pattern is backward compatible
- Existing event consumers don't need changes
- Can be deployed without downstream impacts

## Implementation Checklist

- [ ] Create event_outbox migration file
- [ ] Add outbox configuration to Settings
- [ ] Modify DefaultBatchEventPublisherImpl:
  - [ ] Add OutboxRepositoryProtocol dependency
  - [ ] Implement publish_to_outbox method
  - [ ] Update publish_spellcheck_phase_initiated
  - [ ] Update publish_nlp_phase_initiated
  - [ ] Update publish_cj_assessment_phase_initiated
  - [ ] Update publish_ai_feedback_phase_initiated
  - [ ] Update publish_batch_processing_completed
  - [ ] Update publish_batch_processing_failed
- [ ] Update DI configuration:
  - [ ] Add OutboxProvider
  - [ ] Add OutboxSettings provider
  - [ ] Update event publisher provider
- [ ] Configure EventRelayWorker startup in worker
- [ ] Implement graceful shutdown
- [ ] Create integration tests
- [ ] Update service documentation
- [ ] Test migration and rollback procedures

## Success Criteria
1. All events are stored in outbox before being published
2. Events are reliably delivered even if Kafka is temporarily unavailable
3. Failed events are retried with exponential backoff
4. Metrics provide visibility into outbox operations
5. No events are lost during service restarts
6. Performance impact is minimal (< 5ms per event)