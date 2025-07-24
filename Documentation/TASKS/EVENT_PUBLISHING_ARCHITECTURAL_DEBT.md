# Event Publishing Architectural Debt Analysis

## Executive Summary

The current HuleEdu platform has a critical architectural issue: event publishing is in the synchronous critical path of business operations. When Kafka is unavailable, business operations fail entirely, leaving the system in an inconsistent state.

## Current Architecture (Problem)

```
Business Operation → Database Transaction → Event Publishing → Response
                                               ↓
                                          Kafka Failure
                                               ↓
                                      ENTIRE OPERATION FAILS
```

### Evidence from Code

From `test_content_provisioned_handling_with_publishing_failures` test:
```python
# Configure Kafka to fail
mock_kafka_bus.send_and_wait.side_effect = Exception("Kafka unavailable")

# This reveals the architectural debt - if Kafka fails, the operation fails
with pytest.raises(Exception, match="Kafka unavailable"):
    await handler.handle_essay_content_provisioned(content_event, correlation_id)
```

## Impact Analysis

### 1. **Availability Risk**
- Kafka outages directly impact business operations
- Users cannot upload files when event streaming is down
- Assessment processing halts during Kafka maintenance

### 2. **Data Consistency Issues**
- Partial state updates when event publishing fails mid-transaction
- Database shows success but downstream services never notified
- Manual intervention required to reconcile state

### 3. **Performance Coupling**
- Business operations wait for Kafka acknowledgment
- Network latency to Kafka cluster adds to user response time
- Backpressure from slow consumers affects user operations

### 4. **Operational Complexity**
- Cannot perform Kafka maintenance without service downtime
- Rolling updates require careful coordination
- Disaster recovery complicated by tight coupling

## Root Cause

The services directly call `kafka_bus.send_and_wait()` within business logic:

```python
# In DefaultEventPublisher
await self.kafka_bus.send_and_wait(
    topic=topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
    value=envelope_bytes,
    key=key_bytes,
)
```

If this fails, the entire operation fails, even though the database transaction may have completed.

## Proposed Solution: Transactional Outbox Pattern

### Architecture

```
Business Operation → Database Transaction (includes Outbox) → Response
                            ↓
                      Outbox Table
                            ↓
                   Event Relay Service → Kafka
```

### Implementation Components

#### 1. Outbox Table Schema
```sql
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id VARCHAR(255) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    event_data JSONB NOT NULL,
    event_key VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    INDEX idx_unpublished (published_at) WHERE published_at IS NULL,
    INDEX idx_created (created_at)
);
```

#### 2. Modified Business Logic
```python
async def handle_essay_content_provisioned(self, event_data, correlation_id):
    async with self.repository.transaction() as tx:
        # Business logic
        essay = await tx.assign_slot(...)
        
        # Store event in outbox (same transaction)
        await tx.add_outbox_event(
            aggregate_id=essay.essay_id,
            aggregate_type="essay",
            event_type="EssaySlotAssignedV1",
            event_data=slot_assigned_event.model_dump(mode="json"),
            event_key=essay.essay_id,
        )
        
        # Commit transaction
        await tx.commit()
    
    # Optional: Best-effort immediate publish
    try:
        await self.event_publisher.publish_from_outbox(essay.essay_id)
    except Exception:
        # Log but don't fail - relay will handle it
        logger.warning("Immediate publish failed, will retry via relay")
```

#### 3. Event Relay Service
```python
class EventRelayService:
    """Polls outbox and publishes events to Kafka."""
    
    async def relay_events(self):
        while self.running:
            # Get unpublished events
            events = await self.get_unpublished_events(limit=100)
            
            for event in events:
                try:
                    await self.publish_to_kafka(event)
                    await self.mark_published(event.id)
                except Exception as e:
                    await self.record_failure(event.id, str(e))
            
            await asyncio.sleep(self.poll_interval)
```

### Benefits

1. **Guaranteed Delivery**: Events are never lost
2. **Decoupling**: Business operations succeed regardless of Kafka state
3. **Performance**: No blocking on Kafka operations
4. **Observability**: Clear view of pending/failed events
5. **Resilience**: Automatic retry with backoff

## Migration Strategy

### Phase 1: Add Outbox Infrastructure (Sprint 1)
- Create outbox tables in each service
- Deploy event relay service (inactive)
- Add monitoring/metrics

### Phase 2: Dual Write (Sprint 2)
- Modify services to write to both Kafka and outbox
- Activate relay service in shadow mode
- Validate event delivery consistency

### Phase 3: Switch Primary Path (Sprint 3)
- Make outbox the primary path
- Keep direct Kafka as fallback
- Monitor for issues

### Phase 4: Remove Direct Publishing (Sprint 4)
- Remove direct Kafka calls from business logic
- Clean up old code
- Document new patterns

## Alternative Approaches Considered

### 1. Circuit Breaker Pattern
- **Pros**: Simpler to implement
- **Cons**: Still loses events during outages

### 2. Async Fire-and-Forget
- **Pros**: Doesn't block operations
- **Cons**: No delivery guarantees

### 3. Saga Pattern
- **Pros**: Full distributed transaction support
- **Cons**: Complex, overkill for event publishing

## Estimated Effort

- **Outbox Implementation**: 3-5 days per service
- **Event Relay Service**: 5-7 days
- **Testing & Validation**: 5 days
- **Migration & Rollout**: 3-5 days
- **Total**: 3-4 weeks for full implementation

## Risks & Mitigation

### Risk 1: Increased Database Load
- **Mitigation**: Efficient indexes, periodic cleanup of old events

### Risk 2: Event Ordering
- **Mitigation**: Partition by aggregate_id, preserve order within partition

### Risk 3: Duplicate Events
- **Mitigation**: Idempotent consumers (already implemented)

## Recommendation

Implement the Transactional Outbox Pattern. It provides the best balance of:
- **Reliability**: Guaranteed event delivery
- **Simplicity**: Well-understood pattern
- **Performance**: Minimal impact on business operations
- **Maintainability**: Clear separation of concerns

The investment is justified by the significant improvement in system resilience and operational flexibility.