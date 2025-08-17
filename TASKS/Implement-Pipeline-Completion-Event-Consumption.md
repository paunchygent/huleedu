# Task: Implement Pipeline Completion Event Consumption

## Overview
Currently, `BatchPipelineCompletedV1` events are published by BOS but have no consumers after removing BCS cache clearing. This creates a gap in teacher notifications and result finalization. We need to add two consumers to complete the pipeline completion workflow.

## Implementation Plan

### Part 1: Add Pipeline Completion Notifications (BOS)
**File:** `services/batch_orchestrator_service/notification_projector.py`

#### Step 1.1: Add Pipeline Completion Handler Method
Add new method to `NotificationProjector` class:

```python
async def handle_batch_pipeline_completed(
    self,
    event: BatchPipelineCompletedV1,
) -> None:
    """Project pipeline completion to teacher notification."""
    
    # Get teacher_id from batch metadata
    batch = await self.batch_repo.get_batch(event.batch_id)
    
    notification = TeacherNotificationRequestedV1(
        teacher_id=batch.teacher_id,
        notification_type="pipeline_completed",
        category=WebSocketEventCategory.BATCH_PROGRESS,
        priority=NotificationPriority.MEDIUM,
        payload={
            "batch_id": event.batch_id,
            "pipeline_name": event.pipeline_name,
            "final_status": event.final_status,
            "completed_phases": event.completed_phases,
            "successful_essays": event.successful_essay_count,
            "failed_essays": event.failed_essay_count,
            "duration_seconds": event.processing_duration_seconds,
            "message": f"Pipeline {event.pipeline_name} completed: {event.final_status}"
        },
        action_required=(event.failed_essay_count > 0),
        correlation_id=str(event.correlation_id),
        batch_id=event.batch_id,
    )
    
    await self._publish_notification(notification)
    
    logger.info(
        "Published pipeline_completed notification",
        extra={
            "batch_id": event.batch_id,
            "teacher_id": batch.teacher_id,
            "final_status": event.final_status,
            "correlation_id": str(event.correlation_id),
        },
    )
```

#### Step 1.2: Wire Handler to Pipeline Coordinator
**File:** `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`

After publishing `BatchPipelineCompletedV1` (around line 620), add:

```python
# Project completion notification to teacher
await self.notification_projector.handle_batch_pipeline_completed(completion_event)
```

#### Step 1.3: Update Constructor Dependencies
Ensure `PipelinePhaseCoordinatorImpl` has `notification_projector` injected via DI.

### Part 2: Add Result Aggregator Pipeline Completion Handling

#### Step 2.1: Add Topic Subscription
**File:** `services/result_aggregator_service/kafka_consumer.py`

Add to topics list in `__init__` method:
```python
self.topics = [
    topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
    topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
    topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
    topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
    topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
    topic_name(ProcessingEvent.BATCH_PIPELINE_COMPLETED),  # NEW
]
```

Add to idempotency config:
```python
event_type_ttls={
    # ... existing entries ...
    "BatchPipelineCompletedV1": 259200,  # 72 hours
}
```

#### Step 2.2: Add Message Handler
**File:** `services/result_aggregator_service/kafka_consumer.py`

Add to `_process_message_impl` method:
```python
elif msg.topic == topic_name(ProcessingEvent.BATCH_PIPELINE_COMPLETED):
    envelope: EventEnvelope = EventEnvelope.model_validate_json(msg.value)
    event: BatchPipelineCompletedV1 = BatchPipelineCompletedV1.model_validate(envelope.data)
    await self.event_processor.process_pipeline_completed(event)
    return True
```

#### Step 2.3: Add Event Processor Method
**File:** `services/result_aggregator_service/protocols.py`

Add to `EventProcessorProtocol`:
```python
async def process_pipeline_completed(self, event: BatchPipelineCompletedV1) -> None:
    """Process pipeline completion for final result aggregation."""
    ...
```

#### Step 2.4: Implement Event Processor Method
**File:** `services/result_aggregator_service/implementations/event_processor_impl.py`

```python
async def process_pipeline_completed(self, event: BatchPipelineCompletedV1) -> None:
    """Process pipeline completion for final result aggregation."""
    
    logger.info(
        f"Processing pipeline completion for batch {event.batch_id}",
        extra={
            "batch_id": event.batch_id,
            "final_status": event.final_status,
            "correlation_id": str(event.correlation_id),
        }
    )
    
    # Mark batch as completed in aggregator
    await self.batch_repository.mark_batch_completed(
        batch_id=event.batch_id,
        final_status=event.final_status,
        completion_stats={
            "successful_essays": event.successful_essay_count,
            "failed_essays": event.failed_essay_count,
            "duration_seconds": event.processing_duration_seconds,
            "completed_phases": event.completed_phases,
        }
    )
    
    # Update class-level aggregations
    batch = await self.batch_repository.get_batch(event.batch_id)
    await self.update_class_summary(batch.class_id, event.batch_id)
    
    # Invalidate relevant cache entries
    await self.cache_manager.invalidate_batch_cache(event.batch_id)
    
    logger.info(
        f"Completed pipeline completion processing for batch {event.batch_id}",
        extra={"batch_id": event.batch_id}
    )
```

#### Step 2.5: Add Repository Method
**File:** `services/result_aggregator_service/protocols.py`

Add to `BatchRepositoryProtocol`:
```python
async def mark_batch_completed(
    self,
    batch_id: str,
    final_status: str,
    completion_stats: dict,
) -> None:
    """Mark batch as completed with final statistics."""
    ...
```

**File:** `services/result_aggregator_service/implementations/batch_repository_postgres_impl.py`

Implement the method with proper SQL update.

## Testing Requirements

### Unit Tests
1. Test `NotificationProjector.handle_batch_pipeline_completed()` creates correct notification
2. Test RAS event processor handles pipeline completion correctly
3. Test repository `mark_batch_completed()` updates database correctly

### Integration Tests
1. Test end-to-end: BOS publishes ’ RAS consumes ’ database updated
2. Test end-to-end: BOS publishes ’ notification ’ WebSocket delivery

### E2E Tests
1. Test complete flow: Start pipeline ’ completion ’ teacher receives notification
2. Test dashboard reflects completion status after pipeline finishes

## Success Criteria
-  Teachers receive WebSocket notifications when their pipelines complete
-  Result Aggregator Service finalizes batch state on completion
-  Dashboard shows accurate completion status via REST API
-  All tests pass
-  No orphaned events (all `BatchPipelineCompletedV1` events consumed)

## Implementation Order
1. Part 1 (BOS notifications) - Lower risk, immediate teacher value
2. Part 2 (RAS consumption) - Enables proper result finalization
3. Testing - Comprehensive verification

This completes the pipeline completion event consumption architecture.