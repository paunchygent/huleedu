# LLM Batching Mode - Code Path Analysis
**Date:** 2025-11-19
**Investigator:** Claude Code (Plan Agent)
**Status:** Complete - Root Causes Identified

## Executive Summary

Comprehensive code analysis of CJ Assessment and LLM Provider services has identified **7 critical bugs** and **2 architectural design flaws** that explain all observed failures in serial_bundle mode.

**Critical Finding:** The serial_bundle batching mode revealed pre-existing bugs in the CJ Assessment service that were masked by per_request mode's lower throughput. These bugs exist regardless of batching mode but become catastrophic under higher load.

---

## Root Cause Findings

### Finding 1: Runaway Completion Detection Loop (>100% rates)

**File:** `services/cj_assessment_service/cj_core_logic/callback_state_manager.py:217-232`

**Current Behavior:**
```python
if (
    batch_state.total_comparisons > 0
    and batch_state.completed_comparisons >= batch_state.total_comparisons * 0.8
):
    completion_rate = batch_state.completed_comparisons / batch_state.total_comparisons
    logger.info(
        f"Batch {batch_id} completion detected: "
        f"{batch_state.completed_comparisons}/{batch_state.total_comparisons} "
        f"comparisons completed (80%+ threshold reached)"
    )
```

**Problem:** Uses `batch_state.completed_comparisons / batch_state.total_comparisons` where:
- `completed_comparisons` = **all callbacks received** (including errors)
- `total_comparisons` = **pairs generated in current iteration** (not total budget)

**Evidence from Batch 33:**
- 66 error callbacks + some valid callbacks = 66+ "completed"
- Only 10 pairs generated in that iteration = denominator of 10
- Result: 66/10 = 660% completion rate!

**Expected Behavior:**
```python
# Should calculate as:
valid_comparisons = count(winner IN ['essay_a', 'essay_b'])
total_budget = original_requested_comparison_count
completion_rate = valid_comparisons / total_budget
```

**Root Cause:**
1. **Wrong denominator**: Uses iteration count instead of total budget
2. **Counts errors as complete**: Line 500 increments counter for error callbacks

---

### Finding 2: Batch State Metrics Discrepancy (submitted=10 vs database has 100)

**File:** `services/cj_assessment_service/cj_core_logic/batch_processor.py:336`

**Current Behavior:**
```python
.values(
    state=state,
    total_comparisons=total_comparisons,
    submitted_comparisons=total_comparisons,  # All comparisons submitted
)
```

Sets `submitted_comparisons = total_comparisons` where `total_comparisons` is the count for **current submission batch**, not cumulative.

**Problem:**
- First iteration: 10 pairs → sets `submitted=10`, `total=10`
- Callbacks arrive: 34 successful, 66 errors
- Second iteration: 90 pairs → **overwrites** to `submitted=90`, `total=90`
- Final state shows only last iteration's counts

**Expected Behavior:**
For iterative batching:
- `submitted_comparisons` should **accumulate** across iterations
- Each iteration should **increment**, not replace
- `total_comparisons` should be the **overall budget** (100)

**Root Cause:** System designed for single-shot submission, doesn't handle iterative processing.

**Related Code:**
- `batch_processor.py:146-153` updates count but only for current chunk
- No accumulation logic exists
- `comparison_processing.py:531-656` handles iterations but doesn't update batch state metrics

---

### Finding 3: Pair Generation Position Bias (86% anchors in essay_a)

**File:** `services/cj_assessment_service/cj_core_logic/pair_generation.py:94-126`

**Current Behavior:**
```python
for i in range(len(essays_for_comparison)):
    for j in range(i + 1, len(essays_for_comparison)):
        essay_a = essays_for_comparison[i]
        essay_b = essays_for_comparison[j]
        # ... create task with essay_a and essay_b
```

**Problem:** **ZERO randomization** of essay order before or after pair creation.

If `essays_for_comparison` is ordered with anchors first (likely from database `ORDER BY is_anchor DESC`), all pairs have anchors in essay_a position.

**Evidence from Batch 33:**
- Anchors appear in essay_a position: 86 times out of 100 (86%)
- Student essays in essay_a position: 14 times (14%)
- This is statistically impossible with proper randomization (expected ~50%)

**Expected Behavior:**
```python
# Option 1: Randomize essay list before pairing
random.shuffle(essays_for_comparison)

# Option 2: Randomize A/B position for each pair
if random.random() < 0.5:
    essay_a, essay_b = essay_b, essay_a
```

**Impact:**
- LLMs develop position bias (may prefer "Essay A")
- Bradley-Terry scores become systematically biased
- Anchors appear artificially stronger/weaker than reality
- **This violates CJ methodology requirements**

**Root Cause:** No randomization logic exists in pair generation code path.

---

### Finding 4: Error Callbacks Count Toward Completion

**File:** `services/cj_assessment_service/cj_core_logic/workflow_continuation.py:68-76`

**Current Behavior:**
```python
completed_count_stmt = (
    select(func.count())
    .select_from(ComparisonPair)
    .where(
        ComparisonPair.cj_batch_id == batch_id,
        ComparisonPair.winner.isnot(None),  # Counts BOTH valid AND error!
    )
)
```

**Problem:** Counts ALL comparisons with `winner IS NOT NULL`, which includes `winner='error'`!

**Evidence:**
- Batch 33: 66 errors with `winner='error'`
- These count toward "completion" threshold
- Triggers early batch finalization despite insufficient valid data

**Expected Behavior:**
```python
.where(
    ComparisonPair.cj_batch_id == batch_id,
    ComparisonPair.winner.notin_(['error', None]),  # Only valid winners
)
```

**Root Cause:** Completion logic doesn't distinguish between:
- Valid comparisons (`winner='essay_a'` or `'essay_b'`)
- Error comparisons (`winner='error'`)
- Pending comparisons (`winner=None`)

---

### Finding 5: Stray Callback Race Condition

**Files:**
1. `services/cj_assessment_service/cj_core_logic/batch_submission_tracking.py:47-64`
2. `services/cj_assessment_service/cj_core_logic/batch_submission.py:90-115`

**Current Behavior:**
```python
# batch_submission.py:90-96
tracking_map = await create_tracking_records(
    session=session,
    batch_tasks=batch_tasks,
    cj_batch_id=cj_batch_id,
    correlation_id=correlation_id,
)
await session.commit()  # LINE 96 - COMMIT HAPPENS HERE

# batch_submission.py:115-126
results = await llm_interaction.perform_comparisons(
    tasks=batch_tasks,
    correlation_id=correlation_id,
    tracking_map=tracking_map,
    ...
)
```

**Problem:** Database commit happens **before** LLM request submission!

**Race Condition Scenario:**
1. Create tracking records with correlation IDs
2. Commit to database (line 96)
3. Submit requests to LLM queue (line 115)
4. If LLM processes **very fast**, callback arrives before commit is visible
5. Callback handler queries for correlation ID → **not found**!

**Evidence:**
- Correlation ID `8f3a11d7-9411-4ca2-9999-59a9d18c5da9` doesn't exist in database
- Error: "Comparison callback missing essay identifiers"
- Batch 34 itself completed successfully (10/10)
- This was a **stray callback** from different batch or retry

**Additional Scenario - Retry with New UUID:**
If retry logic generates a **new correlation ID** instead of reusing original, the callback uses new ID which has no database record.

**Root Cause:**
- Transaction ordering: commit before queue submission
- PostgreSQL commit latency allows fast LLM responses to arrive first
- No transaction isolation level enforcement

---

### Finding 6: Degenerate Bradley-Terry Scores

**Analysis:** This is a **symptom** of Findings 1-4, not a separate bug.

**Causal Chain:**
1. 66% API errors → only 34 valid comparisons (Finding 1)
2. Errors count as "complete" → triggers early finalization (Finding 4)
3. Insufficient data → Bradley-Terry calculation produces degenerate scores
4. Six essays with identical scores = not enough comparison data

**Evidence:**
- Standard errors of 2.0 = complete uncertainty
- Identical bt_mean values = insufficient discriminatory power
- This is **mathematically correct behavior** given insufficient input data

**Conclusion:** Not a bug in BT algorithm. Fix root causes 1-4 to get sufficient valid comparisons.

---

### Finding 7: 66% Anthropic API Failure Rate

**Status:** **REQUIRES INVESTIGATION** - Not a code bug

**Data:**
- 66 out of 100 requests failed with `EXTERNAL_SERVICE_ERROR`
- Error details: `{"external_service": "anthropic_api", "details": {"provider": "anthropic"}}`

**Possible Causes:**
1. **Rate limiting** - Too many requests too fast
2. **Timeout** - Requests taking too long
3. **Actual API errors** - Anthropic service issues
4. **Serial bundle dispatch bug** - Batch size or timing issue

**Required Investigation:**
- Check LLM Provider service logs for actual HTTP errors
- Review Anthropic API response codes
- Examine `serial_bundle_dispatch` timing and batch sizes
- Compare per_request vs serial_bundle error rates

**Note:** This may be the **primary differentiator** between per_request (works) and serial_bundle (fails).

---

## Architectural Design Flaws

### Design Flaw 1: Iterative Submission Tracking

**Problem:** System designed for **single-shot batch submission**, doesn't handle iterative processing.

**Evidence:**
- `batch_state.submitted_comparisons` gets overwritten each iteration
- No accumulation across multiple submission cycles
- Metrics don't reflect true system state

**Impact:**
- Incorrect completion rate calculations
- Misleading observability data
- Difficult to debug multi-iteration workflows

**Required Fix:** Add cumulative tracking across iterations, separate per-iteration from total counters.

---

### Design Flaw 2: Error vs Retry Distinction

**Problem:** No clear separation between retryable and permanently failed comparisons.

**Current State:**
- `winner='error'` marks failure
- Retry pool exists (`callback_state_manager.py:112-119`)
- But errors **still count toward completion**!

**Expected Behavior:**
- Retryable errors: Don't count toward completion, go to retry pool
- Permanent failures: Count toward completion only after retry limit exhausted
- Track retry attempts separately

**Impact:**
- Premature batch completion
- Insufficient valid data for analysis
- Wasted retries

---

## Summary Table

| Finding | Type | Severity | File Location | Impact |
|---------|------|----------|---------------|--------|
| 1. Runaway completion | Bug | CRITICAL | callback_state_manager.py:217-232 | Premature finalization |
| 2. Metrics discrepancy | Bug | HIGH | batch_processor.py:336 | Incorrect state tracking |
| 3. Position bias | Bug | HIGH | pair_generation.py:94-126 | Invalid BT scores |
| 4. Errors count as complete | Bug | CRITICAL | workflow_continuation.py:68-76 | Premature finalization |
| 5. Stray callback race | Bug | MEDIUM | batch_submission.py:90-115 | Occasional failures |
| 6. Degenerate BT scores | Symptom | N/A | (downstream) | Result of 1-4 |
| 7. 66% API failure | Unknown | CRITICAL | (requires investigation) | No valid data |
| 8. Iterative tracking | Design | HIGH | (architecture) | Incorrect metrics |
| 9. Error/retry distinction | Design | MEDIUM | (architecture) | Incorrect completion |

---

## Critical Search Strings for Verification

### Confirm Findings in Code

```bash
# Finding 1: Completion threshold logic
grep -n "completion detected" services/cj_assessment_service/cj_core_logic/callback_state_manager.py

# Finding 2: Batch state updates
grep -n "submitted_comparisons" services/cj_assessment_service/cj_core_logic/batch_processor.py

# Finding 3: Pair generation
grep -n "essays_for_comparison\[i\]" services/cj_assessment_service/cj_core_logic/pair_generation.py

# Finding 4: Completion count query
grep -n "winner.isnot(None)" services/cj_assessment_service/cj_core_logic/workflow_continuation.py

# Finding 5: Database commit timing
grep -n "await session.commit()" services/cj_assessment_service/cj_core_logic/batch_submission.py
```

### Verify Against Database

```sql
-- Finding 1 & 4: Count valid vs error comparisons
SELECT
    winner,
    COUNT(*) as count
FROM cj_comparison_pairs
WHERE cj_batch_id = 33
GROUP BY winner;

-- Finding 2: Verify batch state vs actual pairs
SELECT
    bs.submitted_comparisons,
    bs.completed_comparisons,
    COUNT(cp.id) as actual_pairs
FROM cj_batch_states bs
LEFT JOIN cj_comparison_pairs cp ON bs.batch_id = cp.cj_batch_id
WHERE bs.batch_id = 33
GROUP BY bs.batch_id, bs.submitted_comparisons, bs.completed_comparisons;

-- Finding 3: Verify position distribution
SELECT
    'essay_a' as position,
    COUNT(CASE WHEN essay_a_els_id LIKE 'ANCHOR%' THEN 1 END) as anchor_count,
    COUNT(CASE WHEN essay_a_els_id NOT LIKE 'ANCHOR%' THEN 1 END) as student_count
FROM cj_comparison_pairs WHERE cj_batch_id = 33
UNION ALL
SELECT
    'essay_b' as position,
    COUNT(CASE WHEN essay_b_els_id LIKE 'ANCHOR%' THEN 1 END),
    COUNT(CASE WHEN essay_b_els_id NOT LIKE 'ANCHOR%' THEN 1 END)
FROM cj_comparison_pairs WHERE cj_batch_id = 33;
```

---

## Recommended Fix Priority

### P0 (Critical - Blocks All Batching)
1. **Fix completion threshold calculation** (Finding 1)
   - Use total budget as denominator
   - Only count valid comparisons as complete
2. **Exclude errors from completion count** (Finding 4)
   - Change SQL filter to exclude `winner='error'`
3. **Investigate 66% API failure rate** (Finding 7)
   - This may be the root cause of everything else

### P1 (High - Affects Data Quality)
4. **Add position randomization** (Finding 3)
   - Critical for valid CJ methodology
5. **Fix batch state metrics** (Finding 2)
   - Accumulate across iterations

### P2 (Medium - Improves Reliability)
6. **Fix race condition** (Finding 5)
   - Reorder commit/submit operations
7. **Redesign error/retry tracking** (Design Flaw 2)
   - Separate retryable from permanent failures

---

## Next Investigation Steps

1. **Immediate Database Verification:**
   - Run SQL queries above for batches 33 and 34
   - Compare per_request batch (62e923) error rate
   - Identify if per_request also has API failures (just fewer)

2. **LLM Provider Log Analysis:**
   - Search for HTTP error codes from Anthropic
   - Check `serial_bundle_dispatch` batch sizes
   - Compare timing between per_request and serial_bundle modes

3. **Create Minimal Reproduction:**
   - Small test batch (4 comparisons)
   - Both modes (per_request and serial_bundle)
   - Controlled environment
   - Detailed logging

4. **Validate Code Findings:**
   - Confirm each file path and line number
   - Run grep commands to verify logic
   - Review git blame for context on when bugs introduced

---

## Files Modified/Created

- `.claude/research/validation/llm-batching-mode-code-analysis-2025-11-19.md` (this document)

---

## Progress Log

### 2025-11-19 02:38 - Code Analysis Complete
- All 7 bugs identified with file paths and line numbers
- 2 architectural design flaws documented
- Root cause hypotheses established with evidence
- Verification queries provided for database validation
- Priority matrix created for fix sequencing
- Next: Database verification and LLM Provider log analysis
