Claude Session Prompt: File Service Client Traceability - Phase 3 WebSocket Integration

## Session Context

You are continuing work on the HuleEdu microservices platform. In previous sessions, we successfully completed the core File Service Client Traceability feature implementation and significantly enhanced test coverage. We are now in the **final phase of Phase 3: WebSocket Integration and Frontend Guide**.

### Previous Session Accomplishments ✅
1. **Documentation Cleanup**: Fixed AI-slop migration language in WebSocket integration documents, adhering to NO BACKWARDS COMPATIBILITY rule
2. **Type Safety**: Ensured all 593 source files pass `pdm run typecheck-all` 
3. **Test Coverage Enhancement**: 
   - Enhanced MockEventPublisher assertions across ELS distributed tests to validate `file_upload_id` presence and content
   - Updated File Service tests to include comprehensive `file_upload_id` assertions in all event-related tests
   - Verified ELS tests were already compliant with traceability requirements
4. **Code Quality**: Applied linting fixes and maintained coding standards across all modified files

## Immediate First Action Required ⚠️

Before any other work, you MUST:
1. Run `pdm run typecheck-all` from the repository root
2. Fix any type checking issues found  
3. Ensure all 593+ source files pass type checking

## Current Implementation Status

### ✅ COMPLETED - Core Infrastructure
- **File Service**: Generates unique `file_upload_id` for each upload
- **ELS**: Publishes `EssaySlotAssignedV1` events with file → essay mapping  
- **RAS**: Tracks and exposes `file_upload_id` in all essay result responses
- **Integration Tests**: Complete E2E validation (6.82s runtime, passing)
- **Test Coverage**: Comprehensive file_upload_id assertions across all services

### ✅ COMPLETED - Phase 3 Test Coverage
```
File Service:     [██████████] 100% (All event tests include file_upload_id)
ELS:             [██████████] 100% (All MockEventPublisher classes validate file_upload_id)  
Integration:     [██████████] 100% (E2E tests complete and optimized)
Event Validation: [██████████] 100% (All event content properly asserted)
```

### 🔄 REMAINING - WebSocket Integration & Frontend Guide

## ULTRATHINK Primary Tasks for This Session

### Task 1: WebSocket Service Integration (Use Direct Implementation - HIGH PRIORITY)

ULTRATHINK the WebSocket integration systematically:

#### 1.1 Analyze Current WebSocket Architecture
- Review existing WebSocket service patterns in `/services/websocket_service/`
- Understand Redis pub/sub notification system  
- Identify integration points for new event handler

#### 1.2 Implement EssaySlotAssignedV1 Event Handler
```python
# Target implementation in /services/websocket_service/kafka_consumer.py
@consumer.subscribe(topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED))
async def handle_essay_slot_assigned(event: EssaySlotAssignedV1):
    """Handle file → essay mapping notifications for real-time UI updates."""
    # Get user_id from batch context
    batch_info = await get_batch_user_context(event.batch_id)
    
    # Build notification payload
    notification = {
        "event": "essay.slot.assigned",
        "correlation_id": str(event.correlation_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {
            "batch_id": event.batch_id,
            "essay_id": event.essay_id,
            "file_upload_id": event.file_upload_id,
            "text_storage_id": event.text_storage_id,
        }
    }
    
    # Broadcast to user's WebSocket channel
    await broadcast_to_user(batch_info.user_id, notification)
```

#### 1.3 Integration Requirements
- Subscribe to `huleedu.essay.lifecycle.essay.slot.assigned.v1` Kafka topic
- Extract user context for proper channel routing  
- Implement idempotent message delivery
- Add comprehensive error handling for missing user context
- Update DI configuration for new event handler

#### 1.4 Testing Requirements
- Unit tests for event handler logic
- Integration tests for Kafka → WebSocket flow
- Mock Redis pub/sub for testing
- Validate notification payload structure

**Files to modify**:
- `/services/websocket_service/kafka_consumer.py` - Add new event handler
- `/services/websocket_service/websocket_handlers.py` - Update broadcast logic if needed
- `/services/websocket_service/di.py` - Update dependency injection
- `/services/websocket_service/tests/` - Add comprehensive tests

### Task 2: Frontend Integration Guide (Direct Implementation - MEDIUM PRIORITY)

Create comprehensive guide at `/documentation/FRONTEND_INTEGRATION_GUIDE.md`:

#### 2.1 State Management Patterns
```typescript
interface FileUploadState {
  fileUploadId: string;
  filename: string;
  status: 'uploading' | 'processing' | 'assigned' | 'failed';
  assignedEssayId?: string;
  errorDetail?: ErrorDetail;
  timestamp: string;
}

interface BatchState {
  batchId: string;
  fileUploads: Map<string, FileUploadState>;
  essaySlots: Map<string, EssaySlot>;
}
```

#### 2.2 WebSocket Event Handling
```typescript
// WebSocket event subscription
socket.on('essay.slot.assigned', (data) => {
  dispatch(updateFileMapping({
    fileUploadId: data.file_upload_id,
    essayId: data.essay_id,
    status: 'assigned',
    timestamp: data.timestamp
  }));
  
  // Show user notification
  showNotification(`File assigned to essay slot`, {
    filename: getFilename(data.file_upload_id),
    essayId: data.essay_id
  });
});
```

#### 2.3 UI Component Examples
- File upload progress with tracking ID display
- Real-time status updates during processing
- Error display with specific file identification
- Batch overview with file → essay mapping visualization

#### 2.4 API Integration Patterns
- RAS API calls for complete traceability data
- Error handling for WebSocket disconnections
- Fallback to polling when real-time fails

## Architecture Rules to Follow

Reference `.cursor/rules/000-rule-index.mdc` for complete rule set:

### Critical Rules for This Session
- **Rule 020**: Architectural Mandates - Maintain service boundaries, no domain logic in WebSocket service
- **Rule 030**: Event-Driven Architecture - Kafka for all inter-service communication
- **Rule 048**: Structured Error Handling - Use ErrorDetail, proper exception patterns
- **Rule 050**: Python Standards - No type ignores or casts, full PEP 484 compliance  
- **Rule 070**: Testing Standards - Mock at protocol boundaries, comprehensive coverage
- **Rule 084**: Dockerization - Proper container configuration and service orchestration
- **Rule 090**: Documentation Standards - Hyper-technical language, code examples

### WebSocket-Specific Guidelines
- WebSocket service is a **pure relay** - no business logic
- Use existing Redis pub/sub patterns for user notifications
- Maintain connection management and reconnection logic
- Implement circuit breakers for Kafka consumer failures

## Key Files for Reference

### Implementation Files
- `/services/websocket_service/kafka_consumer.py` - Kafka event handlers
- `/services/websocket_service/websocket_handlers.py` - WebSocket connection management
- `/services/websocket_service/implementations/` - Service implementations
- `/services/websocket_service/protocols.py` - Service protocols

### Event Definitions
- `/libs/common_core/src/common_core/events/essay_lifecycle_events.py` - `EssaySlotAssignedV1` model
- `/libs/common_core/src/common_core/event_enums.py` - Topic name mappings
- `/libs/common_core/src/common_core/events/__init__.py` - Event exports

### Documentation Templates
- `/documentation/TASKS/WEBSOCKET_INTEGRATION_DESIGN.md` - Technical implementation design
- `/TASKS/WEBSOCKET_FRONTEND_INTEGRATION_GUIDE.md` - Existing frontend patterns

### Testing References
- `/tests/integration/test_file_traceability_e2e.py` - E2E integration patterns
- `/services/websocket_service/tests/` - Existing WebSocket test patterns

## Expected Outcomes

By End of Session:
1. **WebSocket Integration Complete** ✅
   - `EssaySlotAssignedV1` events trigger real-time notifications
   - Teachers see immediate file → essay mapping updates
   - Tests validate complete notification flow
   - Error scenarios properly handled

2. **Frontend Integration Guide Complete** ✅
   - Comprehensive documentation for UI developers
   - Complete code examples for all integration scenarios
   - State management patterns documented with TypeScript
   - WebSocket event handling examples provided

3. **System Validation** ✅
   - End-to-end traceability flow working with real-time notifications
   - All type checking passing
   - Complete test coverage maintained
   - Documentation accurate and actionable

## Development Environment

- **Monorepo**: PDM-managed with strict dependency isolation
- **Infrastructure**: PostgreSQL, Redis, Kafka via Docker Compose
- **Services**: Containerized microservices with Dishka DI
- **Testing**: testcontainers for integration tests, protocol-based mocking
- **Quality**: Ruff linting, MyPy type checking, comprehensive test coverage

## Testing Strategy

### Unit Testing
- Mock Kafka consumers and Redis clients
- Test event handler logic in isolation
- Validate notification payload construction
- Test error scenarios and edge cases

### Integration Testing  
- Use testcontainers for Kafka and Redis
- Test complete event flow: ELS → Kafka → WebSocket → Redis
- Validate user context resolution
- Test connection management and reconnection

### End-to-End Validation
- Extend existing E2E tests to include WebSocket notifications
- Test complete user workflow with real-time updates
- Validate performance under load
- Test failure scenarios and recovery

## ULTRATHINK Analysis Approach

When implementing tasks:

1. **Service Boundary Respect**: WebSocket service only relays, never processes
   - No business logic in WebSocket handlers
   - User context resolution via existing patterns
   - Maintain separation of concerns

2. **Event-Driven Consistency**: Follow established Kafka patterns
   - Use existing topic subscription patterns
   - Maintain event envelope structure
   - Preserve correlation IDs throughout flow

3. **Real-Time User Experience**: Focus on immediate feedback
   - Sub-second notification delivery
   - Graceful handling of disconnections
   - Clear error states and recovery

## Common Pitfalls to Avoid

- Don't add business logic to WebSocket service (it's a pure relay)
- Don't bypass event-driven architecture for "convenience"  
- Don't forget error handling for missing user context
- Don't use synchronous operations in async event handlers
- Don't break existing WebSocket connection patterns

## Success Metrics

- **Notification Latency**: < 500ms from ELS event to UI update
- **Reliability**: 99%+ notification delivery rate  
- **Type Safety**: 100% of code passes type checking
- **Test Coverage**: All new code covered by unit and integration tests
- **Documentation Quality**: Frontend guide enables immediate integration

## Mindset for This Session

You're completing the **user-facing experience** for file traceability. The infrastructure is built, tested, and validated. Now focus on:

1. **Real-Time Notifications** - Teachers see instant feedback when files are assigned
2. **Developer Experience** - Frontend developers have everything needed for integration
3. **Production Readiness** - System is bulletproof and ready for deployment

Remember: We've built the complete traceability infrastructure. Now we're making it come alive for users with real-time notifications and enabling frontend integration.

The next Claude session should focus on implementing these final pieces to complete the File Service Client Traceability feature.