# WebSocket Teacher Notification Layer Implementation

## Executive Summary

Implement a clean notification projection pattern that separates internal service events from teacher-facing notifications. Each service owns its notification decisions through dedicated projectors, and the WebSocket service becomes a simple notification router.

**Latest Update (2025-08-07)**: BOS notification projector implemented - teachers now receive immediate feedback when triggering pipeline execution. Architecture validated: clean client-triggered design with no automatic pipeline triggers.

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

### Canonical Pattern: Direct Invocation (NO Kafka Round-trip)

**MANDATORY**: All notification projectors MUST use direct invocation pattern to avoid Kafka round-trips and ensure immediate notifications.

```python
# CANONICAL PATTERN - services/*/implementations/event_publisher_impl.py
async def publish_domain_event(self, event_data, correlation_id):
    # Step 1: Publish domain event for service coordination
    await self.outbox_manager.publish_to_outbox(event_data)
    
    # Step 2: DIRECTLY invoke notification projector (NO Kafka consumption)
    if self.notification_projector:
        # Option A: Event has user_id directly
        await self.notification_projector.handle_event(event_data)
        
        # Option B: Resolve user_id from repository
        user_id = await self.resolve_user_id(event_data)
        if user_id:
            await self.notification_projector.handle_event(event_data, user_id)
```

**Benefits**:
- ✅ Immediate notifications (no Kafka delay)
- ✅ No duplicate processing concerns
- ✅ Simpler testing (mock projector directly)
- ✅ Service owns notification decisions

**Anti-pattern to AVOID**:
```python
# ❌ NEVER create separate Kafka consumers for notifications
# ❌ NEVER consume your own events back from Kafka
# ❌ This adds latency and complexity
```

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

## Success Metrics (Current Status)

- ✅ Zero internal events consumed by WebSocket service  
- ✅ 10/10 notification types implemented (Class Mgmt: 4, File: 3, ELS: 2, BOS: 1)
- ✅ 100% teacher ownership validation before notification
- ✅ Clean separation between domain and notification concerns
- ✅ Complete E2E integration testing with 100% pass rate (13/13 tests)
- ✅ Client-triggered pipeline initiation notification implemented (BOS)
- ❌ Missing: Results completion notifications (RAS - needs event emission)

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

## ✅ PHASES 1-2 COMPLETED: Complete WebSocket Infrastructure + E2E Integration

### WebSocket Service Refactoring ✅ COMPLETED
```python
# NotificationEventConsumer - Kafka → Redis pipeline
- Consumes: huleedu.notification.teacher.requested.v1 (single topic)  
- Idempotent: huleedu_service_libs.idempotency_v2 with Redis backup
- Handler: NotificationHandler.handle_teacher_notification()
- Architecture: Pure forwarder, NO business logic, trusts service teacher_id

# NotificationHandler - Redis publishing
- Forwards TeacherNotificationRequestedV1 → publish_user_notification()
- Preserves: priority, category, action_required, payload structure
- Error handling: observability stack integration
```

### Batch Orchestrator Service Notification ✅ COMPLETED

**Implementation Details**:
- **File**: `/services/batch_orchestrator_service/notification_projector.py`
- **Trigger Point**: `ClientPipelineRequestHandler` line 279-291
- **Pattern**: Direct projector invocation (no Kafka round-trip)
- **Priority**: LOW (progress tracking notification)
- **Category**: BATCH_PROGRESS
- **Payload**: Includes requested/resolved pipeline, first phase, total phases
- **User Resolution**: Direct from `batch_context.user_id`

**Architecture Validation**:
```python
# Key findings from investigation:
1. ClientBatchPipelineRequestV1 is the ONLY pipeline trigger
2. NO automatic pipeline triggers exist anywhere
3. BatchEssaysReady handler ONLY stores essays (never initiates)
4. READY_FOR_PIPELINE_EXECUTION requires explicit client action
5. Comments added to prevent future confusion
```

### Complete E2E Integration Testing ✅ COMPLETED  
```python
# /tests/functional/test_e2e_websocket_integration.py
- Tests: Complete pipeline TeacherNotificationRequestedV1 → Kafka → WebSocket → Redis
- Coverage: All 10 notification types across 4 services (File, Class Mgmt, ELS, BOS)
- Parameterized: Priority compliance (LOW/STANDARD/HIGH/IMMEDIATE), action_required flags
- Results: 13/13 tests passing, 0.23s execution time
- Validation: WebSocket service correctly processes and forwards all notification types

# Key Test Architecture
- Kafka producer: Publishes TeacherNotificationRequestedV1 with proper serialization
- Redis subscriber: Validates complete notification structure and content
- Service builders: File/Class/ELS-specific notification construction
- Idempotency: Duplicate handling through WebSocket service layer
```

### Architecture Achievement & Lessons ✅ COMPLETED
1. **Production Pipeline**: Tests actual Kafka→WebSocket→Redis flow vs Redis-direct bypass
2. **False Confidence Elimination**: Removed `/test_e2e_file_service_notifications.py` (bypassed WebSocket service)
3. **Service Integration Validated**: WebSocket service processes all 9 notification types correctly  
4. **Performance**: Complete E2E faster than previous Redis-only tests (0.22s vs 0.4s+)

## PHASE 3: Remaining Service Projectors (PENDING)

## ULTRATHINK: Remaining Implementation Analysis

**Current State**: Complete E2E integration validated - all 9 notification types flow correctly through Kafka→WebSocket→Redis pipeline. WebSocket service is pure notification router with 100% test coverage.

**Architecture Status**:
- ✅ **Infrastructure**: Event contracts, WebSocket router, E2E validation complete
- ✅ **Service Coverage**: Class Management (4 notifications) + File Service (3 notifications) 
- ❌ **Missing**: Essay Lifecycle Service (2 notifications) - batch phase completions

**Implementation Priority & Complexity Analysis**:

### File Service Projector ✅ COMPLETED

```python
# Direct invocation: event_publisher_impl.py → notification_projector.py 
- CANONICAL PATTERN: publish_domain_event() + direct projector.handle_*()
- 3 notifications: batch_files_uploaded (STANDARD), batch_file_removed (STANDARD), batch_validation_failed (IMMEDIATE)
- User attribution: file_uploads.user_id (migration f3ce45362241) for validation failures
- Test coverage: 19/19 passing (unit/integration/E2E)
```

### 1. Essay Lifecycle Service (ELS) ✅ COMPLETED

```python
# Implementation: /services/essay_lifecycle_service/notification_projector.py
- batch_spellcheck_completed → LOW priority (PhaseName.SPELLCHECK)
- batch_cj_assessment_completed → STANDARD priority (PhaseName.CJ_ASSESSMENT)
# Direct invocation: batch_phase_coordinator_impl.py:324-329
# User resolution: batch_tracker.get_batch_status() → user_id
# E2E validated: All ELS notifications flow correctly through pipeline
```

### 2. Batch Orchestrator Service ✅ COMPLETED

**Implementation**: `/services/batch_orchestrator_service/notification_projector.py`
```python
# Notification Flow:
1. Teacher clicks "Start Processing" → POST /v1/batches/{batch_id}/pipelines
2. API Gateway → ClientBatchPipelineRequestV1 → Kafka
3. BOS ClientPipelineRequestHandler processes request
4. Pipeline initiated via phase_coordinator
5. NotificationProjector.handle_batch_processing_started() called directly
6. TeacherNotificationRequestedV1 published with LOW priority

# Key Architecture Findings:
- ✅ ClientBatchPipelineRequestV1 handler exists and is the ONLY pipeline trigger
- ✅ NO automatic pipeline triggers found (clean client-controlled design)
- ✅ Notification injected at optimal point (line 279-291 in handler)
- ✅ Comments added for clarity on client-triggered pattern
```

### 3. Result Aggregator Service - EVENT EMISSION ARCHITECTURE NEEDED

**Deep Dive Required**: RAS needs Kafka producer pattern implementation
```python
# Current: Pure consumer service - no event emission capability
# Required Events (Service Coordination):
- spellcheck_results_aggregated → AI Feedback dependency
- cj_assessment_results_aggregated → AI Feedback dependency
- results_export_completed → Client notification

# Implementation Pattern Needed:
1. Add OutboxManager pattern (like other services)
2. Create event_publisher_impl.py with Kafka publishing
3. Emit events when results aggregation completes
4. Add notification projector for teacher notifications
```

## IMPLEMENTATION PLAN: Next Priorities

**Phase 3A - BOS Pipeline Initiation** ✅ COMPLETED
- **Scope**: Added `batch_processing_started` notification for client-triggered pipelines
- **Investigation**: Confirmed ClientBatchPipelineRequestV1 handler is sole pipeline trigger
- **Architecture**: Clean single pipeline initiation path maintained (client-triggered only)
- **Outcome**: Teachers now get immediate feedback when clicking "Start Processing"
- **Tests**: 5 unit tests + 1 E2E test passing, full typecheck validation

**Phase 3B - RAS Event Emission Architecture** (DEEP DIVE)
- **Scope**: Implement Kafka producer pattern in Result Aggregator Service
- **Pattern**: Add OutboxManager + event_publisher_impl.py (mirror other services)
- **Events**: Results aggregation completion events for AI Feedback coordination
- **Outcome**: Enable service coordination and result notifications

**Critical Architectural Questions**:
1. Does BOS have handler for ClientBatchPipelineRequestV1 or is it missing?
2. Are there automatic pipeline triggers after READY_FOR_PIPELINE_EXECUTION?
3. What is correct pattern for adding Kafka producer to RAS?
4. How does RAS determine when aggregation is complete for event emission?

## Implementation Checklist

**Phase 1 & 2 - Infrastructure & Core Services** ✅ COMPLETED
- [x] Create TeacherNotificationRequestedV1 event + topic mapping
- [x] Implement Class Management notification projector (4 notifications)
- [x] Implement File Service projector with user attribution (3 notifications)
- [x] Implement Essay Lifecycle Service projector (2 notifications)
- [x] Refactor WebSocket service to pure notification router
- [x] Complete E2E integration testing - all 9 notification types validated

**Phase 3A - BOS Client-Triggered Pipeline** ✅ COMPLETED
- [x] Investigated ClientBatchPipelineRequestV1 handler in BOS
- [x] Confirmed NO automatic pipeline triggers exist (clean design)
- [x] Implemented batch_processing_started notification with projector pattern
- [x] Added strategic comments for client-triggered clarity
- [x] Tested with 5 unit tests + E2E integration test

**Phase 3B - RAS Event Emission** (DEEP DIVE)
- [ ] Analyze RAS architecture for event emission points
- [ ] Implement OutboxManager pattern in RAS
- [ ] Create event_publisher_impl.py with Kafka producer
- [ ] Add results completion events for service coordination
- [ ] Implement notification projector for result notifications
