---
id: 'websocket-batch-updates'
title: 'WebSocket Batch Updates'
type: 'task'
status: 'blocked'
priority: 'medium'
domain: 'programs'
service: 'websocket_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "frontend-live-data-integration"]
labels: ["websocket", "real-time", "redis-pubsub"]
---
# WebSocket Batch Updates

## Objective

Enable real-time batch status updates on the Teacher Dashboard via WebSocket, so teachers see processing progress without page refresh.

## Context

Current architecture:
- WebSocket service (port 6000) exists with Redis pub/sub
- `RedisPubSub.publish_user_notification()` can send to user channels
- Frontend has no WebSocket client integration

For dashboard UX:
- When batch status changes (e.g., processing → completed), push update
- Frontend updates Pinia store reactively
- No polling required

## Acceptance Criteria

- [ ] Define batch update event contract (`BatchStatusUpdatedV1`)
- [ ] BFF (or RAS) publishes batch updates to user's Redis channel
- [ ] WebSocket service relays to connected frontend clients
- [ ] Event includes all fields needed to update dashboard item
- [ ] Frontend Vue composable for WebSocket connection (separate frontend task)

## Implementation Notes

**Event contract:**
```python
class BatchStatusUpdatedV1(BaseModel):
    """WebSocket event for batch status change."""
    event_type: Literal["batch_status_updated"] = "batch_status_updated"
    batch_id: str
    status: BatchClientStatus
    completed_essays: int
    failed_essays: int
    processing_phase: str | None
    completed_at: datetime | None
```

**Publishing pattern (in RAS or via Kafka consumer):**
```python
await redis_pubsub.publish_user_notification(
    user_id=batch.user_id,
    notification=BatchStatusUpdatedV1(
        batch_id=batch.batch_id,
        status=batch.status,
        # ... other fields
    ),
)
```

**Architecture decision needed:**
- Option A: RAS publishes directly to Redis on status change
- Option B: Dedicated Kafka consumer listens for batch events and publishes to Redis
- Option C: BFF publishes when it detects changes (less real-time)

**Files to modify:**
- `services/websocket_service/` - ensure event type handling
- `libs/common_core/` - event contract definition
- RAS or dedicated consumer - publishing logic

## Blocked By

- `bff-cms-validation-integration` - complete Phase 3 before real-time

## Blocks

- `frontend-live-data-integration` - frontend needs WebSocket for live updates
