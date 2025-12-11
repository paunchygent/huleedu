---
id: fix-els-batch-registration-transaction
title: Fix Els Batch Registration Transaction
type: task
status: archived
priority: high
domain: infrastructure
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: essay_lifecycle_service
owner: ''
program: ''
related: []
labels: []
---

# TASK – Fix ELS Batch Registration Transaction Failure (P0)

## 1. Problem Statement

### 1.1 Critical Guest Batch Workflow Blocker

The Essay Lifecycle Service (ELS) worker encounters a `DBAPIError` when processing `BatchEssaysRegistered` events, causing **all guest batch workflows to fail**. The transaction failure leaves the system in an inconsistent intermediate state where:

- Batch tracker is created in `batch_essay_trackers` table
- Essay state records are **NOT created** in `essay_states` table (transaction rollback)
- Pending content remains orphaned in `batch_pending_content` table
- `BatchContentProvisioningCompleted` event is never published
- Batch permanently stuck in `awaiting_content_validation` state
- Pipeline execution requests are rejected by BOS with validation error

**Impact**:
- **Severity**: P0 BLOCKING - All guest batch submissions fail
- **Scope**: 100% failure rate for guest batch workflows
- **Discovered**: 2025-11-20 during E2E identity threading test investigation
- **Test Failure**: `test_e2e_identity_threading.py::test_complete_identity_threading_workflow` times out after 45s

### 1.2 Transaction Boundary Violation

The root cause is a **partial transaction success** in `BatchCoordinationHandlerImpl.handle_batch_essays_registered()`:

```python
# PHASE 1: Register and create essays atomically, then commit
async with self.session_factory() as session:
    async with session.begin():
        await self.batch_tracker.register_batch(event_data, correlation_id)  # ✅ SUCCEEDS

        await self.repository.create_essay_records_batch(
            typed_essay_data, correlation_id=correlation_id, session=session
        )  # ❌ FAILS with DBAPIError
```

**Problem**: `batch_tracker.register_batch()` commits successfully but `create_essay_records_batch()` fails, leaving:
1. Batch tracker persisted (inconsistent state)
2. No essay state records
3. Kafka offset NOT committed (event will retry)
4. Retry will fail on batch tracker uniqueness constraint
5. No cleanup or recovery mechanism

### 1.3 Supporting Investigation

**Detailed Evidence**: `.claude/work/session/GUEST_BATCH_STUCK_INVESTIGATION_REPORT.md`

**Test Case**: Batch ID `278f7fd9-37fe-406a-a735-f15128cb6b1f`
- Registration correlation: `9437fe03-1195-4241-b532-91d36df0b1c2`
- Pipeline request correlation: `7242c19e-039b-43d3-b37f-b144133706c9`
- Timestamp: 2025-11-20 18:41:44 - 18:42:26 UTC

**Database State Verification**:
```sql
-- ELS batch_essay_trackers: ✅ 1 row exists
SELECT * FROM batch_essay_trackers WHERE batch_id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';

-- ELS essay_states: ❌ 0 rows (INCONSISTENT!)
SELECT COUNT(*) FROM essay_states WHERE batch_id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';

-- ELS batch_pending_content: ⚠️ 2 rows orphaned
SELECT COUNT(*) FROM batch_pending_content WHERE batch_id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';

-- BOS batches: Stuck in awaiting_content_validation
SELECT status FROM batches WHERE id = '278f7fd9-37fe-406a-a735-f15128cb6b1f';
```

---

## 2. Goals & Non-Goals

### 2.1 Goals

- **G1 – Identify Root DBAPIError**
  Determine the exact PostgreSQL error causing `DBAPIError` during essay record creation (constraint violation, deadlock, schema mismatch, connection issue, etc.).

- **G2 – Atomic Transaction Semantics**
  Ensure batch tracker registration and essay record creation are truly atomic (all-or-nothing). If essay creation fails, batch tracker must be rolled back or marked as failed.

- **G3 – Idempotent Retry Logic**
  Handle Kafka event retries gracefully when partial state exists (batch tracker exists but essays don't). Complete the registration on retry instead of failing.

- **G4 – Cleanup on Failure**
  Add explicit error handling to clean up partial state (delete batch tracker, mark as failed, clear pending content) when essay creation fails.

- **G5 – Observability**
  Add detailed error logging with full exception stack traces, PostgreSQL error codes, and state before/after transaction operations. Add metrics for batch registration failures.

### 2.2 Non-Goals

- **NG1 – Redesign Batch State Machine**
  This task fixes the transaction bug. Broader state machine improvements (timeouts, health monitoring) are deferred to separate task.

- **NG2 – Fix Regular Batch Workflows**
  This issue specifically affects guest batches. Regular batches (with class_id and student matching) are NOT affected and out of scope.

- **NG3 – Content-Before-Registration Race Condition**
  The "pending content" mechanism correctly handles race conditions. That design is sound and out of scope.

---

## 3. Required Reading

Before implementing this fix, read and understand:

1. **Investigation Report**:
   - `.claude/work/session/GUEST_BATCH_STUCK_INVESTIGATION_REPORT.md` (comprehensive evidence and analysis)

2. **Architectural Context**:
   - `.agent/rules/020-architectural-mandates.md` (DDD, service boundaries, transaction patterns)
   - `.agent/rules/020.5-essay-lifecycle-service-architecture.md` (ELS responsibilities and patterns)
   - `.agent/rules/042-async-patterns-and-di.md` (database session management, transaction boundaries)

3. **Batch State Machine**:
   - `libs/common_core/src/common_core/status_enums.py` (lines 104-132: BatchStatus enum and guest batch flow)

4. **Test Creation Standards**:
   - `.agent/rules/075-test-creation-methodology.md` (test structure and coverage requirements)
   - `.agent/rules/075.1-parallel-test-creation-methodology.md` (parallel test execution)

---

## 4. Implementation Plan

### Step 1: Debug Script to Reproduce and Identify Error

**Create**: `scripts/debug_batch_registration_failure.py`

**Purpose**: Reproduce the failure and capture the exact PostgreSQL error, not just `DBAPIError`.

**Script should**:
1. Connect to ELS database
2. Query current state of failed batch (batch_essay_trackers, essay_states, batch_pending_content)
3. Attempt to manually trigger the same operations that fail
4. Capture full exception with PostgreSQL error code
5. Print diagnostic info

**Example**:
```python
"""Debug script to reproduce batch registration transaction failure."""
import asyncio
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import ...

async def debug_batch_registration():
    batch_id = "278f7fd9-37fe-406a-a735-f15128cb6b1f"

    # Print current database state
    print("=== Current Database State ===")
    # Query batch_essay_trackers
    # Query essay_states
    # Query batch_pending_content

    # Attempt to reproduce the failure
    try:
        # Simulate batch registration
        pass
    except Exception as e:
        print(f"Error: {type(e).__name__}")
        print(f"PostgreSQL Error Code: {getattr(e.orig, 'pgcode', None)}")
        print(f"Details: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_batch_registration())
```

**Run**: `pdm run python scripts/debug_batch_registration_failure.py`

**Outcome**: Understand the **actual** error before proposing fixes.

---

### Step 2: Fix Based on Investigation Findings

**After identifying root cause**, implement the fix. Common scenarios:

**If constraint violation**: Fix data consistency issue
**If transaction boundary issue**: Ensure `register_batch()` uses provided session
**If deadlock**: Add proper locking or retry logic
**If schema mismatch**: Update model or migration

**Don't preemptively add logging/metrics** - fix the bug first.

---

## 5. Testing Strategy

**After fix is implemented**:
- Add unit test reproducing the failure scenario
- Verify `test_e2e_identity_threading.py` passes
- Test idempotent retry behavior if relevant

---

## 6. Rollout Plan

1. Run debug script to identify root cause
2. Implement targeted fix
3. Test
4. Deploy

**Estimated Effort**: 2-3 days

---

## 7. Success Criteria

- ✅ Guest batch workflows succeed end-to-end
- ✅ `test_e2e_identity_threading.py` passes consistently
- ✅ Batches transition to `ready_for_pipeline_execution`
- ✅ No orphaned state in database after failures
- ✅ Kafka event retries succeed
- ✅ No performance regression

---

## 8. Related Tasks and Dependencies

### Upstream Dependencies
- None (this is a standalone bug fix)

### Downstream Tasks (Future)
- Batch state machine timeout mechanism (auto-transition stuck batches)
- Batch health monitoring dashboard (Grafana)
- Automated batch cleanup for failed/abandoned batches
- Performance optimization for high-volume batch registration

### Related Documentation
- Investigation report: `.claude/work/session/GUEST_BATCH_STUCK_INVESTIGATION_REPORT.md`
- Original task (separate issue): `.claude/work/tasks/TASK-FIX-PROMPT-REFERENCE-PROPAGATION-AND-BCS-DLQ-TIMEOUT.md`

---

## 9. Risk Assessment

**High Risk**: Transaction performance degradation
- Mitigation: Benchmark before/after, rollback if > 20% slower

**Medium Risk**: Retry race conditions
- Mitigation: Use database row locking if needed

---

## 10. Appendix: Diagnostic Commands

### Check Current State
```bash
# ELS batch tracker state
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT batch_id, expected_count, available_slots, completed_at FROM batch_essay_trackers WHERE batch_id = '<batch_id>';"

# ELS essay states
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT essay_id, batch_id, current_status, text_storage_id FROM essay_states WHERE batch_id = '<batch_id>';"

# ELS pending content
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT essay_file_id, text_storage_id, received_at FROM batch_pending_content WHERE batch_id = '<batch_id>';"

# BOS batch status
docker exec huleedu_batch_orchestrator_db psql -U huleedu_user -d huleedu_batch_orchestrator \
  -c "SELECT id, status, total_essays, created_at FROM batches WHERE id = '<batch_id>';"
```

### Check Logs
```bash
# ELS worker errors during batch registration
docker logs huleedu_essay_lifecycle_worker 2>&1 | grep "<correlation_id>" | grep -i error

# ELS database logs (PostgreSQL errors)
docker logs huleedu_essay_lifecycle_db 2>&1 | grep -i error | grep "<batch_id>"

# BOS batch registration events
docker logs huleedu_batch_orchestrator_service 2>&1 | grep "<batch_id>" | grep -i "register\|BatchEssaysRegistered"
```

### Monitor Metrics
```bash
# ELS batch registration metrics
curl http://localhost:9095/metrics | grep els_batch_registration

# Check for stuck batches
curl http://localhost:9095/health/batches
```

---

**Status**: BLOCKED - Awaiting PR 1 investigation
**Priority**: P0 (Blocks all guest batch workflows)
**Assignee**: TBD
**Created**: 2025-11-20
**Updated**: 2025-11-20
