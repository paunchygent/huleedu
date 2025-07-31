# Pending Content Pattern - Implementation Plan

## Executive Summary

The Pending Content Pattern solves the race condition where `EssayContentProvisioned` events arrive before `BatchEssaysRegistered` events. Instead of marking early-arriving content as "excess", we store it as "pending" and reconcile it when the batch registration arrives.

### Key Benefits:
- ✅ Respects all DDD boundaries - no cross-service queries
- ✅ Maintains event-driven architecture
- ✅ Uses existing Redis infrastructure
- ✅ Minimal code changes (YAGNI)
- ✅ Fully idempotent
- ✅ Easy to test and debug

## Implementation Steps

### Phase 1: Redis Infrastructure for Pending Content

#### 1.1 Create PendingContentOperations Component

**File**: `services/essay_lifecycle_service/implementations/redis_pending_content_ops.py`

```python
"""
Redis operations for managing pending content.

Handles content that arrives before batch registration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List

from huleedu_service_libs.logging_utils import create_service_logger
from redis.asyncio import Redis


class RedisPendingContentOperations:
    """Manages pending content storage and retrieval in Redis."""
    
    def __init__(self, redis_client: Redis):
        self._redis = redis_client
        self._logger = create_service_logger("redis_pending_content")
        
    async def store_pending_content(
        self,
        batch_id: str,
        text_storage_id: str,
        content_metadata: Dict[str, Any]
    ) -> None:
        """Store content as pending until batch registration arrives."""
        pending_key = f"pending_content:{batch_id}"
        
        # Add timestamp and storage ID to metadata
        metadata_with_storage = {
            **content_metadata,
            "text_storage_id": text_storage_id,
            "stored_at": datetime.now(UTC).isoformat()
        }
        
        # Store in batch-specific set
        await self._redis.sadd(pending_key, json.dumps(metadata_with_storage))
        
        # Add to global index for monitoring/cleanup (score = timestamp)
        index_key = "pending_content:index"
        score = datetime.now(UTC).timestamp()
        await self._redis.zadd(index_key, {batch_id: score})
        
        # Set TTL (24 hours) to prevent indefinite storage
        await self._redis.expire(pending_key, 86400)
        
        self._logger.info(
            f"Stored pending content for batch {batch_id}: {text_storage_id}",
            extra={
                "batch_id": batch_id,
                "text_storage_id": text_storage_id,
                "has_ttl": True,
                "ttl_seconds": 86400
            }
        )
    
    async def get_pending_content(self, batch_id: str) -> List[Dict[str, Any]]:
        """Retrieve all pending content for a batch."""
        pending_key = f"pending_content:{batch_id}"
        
        # Get all pending content items
        pending_items = await self._redis.smembers(pending_key)
        
        if not pending_items:
            return []
        
        # Parse JSON metadata
        content_list = []
        for item in pending_items:
            try:
                metadata = json.loads(item)
                content_list.append(metadata)
            except json.JSONDecodeError:
                self._logger.error(
                    f"Failed to parse pending content metadata",
                    extra={"batch_id": batch_id, "raw_item": item}
                )
        
        return content_list
    
    async def remove_pending_content(
        self,
        batch_id: str,
        text_storage_id: str
    ) -> bool:
        """Remove specific pending content after it's been processed."""
        pending_key = f"pending_content:{batch_id}"
        
        # Find and remove the specific item
        pending_items = await self._redis.smembers(pending_key)
        
        for item in pending_items:
            try:
                metadata = json.loads(item)
                if metadata.get("text_storage_id") == text_storage_id:
                    await self._redis.srem(pending_key, item)
                    
                    # Clean up index if batch has no more pending content
                    remaining = await self._redis.scard(pending_key)
                    if remaining == 0:
                        await self._redis.zrem("pending_content:index", batch_id)
                        await self._redis.delete(pending_key)
                    
                    self._logger.info(
                        f"Removed pending content {text_storage_id} from batch {batch_id}",
                        extra={
                            "batch_id": batch_id,
                            "text_storage_id": text_storage_id,
                            "remaining_pending": remaining
                        }
                    )
                    return True
            except json.JSONDecodeError:
                continue
        
        return False
    
    async def clear_all_pending(self, batch_id: str) -> int:
        """Clear all pending content for a batch. Returns count of items cleared."""
        pending_key = f"pending_content:{batch_id}"
        
        # Get count before deletion
        count = await self._redis.scard(pending_key)
        
        # Delete the set and remove from index
        await self._redis.delete(pending_key)
        await self._redis.zrem("pending_content:index", batch_id)
        
        if count > 0:
            self._logger.info(
                f"Cleared {count} pending content items for batch {batch_id}",
                extra={"batch_id": batch_id, "cleared_count": count}
            )
        
        return count
```

#### 1.2 Update DI Configuration

**File**: `services/essay_lifecycle_service/di.py`

Add to the `EssayLifecycleProvider`:

```python
from services.essay_lifecycle_service.implementations.redis_pending_content_ops import (
    RedisPendingContentOperations,
)

# In provide_redis_pending_content_ops method:
@provide(scope=Scope.APP)
async def provide_redis_pending_content_ops(
    self, redis_client: Redis
) -> RedisPendingContentOperations:
    """Provide Redis pending content operations."""
    return RedisPendingContentOperations(redis_client)
```

### Phase 2: Enhanced Batch Tracker

#### 2.1 Update BatchEssayTracker Protocol

**File**: `services/essay_lifecycle_service/protocols.py`

Add new method to the protocol:

```python
async def process_pending_content_for_batch(self, batch_id: str) -> int:
    """
    Process any pending content for a newly registered batch.
    
    Returns:
        Number of pending content items processed
    """
    ...
```

#### 2.2 Enhance DefaultBatchEssayTracker

**File**: `services/essay_lifecycle_service/implementations/batch_essay_tracker_impl.py`

Add dependency injection and new method:

```python
def __init__(
    self,
    persistence: BatchTrackerPersistence,
    batch_state: RedisBatchState,
    batch_queries: RedisBatchQueries,
    failure_tracker: RedisFailureTracker,
    slot_operations: RedisSlotOperations,
    pending_content_ops: RedisPendingContentOperations,  # NEW
) -> None:
    # ... existing init ...
    self._pending_content_ops = pending_content_ops

async def register_batch(self, event: Any, correlation_id: UUID) -> None:
    """Register batch slot expectations with pending content reconciliation."""
    # ... existing registration logic ...
    
    # NEW: After successful batch registration, check for pending content
    pending_count = await self.process_pending_content_for_batch(batch_id)
    
    if pending_count > 0:
        self._logger.info(
            f"Processed {pending_count} pending content items for batch {batch_id}",
            extra={
                "batch_id": batch_id,
                "pending_count": pending_count,
                "correlation_id": str(correlation_id)
            }
        )

async def process_pending_content_for_batch(self, batch_id: str) -> int:
    """Process any pending content for a newly registered batch."""
    # Get all pending content
    pending_content = await self._pending_content_ops.get_pending_content(batch_id)
    
    if not pending_content:
        return 0
    
    processed_count = 0
    
    for content_metadata in pending_content:
        text_storage_id = content_metadata["text_storage_id"]
        
        # Try to assign to available slot
        assigned_essay_id = await self._slot_operations.assign_slot_atomic(
            batch_id, content_metadata
        )
        
        if assigned_essay_id:
            # Successfully assigned - remove from pending
            await self._pending_content_ops.remove_pending_content(
                batch_id, text_storage_id
            )
            
            # Mark slot as fulfilled (will check batch completion)
            completion_result = await self.mark_slot_fulfilled(
                batch_id, assigned_essay_id, text_storage_id
            )
            
            if completion_result:
                # Batch is complete - completion event will be published
                # by the caller (batch_coordination_handler)
                pass
            
            processed_count += 1
            
            self._logger.info(
                f"Reconciled pending content: {text_storage_id} -> {assigned_essay_id}",
                extra={
                    "batch_id": batch_id,
                    "text_storage_id": text_storage_id,
                    "assigned_essay_id": assigned_essay_id
                }
            )
        else:
            # No slots available - content remains as excess
            self._logger.warning(
                f"No slots for pending content {text_storage_id} in batch {batch_id}",
                extra={
                    "batch_id": batch_id,
                    "text_storage_id": text_storage_id
                }
            )
    
    return processed_count
```

### Phase 3: Update Coordination Handler

#### 3.1 Modify handle_essay_content_provisioned

**File**: `services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py`

Replace the "No slots available" section:

```python
async def handle_essay_content_provisioned(
    self,
    event_data: EssayContentProvisionedV1,
    correlation_id: UUID,
) -> bool:
    """Handle EssayContentProvisionedV1 event with pending content support."""
    try:
        # ... existing logging ...
        
        # Step 1: Try slot assignment first
        assigned_essay_id = await self.batch_tracker.assign_slot_to_content(
            event_data.batch_id, event_data.text_storage_id, event_data.original_file_name
        )
        
        if assigned_essay_id is None:
            # NEW: Check if batch exists before deciding on pending vs excess
            batch_status = await self.batch_tracker.get_batch_status(event_data.batch_id)
            
            if batch_status is None:
                # ALWAYS store as pending content when batch not registered
                logger.info(
                    "Batch not registered yet, storing content as pending",
                    extra={
                        "batch_id": event_data.batch_id,
                        "text_storage_id": event_data.text_storage_id,
                        "correlation_id": str(correlation_id),
                    }
                )
                
                # Store as pending (inject pending_content_ops via DI)
                content_metadata = {
                    "original_file_name": event_data.original_file_name,
                    "file_upload_id": event_data.file_upload_id,
                    "raw_file_storage_id": event_data.raw_file_storage_id,
                    "file_size_bytes": event_data.file_size_bytes,
                    "content_md5_hash": event_data.content_md5_hash,
                    "correlation_id": str(event_data.correlation_id),
                }
                
                await self.pending_content_ops.store_pending_content(
                    event_data.batch_id,
                    event_data.text_storage_id,
                    content_metadata
                )
                
                # Successfully handled as pending - NO EXCESS CONTENT EVENT
                return True
            
            # Batch exists but no slots - this is true excess content
            logger.warning(
                "No available slots for content, publishing excess content event",
                # ... existing logging ...
            )
            
            # ... existing ExcessContentProvisionedV1 logic ...
```

#### 3.2 Update handle_batch_essays_registered

**File**: `services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py`

Add pending content processing after batch registration:

```python
async def handle_batch_essays_registered(
    self,
    event_data: BatchEssaysRegistered,
    correlation_id: UUID,
) -> bool:
    """Handle BatchEssaysRegistered event with pending content reconciliation."""
    try:
        # ... existing registration logic ...
        
        # After successful batch registration in tracker
        await self.batch_tracker.register_batch(event_data, correlation_id)
        
        # NEW: Process any pending content for this batch
        pending_results = await self._process_pending_content_after_registration(
            event_data.batch_id, correlation_id, session
        )
        
        # Check if batch is complete (existing logic handles this)
        batch_completion_result = await self.batch_tracker.check_batch_completion(
            event_data.batch_id
        )
        
        # ... rest of existing logic ...

async def _process_pending_content_after_registration(
    self,
    batch_id: str,
    correlation_id: UUID,
    session: AsyncSession
) -> List[Dict[str, Any]]:
    """Process pending content after batch registration."""
    results = []
    
    # Get pending content
    pending_content = await self.pending_content_ops.get_pending_content(batch_id)
    
    for content_metadata in pending_content:
        text_storage_id = content_metadata["text_storage_id"]
        
        # Re-trigger content provisioning flow for pending content
        # This ensures all the same logic applies (idempotency, state updates, etc.)
        pseudo_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            original_file_name=content_metadata["original_file_name"],
            file_upload_id=content_metadata["file_upload_id"],
            raw_file_storage_id=content_metadata["raw_file_storage_id"],
            file_size_bytes=content_metadata["file_size_bytes"],
            content_md5_hash=content_metadata.get("content_md5_hash"),
            correlation_id=UUID(content_metadata["correlation_id"]),
            timestamp=datetime.now(UTC),
        )
        
        # Process through normal flow
        success = await self.handle_essay_content_provisioned(
            pseudo_event, correlation_id
        )
        
        results.append({
            "text_storage_id": text_storage_id,
            "success": success,
            "was_pending": True
        })
        
        # Remove from pending regardless of outcome
        await self.pending_content_ops.remove_pending_content(
            batch_id, text_storage_id
        )
    
    if results:
        logger.info(
            f"Processed {len(results)} pending content items for batch {batch_id}",
            extra={
                "batch_id": batch_id,
                "pending_count": len(results),
                "correlation_id": str(correlation_id)
            }
        )
    
    return results
```

### Phase 4: Testing Strategy

#### 4.1 Unit Tests

**File**: `services/essay_lifecycle_service/tests/unit/test_pending_content_operations.py`

Test the RedisPendingContentOperations component in isolation.

#### 4.2 Integration Tests

**File**: `services/essay_lifecycle_service/tests/integration/test_pending_content_integration.py`

Test the full flow with real Redis but mocked repositories.

#### 4.3 Update Existing Tests

REMOVE all tests that expect excess content for early-arriving essays. The new behavior is:
- Essays arriving before batch registration → ALWAYS pending
- Essays arriving after batch with no slots → excess content

### Phase 5: Monitoring & Observability

#### 5.1 Add Metrics

```python
# In RedisPendingContentOperations
pending_content_stored_total = Counter(
    "els_pending_content_stored_total",
    "Total pending content items stored",
    ["batch_id"]
)

pending_content_reconciled_total = Counter(
    "els_pending_content_reconciled_total", 
    "Total pending content items reconciled",
    ["batch_id", "outcome"]  # outcome: assigned, excess
)

pending_content_age_seconds = Histogram(
    "els_pending_content_age_seconds",
    "Age of pending content when reconciled"
)
```

#### 5.2 Add Logging

Enhanced structured logging throughout the flow with correlation IDs and batch IDs.

### Phase 6: Cleanup & Maintenance

#### 6.1 Periodic Cleanup Task

Add a background task to clean up orphaned pending content older than 24 hours.

#### 6.2 Admin Endpoints

Optional: Add admin endpoints to view/manage pending content if needed.

## Deployment Strategy

Since we're in pure development with no backwards compatibility needs:

1. **Direct implementation** - Replace existing behavior entirely
2. **Remove old excess content logic** - Essays arriving early are ALWAYS pending
3. **No feature flags needed** - This is the new correct behavior

## Success Criteria

1. Functional tests no longer hang waiting for BatchEssaysReady
2. No essays marked as excess when they arrive before batch registration
3. All essays correctly assigned once batch is registered
4. Metrics show pending content being reconciled successfully

## Phase 7: Additional Component Updates

### 7.1 Event Processing & Kafka Consumer

**File**: `services/batch_orchestrator_service/kafka_consumer.py`

- BOS needs to understand the new behavior when receiving `ExcessContentProvisionedV1` events
- Update any logic that treats "batch not registered" excess content as an error
- `ExcessContentProvisionedV1` events should now ONLY occur for true excess (more essays than slots)

### 7.2 Test Utilities & Mocks

**File**: `services/essay_lifecycle_service/tests/distributed/test_utils.py`

Update `MockBatchLifecyclePublisher`:
```python
async def publish_excess_content_provisioned(
    self, event_data: Any, correlation_id: UUID, session: AsyncSession | None = None
) -> None:
    """Mock publisher - now ONLY for true excess content."""
    # Verify this is true excess, not timing issue
    assert event_data.reason != "batch_not_registered", "Early essays should be pending, not excess"
    self.published_events.append(("excess_content_provisioned", event_data, correlation_id))
```

**File**: `services/essay_lifecycle_service/tests/integration/test_atomic_batch_creation_integration.py`

Similar updates to `TestBatchLifecyclePublisher` mock.

### 7.3 Protocol Documentation

**File**: `services/essay_lifecycle_service/protocols.py`

Update the `BatchLifecyclePublisher` protocol documentation:
```python
async def publish_excess_content_provisioned(
    self,
    event_data: Any,  # ExcessContentProvisionedV1
    correlation_id: UUID,
    session: AsyncSession | None = None,
) -> None:
    """
    Publish event for TRUE excess content (more essays than available slots).
    
    NOTE: This is NO LONGER used for essays arriving before batch registration.
    Those are now stored as pending content and reconciled later.
    
    Valid reasons:
    - "NO_AVAILABLE_SLOT" - All slots filled
    - "BATCH_FULL" - Batch at capacity
    
    INVALID reasons (no longer used):
    - "batch_not_registered" - Use pending content instead
    """
    ...
```

### 7.4 Event Data Model Documentation

**File**: `libs/common_core/src/common_core/events/batch_coordination_events.py`

Update `ExcessContentProvisionedV1` class docstring:
```python
class ExcessContentProvisionedV1(BaseModel):
    """
    Event sent by ELS when content cannot be assigned to any available slot.

    This occurs when more files are uploaded than expected_essay_count for a batch.
    
    IMPORTANT: This event is NO LONGER sent for essays arriving before batch registration.
    Those are stored as pending content and reconciled when the batch is registered.
    
    Valid reasons:
    - 'NO_AVAILABLE_SLOT': All batch slots are filled
    - 'BATCH_FULL': Batch has reached capacity
    
    DEPRECATED reasons (no longer used):
    - 'batch_not_registered': Essays now stored as pending instead
    """
```

### 7.5 Integration Test Updates

**File**: `services/essay_lifecycle_service/tests/integration/test_content_provisioned_flow.py`

Search for any tests expecting excess content for early essays and update:
```python
# OLD EXPECTATION (remove):
assert event.reason == "batch_not_registered"

# NEW BEHAVIOR:
# Early essays are stored as pending, not published as excess
```

**File**: `services/essay_lifecycle_service/tests/integration/test_pending_validation_simple.py`

Update any assumptions about batch registration timing.

### 7.6 Functional Test Updates

These tests should automatically pass once the race condition is fixed:
- `tests/functional/test_e2e_client_pipeline_resolution_workflow.py`
- `tests/functional/test_validation_coordination_*.py`

However, check for any assertions expecting specific excess content events.

### 7.7 Metrics & Monitoring Updates

Remove/update any metrics or alerts monitoring:
```python
# DEPRECATED METRIC:
excess_content_reason_batch_not_registered_total

# NEW METRICS (from Phase 5):
els_pending_content_stored_total
els_pending_content_reconciled_total
els_pending_content_age_seconds
```

### 7.8 Documentation Updates

Update the following documentation:
1. **Service READMEs** - Update ELS README to describe pending content pattern
2. **Architecture diagrams** - Show pending content flow in event diagrams
3. **API documentation** - Note behavior change for early-arriving essays
4. **Runbooks** - Update any troubleshooting guides mentioning excess content

### 7.9 Key Clarifications

**IMPORTANT**: We are NOT removing the excess content mechanism entirely:
- `ExcessContentProvisionedV1` event still exists and is used
- `publish_excess_content_provisioned` method remains in all interfaces
- The change is ONLY about WHEN it's used:
  - ❌ OLD: Used for timing issues (essays before batch)
  - ✅ NEW: ONLY for true excess (more essays than slots)

**BOS Changes**: None required! BOS simply stops receiving false "excess" events caused by race conditions.

## Timeline

- Phase 1-2: 2 hours (Redis infrastructure + batch tracker)
- Phase 3: 1 hour (coordination handler updates)
- Phase 4: 2 hours (comprehensive testing)
- Phase 5-6: 1 hour (monitoring + cleanup)
- Phase 7: 2 hours (additional component updates)

Total: ~8 hours of implementation