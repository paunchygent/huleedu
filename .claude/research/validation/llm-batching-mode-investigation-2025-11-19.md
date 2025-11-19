# LLM Batching Mode Investigation
**Date:** 2025-11-19
**Researcher:** Claude Code
**Status:** In Progress

## Executive Summary

Investigation into why `per_request` batching succeeds while `serial_bundle` batching fails or gets stuck. Initial evidence shows:
- Per-request mode: Failed on schema path issue (unrelated to batching)
- Serial bundle mode: Stuck queue with missing essay identifiers in callbacks

## Test Matrix

| Run ID | Mode | Comparisons | Status | Key Finding |
|--------|------|-------------|--------|-------------|
| 62e923 | per_request | 4 | Failed | Schema path resolution error |
| 84ebf6 | serial_bundle | 100 | Stuck | Queue frozen at 1 item for 40+ min |
| b525a2 | serial_bundle | 10 | Failed | Missing essay_a_id/essay_b_id in callback |

## Investigation Plan

### Phase 1: Data Collection ✓
- [x] Collect runner outputs
- [x] Collect service logs (CJ, LLM Provider)
- [x] Identify error patterns
- [ ] Trace specific correlation IDs through full lifecycle

### Phase 2: Root Cause Analysis (Current)
- [ ] Why do serial_bundle callbacks lack essay identifiers?
- [ ] Why is LLM queue stuck with 1 item?
- [ ] What happened to the other 9 comparisons in bundle?
- [ ] Are database errors blocking completion?

### Phase 3: Code Path Analysis
- [ ] Trace request_metadata population in CJ service
- [ ] Compare per_request vs serial_bundle code paths
- [ ] Identify where essay IDs should be attached
- [ ] Verify LLM provider callback construction

### Phase 4: Validation
- [ ] Create minimal reproduction case
- [ ] Test fix for missing essay identifiers
- [ ] Verify queue unsticking mechanism
- [ ] Validate database transaction handling

---

## Evidence Collection

### 1. Schema Path Issue (62e923 - per_request)

**Error:**
```
FileNotFoundError: Schema file not found at /Users/olofs_mba/Documents/Repos/huledu-reboot/scripts/cj_experiments_runners/eng5_np/schema.json
```

**Expected Path (from paths.py:36-42):**
```python
schema_path=(
    repo_root
    / "docs"
    / "reference"
    / "schemas"
    / "eng5_np"
    / "assessment_run.schema.json"
),
```

**Actual File Location (verified):**
```bash
/Users/olofs_mba/Documents/Repos/huledu-reboot/docs/reference/schemas/eng5_np/assessment_run.schema.json
# File exists, 10408 bytes, modified Nov 8 19:13
```

**Hypothesis:** Error message shows wrong path (`scripts/cj_experiments_runners/eng5_np/schema.json`), but code should use correct path. Possible:
1. Exception handling showing wrong path in error message
2. Fallback path logic being triggered
3. CWD issue during execution

**Action Required:** Check `ensure_schema_available()` implementation for path handling logic.

---

### 2. Missing Essay Identifiers (b525a2 - serial_bundle, 10 comparisons)

**Error:**
```
Kafka publish failed (ValueError: Comparison callback missing essay identifiers; correlation=8f3a11d7-9411-4ca2-9999-59a9d18c5da9)
```

**Validation Code (hydrator.py:207-215):**
```python
metadata = envelope.data.request_metadata or {}
essay_a = metadata.get("essay_a_id")
essay_b = metadata.get("essay_b_id")
...
if not essay_a or not essay_b:
    raise ValueError(
        "Comparison callback missing essay identifiers; "
        f"correlation={envelope.correlation_id}",
    )
```

**Key Questions:**
1. **Who populates request_metadata?** → CJ Assessment Service when creating LLM requests
2. **Where should essay_a_id/essay_b_id come from?** → Comparison pair data structure
3. **Why would serial_bundle lack this data when per_request has it?** → INVESTIGATE

**Correlation ID:** `8f3a11d7-9411-4ca2-9999-59a9d18c5da9`

**Action Required:**
- Search CJ service logs for this correlation_id
- Trace request creation in CJ service
- Compare request_metadata between batching modes

---

### 3. Stuck LLM Queue (84ebf6 - serial_bundle, 100 comparisons)

**Dispatch Evidence:**
```
2025-11-18 23:48:23 serial_bundle_dispatch [bundle_size: 8]
2025-11-18 23:48:39 serial_bundle_dispatch [bundle_size: 2]
```

**Total Dispatched:** 10 comparisons (not 100!)

**Queue Metrics (40+ minutes):**
```
queue_current_size: 1
queue_queued_count: 0
queue_usage_percent: 0.1
```

**Critical Questions:**
1. **Why only 10 comparisons dispatched instead of 100?**
   - Possible: Batch generation stopped early
   - Possible: CJ service didn't create all pairs
   - Possible: Configuration limit somewhere

2. **What is the 1 stuck item in the queue?**
   - Waiting for LLM response?
   - Waiting for callback acknowledgment?
   - Deadlocked on some resource?

3. **What happened to comparisons 1-9?**
   - Did they complete successfully?
   - Did they fail silently?
   - Are they recorded in the database?

**Action Required:**
- Check CJ service logs for batch creation
- Count actual comparison pairs created
- Identify the stuck request in LLM queue
- Check for any completed callbacks

---

### 4. Database Transaction Errors

**Evidence from CJ Service Logs:**
```
IntegrityError ... (Background on this error at: https://sqlalche.me/e/20/gkpj)
PendingRollbackError ... (Background on this error at: https://sqlalche.me/e/20/7s2a)
```

**Context:** Occurred during grade projection calculation (batch ID 34)

**Logged Actions:**
```
2025-11-18 23:48:42 [debug] Updating batch state to SCORING [cj_batch_id: 34]
2025-11-18 23:48:42 [info] Recording 0 comparison results for CJ Batch ID: 34
2025-11-18 23:48:42 [info] Stored 0 new comparison pairs for CJ Batch ID: 34
2025-11-18 23:48:43 [info] Generating final rankings for CJ Batch ID: 34
2025-11-18 23:48:43 [info] Generated rankings for 24 essays in CJ Batch 34
[ERROR] IntegrityError during grade projection
[ERROR] PendingRollbackError during workflow continuation
```

**Key Observations:**
- **0 comparison results recorded** → No successful LLM completions!
- Generated rankings anyway (likely default/empty rankings)
- IntegrityError suggests constraint violation (duplicate? missing FK?)
- PendingRollbackError suggests transaction not properly handled after first error

**Action Required:**
- Find exact SQL causing IntegrityError
- Check grade_projections table constraints
- Verify transaction isolation levels
- Review error handling in batch_finalizer.py

---

## Hypotheses to Test

### Hypothesis 1: Serial Bundle Doesn't Populate request_metadata
**Theory:** The serial_bundle code path skips or incorrectly populates request_metadata when creating LLM requests.

**Test:**
```sql
-- Check if request_metadata is populated in database
SELECT request_id, request_metadata FROM llm_requests WHERE ...
```

**Verification:** Compare CJ service request creation between modes.

---

### Hypothesis 2: Queue Stuck Due to Failed Callback Processing
**Theory:** One comparison callback failed processing, blocking the entire serial bundle queue.

**Test:** Check LLM provider logs for:
- Callback send attempts
- Kafka publish errors
- Timeout/retry logic

---

### Hypothesis 3: Database Error Causes Cascade Failures
**Theory:** IntegrityError during grade projection causes batch to fail, preventing further comparisons.

**Test:**
- Check batch state transitions
- Verify if batch marked as failed
- Check if failed batch blocks new comparisons

---

### Hypothesis 4: Race Condition Between Modes
**Theory:** Serial bundle's parallel processing within bundle causes race condition that per_request avoids.

**Test:**
- Check database transaction logs
- Look for concurrent write attempts
- Verify locking mechanisms

---

## Next Steps

1. **Immediate (Required for Diagnosis):**
   - [ ] Trace correlation_id `8f3a11d7-9411-4ca2-9999-59a9d18c5da9` through full system
   - [ ] Query CJ database for batch 34 comparison pairs
   - [ ] Find the stuck LLM queue item details
   - [ ] Count successful vs failed comparisons

2. **Code Analysis:**
   - [ ] Compare `_create_llm_comparison_request()` between batching modes
   - [ ] Review `request_metadata` population logic
   - [ ] Trace essay identifier flow from pair creation to callback

3. **Database Deep Dive:**
   - [ ] Get exact IntegrityError SQL and constraint
   - [ ] Check grade_projections table for batch 34
   - [ ] Verify cj_batch_states table consistency

4. **LLM Provider Investigation:**
   - [ ] Identify stuck queue item
   - [ ] Check for hanging network calls
   - [ ] Review serial_bundle dispatch logic

---

## Diagnostic Queries

### Check Batch 34 Comparison Pairs
```sql
-- Run against CJ assessment database
SELECT
    cj_batch_id,
    COUNT(*) as total_pairs,
    COUNT(winner) as pairs_with_winner
FROM cj_comparison_pairs
WHERE cj_batch_id = 34
GROUP BY cj_batch_id;
```

### Check Grade Projections for Batch 34
```sql
SELECT COUNT(*) as projection_count
FROM grade_projections
WHERE cj_batch_id = 34;
```

### Check Batch State
```sql
SELECT
    bs.batch_id,
    bu.bos_batch_id,
    bs.state,
    bs.submitted_comparisons,
    bs.completed_comparisons,
    bs.current_iteration
FROM cj_batch_states bs
JOIN cj_batch_uploads bu ON bs.batch_id = bu.id
WHERE bs.batch_id = 34;
```

---

## Tools and Commands

### Check Service Logs
```bash
# CJ Service - specific correlation
docker logs huleedu_cj_assessment_service 2>&1 | grep "8f3a11d7-9411-4ca2-9999-59a9d18c5da9"

# LLM Provider - queue status
docker logs huleedu_llm_provider_service 2>&1 | grep -E "(serial_bundle_dispatch|queue_metrics)"

# Find stuck item
docker logs huleedu_llm_provider_service 2>&1 | grep "queue_current_size: 1" -B 10
```

### Database Access
```bash
# CJ Assessment DB
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "<QUERY>"
```

### Runner Status
```bash
# Check background jobs
ps aux | grep eng5-np-run

# Kill stuck runners
kill -9 <PID>
```

---

## Risk Assessment

### Critical Blockers
1. **LLM Queue Stuck** - Prevents all serial_bundle runs from completing
2. **Missing Essay IDs** - Causes runtime failures even when queue processes
3. **Database Errors** - May corrupt batch state, requiring manual cleanup

### Medium Impact
1. **Schema Path** - Only affects per_request startup, easy workaround
2. **Transaction Handling** - May cause inconsistent state but not blocking

### Low Impact
1. **Metrics/Observability** - Logs are working, correlation IDs present

---

## Success Criteria

Investigation complete when:
- [ ] Root cause of missing essay_a_id/essay_b_id identified and documented
- [ ] Reason for stuck LLM queue understood
- [ ] Database transaction errors explained
- [ ] Comparison between per_request and serial_bundle code paths mapped
- [ ] Reproducible test case created
- [ ] Fix recommendations documented with confidence levels

---

## Progress Log

### 2025-11-19 00:05 - Investigation Started
- Created research document
- Catalogued initial evidence
- Defined investigation phases
- Next: Database queries and correlation ID trace
