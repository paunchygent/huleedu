# Investigation Report: Guest Batch Stuck in `awaiting_content_validation`

## Executive Summary

**Root Cause**: ELS worker encounters a `DBAPIError` when creating essay state records during `BatchEssaysRegistered` event processing, causing the transaction to roll back. This prevents:
1. Essay state records from being created
2. Pending content from being assigned to essay slots  
3. `BatchContentProvisioningCompleted` event from being published
4. Batch state transition to `ready_for_pipeline_execution`

**Impact**: Guest batches cannot progress to pipeline execution, blocking all guest batch workflows.

**Status**: **CONFIRMED BUG** - Database transaction failure leaves batch in inconsistent state

---

## Investigation Timeline

### Test Details
- **Test**: `tests/functional/test_e2e_identity_threading.py::test_complete_identity_threading_workflow`
- **Batch ID**: `278f7fd9-37fe-406a-a735-f15128cb6b1f`
- **Registration Correlation ID**: `9437fe03-1195-4241-b532-91d36df0b1c2`
- **Pipeline Request Correlation ID**: `7242c19e-039b-43d3-b37f-b144133706c9`
- **Timestamp**: 2025-11-20 18:41:44 - 18:42:26 UTC

### Expected Guest Batch Flow

According to `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/status_enums.py` lines 107-111:

```
GUEST flow: AWAITING_CONTENT_VALIDATION → AWAITING_PIPELINE_CONFIGURATION →
READY_FOR_PIPELINE_EXECUTION → PROCESSING_PIPELINES → terminal.
```

**Transition trigger**: `BatchContentProvisioningCompleted` event (published by ELS when all content is assigned)

---

## Evidence Chain

### 1. File Service: Content Upload Successful ✅

**Evidence**: File Service logs at 18:41:50
```
Successfully stored content (type: extracted_plaintext), storage_id: cf3ea970ffc94727b79cdb6051f76e6a
Successfully stored content (type: extracted_plaintext), storage_id: b2f1d444e90243fc8a79c2285242c352
```

**Events Published**:
- 2x `EssayContentProvisionedV1` events to Kafka
- Event IDs: `995af3ca-9792-4289-b9f5-30a99d17f3ac`, `ae052486-f25f-4f38-b9f8-84a4e8fec939`

### 2. ELS Worker: Content Received But Stored as Pending ✅

**Evidence**: ELS worker logs at 18:41:50
```
Processing EssayContentProvisionedV1 event [batch_coordination_handler] 
   batch_id: 278f7fd9-37fe-406a-a735-f15128cb6b1f
   text_storage_id: cf3ea970ffc94727b79cdb6051f76e6a
   
Batch not registered yet, storing content as pending [batch_coordination_handler]
```

**Database Confirmation** (`batch_pending_content` table):
```sql
SELECT * FROM batch_pending_content WHERE batch_id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';
```
Result: **2 rows** with storage IDs `cf3ea970ffc94727b79cdb6051f76e6a` and `b2f1d444e90243fc8a79c2285242c352`

**Analysis**: Content arrived before batch registration (race condition), correctly stored as pending per design.

### 3. BOS: Batch Registration Successful ✅

**Evidence**: BOS logs at 18:41:50
```json
{"event": "Registering new batch 278f7fd9-37fe-406a-a735-f15128cb6b1f with 2 essays",
 "correlation_id": "9437fe03-1195-4241-b532-91d36df0b1c2"}

{"event": "Published BatchEssaysRegistered event for batch 278f7fd9-37fe-406a-a735-f15128cb6b1f with 2 internal essay slots"}
```

**Database Confirmation** (BOS `batches` table):
```sql
SELECT id, status, total_essays FROM batches WHERE id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';
```
Result: 
- status: `awaiting_content_validation`
- total_essays: `2`

### 4. ELS Worker: Batch Registration Processing - PARTIAL SUCCESS ⚠️

**Evidence**: ELS worker logs at 18:41:50-18:41:51

```
Processing BatchEssaysRegistered event [batch_coordination_handler]
   batch_id: 278f7fd9-37fe-406a-a735-f15128cb6b1f
   expected_count: 2

Registered batch 278f7fd9-37fe-406a-a735-f15128cb6b1f in database with 2 slots, course: ENG5

Creating initial essay records in database for batch
   batch_id: 278f7fd9-37fe-406a-a735-f15128cb6b1f
   essay_count: 2
   
Creating batch of 2 essay records for batch 278f7fd9-37fe-406a-a735-f15128cb6b1f: 
   ['62431c17-f141-444a-b709-6c08e7c6eff2', 'fc35b304-58eb-44b6-936a-789055876b56']

[error] Error routing event [batch_command_handlers] 
   error: '[PROCESSING_ERROR] Database error during batch essay creation: DBAPIError'
   event_type: 'huleedu.batch.essays.registered.v1'
   correlation_id: '9437fe03-1195-4241-b532-91d36df0b1c2'

[error] Event processing failed [batch_command_handlers]

Message processing failed - offset not committed [worker_main]
   topic: 'huleedu.batch.essays.registered.v1'
   partition: 2
   offset: 12
```

### 5. Database State Analysis: Inconsistent State ❌

**ELS `batch_essay_trackers` table**:
```sql
SELECT batch_id, expected_count, available_slots, completed_at 
FROM batch_essay_trackers 
WHERE batch_id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';
```
Result:
- expected_count: `2`
- available_slots: `["fc35b304-58eb-44b6-936a-789055876b56", "62431c17-f141-444a-b709-6c08e7c6eff2"]`
  
**PROBLEM**: Both slots are still available (unfulfilled)

**ELS `essay_states` table**:
```sql
SELECT essay_id, batch_id, text_storage_id, current_status 
FROM essay_states 
WHERE batch_id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';
```
Result: **0 rows**

**CRITICAL**: No essay state records were created!

**ELS `batch_pending_content` table**:
Still contains **2 rows** - content never processed!

### 6. BOS Rejects Pipeline Request ❌

**Evidence**: BOS logs for pipeline request correlation `7242c19e-039b-43d3-b37f-b144133706c9`
```
Batch 278f7fd9-37fe-406a-a735-f15128cb6b1f is not ready for pipeline execution.
Current status: awaiting_content_validation
Expected status: ready_for_pipeline_execution
```

---

## Root Cause Analysis

### Transaction Failure Sequence

Looking at `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py` lines 79-103:

```python
# PHASE 1: Register and create essays atomically, then commit
async with self.session_factory() as session:
    async with session.begin():
        await self.batch_tracker.register_batch(event_data, correlation_id)
        
        await self.repository.create_essay_records_batch(
            typed_essay_data, correlation_id=correlation_id, session=session
        )
```

**What Happened**:
1. `batch_tracker.register_batch()` **succeeded** and committed to `batch_essay_trackers`
2. `repository.create_essay_records_batch()` **failed** with `DBAPIError`
3. Transaction rollback occurred
4. Kafka offset **NOT committed** (event will be retried)
5. **BUT**: `batch_essay_trackers` record persists (separate transaction or autocommit)

### Why Pending Content Was Never Processed

Lines 113-149 show Phase 2 logic:

```python
# PHASE 2: Process any pending content after commit to ensure MVCC visibility
pending_content_list = await self.pending_content_ops.get_pending_content(event_data.entity_id)
```

**Phase 2 never executed** because Phase 1 failed and raised an exception.

### Why BatchContentProvisioningCompleted Was Never Published

Per `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/domain_services/content_assignment_service.py` lines 129-167:

```python
batch_completion_result = await self.batch_tracker.mark_slot_fulfilled(
    batch_id, final_essay_id, text_storage_id
)

if batch_completion_result is not None:
    # Publish BatchContentProvisioningCompletedV1
```

**Event is only published when**:
- Content is assigned to an essay slot
- `mark_slot_fulfilled()` determines batch is complete (all slots filled)

**Since no content was assigned**, the event was never published.

---

## Architectural Issues Identified

### 1. Transaction Boundary Problem

The `batch_tracker.register_batch()` call appears to use a separate transaction or autocommit, allowing it to persist even when essay creation fails. This creates an **inconsistent intermediate state**:
- Batch tracker exists
- Essay slots available
- No essay state records
- Pending content never processed

### 2. Incomplete Error Recovery

When `BatchEssaysRegistered` processing fails:
- Kafka offset not committed (event will retry)
- But `batch_essay_trackers` already exists
- Retry will likely fail on uniqueness constraint
- No cleanup of partial state

### 3. Race Condition Handling Gap

The "pending content" mechanism correctly handles the race where content arrives before batch registration. However, if batch registration fails after storing pending content, there's no mechanism to:
- Clean up pending content
- Notify upstream services of failure
- Transition batch to failed state

---

## Immediate vs. Underlying Issues

### Immediate Issue: DBAPIError

**Question**: What caused the `DBAPIError` during essay record creation?

**Hypothesis**:
- Database connection issue
- Constraint violation (unlikely - essay IDs are UUIDs)
- Table lock/contention
- Schema mismatch

**Required Investigation**:
- Check ELS database logs for exact PostgreSQL error
- Review essay_states table constraints
- Check for concurrent operations on same batch

### Underlying Issue: Transaction Design

**Problem**: The current transaction design allows partial success:
1. Batch tracker registration succeeds
2. Essay creation fails
3. System left in inconsistent state
4. Retry will fail (batch already exists)

**Solution Needed**:
- Single atomic transaction for both operations OR
- Explicit rollback/cleanup on failure OR
- Idempotent retry logic that handles partial state

---

## Impact Assessment

### Test Failure

**Test**: `test_complete_identity_threading_workflow`
**Failure Mode**: Timeout after 45 seconds
**Reason**: Batch stuck in `awaiting_content_validation`, pipeline request rejected

### Production Risk

**Severity**: **HIGH** - Blocks all guest batch workflows

**Affected Flows**:
- Guest user batch submissions
- Any batch where content arrives before batch registration
- Recovery from transient database errors

**NOT Affected**:
- Regular batches (with class_id and student matching)
- Batches where content arrives after registration completes successfully

---

## Recommended Next Steps

### Immediate (P0)

1. **Identify DBAPIError Root Cause**
   - Query PostgreSQL logs in ELS database container
   - Check for constraint violations, deadlocks, or connection issues
   - File: Line in logs: `[PROCESSING_ERROR] Database error during batch essay creation: DBAPIError`

2. **Add Detailed Error Logging**
   - Capture full exception stack trace and PostgreSQL error code
   - Log state before/after transaction operations
   - File: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py`

3. **Implement Cleanup on Failure**
   - Delete `batch_essay_trackers` record if essay creation fails
   - Or: Mark batch as failed in tracker
   - Ensure atomic all-or-nothing semantics

### Short-term (P1)

4. **Fix Transaction Boundaries**
   - Ensure `register_batch()` and `create_essay_records_batch()` are in same transaction
   - Add explicit rollback handling
   - Test with intentional failures

5. **Add Idempotent Retry Logic**
   - Handle case where batch tracker exists but essays don't
   - Complete the registration process on retry
   - Don't fail on "batch already exists" if state is incomplete

6. **Improve Observability**
   - Add metrics for batch registration failures
   - Alert on batches stuck in `awaiting_content_validation` > 5 minutes
   - Dashboard for pending content age

### Long-term (P2)

7. **Guest Batch State Machine Review**
   - Document all state transitions and triggers
   - Add timeout-based auto-transitions
   - Implement batch health monitoring

8. **End-to-End Testing**
   - Add test for essay creation failure scenario
   - Test content-before-registration race condition
   - Verify cleanup on all failure paths

---

## Files for Developer Handoff

### Code Files
1. `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py` (lines 62-200)
2. `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/domain_services/content_assignment_service.py` (lines 125-167)
3. `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/implementations/batch_essay_tracker_impl.py` (register_batch method)
4. `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/protocols.py` (ContentAssignmentProtocol)

### Test Files
1. `/Users/olofs_mba/Documents/Repos/huledu-reboot/tests/functional/test_e2e_identity_threading.py` (line 44-82)
2. `/Users/olofs_mba/Documents/Repos/huledu-reboot/tests/functional/pipeline_harness_helpers/batch_setup.py` (lines 153-241)
3. `/Users/olofs_mba/Documents/Repos/huledu-reboot/tests/functional/pipeline_harness_helpers/event_waiters.py` (lines 88-144)

### State Machine Documentation
1. `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/status_enums.py` (lines 104-132)

---

## Diagnostic Commands

### Check Batch State
```bash
# BOS batch status
docker exec huleedu_batch_orchestrator_db psql -U huleedu_user -d huleedu_batch_orchestrator \
  -c "SELECT id, status, total_essays FROM batches WHERE id = '<batch_id>';"

# ELS batch tracker
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT batch_id, expected_count, available_slots FROM batch_essay_trackers WHERE batch_id = '<batch_id>';"

# ELS essay states
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT COUNT(*) FROM essay_states WHERE batch_id = '<batch_id>';"

# ELS pending content
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT COUNT(*) FROM batch_pending_content WHERE batch_id = '<batch_id>';"
```

### Check Logs
```bash
# ELS worker errors
docker logs huleedu_essay_lifecycle_worker 2>&1 | grep "<correlation_id>" | grep -i error

# BOS batch registration
docker logs huleedu_batch_orchestrator_service 2>&1 | grep "<batch_id>" | grep -i register

# File service content provisioning
docker logs huleedu_file_service 2>&1 | grep "<batch_id>"
```

---

## Conclusion

The guest batch is stuck in `awaiting_content_validation` because:

1. **Immediate Cause**: ELS worker failed to create essay state records due to `DBAPIError`
2. **Consequence**: Pending content was never assigned to essay slots
3. **Result**: `BatchContentProvisioningCompleted` event was never published
4. **Impact**: BOS never transitioned batch to `ready_for_pipeline_execution`

The root cause is a **database transaction failure combined with incomplete error handling** that leaves the system in an inconsistent state. The batch tracker exists but essays don't, and there's no recovery mechanism.

**Priority**: This is a **P0 blocking bug** for guest batch workflows. All guest batches will fail in the same way until the underlying database error is identified and the transaction handling is fixed.

**Next Agent**: Implementation agent should:
1. Investigate the exact PostgreSQL error causing `DBAPIError`
2. Fix transaction boundaries to ensure atomicity
3. Add idempotent retry logic
4. Add comprehensive error handling and cleanup
