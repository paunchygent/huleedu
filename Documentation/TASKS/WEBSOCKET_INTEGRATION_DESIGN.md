# WebSocket Service Integration Design

## Overview

This document outlines the integration design for real-time notifications of `EssaySlotAssignedV1` events through the existing WebSocket service infrastructure.

## Current WebSocket Architecture

Based on the codebase analysis, HuleEdu uses a Redis-based pub/sub pattern for real-time notifications:

```
Service → Kafka (async processing)
    ↓
Service → Redis pub/sub → WebSocket Service → Client
         (real-time notifications)
```

### Key Components

1. **Redis Channels**: `ws:{user_id}` - User-specific notification channels
2. **Event Publishing**: Services dual-publish to Kafka and Redis
3. **WebSocket Service**: Generic relay that doesn't understand event types
4. **Client Subscription**: WebSocket clients subscribe to their user channel

## Integration Requirements

### 1. EssaySlotAssignedV1 Notification

Teachers need real-time notification when files are assigned to essay slots:

```json
{
  "event": "essay_slot_assigned",
  "data": {
    "batch_id": "batch-123",
    "essay_id": "essay-456",
    "file_upload_id": "upload-789",
    "filename": "student_essay.txt",
    "slot_index": 3,
    "timestamp": "2025-07-24T10:30:00Z"
  }
}
```

## Implementation Design

### ELS Redis Publishing Implementation

Modify `DefaultEventPublisher` to dual-publish `EssaySlotAssignedV1`:

```python
async def publish_essay_slot_assigned(self, event_data: EssaySlotAssignedV1, correlation_id: UUID) -> None:
    """Publish essay slot assignment event to Kafka and Redis."""
    # Existing Kafka publishing
    await self._publish_event_to_kafka(...)
    
    # NEW: Redis publishing for real-time notification
    await self._publish_essay_slot_assigned_to_redis(event_data, correlation_id)

async def _publish_essay_slot_assigned_to_redis(
    self, event_data: EssaySlotAssignedV1, correlation_id: UUID
) -> None:
    """Publish slot assignment to Redis for WebSocket notification."""
    try:
        # Get user_id from batch
        batch_status = await self.batch_tracker.get_batch_status(event_data.batch_id)
        if not batch_status or "user_id" not in batch_status:
            logger.warning(
                "Cannot publish WebSocket notification: user_id not found",
                batch_id=event_data.batch_id,
            )
            return
        
        user_id = batch_status["user_id"]
        
        # Get filename from repository (optional enhancement)
        filename = None
        essay_state = await self.repository.get_essay_state(event_data.essay_id)
        if essay_state and essay_state.processing_metadata:
            filename = essay_state.processing_metadata.get("original_file_name")
        
        # Build notification payload
        notification = {
            "event": "essay_slot_assigned",
            "correlation_id": str(correlation_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "batch_id": event_data.batch_id,
                "essay_id": event_data.essay_id,
                "file_upload_id": event_data.file_upload_id,
                "filename": filename,
                "text_storage_id": event_data.text_storage_id,
            }
        }
        
        # Publish to user's WebSocket channel
        channel = f"ws:{user_id}"
        await self.redis_client.publish(channel, json.dumps(notification))
        
        logger.info(
            "Published slot assignment to WebSocket",
            channel=channel,
            essay_id=event_data.essay_id,
            file_upload_id=event_data.file_upload_id,
        )
        
    except Exception as e:
        # Log but don't fail - WebSocket is best-effort
        logger.error(
            "Failed to publish WebSocket notification",
            error=str(e),
            batch_id=event_data.batch_id,
        )
```

### Client Integration

Frontend clients need to handle the new event type:

```typescript
// WebSocket event handler
websocket.on('message', (data) => {
  const event = JSON.parse(data);
  
  switch (event.event) {
    case 'essay_slot_assigned':
      handleSlotAssignment(event.data);
      break;
    // ... other event types
  }
});

function handleSlotAssignment(data: SlotAssignmentData) {
  // Update UI to show file → essay mapping
  updateFileStatus(data.file_upload_id, {
    status: 'assigned',
    essayId: data.essay_id,
    slotIndex: data.slot_index
  });
  
  // Show notification
  showNotification(`File "${data.filename}" assigned to essay slot`);
}
```

### Enhanced RAS API Response

With RAS now tracking `file_upload_id`, the complete flow is:

1. **Real-time**: WebSocket notification of assignment
2. **Query**: RAS API returns complete traceability

```json
GET /internal/v1/batches/{batch_id}/status

{
  "batch_id": "batch-123",
  "essays": [
    {
      "essay_id": "essay-456",
      "file_upload_id": "upload-789",  // NEW: Complete traceability
      "filename": "student_essay.txt",
      "spellcheck_status": "completed",
      "cj_assessment_status": "completed",
      "cj_rank": 1,
      "cj_score": 85.5
    }
  ]
}
```

## Error Handling

### Redis Pub/Sub Failures
- Log errors but don't block business operations
- Clients can fall back to polling RAS API
- WebSocket reconnection handled by client library

### Missing User Association
- Some events may not have user_id available
- Log warning and skip WebSocket notification
- Client discovers via API polling

## Security Considerations

1. **Channel Isolation**: Each user only receives their own events
2. **No Sensitive Data**: Notifications contain IDs, not content
3. **Authentication**: WebSocket service validates user tokens
4. **Rate Limiting**: Prevent notification flooding

## Testing Strategy

### Unit Tests
```python
async def test_essay_slot_assigned_redis_publishing():
    """Test that slot assignment publishes to Redis."""
    mock_redis = AsyncMock()
    event_publisher = DefaultEventPublisher(redis_client=mock_redis, ...)
    
    await event_publisher.publish_essay_slot_assigned(slot_event, correlation_id)
    
    mock_redis.publish.assert_called_once()
    channel, payload = mock_redis.publish.call_args[0]
    assert channel == "ws:test_user_123"
    assert "essay_slot_assigned" in payload
```

### Integration Tests
- Verify event flows from ELS → Redis → WebSocket
- Test missing user_id handling
- Validate notification payload structure

## Monitoring & Metrics

### Key Metrics
- Redis publish success/failure rate
- Notification latency (event → WebSocket)
- Channel subscription count
- Message delivery rate

### Dashboards
- WebSocket connection health
- Redis pub/sub performance
- Per-user notification volume
- Error rates by event type

## Conclusion

The WebSocket integration for `EssaySlotAssignedV1` events provides immediate feedback to users about file-to-essay assignment, improving the user experience while maintaining system decoupling through the existing Redis pub/sub infrastructure. The implementation is straightforward, leveraging existing patterns in the codebase.