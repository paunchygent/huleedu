Claude Session Prompt: File Service Client Traceability - Phase 3

## Session Context

You are continuing work on the HuleEdu microservices platform. In previous sessions, we successfully:
1. Implemented the File Service Client Traceability feature (Phase 1)
2. Created integration tests and enhanced Result Aggregator Service (Phase 2)
3. Fixed integration test failures by correcting event_type field usage in tests

The integration tests are now passing, validating the complete traceability flow from file upload through slot assignment via the `file_upload_id` correlation mechanism.

## Immediate First Action Required ⚠️

Before any other work, you MUST:
1. Run `pdm run typecheck-all` from the repository root
2. Fix any type checking issues found
3. Ensure all 590+ source files pass type checking

## What We've Accomplished So Far

### Phase 1: Core Implementation ✅
- Added `file_upload_id` tracking to all file-related events
- Updated File Service to generate unique tracking IDs
- Modified ELS to publish `EssaySlotAssignedV1` when content is assigned
- Achieved full type safety across all services

### Phase 2: Testing & RAS Enhancement ✅ 
- Created comprehensive integration tests
- Enhanced Result Aggregator Service to track file_upload_id
- Added database migration for RAS
- Documented architectural debt and WebSocket integration design

### Integration Test Fix ✅
- Fixed event_type field in tests (was using class names instead of topic names)
- Removed unnecessary sleep delays after fixing root cause
- All tests now pass reliably and run faster (6.82s vs 17s)

## Current State

### Working Features
- File Service generates unique `file_upload_id` for each upload
- ELS publishes `EssaySlotAssignedV1` events with file → essay mapping
- Result Aggregator Service tracks and exposes file_upload_id in results
- Integration tests validate complete event flow

### Discovered Issues
- **Architectural Debt**: Event publishing is synchronous and blocks business operations
- **Test Coverage Gaps**: Only 46% of File Service tests and 14% of ELS tests include file_upload_id
- **Missing WebSocket Integration**: Real-time notifications not yet implemented

## ULTRATHINK Primary Tasks for This Session

### Task 1: Critical Integration Test Coverage (Use Direct Implementation)

ULTRATHINK the test coverage gaps systematically:

1. **Enhance MockEventPublisher Assertions**
   ```python
   # Current: Events recorded but not validated
   mock_publisher.published_events.append(("essay_slot_assigned", event_data, correlation_id))
   
   # Required: Content validation
   assert event_data.file_upload_id == expected_upload_id
   assert event_data.essay_id == expected_essay_id
   assert event_data.batch_id == batch_id
   assert event_data.text_storage_id == text_storage_id
   ```

2. **Add Error Scenario Tests**
   - Validation failures preserve file_upload_id
   - Duplicate uploads handle tracking correctly
   - Concurrent provisioning maintains correlation

3. **Update Existing Tests**
   - Add file_upload_id to remaining 53% of File Service tests
   - Add file_upload_id to remaining 86% of ELS tests

Files to update:
- `/services/file_service/tests/unit/*.py` (8 files need updates)
- `/services/essay_lifecycle_service/tests/**/*.py` (43 files need updates)

### Task 2: WebSocket Service Integration (Use Agent if Needed)

Use the Task tool with ULTRATHINK to implement:

1. **Event Handler for EssaySlotAssignedV1**
   ```python
   @consumer.subscribe(topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED))
   async def handle_essay_slot_assigned(event: EssaySlotAssignedV1):
       # Notify connected clients about file → essay mapping
       await broadcast_to_batch_subscribers(
           batch_id=event.batch_id,
           event_type="essay.slot.assigned",
           data={
               "file_upload_id": event.file_upload_id,
               "essay_id": event.essay_id,
               "timestamp": event.timestamp
           }
       )
   ```

2. **Client Notification Protocol**
   - Real-time updates when files get assigned to essay slots
   - Handle connection management for batch subscriptions
   - Ensure idempotent message delivery

The agent should:
- Analyze WebSocket service architecture
- Implement Kafka consumer for new event
- Add real-time broadcast logic
- Update tests for new functionality

### Task 3: Frontend Integration Guide (Direct Implementation)

Create comprehensive guide for UI developers:

1. **State Management Updates**
   ```typescript
   interface FileUploadState {
     fileUploadId: string;
     filename: string;
     status: 'uploading' | 'processing' | 'assigned' | 'failed';
     assignedEssayId?: string;
     errorDetail?: ErrorDetail;
   }
   ```

2. **WebSocket Event Handling**
   ```typescript
   socket.on('essay.slot.assigned', (data) => {
     dispatch(updateFileMapping({
       fileUploadId: data.file_upload_id,
       essayId: data.essay_id
     }));
   });
   ```

3. **UI Component Examples**
   - File upload progress with tracking ID
   - Real-time status updates
   - Error display with file identification

Create: `/documentation/FRONTEND_INTEGRATION_GUIDE.md`

## Architecture Rules to Follow

Reference the rule index at `.cursor/rules/000-rule-index.mdc`:

### Critical Rules for This Session
- **Rule 020**: Architectural Mandates - Maintain bounded contexts
- **Rule 030**: Event-Driven Architecture - Kafka for all inter-service communication  
- **Rule 048**: Structured Error Handling - Use ErrorDetail, not strings
- **Rule 050**: Python Standards - No type ignores or casts
- **Rule 052**: Event Contract Standards - Maintain backward compatibility
- **Rule 070**: Testing Standards - Mock at protocol boundaries
- **Rule 084**: Dockerization - All services containerized with proper PYTHONPATH
- **Rule 090**: Documentation Standards - Compress completed tasks, hyper-technical language

### Testing Specific Guidelines
- Run tests from repository root: `pdm run pytest`
- Type check from root: `pdm run mypy services/<service>`
- Use testcontainers for integration tests requiring infrastructure
- Clear Prometheus registry between tests to avoid metric conflicts

## Key Files for Reference

### Event Definitions
- `/libs/common_core/src/common_core/events/essay_lifecycle_events.py` - `EssaySlotAssignedV1` definition
- `/libs/common_core/src/common_core/events/file_events.py` - File event definitions
- `/libs/common_core/src/common_core/event_enums.py` - Topic name mappings

### Implementation Files  
- `/services/essay_lifecycle_service/implementations/event_publisher.py` - `publish_essay_slot_assigned`
- `/services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py` - Slot assignment logic
- `/services/file_service/core_logic.py` - File upload tracking implementation

### Test Files Needing Updates
- `/services/file_service/tests/unit/test_file_validation.py` - Add file_upload_id
- `/services/file_service/tests/unit/test_batch_file_operations.py` - Add tracking assertions
- `/services/essay_lifecycle_service/tests/unit/**/*.py` - Update event constructions

### WebSocket Service
- `/services/websocket_service/kafka_consumer.py` - Add new event handler
- `/services/websocket_service/websocket_handlers.py` - Broadcast logic
- `/services/websocket_service/tests/` - Test new functionality

## Expected Outcomes

By End of Session:
1. **Test Coverage Improved** ✅
   - 80%+ of tests include file_upload_id assertions
   - All MockEventPublisher classes validate event content
   - Error scenarios thoroughly tested
   
2. **WebSocket Integration Complete** ✅
   - EssaySlotAssignedV1 events trigger real-time notifications
   - Clients receive file → essay mapping updates
   - Tests validate broadcast functionality
   
3. **Frontend Guide Created** ✅
   - Complete integration documentation
   - Code examples for all scenarios
   - State management patterns documented

## Development Environment

- Monorepo structure managed by PDM
- PostgreSQL for persistence, Redis for coordination
- Kafka for event streaming  
- Docker Compose for local development
- Strict DDD with protocols/implementations pattern

## Testing Strategy

1. **Unit Test Enhancement**
   - Add content assertions to all event publications
   - Validate file_upload_id preservation
   - Test error scenarios

2. **Integration Test Expansion**
   - Test WebSocket real-time notifications
   - Validate cross-service event correlation
   - Performance test high-concurrency scenarios

3. **Documentation as Tests**
   - Frontend guide includes testable examples
   - Integration patterns documented with code

## ULTRATHINK Analysis Approach

When implementing tasks:

1. **Prioritize Test Coverage**: Tests are documentation and safety net
   - Start with failing tests
   - Implement to make tests pass
   - Refactor with confidence

2. **Maintain Architecture**: Respect service boundaries
   - WebSocket service only broadcasts, doesn't process
   - Frontend guide follows existing patterns
   - No domain logic leakage

3. **Document Everything**: Code tells what, docs tell why
   - Update READMEs when changing services
   - Add inline comments for complex logic
   - Create examples for integration points

## Additional Context

### Event Flow Reminder
```
File Upload → File Service generates file_upload_id
    ↓
EssayContentProvisionedV1 (with file_upload_id)
    ↓
ELS assigns content to essay slot
    ↓
EssaySlotAssignedV1 (file_upload_id → essay_id mapping)
    ↓
RAS updates essay record with file_upload_id
    ↓
WebSocket broadcasts mapping to UI (TO BE IMPLEMENTED)
```

### Common Pitfalls to Avoid
- Don't add file_upload_id to essay creation (it comes later during provisioning)
- Don't bypass event-driven architecture for "convenience"
- Don't forget to update tests when changing event schemas
- Don't use type ignores or casts - fix the root cause

## Mindset for This Session

You're completing the client experience for file traceability. The backend infrastructure is built and tested. Now focus on:

1. **Test Quality** - Make the implicit explicit through assertions
2. **Real-time Experience** - WebSocket integration for immediate feedback
3. **Developer Experience** - Clear, actionable frontend guide

Use agents for research and complex implementations, but implement test updates directly. The goal is 100% confidence in the traceability feature before production deployment.

Remember: We've built the infrastructure. Now we're making it bulletproof and user-facing.