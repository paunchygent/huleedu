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

- [ ] Define a `TeacherNotificationRequestedV1` notification_type + payload shape for dashboard batch updates
- [ ] RAS publishes `TeacherNotificationRequestedV1` for relevant batch transitions (phase completion / batch completion)
- [ ] WebSocket service relays notifications to connected frontend clients (existing forwarder pattern)
- [ ] Payload includes all fields needed to update a dashboard item without refetching
- [ ] Frontend Vue composable for WebSocket connection (separate frontend task)

## Implementation Notes

**Do NOT add a new WebSocket event contract model.**

WebSocket delivery uses the existing `TeacherNotificationRequestedV1` contract
(`common_core.events.notification_events.TeacherNotificationRequestedV1`), which the
WebSocket service forwards to Redis and connected clients.

**Publishing pattern (recommended):**
```python
# RAS emits TeacherNotificationRequestedV1 (via outbox + notification projector)
TeacherNotificationRequestedV1(
    teacher_id=<resolved teacher/user>,
    notification_type="batch_status_updated",
    category=WebSocketEventCategory.BATCH_PROGRESS,
    priority=NotificationPriority.STANDARD,
    payload={
        "batch_id": "<uuid>",
        "status": "<batch_client_status>",
        "completed_essays": 12,
        "failed_essays": 1,
        "processing_phase": "spellcheck" | "cj_assessment" | None,
        "completed_at": "<iso>" | None,
    },
    correlation_id="<corr>",
    batch_id="<uuid>",
)
```

**Architecture decision (set):**
- RAS is the source of truth for batch status/progress and will publish dashboard update
  notifications via `TeacherNotificationRequestedV1`.
- WebSocket service remains a pure forwarder (no business logic, no polling, no Redis writes from BFF).

**Files to modify:**
- `services/result_aggregator_service/` - publish `TeacherNotificationRequestedV1` on relevant transitions
- `services/websocket_service/` - no new contract; validate forwarding behavior remains intact

## Blocked By

- `bff-cms-validation-integration` - complete Phase 3 before real-time

## Blocks

- `frontend-live-data-integration` - frontend needs WebSocket for live updates
