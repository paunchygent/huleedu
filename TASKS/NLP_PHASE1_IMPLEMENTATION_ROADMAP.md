# NLP Phase 1 Implementation Roadmap

**Status:** STEPS 1-4 COMPLETE, STEP 5 IN PROGRESS  
**Approach:** Inside-out (core → features)  
**Last Updated:** 2025-08-02

## Progress Summary (2025-08-02)

### ✅ Completed Steps
- **Step 1:** Core Event Models - All Phase 1 events added to common_core
- **Step 2:** BOS State Transitions - Handler correctly routes GUEST/REGULAR batches
- **Step 3:** BOS Pipeline Validation - Integration tests verify readiness checks
- **Step 4:** BOS Student Association Handler - Handler implemented and tested

### 🔄 In Progress
- **Step 5:** ELS Command Handler - Next task for implementation

### ❌ Not Started
- Steps 6-10: ELS association handler, event publishing, migrations, NLP handler, Class Management

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

### Step 5: ELS Command Handler (2 hours)
**New File:** `services/essay_lifecycle_service/implementations/student_matching_command_handler.py`

```python
class StudentMatchingCommandHandler:
    async def handle(self, command: BatchServiceStudentMatchingInitiateCommandDataV1):
        # 1. Mark essays as awaiting_student_association
        # 2. Publish BatchStudentMatchingRequestedV1 to NLP
```

### Step 6: ELS Association Handler (2 hours)
**New File:** `services/essay_lifecycle_service/implementations/student_association_handler.py`

```python
class StudentAssociationHandler:
    async def handle(self, event: StudentAssociationsConfirmedV1):
        # 1. Update essay records with student_id
        # 2. Check if all essays have associations
        # 3. Publish BatchEssaysReady for REGULAR batches
```

### Step 7: ELS Publishes New Event (1 hour)
**File:** `services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py`

Replace BatchEssaysReady publication with:
```python
# Publish BatchContentProvisioningCompletedV1 instead
event = BatchContentProvisioningCompletedV1(
    batch_id=batch_id,
    provisioned_count=filled_count,
    expected_count=expected_count,
    course_code=batch_context.course_code,
    user_id=batch_context.user_id,
    essays_for_processing=essays,
    # class_id NOT included - ELS doesn't have it
)
```

### Step 8: Database Migrations (30 min)
**BOS Migration:**
```sql
-- Already done: class_id column exists
```

**ELS Migration:**
```sql
ALTER TABLE processed_essays
ADD COLUMN student_id VARCHAR(255),
ADD COLUMN association_confirmed_at TIMESTAMP,
ADD COLUMN association_method VARCHAR(50);
```

### Step 9: NLP Batch Handler (4 hours)
**New File:** `services/nlp_service/implementations/batch_student_matching_handler.py`

Core logic:
1. Process all essays in parallel
2. Extract student names using multiple strategies
3. Match against class roster
4. Publish BatchAuthorMatchesSuggestedV1

### Step 10: Class Management Kafka (1 day)
1. Create `kafka_consumer.py`
2. Add match suggestion handler
3. Add timeout monitor
4. Create validation API endpoints

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

## Next Session Tasks (Step 5: ELS Command Handler)

### Primary Task: Implement StudentMatchingCommandHandler
**Why this is next:** BOS is now correctly initiating student matching commands, but ELS doesn't have a handler to receive and process them. This is the critical missing link in the Phase 1 flow.

**Implementation checklist:**
1. Create `student_matching_command_handler.py` in ELS
2. Handle `BATCH_STUDENT_MATCHING_INITIATE_COMMAND` from BOS
3. Update batch tracker state to AWAITING_STUDENT_ASSOCIATIONS
4. Publish `BATCH_STUDENT_MATCHING_REQUESTED` to NLP Service
5. Set up 24-hour timeout tracking
6. Add handler to ELS Kafka consumer routing
7. Update ELS DI configuration
8. Write integration tests

### Secondary Tasks (if time permits):
- Fix `BatchContentProvisioningCompletedV1` model (make class_id optional)
- Start on Step 6: ELS Association Handler

**Expected outcomes:**
- ELS can receive and process student matching commands from BOS
- Commands are properly routed to NLP Service for processing
- Integration tests verify the BOS → ELS → NLP flow