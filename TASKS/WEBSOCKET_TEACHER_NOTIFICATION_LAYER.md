# WebSocket Teacher Notification Layer Implementation

## Executive Summary

Implement a clean notification projection pattern that separates internal service events from teacher-facing notifications. Each service owns its notification decisions through dedicated projectors, and the WebSocket service becomes a simple notification router.

## Core Problem

The WebSocket service currently attempts to consume internal domain events, but:
- Most internal events lack user context (designed for service coordination)
- Mixing internal events with notifications violates separation of concerns
- Security risk: broadcasting user_ids in internal events
- No clear ownership of notification decisions

## Architectural Solution

### Three-Layer Separation

1. **Internal Domain Events** (`huleedu.{service}.{entity}.{action}.v1`)
   - Service-to-service coordination only
   - Never consumed by WebSocket service
   - No user context required

2. **Teacher Notification Events** (`huleedu.notification.teacher.requested.v1`)
   - Single event type for all notifications
   - Always contains teacher_id for routing
   - Explicit payload for UI consumption

3. **Service Notification Projectors** (`notification_projector.py`)
   - Each service maps its events to notifications
   - Owns authorization and filtering logic
   - Validates teacher relationships

## Teacher Notification Catalog (15 Events)

### CRITICAL Priority (24-hour deadline)
| Service | Notification Type | Description | Action Required |
|---------|------------------|-------------|-----------------|
| Class Management | `student_matching_confirmation_required` | Unmatched students need teacher confirmation | Yes - 24hr deadline |
| Class Management | `student_matching_deadline_approaching` | 4-hour warning before deadline | Yes - urgent |

### IMMEDIATE Priority (Blocks workflow)
| Service | Notification Type | Description | Action Required |
|---------|------------------|-------------|-----------------|
| File Service | `batch_validation_failed` | Validation errors prevent processing | Yes - fix errors |
| File Service | `batch_file_corrupted` | File cannot be read/processed | Yes - re-upload |
| Batch Orchestrator | `batch_registration_failed` | Batch setup failed | Yes - retry |

### HIGH Priority (Important outcomes)
| Service | Notification Type | Description | Action Required |
|---------|------------------|-------------|-----------------|
| Batch Orchestrator | `batch_processing_completed` | All processing finished successfully | No |
| Batch Orchestrator | `batch_processing_failed` | Processing pipeline failed | Yes - review |
| Result Aggregator | `cj_assessment_results_ready` | CJ rankings ready for review | No |

### STANDARD Priority (Status updates)
| Service | Notification Type | Description | Action Required |
|---------|------------------|-------------|-----------------|
| Batch Orchestrator | `batch_students_associated` | Phase 1 complete, all matched | No |
| Class Management | `class_roster_updated` | Students added/removed | No |
| Class Management | `class_created` | New class created successfully | No |
| File Service | `batch_files_uploaded` | Upload successful | No |

### LOW Priority (Progress tracking)
| Service | Notification Type | Description | Action Required |
|---------|------------------|-------------|-----------------|
| Batch Orchestrator | `batch_processing_started` | Pipeline initiated | No |
| Spellchecker | `batch_spellcheck_completed` | Spellcheck phase done | No |
| CJ Assessment | `batch_cj_assessment_completed` | Assessment phase done | No |

## Implementation Guide

### Step 1: Create Notification Event Contract

Location: `libs/common_core/src/common_core/events/notification_events.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from common_core.websocket_enums import NotificationCategory, NotificationPriority


class TeacherNotificationRequestedV1(BaseModel):
    """
    Teacher notification event for WebSocket delivery.
    
    This is the ONLY event type consumed by WebSocket service.
    Each service publishes this event when teachers need to be notified.
    """
    
    # Routing
    teacher_id: str = Field(..., description="Teacher to notify")
    
    # Notification metadata
    notification_type: str = Field(..., description="One of the 15 defined types")
    category: NotificationCategory = Field(..., description="UI category for grouping")
    priority: NotificationPriority = Field(..., description="Delivery priority")
    
    # Content
    payload: Dict[str, Any] = Field(..., description="Type-specific notification data")
    
    # Action tracking
    action_required: bool = Field(default=False, description="Teacher action needed")
    deadline_timestamp: Optional[datetime] = Field(None, description="Action deadline")
    
    # Correlation
    correlation_id: str = Field(..., description="Links to originating event")
    batch_id: Optional[str] = Field(None, description="Related batch if applicable")
    class_id: Optional[str] = Field(None, description="Related class if applicable")
    
    # Timestamp
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### Step 2: Implement Service Projectors

#### Template: `services/{service_name}/notification_projector.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationCategory, NotificationPriority
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from .protocols import EventPublisherProtocol, RepositoryProtocol

logger = create_service_logger("notification_projector")


class NotificationProjector:
    """Projects internal service events to teacher notifications."""
    
    def __init__(
        self,
        repository: RepositoryProtocol,
        publisher: EventPublisherProtocol,
    ) -> None:
        self.repository = repository
        self.publisher = publisher
    
    async def handle_internal_event(self, event: InternalEventType) -> None:
        """Map internal event to teacher notification if needed."""
        
        # 1. Determine if teacher needs notification
        if not self._should_notify_teacher(event):
            return
        
        # 2. Fetch teacher context
        teacher_id = await self._get_teacher_id(event)
        if not teacher_id:
            logger.warning(f"No teacher found for event {event.event_id}")
            return
        
        # 3. Build notification payload
        payload = self._build_notification_payload(event)
        
        # 4. Publish notification event
        notification = TeacherNotificationRequestedV1(
            teacher_id=teacher_id,
            notification_type="specific_notification_type",
            category=NotificationCategory.APPROPRIATE_CATEGORY,
            priority=NotificationPriority.APPROPRIATE_PRIORITY,
            payload=payload,
            action_required=False,
            correlation_id=event.event_id,
            batch_id=event.batch_id if hasattr(event, "batch_id") else None,
        )
        
        await self.publisher.publish(notification)
        
        logger.info(
            f"Published teacher notification",
            extra={
                "teacher_id": teacher_id,
                "notification_type": notification.notification_type,
                "correlation_id": event.event_id,
            }
        )
    
    def _should_notify_teacher(self, event: InternalEventType) -> bool:
        """Determine if this event warrants teacher notification."""
        # Service-specific logic
        return True
    
    async def _get_teacher_id(self, event: InternalEventType) -> Optional[str]:
        """Resolve teacher ID from event context."""
        # Service-specific resolution
        # Example: fetch from repository based on batch_id
        entity = await self.repository.get(event.entity_id)
        return entity.teacher_id if entity else None
    
    def _build_notification_payload(self, event: InternalEventType) -> Dict[str, Any]:
        """Build safe, UI-ready payload."""
        return {
            # Only include what UI needs
            # Filter sensitive data
            # Format for display
        }
```

### Step 3: Wire Projectors in Services

#### Update DI Container (`services/{service_name}/di.py`)

```python
from .notification_projector import NotificationProjector

class NotificationProvider(Provider):
    scope = Scope.APP
    
    @provide
    def provide_notification_projector(
        self,
        repository: RepositoryProtocol,
        publisher: EventPublisherProtocol,
    ) -> NotificationProjector:
        return NotificationProjector(repository, publisher)
```

#### Update Event Processor to Call Projector

```python
class EventProcessor:
    def __init__(
        self,
        # ... existing deps
        notification_projector: NotificationProjector,
    ):
        self.notification_projector = notification_projector
    
    async def handle_internal_event(self, event: InternalEvent) -> None:
        # ... existing business logic
        
        # Project to notification if needed
        await self.notification_projector.handle_internal_event(event)
```

### Step 4: Update WebSocket Service

Location: `services/websocket_service/implementations/domain_event_processor.py`

```python
from common_core.events.notification_events import TeacherNotificationRequestedV1

class DomainEventProcessor(EventProcessorProtocol):
    """Routes ONLY teacher notification events."""
    
    def _build_routes(self) -> Dict[str, Tuple[Type[BaseModel], Callable]]:
        return {
            # Single route for all teacher notifications
            "huleedu.notification.teacher.requested.v1": (
                TeacherNotificationRequestedV1,
                self.notification_handler.handle_teacher_notification,
            ),
            # NO internal event routes
        }
```

Location: `services/websocket_service/implementations/user_notification_handler.py`

```python
async def handle_teacher_notification(
    self, 
    event: TeacherNotificationRequestedV1
) -> None:
    """Handle unified teacher notification event."""
    
    await self._publish_notification(
        user_id=event.teacher_id,
        event_type=event.notification_type,
        data={
            **event.payload,
            "category": event.category,
            "priority": event.priority,
            "action_required": event.action_required,
            "deadline": event.deadline_timestamp.isoformat() if event.deadline_timestamp else None,
        },
        category=event.category,
        priority=event.priority,
    )
```

### Step 5: Update WebSocket Config

```python
class Settings:
    @property
    def get_subscribed_topics(self) -> List[str]:
        """Subscribe ONLY to notification events."""
        return [
            "huleedu.notification.teacher.requested.v1",
            # NO internal event topics
        ]
```

## Service Implementation Priority

1. **Class Management Service** - CRITICAL events (24-hour deadlines)
2. **Batch Orchestrator Service** - Core workflow visibility
3. **File Service** - Upload feedback loop
4. **Result Aggregator Service** - Results delivery
5. **Assessment Services** - Progress tracking

## Testing Strategy

### Unit Tests
```python
async def test_notification_projector_maps_event():
    """Test that internal events map to correct notifications."""
    projector = NotificationProjector(mock_repo, mock_publisher)
    
    internal_event = SomeInternalEvent(...)
    await projector.handle_internal_event(internal_event)
    
    mock_publisher.publish.assert_called_once()
    notification = mock_publisher.publish.call_args[0][0]
    assert notification.notification_type == "expected_type"
    assert notification.teacher_id == "expected_teacher"
```

### Integration Tests
```python
async def test_end_to_end_notification_flow():
    """Test: Internal Event → Projector → Notification → WebSocket."""
    # Trigger internal event
    # Verify notification published
    # Verify WebSocket receives and routes
```

### Security Tests
```python
async def test_teacher_authorization():
    """Ensure only authorized teacher receives notifications."""
    # Test that projector validates teacher ownership
    # Test that wrong teacher_id is rejected
```

## WebSocket Service Refactoring Requirements

### Current State Analysis

The WebSocket service currently handles 5 internal domain events directly:
- `BatchFileAddedV1` / `BatchFileRemovedV1` (File Service)
- `BatchContentProvisioningCompletedV1` (Batch Orchestrator)
- `ValidationTimeoutProcessedV1` (Class Management)
- `ClassCreatedV1` (Class Management)

### Required Refactoring

#### 1. Remove Internal Event Imports

**File**: `services/websocket_service/implementations/domain_event_processor.py`

Remove:
```python
from common_core.events.batch_coordination_events import (
    BatchContentProvisioningCompletedV1,
)
from common_core.events.class_events import (
    ClassCreatedV1,
)
from common_core.events.file_management_events import (
    BatchFileAddedV1,
    BatchFileRemovedV1,
)
from common_core.events.validation_events import (
    ValidationTimeoutProcessedV1,
)
```

Add:
```python
from common_core.events.notification_events import TeacherNotificationRequestedV1
```

#### 2. Replace Event Routes

**File**: `services/websocket_service/implementations/domain_event_processor.py`

Replace entire `_build_routes()` method:
```python
def _build_routes(self) -> Dict[str, Tuple[Type[BaseModel], Callable]]:
    """Build routing table - ONLY teacher notification events."""
    return {
        "huleedu.notification.teacher.requested.v1": (
            TeacherNotificationRequestedV1,
            self.notification_handler.handle_teacher_notification,
        ),
    }
```

#### 3. Update Notification Handler

**File**: `services/websocket_service/implementations/user_notification_handler.py`

Remove all specific event handlers:
- `handle_batch_file_added()`
- `handle_batch_file_removed()`
- `handle_batch_content_provisioning_completed()`
- `handle_validation_timeout_processed()`
- `handle_class_created()`

Replace with single handler:
```python
async def handle_teacher_notification(
    self, 
    event: TeacherNotificationRequestedV1
) -> None:
    """Handle unified teacher notification event."""
    
    await self._publish_notification(
        user_id=event.teacher_id,
        event_type=event.notification_type,
        data={
            **event.payload,
            "category": event.category.value,
            "priority": event.priority.value,
            "action_required": event.action_required,
            "deadline": event.deadline_timestamp.isoformat() if event.deadline_timestamp else None,
        },
        category=event.category,
        priority=event.priority,
    )
```

#### 4. Update Protocols

**File**: `services/websocket_service/protocols.py`

Remove `UserNotificationHandlerProtocol` specific methods and replace with:
```python
class UserNotificationHandlerProtocol(Protocol):
    """Protocol for user notification handler - notification layer."""
    
    async def handle_teacher_notification(
        self, event: TeacherNotificationRequestedV1
    ) -> None: ...
```

#### 5. Clean Up Config

**File**: `services/websocket_service/config.py`

Remove all internal event topic properties:
- `BATCH_FILE_ADDED_TOPIC`
- `BATCH_FILE_REMOVED_TOPIC`
- `BATCH_CONTENT_PROVISIONING_COMPLETED_TOPIC`
- `VALIDATION_TIMEOUT_PROCESSED_TOPIC`
- `CLASS_CREATED_TOPIC`

Add single notification topic:
```python
@property
def TEACHER_NOTIFICATION_TOPIC(self) -> str:
    """Teacher notification event topic."""
    return "huleedu.notification.teacher.requested.v1"

def get_subscribed_topics(self) -> list[str]:
    """Get list of Kafka topics to subscribe to."""
    return [self.TEACHER_NOTIFICATION_TOPIC]
```

#### 6. Update Tests

**File**: `services/websocket_service/tests/test_file_notifications.py`

Rename to: `test_teacher_notifications.py`

Update all tests to use `TeacherNotificationRequestedV1` instead of internal events.

Example test:
```python
async def test_handle_teacher_notification(self) -> None:
    """Test handling of teacher notification event."""
    redis_client = AsyncMock()
    handler = UserNotificationHandler(redis_client=redis_client)
    
    event = TeacherNotificationRequestedV1(
        teacher_id="teacher-123",
        notification_type="batch_processing_completed",
        category=NotificationCategory.BATCH_PROGRESS,
        priority=NotificationPriority.HIGH,
        payload={
            "batch_id": "batch-456",
            "batch_name": "Essay Batch 1",
            "status": "completed",
        },
        action_required=False,
        correlation_id="event-789",
    )
    
    await handler.handle_teacher_notification(event)
    
    redis_client.publish_user_notification.assert_called_once()
```

#### 7. Update Startup

**File**: `services/websocket_service/startup_setup.py`

Ensure DI container only provides simplified handlers without internal event dependencies.

### Files to Delete

- Remove any remaining legacy notification handlers if they exist
- Remove internal event type imports from `__init__.py` files

### Files to Update Summary

| File | Changes |
|------|---------|
| `domain_event_processor.py` | Remove internal events, single route |
| `user_notification_handler.py` | Single unified handler |
| `protocols.py` | Simplified protocol |
| `config.py` | Single notification topic |
| `test_file_notifications.py` | Rename and update tests |
| `test_kafka_consumer_integration.py` | Update integration tests |

## Migration Checklist

- [ ] Create `TeacherNotificationRequestedV1` in common_core
- [ ] Implement Class Management `notification_projector.py`
- [ ] Implement Batch Orchestrator `notification_projector.py`
- [ ] Implement File Service `notification_projector.py`
- [ ] Implement Result Aggregator `notification_projector.py`
- [ ] Implement Assessment Services `notification_projector.py`
- [ ] Update WebSocket service to consume only notification events
- [ ] Remove all internal event routes from WebSocket
- [ ] Add comprehensive tests for each projector
- [ ] Verify E2E flow for CRITICAL 24-hour notifications
- [ ] Update monitoring to track notification delivery

## Success Metrics

- Zero internal events consumed by WebSocket service
- All 15 notification types implemented and tested
- 100% teacher ownership validation before notification
- Clean separation between domain and notification concerns
- Type safety maintained throughout

## Anti-Patterns to Avoid

❌ **Don't**: Consume internal events in WebSocket service
❌ **Don't**: Add user_id to internal events for notification purposes
❌ **Don't**: Mix business logic with notification logic
❌ **Don't**: Send unfiltered internal data to UI
❌ **Don't**: Skip teacher authorization checks

✅ **Do**: Keep notification logic in dedicated projectors
✅ **Do**: Validate teacher ownership at service level
✅ **Do**: Filter and format data for UI consumption
✅ **Do**: Use single notification event type
✅ **Do**: Maintain clear separation of concerns