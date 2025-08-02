# NLP Phase 1 Implementation Roadmap

**Status:** STEPS 1-9 COMPLETE, STEP 10 INFRASTRUCTURE COMPLETE, HANDLERS PENDING  
**Approach:** Inside-out (core → features)  
**Last Updated:** 2025-08-02 (Late Evening Session)

## Progress Summary (2025-08-02 Evening)

### ✅ Completed (Steps 1-9)
- **Common Core:** All event models implemented with proper DDD boundaries
- **BOS:** 100% complete - handlers, state transitions, integration tests
- **ELS:** 100% complete - all handlers, event publishing, database migration
- **NLP:** Phase 1 handler fixed - now processes batch events correctly

### ⏳ Infrastructure Complete, Handlers Pending
- **Step 10:** Class Management Kafka infrastructure - INFRASTRUCTURE COMPLETE
- **Remaining:** Event handlers and business logic

## Implementation Order

### Step 1: Fix Core Event Models (30 min) ✅ COMPLETE
**File:** `libs/common_core/src/common_core/events/batch_coordination_events.py`

```python
# BatchContentProvisioningCompletedV1 - line 177
class_id: str | None = Field(  # Make optional
    default=None,
    description="Class ID if REGULAR batch, None if GUEST"
)
```
**Note:** Model exists but still needs the fix to make class_id optional

### Step 2: BOS State Transitions (1 hour) ✅ COMPLETE
**File:** `services/batch_orchestrator_service/implementations/batch_content_provisioning_completed_handler.py`

**Implemented:**
- Handler detects GUEST vs REGULAR batches based on class_id
- For REGULAR: Initiates student matching via phase initiator
- For GUEST: Updates status to READY_FOR_PIPELINE_EXECUTION and stores essays
- All state transitions working correctly in integration tests

### Step 3: BOS Pipeline Validation (30 min) ✅ COMPLETE
**File:** `services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py`

**Verified through tests:**
- Pipeline validation checks batch status before execution
- Only batches in READY_FOR_PIPELINE_EXECUTION state can proceed
- Integration tests confirm proper validation

### Step 4: BOS Student Association Handler (2 hours) ✅ COMPLETE
**File:** `services/batch_orchestrator_service/implementations/student_associations_confirmed_handler.py`

**Implemented:**
- Handler processes StudentAssociationsConfirmedV1 events
- Updates batch status to READY_FOR_PIPELINE_EXECUTION
- Validates batch exists and is in correct state
- Integration with Kafka consumer working
- Phase 1 integration tests passing

### Steps 5-8: ELS Implementation ✅ COMPLETE

**Implemented Components:**
1. **StudentMatchingCommandHandler** - Receives BOS commands, publishes to NLP via outbox
2. **StudentAssociationHandler** - Processes confirmations, publishes BatchEssaysReady
3. **Event Publishing** - ELS correctly publishes BatchContentProvisioningCompletedV1
4. **Database Migration** - Student association fields added to essay_states table

**Key Implementation Details:**
- All handlers use outbox pattern for reliable event delivery
- Proper DDD boundaries maintained (no class_id in ELS events)
- Integration with Kafka consumer and DI complete
- All unit and integration tests passing

### Step 9: NLP Batch Handler ✅ COMPLETE (2025-08-02)
**File:** `services/nlp_service/command_handlers/essay_student_matching_handler.py`

**Implemented:**
- Updated existing handler to listen for `huleedu.batch.student.matching.requested.v1`
- Processes entire batches using `BatchStudentMatchingRequestedV1`
- Collects all essay results and publishes `BatchAuthorMatchesSuggestedV1`
- Added comprehensive error handling for partial failures
- Protocol updated with `publish_batch_author_match_results` method
- All unit and integration tests passing

### Step 10: Class Management Kafka ⏳ INFRASTRUCTURE COMPLETE, HANDLERS PENDING

**✅ Completed Infrastructure:**
- Kafka consumer infrastructure (`kafka_consumer.py`) with idempotent processing
- Event processing router (`event_processor.py`) for event dispatch
- Transactional outbox pattern (`outbox_manager.py`)
- Event publisher updated with outbox pattern
- EventOutbox database model and migration (220aebb1348a)
- CommandHandlerProtocol for event handlers
- All type errors fixed

**❌ Missing Components:**
- Event handler for `BatchAuthorMatchesSuggestedV1` events
- Kafka consumer DI configuration and handler wiring
- Validation API endpoints for teacher approval
- Timeout monitoring mechanism

## Testing Strategy

### Unit Tests First
1. Test state transitions in isolation
2. Mock all external dependencies
3. Verify idempotency

### Integration Tests
1. Test event flow between services
2. Use testcontainers for Kafka
3. Verify state consistency

### E2E Scenario
```python
# Test GUEST flow
1. Register batch without class_id
2. Upload files
3. Verify direct transition to READY
4. Request pipeline execution

# Test REGULAR flow  
1. Register batch with class_id
2. Upload files
3. Verify student matching initiated
4. Simulate validation
5. Verify transition to READY
6. Request pipeline execution
```

## Risk Mitigation

1. **Feature Flag Everything**
   ```python
   if settings.STUDENT_MATCHING_ENABLED:
       # New flow
   else:
       # Old flow
   ```

2. **Parallel Development**
   - BOS team: Steps 1-4
   - ELS team: Steps 5-7
   - NLP team: Step 9
   - Class Mgmt team: Step 10

3. **Incremental Rollout**
   - Deploy BOS changes (harmless without ELS)
   - Deploy ELS changes (backward compatible)
   - Enable feature flag for test batches
   - Monitor metrics
   - General rollout

## Success Metrics

- Zero regression in GUEST batch flow
- REGULAR batches complete student matching < 30s
- 95%+ match accuracy for clear student names
- Zero stuck batches (timeout handling works)
- All state transitions logged with correlation_id

## Next Session: Class Management Event Handlers (CRITICAL)

**Current State:** BOS → ELS → NLP flow complete, Class Management Kafka infrastructure complete

**Infrastructure Ready:**
- ✅ Kafka consumer with idempotent processing  
- ✅ Event processing router for handler dispatch
- ✅ Transactional outbox pattern for reliable publishing
- ✅ Database migration for event storage
- ✅ All type safety verified

**Primary Task:** Complete event handling implementation
- Create `BatchAuthorMatchesHandler` for `BatchAuthorMatchesSuggestedV1` events
- Wire Kafka consumer and handlers in DI configuration  
- Store match suggestions and update batch status
- Implement business logic for student association validation
- Add comprehensive testing for event flow

**Why Critical:** The infrastructure is now complete, but the business logic handlers are needed to process NLP match suggestions and complete the Phase 1 student matching cycle. This is the final implementation step before integration testing.