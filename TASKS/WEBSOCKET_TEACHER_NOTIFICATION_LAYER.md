# WebSocket Teacher Notification Layer Implementation

## Executive Summary

Implement a clean notification projection pattern that separates internal service events from teacher-facing notifications. Each service owns its notification decisions through dedicated projectors, and the WebSocket service becomes a simple notification router.

## ✅ PHASE 1 COMPLETED: Infrastructure & Class Management Integration

### Implemented Components
```python
# TeacherNotificationRequestedV1 in common_core/events/notification_events.py
class TeacherNotificationRequestedV1(BaseModel):
    teacher_id: str  # Explicit teacher routing
    notification_type: str  # One of 15 defined types
    category: WebSocketEventCategory  # UI grouping
    priority: NotificationPriority  # 5-tier: CRITICAL/IMMEDIATE/HIGH/STANDARD/LOW
    payload: Dict[str, Any]  # Type-specific data
    action_required: bool = False
    deadline_timestamp: Optional[datetime] = None
    correlation_id: str  # Links to originating event
    batch_id: Optional[str] = None
    class_id: Optional[str] = None

# NotificationProjector in class_management_service/notification_projector.py
- handle_class_created() → STANDARD priority
- handle_student_created() → LOW priority (fetches teacher via class_id)
- handle_validation_timeout_processed() → IMMEDIATE priority
- handle_student_associations_confirmed() → HIGH priority (fetches teacher via class_id)
```

### Key Lessons Learned
1. **Platform is TEACHER-CENTRIC**: No student accounts, all notifications go to teachers
2. **User Resolution Pattern**: Events with class_id require repository lookup for teacher_id
3. **Trust Boundary**: WebSocket trusts teacher_id in notifications (services are trusted)
4. **Event Categories**: Critical for UI grouping and filtering

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

### Step 1: Create Notification Event Contract ✅ COMPLETED

Created `TeacherNotificationRequestedV1` in `libs/common_core/src/common_core/events/notification_events.py` with teacher_id routing, 5-tier priority system (CRITICAL/IMMEDIATE/HIGH/STANDARD/LOW), type-specific payload, action tracking with deadlines, and correlation IDs. Added to `event_enums.py` with topic mapping `"huleedu.notification.teacher.requested.v1"`.

### Step 2: Implement Service Projectors ✅ COMPLETED (Class Management)

Implemented `NotificationProjector` in `/services/class_management_service/notification_projector.py` with 4 handlers:
- `handle_class_created()` → STANDARD priority (direct user_id)
- `handle_student_created()` → LOW priority (fetches teacher via class_id lookup)
- `handle_validation_timeout_processed()` → IMMEDIATE priority (direct user_id)
- `handle_student_associations_confirmed()` → HIGH priority (fetches teacher via class_id lookup)

Key pattern: Events without user_id require repository lookup via class_id to resolve teacher_id. Wired into DI container and service implementation with `notification_projector` parameter.

### Step 3: Wire Projectors in Services ✅ COMPLETED (Class Management)

Added `NotificationProjector` to DI container in `services/class_management_service/di.py` with `provide_notification_projector()` method. Injected into `ClassManagementServiceImpl` constructor with optional parameter. Service calls projector after publishing domain events: `await self.notification_projector.handle_class_created(event_data)`.

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

## Testing Strategy ✅ COMPLETED (Class Management)

Created comprehensive behavioral tests in `/services/class_management_service/tests/unit/test_notification_projector.py` with 8 test cases covering:
- Event projection to correct priority levels (STANDARD/LOW/IMMEDIATE/HIGH)
- Teacher ID resolution via repository lookups for events without user_id
- Edge cases: missing class IDs, non-existent classes, publishing errors
- 100% pass rate following test creation methodology rule 075

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

## ✅ PHASE 2 COMPLETED: WebSocket Service Refactoring

### Implemented Components ✅ COMPLETED
```python
# NEW: notification_event_consumer.py
class NotificationEventConsumer(NotificationEventConsumerProtocol):
    - Consumes ONLY: topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    - Idempotent processing with huleedu_service_libs.idempotency_v2
    - Single handler: handle_teacher_notification()
    - Graceful Redis failure resilience

# NEW: notification_handler.py  
class NotificationHandler(NotificationHandlerProtocol):
    - Pure forwarder: NO business logic, NO authorization
    - Forwards to Redis: publish_user_notification(event.teacher_id, ...)
    - Trusts teacher_id from services (trusted boundary)
    - Structured error handling with observability stack
```

### Key Architecture Achievements ✅ COMPLETED
- **Pure Router**: WebSocket service has NO business logic, NO event filtering  
- **Single Event Type**: Consumes only `TeacherNotificationRequestedV1` events
- **Idempotency Protection**: Redis-backed duplicate detection with graceful degradation
- **Clean Separation**: Internal domain events completely separated from notifications

### Comprehensive Testing ✅ COMPLETED  
- **59/59 tests passing**: Full WebSocket service test coverage
- **8 idempotency tests**: Both happy path (Redis working) and resilience path (Redis failures)
- **Behavioral testing methodology**: Rule 075 compliance - tests outcomes, not implementation details
- **Integration tests**: End-to-end notification flow from Kafka to Redis

### Lessons Learned ✅ COMPLETED
1. **Test Behavioral Outcomes**: Verify handler called/not called, not Redis call patterns
2. **Idempotency Resilience**: System gracefully degrades when Redis fails - continues processing  
3. **Implementation vs Behavior**: Rule 075 - test actual behavior and side effects, avoid fragile implementation testing
4. **Architecture Validation**: WebSocket service successfully transformed to pure notification router

## PHASE 3: Remaining Service Projectors (PENDING)

## ULTRATHINK: Next Phase Analysis

**Current State**: WebSocket service refactoring complete - pure notification router consuming only `TeacherNotificationRequestedV1` events with comprehensive idempotency testing.

**Next Priority**: Implement notification projectors for remaining services following established Class Management pattern.

**Implementation Order**: File Service → Assessment Services (via ELS) → Batch Orchestrator → Result Aggregator (RAS is most complex - emits phase events for AI Feedback Service coordination)

### File Service Projector ✅ COMPLETED

**Implementation**: Direct invocation pattern matching Class Management Service

```python
# services/file_service/notification_projector.py
class FileServiceNotificationProjector:
    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None:
        # Direct user_id from event → STANDARD priority
        await self.kafka_publisher.publish(envelope)
    
    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None:
        # Direct user_id from event → STANDARD priority
        
    async def handle_essay_validation_failed(self, event: EssayValidationFailedV1, user_id: str) -> None:
        # user_id from file_uploads table lookup → IMMEDIATE priority
```

**Architecture Decision**: Option 2 - Persistent user attribution in `file_uploads` table
- Migration: `20250106_0001_add_file_uploads_table.py` (NOT YET APPLIED)
- Repository: `FileRepository` with full CRUD operations
- Integration: `DefaultEventPublisher` directly calls projector after outbox (same as Class Management)

**Key Pattern Difference**: File Service stores user_id in database for:
- Audit trail compliance
- Retry resilience (user context preserved)
- Validation failure notifications (EssayValidationFailedV1 lacks user_id)

**Status**: 6/6 unit tests passing, migration pending application

### Assessment Services (SECOND - 3 notifications via ELS)

**Priority**: HIGH - ELS already aggregates essay-level results into batch outcomes

**Current State**: 
- ✅ Essay-level events exist: `SpellcheckResultDataV1`, `CJAssessmentCompletedV1`, `AIFeedbackResultDataV1`
- ✅ ELS aggregates into `ELSBatchPhaseOutcomeV1` events  
- ❌ Missing notification projector to convert `ELSBatchPhaseOutcomeV1` to teacher notifications

**Target Notifications**:
- `batch_spellcheck_completed` → LOW priority (spellcheck phase complete)
- `batch_cj_assessment_completed` → STANDARD priority (CJ assessment phase complete)  
- `batch_ai_feedback_completed` → STANDARD priority (AI feedback phase complete)

**Implementation Pattern**: 
- ELS notification projector listens to `ELSBatchPhaseOutcomeV1` events
- Maps phase names to specific notification types
- Requires batch repository lookup for teacher_id resolution

### Batch Orchestrator (THIRD - 3 notifications)  

**Current State**:
- ✅ ELS publishes batch lifecycle events: `BatchContentProvisioningCompletedV1`, `ELSBatchPhaseOutcomeV1`
- ❌ Missing notification projector to convert lifecycle events to teacher notifications

**Target Notifications**:
- `batch_processing_started` → STANDARD (triggered by `BatchContentProvisioningCompletedV1`)
- `batch_processing_completed` → HIGH (triggered by final `ELSBatchPhaseOutcomeV1`)
- `batch_processing_failed` → IMMEDIATE (triggered by failed `ELSBatchPhaseOutcomeV1`)

### Result Aggregator (LAST - Results Events + 3 notifications)

**Status**: ❌ BLOCKED - No event emission capability, depends on all other services

**Critical Architecture**: RAS emits **results completion events** for service coordination with AI Feedback Service

**Missing Implementation**:
- RAS consumes events but doesn't emit results completion or aggregation completion events
- CJ Assessment pipeline completion handling not yet implemented  
- Results completion events needed for AI Feedback Service dependency chain
- Needs event emission added for both service coordination AND teacher notifications

**Results Completion Events** (Service Coordination):
- `spellcheck_results_completed` / `spellcheck_results_partially_completed` → AI Feedback dependency  
- `cj_assessment_results_completed` / `cj_assessment_results_partially_completed` → AI Feedback dependency
- `nlp_results_completed` / `nlp_results_partially_completed` → AI Feedback dependency
- `grammar_results_completed` / `grammar_results_partially_completed` → AI Feedback dependency

**Teacher Notification Events**:
- `batch_results_ready` → HIGH priority (when all assessment results aggregated and available)
- `batch_export_completed` → STANDARD priority (export operations completed)
- `batch_analysis_available` → STANDARD priority (analysis reports ready for viewing)

**AI Feedback Service Dependency**: AI Feedback listens to RAS results completion events, collects curated assessment data from RAS, creates dynamic feedback prompts for LLM Provider Service

## Implementation Checklist

- [x] Create TeacherNotificationRequestedV1 event
- [x] Add to event_enums.py with topic mapping
- [x] Update websocket_enums.py with 5-tier priorities
- [x] Implement Class Management notification projector
- [x] Wire projector into Class Management DI
- [x] Create comprehensive behavioral tests
- [x] Refactor WebSocket to consume only notifications ✅ COMPLETED
- [x] Remove all internal event handling from WebSocket ✅ COMPLETED
- [x] Implement idempotency testing with behavioral methodology ✅ COMPLETED
- [ ] Implement File Service projector (FIRST - has direct user_id events)
- [ ] Implement Assessment Services projectors (SECOND - ELS batch aggregation via ELSBatchPhaseOutcomeV1)  
- [ ] Implement Batch Orchestrator projector (THIRD - lifecycle events from ELS)
- [ ] Implement Result Aggregator projector (LAST - needs event emission capability added)
- [ ] End-to-end integration test
- [ ] Update service READMEs
