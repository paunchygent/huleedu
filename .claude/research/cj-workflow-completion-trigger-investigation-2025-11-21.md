# CJ Workflow Completion Trigger Investigation - 2025-11-21

## Investigation Context

**Source**: Test finding from `test_full_batch_lifecycle_with_real_database`
**Issue**: `publish_assessment_completed` called 4 times instead of once
**Question**: Is this a production bug or expected behavior with proper guards?

## Executive Summary

**Finding**: **MEDIUM RISK** - Multiple triggers CAN cause duplicate event publications in production, but outbox pattern provides PARTIAL protection.

**Critical Gaps Identified**:
1. ❌ **No idempotency guard in `finalize_scoring()`** - Can be called multiple times
2. ❌ **No state check before event publication** - Events always published regardless of batch status
3. ⚠️ **Outbox pattern provides deduplication BUT with caveats**
4. ✅ **`finalize_single_essay()` HAS idempotency guard** (lines 236-242)

**Recommendation**: Add idempotency guard to `finalize_scoring()` matching the pattern in `finalize_single_essay()`.

---

## Flow Analysis: All Paths to `publish_assessment_completed()`

### Path 1: Callback-Driven Workflow Continuation

```
continue_cj_assessment_workflow() [batch_callback_handler.py:46]
  ↓
check_workflow_continuation() [workflow_continuation.py:42]
  → Returns TRUE if: completed_count % 5 == 0 OR threshold reached
  ↓
trigger_existing_workflow_continuation() [workflow_continuation.py:125]
  ↓
BatchFinalizer.finalize_scoring() [batch_finalizer.py:62]
  ↓
publish_dual_assessment_events() [dual_event_publisher.py:54]
  ↓
event_publisher.publish_assessment_completed() [line 155]
```

**Trigger Conditions**:
- Every 5 completions (line 83: `completed_count % 5 == 0`)
- Completion threshold reached (e.g., 80% of total_budget)
- Budget exhausted (pairs_remaining <= 0)

**Entry Guards**: NONE - `finalize_scoring()` has no check for existing completion

### Path 2: BatchMonitor Completion Sweep

```
BatchMonitor.check_stuck_batches() [batch_monitor.py:91]
  ↓
Fast-path completion sweeper (lines 163-211)
  → Finds batches with: completed_comparisons >= total_comparisons
  ↓
BatchFinalizer.finalize_scoring()
  ↓
publish_dual_assessment_events()
  ↓
event_publisher.publish_assessment_completed()
```

**Trigger Conditions**:
- BatchMonitor periodic scan (every `BATCH_MONITOR_INTERVAL_MINUTES`, default 5 minutes)
- Batch in `WAITING_CALLBACKS` state
- `completed_comparisons >= total_comparisons`

**Entry Guards**: NONE

### Path 3: Explicit Test Trigger

```
test_full_batch_lifecycle_with_real_database [line 209]
  ↓
trigger_existing_workflow_continuation()
  ↓
[Same path as Path 1]
```

**Trigger Conditions**:
- Test explicitly calls continuation after simulating callbacks
- Ensures completion even if periodic triggers don't align

**Entry Guards**: NONE

### Path 4: BatchMonitor Stuck Batch Recovery

```
BatchMonitor._handle_stuck_batch() [batch_monitor.py:234]
  ↓
BatchMonitor._trigger_scoring() [batch_monitor.py:428]
  ↓
publish_dual_assessment_events()
  ↓
event_publisher.publish_assessment_completed()
```

**Trigger Conditions**:
- Batch stuck (last_activity_at > timeout_hours)
- Progress >= 80%

**Entry Guards**: NONE

---

## Idempotency Analysis

### Level 1: `finalize_scoring()` - ❌ NO GUARD

**File**: `services/cj_assessment_service/cj_core_logic/batch_finalizer.py:62-188`

**Current Logic**:
```python
async def finalize_scoring(self, batch_id, correlation_id, session, log_extra):
    # Get batch upload
    batch_upload = await session.get(CJBatchUpload, batch_id)
    
    # NO CHECK HERE - proceeds regardless of status
    
    # Transition to SCORING
    await update_batch_state_in_session(state=CoreCJState.SCORING, ...)
    
    # Compute scores, rankings, grade projections
    # ...
    
    # Mark as COMPLETE_STABLE
    await self._db.update_cj_batch_status(status=CJBatchStatusEnum.COMPLETE_STABLE)
    
    # ALWAYS PUBLISHES - no guard here
    await publish_dual_assessment_events(...)
    
    # Mark as COMPLETED
    await update_batch_state_in_session(state=CoreCJState.COMPLETED, ...)
```

**Problem**: If called twice concurrently or sequentially:
1. First call: Sets status to `COMPLETE_STABLE`, publishes events
2. Second call: Sees `COMPLETE_STABLE`, but proceeds anyway, publishes events AGAIN

**Evidence**: No early return for terminal states like in `finalize_single_essay()`

### Level 2: `finalize_single_essay()` - ✅ HAS GUARD

**File**: `services/cj_assessment_service/cj_core_logic/batch_finalizer.py:206-324`

**Correct Pattern** (lines 236-242):
```python
async def finalize_single_essay(self, batch_id, correlation_id, session, log_extra):
    batch_upload = await session.get(CJBatchUpload, batch_id)
    
    # IDEMPOTENCY GUARD - checks terminal status
    status_str = str(batch_upload.status)
    if status_str.startswith("COMPLETE") or status_str.startswith("ERROR"):
        logger.info("Batch already terminal, skipping finalization", ...)
        return  # EARLY EXIT
    
    # Proceed with finalization...
```

**This pattern SHOULD be applied to `finalize_scoring()`**

### Level 3: Outbox Pattern - ⚠️ PARTIAL PROTECTION

**File**: `services/cj_assessment_service/implementations/event_publisher_impl.py:36-74`

**How It Works**:
```python
async def publish_assessment_completed(self, completion_data, correlation_id):
    aggregate_id = str(completion_data.data.entity_id)  # BOS batch ID
    
    # Stores in outbox table with aggregate_id as key
    await self.outbox_manager.publish_to_outbox(
        aggregate_type="cj_batch",
        aggregate_id=aggregate_id,
        event_type=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
        event_data=completion_data,
        topic=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
    )
```

**Outbox Table Schema** (from Rule 042.1):
- `id` (PK, auto-increment)
- `aggregate_id` (string, NOT unique)
- `aggregate_type` (string)
- `event_type` (string)
- `event_data` (JSON)
- `published_at` (timestamp, NULL for unpublished)
- `retry_count`, `last_error`

**Key Observation**: 
- **NO UNIQUE CONSTRAINT on `(aggregate_id, event_type)`**
- Multiple calls with same `aggregate_id` create MULTIPLE OUTBOX ROWS
- Relay worker publishes ALL unpublished rows

**Deduplication Happens At**:
1. **Consumer-side idempotency** (not shown in code)
2. **Kafka message key** (uses aggregate_id for partition routing, but NOT deduplication)
3. **event_id header** (generated per outbox row, so DIFFERENT for each duplicate)

**Conclusion**: Outbox pattern ensures atomic consistency (database + events), but does NOT prevent duplicate event publication from multiple `publish_to_outbox()` calls.

### Level 4: Database State Transitions - ⚠️ INSUFFICIENT

**Status Field**: `CJBatchUpload.status` (type: `CJBatchStatusEnum`)

**Available States**:
```python
class CJBatchStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    FETCHING_CONTENT = "FETCHING_CONTENT"
    PERFORMING_COMPARISONS = "PERFORMING_COMPARISONS"
    COMPLETE_STABLE = "COMPLETE_STABLE"  # Terminal state
    COMPLETE_MAX_COMPARISONS = "COMPLETE_MAX_COMPARISONS"
    COMPLETE_INSUFFICIENT_ESSAYS = "COMPLETE_INSUFFICIENT_ESSAYS"
    ERROR_PROCESSING = "ERROR_PROCESSING"  # Terminal state
    ERROR_ESSAY_PROCESSING = "ERROR_ESSAY_PROCESSING"
```

**Problem**: `finalize_scoring()` doesn't check status before proceeding

**Fine-Grained State**: `CJBatchState.state` (type: `CJBatchStateEnum`)
- Has `COMPLETED` state (line 181 in batch_finalizer.py)
- BUT not checked before finalization starts

**Missing Guard**:
```python
# SHOULD BE ADDED at line 91 in batch_finalizer.py
if batch_upload.status in [
    CJBatchStatusEnum.COMPLETE_STABLE,
    CJBatchStatusEnum.COMPLETE_MAX_COMPARISONS,
    CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS,
    CJBatchStatusEnum.ERROR_PROCESSING,
    CJBatchStatusEnum.ERROR_ESSAY_PROCESSING,
]:
    logger.info("Batch already in terminal state, skipping finalization", ...)
    return
```

---

## Production Risk Assessment

### Scenario 1: Callback-Driven Multiple Triggers

**Situation**: Batch with 10 comparisons, threshold = 80% (8 comparisons)

**Timeline**:
1. Callback #5 arrives → `check_workflow_continuation()` returns TRUE (5 % 5 == 0)
   - Triggers `finalize_scoring()` prematurely (only 50% complete)
   - Publishes events ❌ INCORRECT
2. Callbacks #6-8 arrive → Threshold reached (80%)
   - Triggers `finalize_scoring()` again
   - Publishes events AGAIN ❌ DUPLICATE
3. Callbacks #9-10 arrive → 10 % 5 == 0
   - Triggers `finalize_scoring()` THIRD TIME
   - Publishes events AGAIN ❌ DUPLICATE

**Root Cause**: 
- Periodic trigger (line 83) fires REGARDLESS of completion threshold
- No coordination between periodic and threshold-based triggers

**Impact**: Up to 3 completion events for same batch

### Scenario 2: BatchMonitor Concurrent Trigger

**Situation**: Batch completes naturally, but BatchMonitor also finds it ready

**Timeline**:
1. Callback #10 arrives → Workflow continuation triggers finalization
   - Transaction starts, updates status to SCORING
2. BatchMonitor scan (5 min interval) finds batch in WAITING_CALLBACKS with 10/10 complete
   - Concurrent finalization attempt
3. Both transactions proceed, both publish events

**Race Condition**: Database allows concurrent status updates (no `FOR UPDATE` lock)

**Impact**: 2 completion events

### Scenario 3: Test Artifact (Non-Production)

**Situation**: Test explicitly triggers continuation after simulator

**Evidence**:
```python
# Line 209 in test_real_database_integration.py
await trigger_existing_workflow_continuation(...)
```

**Impact**: Test-only, not production issue

**Mitigation**: Test comment already notes multiple calls are acceptable (line 235-239)

---

## Recommended Fixes

### Fix 1: Add Idempotency Guard to `finalize_scoring()` (P0 - CRITICAL)

**Location**: `services/cj_assessment_service/cj_core_logic/batch_finalizer.py:91`

**Add**:
```python
# After line 90 (batch_upload null check)
# Idempotency guard - skip if already terminal
status_str = str(batch_upload.status)
if status_str.startswith("COMPLETE") or status_str.startswith("ERROR"):
    logger.info(
        "Batch already in terminal state, skipping finalization",
        extra={**log_extra, "batch_id": batch_id, "status": status_str},
    )
    return
```

**Justification**: Matches pattern in `finalize_single_essay()` (lines 236-242)

### Fix 2: Coordinate Periodic and Threshold Triggers (P1 - MEDIUM)

**Location**: `services/cj_assessment_service/cj_core_logic/workflow_continuation.py:83-93`

**Change**:
```python
# Current (line 82-84)
if completed_count > 0 and completed_count % 5 == 0:
    should_continue = True

# Proposed
if completed_count > 0 and completed_count % 5 == 0:
    # Only trigger periodic continuation if NOT at completion threshold
    if denominator > 0:
        completion_percentage = (completed_count / denominator) * 100
        threshold_reached = (
            batch_state.completion_threshold_pct
            and completion_percentage >= batch_state.completion_threshold_pct
        )
        if not threshold_reached:
            should_continue = True
    else:
        should_continue = True
```

**Justification**: Avoid duplicate triggers when both conditions align

### Fix 3: Add Locking to BatchMonitor Completion Sweep (P2 - LOW)

**Location**: `services/cj_assessment_service/batch_monitor.py:163-211`

**Change**:
```python
# Line 166
ready_stmt = (
    select(CJBatchState)
    .options(selectinload(CJBatchState.batch_upload))
    .where(
        CJBatchState.state == CJBatchStateEnum.WAITING_CALLBACKS,
        CJBatchState.total_comparisons > 0,
        CJBatchState.completed_comparisons >= CJBatchState.total_comparisons,
    )
    .with_for_update(skip_locked=True)  # ADD THIS
)
```

**Justification**: Prevent concurrent finalization by callback handler and monitor

---

## Test Evidence Analysis

### Test Code Review

**File**: `services/cj_assessment_service/tests/integration/test_real_database_integration.py:235-240`

```python
# NOTE: publish_assessment_completed may be called multiple times due to:
# 1. CallbackSimulator triggering workflow continuation internally
# 2. Explicit trigger_existing_workflow_continuation call above (line 209)
# 3. Periodic triggers every 5 completions
# This is acceptable - we just need to verify it was called at least once
assert mock_event_publisher.publish_assessment_completed.call_count >= 1
```

**Test Behavior**:
- Test processes 5 essays → 10 comparison pairs (nC2)
- CallbackSimulator processes all 10 callbacks
  - Triggers at callback #5 (5 % 5 == 0)
  - Triggers at callback #10 (10 % 5 == 0)
- Test explicitly calls `trigger_existing_workflow_continuation()` (line 209)
- **Result**: 3-4 calls to `publish_assessment_completed`

**Interpretation**: Test CORRECTLY identifies the issue but marks it as acceptable

---

## Production vs Test Differences

### Test-Specific Factors
1. **CallbackSimulator**: Synchronously processes all callbacks in tight loop
   - Production: Callbacks arrive asynchronously over time
   - Impact: Test exaggerates trigger alignment
2. **Explicit trigger** (line 209): Test-only to ensure completion
   - Production: No manual triggers
3. **Small batch size** (5 essays = 10 pairs): Threshold alignment more likely
   - Production: Larger batches reduce alignment probability

### Production Mitigations
1. **Asynchronous callback arrival**: Natural spacing reduces concurrent triggers
2. **Database transaction timing**: Most calls see terminal status from prior finalization
3. **Consumer idempotency**: Downstream services (ELS, RAS) may deduplicate
4. **Outbox relay worker batching**: May coalesce rapid duplicates

**Conclusion**: Test demonstrates REAL production risk, but severity depends on timing and batch size.

---

## Conclusion

### Is This a Bug?

**YES**, but with caveats:

1. **Design Flaw**: Multiple code paths can trigger finalization without coordination
2. **Missing Guard**: `finalize_scoring()` lacks idempotency check present in `finalize_single_essay()`
3. **Partial Protection**: Outbox pattern ensures atomicity but NOT deduplication

### Can It Happen in Production?

**YES**, under these conditions:
- Batch size aligns with periodic trigger interval (e.g., 10, 15, 20 comparisons)
- Completion threshold exactly matches periodic trigger point
- BatchMonitor scan occurs during natural completion window
- High callback processing rate (tight timing)

**Probability**: MEDIUM for small batches, LOW for large batches

### What's the Impact?

**Duplicate Events Published**:
- ELS receives multiple `CJAssessmentCompletedV1` events for same batch
- RAS receives multiple `AssessmentResultV1` events for same batch
- Entitlements receives multiple `ResourceConsumptionV1` events (⚠️ CREDIT LEAK)

**Consumer Responsibility**:
- ELS must deduplicate based on `entity_id` (BOS batch ID)
- RAS must deduplicate based on `cj_assessment_job_id`
- Entitlements MUST have idempotency to prevent double-charging

**Outbox Protection**:
- Ensures events are stored atomically with database state
- Does NOT prevent multiple outbox rows for same aggregate_id
- Relay worker publishes all unpublished rows

---

## Next Steps

### Immediate Actions (Before Next Production Run)
1. ✅ Document finding in research file (this document)
2. ❌ **P0**: Add idempotency guard to `finalize_scoring()`
3. ⚠️ **P0**: Verify consumer-side idempotency (ELS, RAS, Entitlements)

### Follow-Up Tasks
1. **P1**: Coordinate periodic and threshold triggers
2. **P2**: Add locking to BatchMonitor completion sweep
3. **P2**: Add integration test verifying single event publication
4. **P3**: Consider unique constraint on outbox `(aggregate_id, event_type, published_at IS NULL)`

---

## References

- **Rule**: `.claude/rules/042.1-transactional-outbox-pattern.md`
- **Test**: `services/cj_assessment_service/tests/integration/test_real_database_integration.py:134-249`
- **Flow Diagram**: See "Flow Analysis" section above
- **Code Locations**: All file paths include absolute paths from repo root
