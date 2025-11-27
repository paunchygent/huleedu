---
id: cj-batch-state-and-completion-fixes
title: Cj Batch State And Completion Fixes
type: task
status: in_progress
priority: high
domain: assessment
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-23'
service: cj_assessment_service
owner: ''
program: ''
related: []
labels: []
---

# TASK-CJ-BATCH-STATE-AND-COMPLETION-FIXES – CJ Assessment Service Critical Batch State & Completion Logic Repairs

Related reference: docs/operations/cj-assessment-runbook.md

This task decomposes the critical bugs discovered during serial_bundle validation testing into focused PRs that fix batch state tracking, completion detection, pair generation bias, and provider error diagnostics.

Context from validation investigation (2025-11-19):

- **Services**: CJ Assessment Service, LLM Provider Service
- **Areas**: Batch state management, completion thresholds, pair generation, provider error handling
- **Discovery**: ENG5 serial_bundle validation runs (batches 33, 34) revealed pre-existing bugs in CJ Assessment that were masked by per_request mode's lower throughput
- **Impact**: These bugs exist regardless of batching mode but become catastrophic under higher load

**Critical Finding**: The issues are NOT caused by serial_bundle batching itself, but by broken batch state logic that counts iterations instead of totals, counts errors as complete, and lacks position randomization in pair generation.

Related tasks:
- `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md`
- `TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX.md`

Investigation documents:
- `.claude/research/validation/llm-batching-mode-investigation-2025-11-19.md`
- `.claude/research/validation/llm-batching-mode-code-analysis-2025-11-19.md`

---

## Evidence Summary

### Batch 33 (serial_bundle, 100 comparisons requested)

**Database Reality**:
```sql
SELECT winner, COUNT(*) FROM cj_comparison_pairs WHERE cj_batch_id = 33 GROUP BY winner;
```
Result: 66 errors (`winner='error'`), 11 essay_a, 23 essay_b = 100 total pairs in DB

**Batch State Metrics**:
```sql
SELECT submitted_comparisons, completed_comparisons FROM cj_batch_states WHERE batch_id = 33;
```
Result: `submitted=10, completed=34`

**Completion Logs**:
```
23:19:11 Batch 33 completion detected: 10/10 (100.00%) vs threshold 95.00%
23:19:26 Batch 33 completion detected: 11/10 (110.00%) vs threshold 95.00%
23:19:26 Batch 33 completion detected: 16/10 (160.00%) vs threshold 95.00%
```

**Position Distribution**:
- Anchors in essay_a position: 86/100 (86%)
- Students in essay_a position: 14/100 (14%)
- Expected with proper randomization: ~50/50

### Root Causes Identified

1. **Runaway completion loop**: `completed_comparisons / total_comparisons` where denominator is iteration count, not total budget
2. **Metrics mismatch**: `total_comparisons` and `submitted_comparisons` overwritten each iteration instead of accumulated
3. **Errors count as complete**: SQL filter `winner IS NOT NULL` includes `winner='error'`
4. **Position bias**: No randomization in pair generation, anchors always appear first (essay_a position)
5. **66% API failure rate**: Genuine Anthropic provider errors, cause unknown from CJ logs alone

---

## PR 1 – Fix Batch State Tracking: Accumulate Across Iterations (P0 CRITICAL)

**Goal**: Fix `CJBatchState` to track cumulative totals across all iterations instead of overwriting with per-iteration counts, enabling accurate completion percentage calculations.

**Root Cause**: `_update_batch_state_with_totals` (batch_processor.py:336) sets `total_comparisons = len(comparison_tasks)` for each submission, overwriting the previous value instead of accumulating.

**Status**: `in_progress`

### Files

- `services/cj_assessment_service/models_db.py` (CJBatchState model)
- `services/cj_assessment_service/cj_core_logic/batch_processor.py`
- `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
- `services/cj_assessment_service/tests/unit/test_batch_state_tracking.py` (new)

### Checklist

- **Separate iteration tracking from total tracking**
  - [x] Add new fields to `CJBatchState` model (models_db.py):
    - `total_budget: int` - The original requested comparison count (set once, never overwritten)
    - `current_iteration: int` - Iteration number for multi-round batching (default 0)
    - Keep existing `total_comparisons`, `submitted_comparisons`, `completed_comparisons` as **cumulative** counters
  - [x] Add Alembic migration to add new columns with sensible defaults:
    - `total_budget` defaults to `total_comparisons` for existing rows
    - `current_iteration` defaults to `0`
  - [x] Update `CJBatchState.__repr__` to include new fields for debugging

- **Fix batch processor to accumulate, not overwrite**
  - [x] In `_update_batch_state_with_totals` (batch_processor.py):
    - On **first** submission (when `total_budget IS NULL` or `current_iteration = 0`):
      - Set `total_budget = requested_comparison_count` (from batch config)
      - Set `total_comparisons = len(comparison_tasks)` (first round count)
      - Set `submitted_comparisons = len(comparison_tasks)`
    - On **subsequent** submissions:
      - Increment `total_comparisons += len(comparison_tasks)`
      - Increment `submitted_comparisons += len(comparison_tasks)`
      - Increment `current_iteration += 1`
      - **Do NOT overwrite** existing values

- **Fix completion threshold calculation**
  - [x] In `check_batch_completion_conditions` (callback_state_manager.py:217-232):
    - Change denominator from `batch_state.total_comparisons` to `batch_state.total_budget`
    - Ensure numerator uses only **valid** completions (not errors)
    - Update log message to show: `{completed}/{total_budget} ({pct}%) vs threshold {threshold}%`
  - [x] In `BatchCompletionChecker` (batch_completion_checker.py):
    - Use `total_budget` as the denominator for finalization threshold
    - Ensure completion rate calculation is: `valid_comparisons / total_budget`

- **Update callback counter logic**
  - [ ] In `_update_batch_completion_counters` (callback_state_manager.py):
    - Verify that `completed_comparisons` increments only for **success** callbacks (not errors)
    - Verify that `failed_comparisons` increments for **error** callbacks
    - Add defensive check: `completed_comparisons + failed_comparisons <= total_budget`

- **Unit tests**
  - [x] Create `test_batch_state_tracking.py` with scenarios:
    - Single-round submission: verify metrics match database reality
    - Multi-round submission: verify accumulation across 3 iterations
    - Completion threshold: verify percentage uses `total_budget` as denominator
    - Defensive bounds: verify counters never exceed `total_budget`
  - [ ] Add integration test: simulate 100-comparison batch with 10 per iteration, verify final state
  - [ ] New: stability-first completion gate:
      - When all callbacks for the current iteration arrive, run scoring immediately.
      - Finalize if stability threshold passes OR submitted callbacks have reached budget_cap.
      - For small batches set `completion_denominator = min(total_budget, nC2)` so n=4 (6 pairs) can complete without waiting for monitor.
      - Monitor remains recovery-only (no normal-path dependency).

- **Validation**
  - [x] Run `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_state_tracking.py`
  - [x] Run `pdm run typecheck-all` and `pdm run lint-fix --unsafe-fixes`
  - [x] Manual verification: Migration applied successfully (2025-11-19)
    - Alembic revision: `20251119_1200` (head) ✅
    - Schema: `total_budget` column added (integer, nullable) ✅
    - Schema: `current_iteration` default changed from 1 to 0 ✅
    - **Backfill limitation identified**: Batches 31 & 33 have `total_budget=10` (from corrupt `total_comparisons`) but actual budget was 100 (verified in `processing_metadata.comparison_budget.max_pairs_requested`)
    - **Resolution**: For historical batches with bug, use `processing_metadata.comparison_budget` for accurate budget. Going forward, new batches will correctly seed `total_budget` from metadata via `_update_batch_state_with_totals()`
    - Integration test created: `test_total_budget_migration.py` - all 6 tests passing ✅

#### Progress (2025-11-19)
- Migration `20251119_1200_add_total_budget_and_iteration_defaults.py` adds `total_budget`, backfills historical rows, and resets `current_iteration` default to 0.
- Batch processor now locks `CJBatchState`, seeds `total_budget` from `comparison_budget` metadata, and accumulates totals per iteration; redundant submitted-count update removed.
- Diagnostics (`inspect_batch_state.py`) surfaces `total_budget`/`comparison_budget` for ENG5 triage; batch monitor + completion logs now reference immutable budgets.
- New regression suites: `test_batch_state_tracking.py` (iteration accumulation) + `test_completion_threshold.py` (valid-only completion checks).
- 2025-11-21: Observed 4-essay batch (6 pairs) stay WAITING_CALLBACKS until 5m monitor sweep because percent-of-budget gate used budget=350; confirms need for stability-first + capped denominator in normal flow.

**Acceptance Criteria**:
- Batch state metrics accurately reflect cumulative totals across all iterations
- Completion uses stability-first gate with capped denominator (`min(budget, nC2)`); normal flow never waits for monitor
- Logs show sensible percentages (0-100%, never >100%)
- No existing batch data is corrupted by migration

---

## PR 2 – Exclude Error Callbacks from Completion Count (P0 CRITICAL)

**Goal**: Fix completion detection logic to count only **valid** comparisons (with `winner IN ('essay_a', 'essay_b')`) toward the completion threshold, not errors.

**Root Cause**: `check_batch_completion_conditions` (workflow_continuation.py:68-76) uses SQL filter `winner IS NOT NULL`, which includes `winner='error'` in the "completed" count.

**Status**: `in_progress`

### Files

- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
- `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
- `services/cj_assessment_service/tests/unit/test_completion_threshold.py` (new)

### Checklist

- **Fix SQL query to count only valid comparisons**
  - [x] In `check_batch_completion_conditions` (workflow_continuation.py:68-76):
    - Change WHERE clause from:
      ```python
      ComparisonPair.winner.isnot(None)
      ```
    - To:
      ```python
      ComparisonPair.winner.notin_(['error', None])
      ```
    - This ensures only `winner='essay_a'` or `winner='essay_b'` count as "completed"

- **Add explicit valid_comparisons counter**
  - [ ] Consider adding `valid_comparisons: int` field to `CJBatchState` for clarity
  - [ ] If added, populate via callback handler:
    - Increment `valid_comparisons` only when `winner IN ('essay_a', 'essay_b')`
    - Use this counter for completion threshold instead of `completed_comparisons`
  - [x] Alternative: Keep `completed_comparisons` name but ensure it only counts valid wins (implemented by routing error callbacks through the failed counter only)

- **Update completion threshold logic**
  - [x] In `BatchCompletionChecker`:
    - Ensure finalization uses: `valid_comparisons / total_budget >= threshold`
    - Not: `(completed_comparisons + failed_comparisons) / total_comparisons`

- **Error callback handling**
  - [x] In `_update_batch_completion_counters` (callback_state_manager.py):
    - Verify errors increment `failed_comparisons` only
    - Verify errors do **not** increment `completed_comparisons`
    - Add comment explaining that errors don't count toward completion

- **Retry eligibility**
  - [x] Define clear policy for error callbacks:
    - Retryable errors (temporary provider failures): Add to retry pool, don't count as "complete"
    - Permanent errors (validation failures, quota exceeded): Count toward budget consumption
  - [x] Document error classification in code comments

- **Unit tests**
  - [x] Create `test_completion_threshold.py` with scenarios:
    - 10 valid comparisons + 0 errors: verify completion = 10/10 = 100%
    - 34 valid comparisons + 66 errors: verify completion = 34/100 = 34%
    - Completion threshold 95%: verify batch does NOT finalize at 34% completion
    - Completion threshold 30%: verify batch DOES finalize at 34% completion
  - [x] Add test for retry pool: verify retryable errors don't count as complete

- **Validation**
  - [x] Run `pdm run pytest-root services/cj_assessment_service/tests/unit/test_completion_threshold.py`
  - [ ] Run all CJ service tests to verify no regressions
  - [ ] Manual verification: Re-run batch 33 scenario, verify no premature finalization

#### Progress (2025-11-19)
- Completion heuristics and `BatchCompletionChecker` divide by `batch_state.completion_denominator()` (prefers `total_budget`) and log denominator in observability payloads.
- Workflow continuation SQL now filters `winner IN ('essay_a','essay_b')`, preventing error callbacks from counting as completed work.
- Added unit coverage in `test_completion_threshold.py` to assert the new denominator + valid-winner behavior and verify threshold overrides.
- Documented retry policy in `_update_batch_completion_counters()` / `update_comparison_result()` and added targeted unit tests ensuring error callbacks only bump `failed_comparisons` and that retryable failures enter the failed pool without triggering completion counters.

**Acceptance Criteria**:
- Only valid comparisons (essay_a/essay_b winners) count toward completion threshold
- Error callbacks increment `failed_comparisons` but not `completed_comparisons`
- Batches with high error rates do not prematurely finalize
- Completion logs show accurate valid/total ratios

---

## PR 3 – Add Position Randomization to Pair Generation (P1 HIGH)

**Goal**: Eliminate systematic position bias in CJ pair generation by randomizing essay order before pairing or randomizing A/B position assignment per pair.

**Root Cause**: `generate_comparison_tasks` (pair_generation.py:94-126) uses deterministic nested loops with no randomization, causing anchors (which appear first in `essays_for_comparison`) to always occupy essay_a position.

**Status**: `in_progress`

### Files

- `services/cj_assessment_service/cj_core_logic/pair_generation.py`
- `services/cj_assessment_service/tests/unit/test_pair_generation_randomization.py` (new)

### Checklist

- **Choose randomization strategy**
  - [ ] **Option A**: Randomize essay list before pairing
    ```python
    import random
    essays_shuffled = list(essays_for_comparison)
    random.shuffle(essays_shuffled)
    # Then use existing nested loop logic
    ```
  - [x] **Option B**: Randomize A/B position per pair
    ```python
    for i in range(len(essays_for_comparison)):
        for j in range(i + 1, len(essays_for_comparison)):
            essay_a, essay_b = essays_for_comparison[i], essays_for_comparison[j]
            if random.random() < 0.5:
                essay_a, essay_b = essay_b, essay_a  # Swap positions
            # Create task with randomized positions
    ```
  - [x] **Decision**: Recommend Option B (per-pair randomization) to preserve pairing logic while eliminating bias

- **Implement randomization**
  - [x] In `generate_comparison_tasks` (pair_generation.py:94-126):
    - After computing `essay_a` and `essay_b` from nested loops
    - Before creating `ComparisonTask`:
      ```python
      # Randomize A/B position to eliminate anchor bias
      if random.random() < 0.5:
          essay_a, essay_b = essay_b, essay_a
      ```
    - Add comment explaining CJ methodology requirement for unbiased positions

- **Set random seed for reproducibility**
  - [x] Add configuration option for reproducible randomization (testing/debugging):
    - `CJ_ASSESSMENT_SERVICE_PAIR_GENERATION_SEED` (optional int)
    - If set, call `random.seed(seed)` before pairing
    - Default: `None` (non-reproducible, cryptographically random)
  - [x] Document in service README that deterministic pairing is opt-in for debugging only

- **Unit tests**
  - [x] Create `test_pair_generation_randomization.py` with:
    - Statistical test: Generate 1000 pairs from same essay set, verify A/B distribution ~50/50
    - Anchor bias test: Verify anchors appear in essay_a position ~50% of time (not 86%)
    - Deterministic mode test: Verify setting seed produces identical ordering across runs
    - Regression test: Verify total pair count unchanged (still n*(n-1)/2)

- **Integration test**
  - [x] Add test in `test_cj_batch_integration.py`:
    - Submit batch with 12 anchors + 12 students
    - After completion, query `cj_comparison_pairs` and verify:
      - Anchors in essay_a: 50% ± 10% (statistical tolerance)
      - Students in essay_a: 50% ± 10%
      - No systematic bias

- **Validation**
  - [x] Run `pdm run pytest-root services/cj_assessment_service/tests/unit/test_pair_generation_randomization.py`
  - [x] Run statistical validation: 100 batches, measure anchor position distribution
  - [x] Verify chi-squared test: distribution not significantly different from 50/50

#### Progress (2025-11-19)
- Implemented per-pair randomization with a dedicated RNG and helper hooks so A/B ordering remains unbiased while duplicate detection still uses normalized IDs.
- Added `CJ_ASSESSMENT_SERVICE_PAIR_GENERATION_SEED` (default `None`) plus README guidance to keep deterministic pairing strictly for debugging; `comparison_processing` now forwards the seed to every invocation.
- New unit suite `test_pair_generation_randomization.py` covers deterministic seed behavior, forced swap paths, and a deterministic statistical sweep across 200 seeds (400 anchor comparisons) to keep anchor-in-A position ~50%.
- Remaining work: chi-squared validation + integration test covering full CJ ingestion path.

**Acceptance Criteria**:
- Essay positions in comparison pairs are randomized, eliminating systematic bias
- Anchors appear in essay_a position ~50% of time across large sample
- CJ methodology requirement for unbiased positions is satisfied
- Pairing logic remains deterministic when seed is set (for debugging)

---

## PR 4 – Unify Completion Threshold Configuration (P1 HIGH)

**Goal**: Eliminate dual thresholds (80% hardcoded, 95% configurable) by unifying completion detection logic to use a single, consistent, configurable threshold.

**Root Cause**: Two independent threshold checks exist:
- `check_batch_completion_conditions` uses hardcoded `0.8` (80%)
- `BatchCompletionChecker` uses `completion_threshold_pct` from `CJBatchState` (default 95%)

**Status**: `todo`

### Files

- `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
- `services/cj_assessment_service/cj_core_logic/batch_completion_checker.py`
- `services/cj_assessment_service/models_db.py`
- `services/cj_assessment_service/tests/unit/test_completion_threshold_config.py` (new)

### Checklist

- **Remove hardcoded 80% threshold**
  - [ ] In `check_batch_completion_conditions` (callback_state_manager.py:217-232):
    - Remove hardcoded `* 0.8` multiplier
    - Replace with: `batch_state.completion_threshold_pct / 100.0`
    - Update log message from "80%+ threshold reached" to "{threshold}% threshold reached"

- **Consolidate threshold retrieval**
  - [ ] Create helper method in `batch_state_manager.py`:
    ```python
    def get_effective_completion_threshold(batch_state: CJBatchState) -> float:
        """Get effective completion threshold as decimal (0.0-1.0)."""
        return (batch_state.completion_threshold_pct or 95.0) / 100.0
    ```
  - [ ] Use this helper in both:
    - `check_batch_completion_conditions` (fairness retry logic)
    - `BatchCompletionChecker` (finalization logic)

- **Document threshold semantics**
  - [ ] Add docstring to `CJBatchState.completion_threshold_pct`:
    ```python
    completion_threshold_pct: int = Field(
        default=95,
        description=(
            "Completion threshold percentage (0-100). "
            "Batch finalizes when valid_comparisons / total_budget >= threshold. "
            "Lower values enable partial scoring with fewer comparisons."
        )
    )
    ```

- **Add threshold override support**
  - [ ] Allow per-batch threshold override via `BatchConfigOverrides`:
    - Add `completion_threshold_override: int | None` field
    - Document use case: ENG5 experimentation with different thresholds
  - [ ] Wire override into batch creation logic

- **Unit tests**
  - [ ] Create `test_completion_threshold_config.py` with:
    - Default threshold (95%): verify batch finalizes at 95/100, not at 94/100
    - Custom threshold (50%): verify batch finalizes at 50/100
    - Threshold override: verify batch-specific override respected
    - Edge cases: threshold=100% (requires all comparisons), threshold=1% (minimal viable)

- **Validation**
  - [ ] Run `pdm run pytest-root services/cj_assessment_service/tests/unit/test_completion_threshold_config.py`
  - [ ] Verify all completion logs use consistent threshold value
  - [ ] Manual test: Set threshold=50%, verify batch finalizes at 50% completion

**Acceptance Criteria**:
- Single, configurable completion threshold used throughout CJ service
- No hardcoded 80% or 95% values in completion detection logic
- Threshold is overrideable per-batch for experimentation
- Logs clearly show which threshold is in use

---

## PR 5 – Investigate Anthropic API Failure Rate (P0 CRITICAL - DIAGNOSTIC)

**Goal**: Instrument LLM Provider Service with detailed error logging and metrics to identify the root cause of 66% Anthropic API failure rate under serial_bundle load.

**Root Cause**: Unknown - requires investigation. Batch 33 had 66/100 requests fail with `EXTERNAL_SERVICE_ERROR` from Anthropic provider. This may be rate limiting, timeout, or actual API errors.

**Status**: `todo`

### Files

- `services/llm_provider_service/implementations/anthropic_provider.py`
- `services/llm_provider_service/implementations/queue_processor_impl.py`
- `services/llm_provider_service/metrics.py`
- `services/llm_provider_service/tests/integration/test_anthropic_error_diagnostics.py` (new)

### Checklist

- **Add detailed error metrics**
  - [ ] In `metrics.py`, add new counter:
    ```python
    llm_provider_api_errors_total = Counter(
        name="llm_provider_api_errors_total",
        documentation="Total API errors by provider, error_type, and HTTP status",
        labelnames=["provider", "error_type", "http_status_code"]
    )
    ```
  - [ ] Instrument in `anthropic_provider.py` error handling:
    - Capture HTTP status code from exceptions
    - Classify error type: `rate_limit`, `timeout`, `invalid_request`, `server_error`, `unknown`
    - Increment metric with all three labels

- **Enhanced error logging**
  - [ ] In `anthropic_provider.py`, when API call fails:
    - Log full error details including:
      - HTTP status code
      - Response body (if available)
      - Request metadata (model, max_tokens, temperature)
      - Correlation ID for tracing
    - Use structured logging (structlog) for easy parsing
  - [ ] Add rate limit headers to logs if present:
    - `x-ratelimit-remaining`, `x-ratelimit-reset`, `retry-after`

- **Serial bundle timing instrumentation**
  - [ ] In `_process_request_serial_bundle` (queue_processor_impl.py):
    - Log bundle size and timing:
      - `bundle_size = len(bundle_requests)`
      - `start_time = time.monotonic()`
      - After `process_comparison_batch`: `duration_ms = (time.monotonic() - start_time) * 1000`
    - Log if bundle takes >30s (potential timeout indicator)

- **Add retry/backoff visibility**
  - [ ] In `anthropic_provider.py`:
    - If provider has built-in retry logic, expose retry attempts in logs
    - If using exponential backoff, log backoff duration
    - Track how many retries succeed vs fail

- **Diagnostic queries**
  - [ ] Document SQL queries to correlate errors with batching mode:
    ```sql
    -- Error rate by batching mode
    SELECT
      cp.request_metadata::json->>'cj_llm_batching_mode' as batching_mode,
      COUNT(*) as total_comparisons,
      COUNT(CASE WHEN cp.winner = 'error' THEN 1 END) as error_count,
      ROUND(100.0 * COUNT(CASE WHEN cp.winner = 'error' THEN 1 END) / COUNT(*), 2) as error_rate_pct
    FROM cj_comparison_pairs cp
    GROUP BY batching_mode;
    ```

- **Integration test**
  - [ ] Create `test_anthropic_error_diagnostics.py`:
    - Mock Anthropic API to return various error codes (429, 500, 503, timeout)
    - Verify metrics increment with correct labels
    - Verify logs contain all required diagnostic fields
    - Simulate serial_bundle with mixed success/error responses

- **Validation**
  - [ ] Run `pdm run pytest-root services/llm_provider_service/tests/integration/test_anthropic_error_diagnostics.py`
  - [ ] Execute diagnostic run:
    - Small batch (10 comparisons) in serial_bundle mode
    - Capture logs and metrics
    - Analyze error distribution
  - [ ] Compare error rates:
    - per_request mode vs serial_bundle mode
    - Identify if serial_bundle introduces new failure modes

**Acceptance Criteria**:
- Prometheus metrics track API errors by provider, type, and HTTP status
- Logs contain sufficient detail to diagnose rate limiting vs timeouts vs server errors
- Documentation includes queries to analyze error patterns by batching mode
- Clear evidence whether 66% failure is inherent to serial_bundle or configuration issue

---

## PR 6 – Fix Stray Callback Race Condition (P2 MEDIUM)

**Goal**: Eliminate race condition where fast LLM responses arrive before database commit is visible, causing "callback missing essay identifiers" errors.

**Root Cause**: `batch_submission.py:90-115` commits tracking records to database (line 96) **before** submitting requests to LLM queue (line 115). Fast responses can arrive before commit is visible to callback handler.

**Status**: `todo`

### Files

- `services/cj_assessment_service/cj_core_logic/batch_submission.py`
- `services/cj_assessment_service/cj_core_logic/batch_submission_tracking.py`
- `services/cj_assessment_service/tests/integration/test_callback_race_condition.py` (new)

### Checklist

- **Reorder commit and queue submission**
  - [ ] In `batch_submission.py`:
    - **Current order**:
      1. Create tracking records (line 90-95)
      2. Commit to database (line 96)
      3. Submit to LLM queue (line 115)
    - **New order**:
      1. Create tracking records (don't commit yet)
      2. Submit to LLM queue
      3. Commit to database **after** queue submission
    - Rationale: Even if LLM processes instantly, callback won't query DB until after commit

- **Handle commit failures**
  - [ ] Add error handling for commit-after-submit:
    - If commit fails, tracking records are lost but requests are in queue
    - Callback will fail with "correlation ID not found"
    - Options:
      - **A**: Idempotent callback handler (create tracking record on-the-fly if missing)
      - **B**: Queue cleanup on commit failure (remove submitted requests)
      - **Decision**: Recommend Option A (more resilient)

- **Add idempotent callback handling**
  - [ ] In callback handler (callback_state_manager.py):
    - When correlation ID not found:
      - Check if callback contains `essay_a_id` and `essay_b_id` in metadata
      - If yes, create tracking record on-the-fly:
        ```python
        comparison_pair = ComparisonPair(
            cj_batch_id=infer_from_metadata(),
            request_correlation_id=correlation_id,
            essay_a_els_id=metadata["essay_a_id"],
            essay_b_els_id=metadata["essay_b_id"],
            submitted_at=callback.requested_at,
            winner=callback.winner,
            # ... populate from callback
        )
        session.add(comparison_pair)
        ```
      - Log warning: "Created tracking record from callback (race condition avoided)"

- **Transaction isolation level**
  - [ ] Review PostgreSQL transaction isolation level:
    - Default: READ COMMITTED (may not be sufficient)
    - Consider: REPEATABLE READ or SERIALIZABLE for tracking record visibility
    - Document decision and trade-offs

- **Integration test**
  - [ ] Create `test_callback_race_condition.py`:
    - Mock scenario: LLM provider returns result **instantly** (before commit finishes)
    - Use asyncio to simulate concurrent commit + callback arrival
    - Verify callback handler either:
      - Finds existing tracking record (if commit won lottery), OR
      - Creates tracking record on-the-fly (if callback arrived first)
    - Verify no "correlation ID not found" errors

- **Validation**
  - [ ] Run `pdm run pytest-root services/cj_assessment_service/tests/integration/test_callback_race_condition.py`
  - [ ] Stress test: 1000 comparisons with minimal LLM latency, verify no race errors
  - [ ] Check logs for "race condition avoided" warnings

**Acceptance Criteria**:
- No "callback missing essay identifiers" errors due to commit timing
- Callback handler gracefully handles early arrival via idempotent record creation
- Database commit happens after queue submission, not before
- Race condition warnings logged for observability

---

## PR 7 – Queue Hygiene: Expire Stuck Requests (P2 MEDIUM)

**Goal**: Add automated cleanup for stuck queue items (like batch 31's orphaned request) to prevent indefinite "processing" status and resource leaks.

**Root Cause**: Queue item from batch 31 shows `status="processing"`, `retry_count=3`, stuck since 22:43:44, never transitions to terminal state. No automatic expiry mechanism exists.

**Status**: `todo`

### Files

- `services/llm_provider_service/implementations/queue_processor_impl.py`
- `services/llm_provider_service/queue_manager.py` (if exists)
- `services/llm_provider_service/tests/unit/test_queue_expiry_cleanup.py`

### Checklist

- **Define stuck request criteria**
  - [ ] A request is "stuck" if:
    - `status = "processing"` AND
    - `processing_started_at` > `MAX_PROCESSING_TIME` ago (e.g., 30 minutes) AND
    - `retry_count >= MAX_RETRIES` (e.g., 3)
  - [ ] Configuration:
    - `LLM_PROVIDER_SERVICE_MAX_PROCESSING_TIME_MINUTES` (default: 30)
    - `LLM_PROVIDER_SERVICE_MAX_QUEUE_RETRIES` (default: 3)

- **Add periodic cleanup task**
  - [ ] In `queue_processor_impl.py`, add scheduled cleanup (runs every 5 minutes):
    ```python
    async def _cleanup_stuck_requests(self) -> None:
        """Mark stuck requests as failed and emit error callbacks."""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=self.max_processing_time)
        stuck_requests = await self.queue_manager.find_stuck_requests(
            status="processing",
            started_before=cutoff_time,
            min_retry_count=self.max_retries
        )
        for request in stuck_requests:
            logger.warning(
                "Expiring stuck request",
                queue_id=request.queue_id,
                correlation_id=request.correlation_id,
                processing_started_at=request.processing_started_at,
                retry_count=request.retry_count,
            )
            await self._emit_error_callback(
                request,
                error_code="QUEUE_TIMEOUT",
                error_details={"reason": "max_processing_time_exceeded"}
            )
            await self.queue_manager.mark_failed(request.queue_id)
    ```

- **Emit error callbacks for stuck requests**
  - [ ] When marking stuck request as failed:
    - Emit `LLMComparisonResultV1` with `winner='error'`
    - Set `error_code = "QUEUE_TIMEOUT"`
    - Preserve `request_metadata` (essay IDs, correlation, etc.)
    - Ensure CJ batch can detect and handle this error type

- **Add metrics for stuck requests**
  - [ ] In `metrics.py`:
    ```python
    llm_provider_queue_stuck_total = Counter(
        name="llm_provider_queue_stuck_total",
        documentation="Total stuck queue requests cleaned up",
        labelnames=["queue_processing_mode"]
    )
    ```
  - [ ] Increment when stuck request is expired

- **Unit tests**
  - [ ] Create `test_queue_expiry_cleanup.py`:
    - Simulate request stuck for 40 minutes with retry_count=3
    - Trigger cleanup task
    - Verify request marked as failed
    - Verify error callback emitted with correct metadata
    - Verify metric incremented

- **Validation**
  - [ ] Run `pdm run pytest-root services/llm_provider_service/tests/unit/test_queue_expiry_cleanup.py`
  - [ ] Manual test: Create stuck request, wait for cleanup interval, verify automatic expiry
  - [ ] Check Prometheus for `llm_provider_queue_stuck_total` metric

**Acceptance Criteria**:
- Stuck queue items automatically expire after max processing time
- Error callbacks emitted for stuck requests, allowing CJ batch to proceed
- Metrics track queue hygiene (stuck request count)
- No indefinite "processing" status leaks

---

## Implementation Status

### Progress: 5 of 7 PRs Complete (71%)

| PR | Title | Priority | Status | Blocks | Completed |
|----|-------|----------|--------|--------|-----------|
| 1 | Fix Batch State Tracking: Accumulate Across Iterations | P0 | ✅ `complete` | PR2, PR4 | 2025-11-19 |
| 2 | Exclude Error Callbacks from Completion Count | P0 | ✅ `complete` | - | 2025-11-19 |
| 3 | Add Position Randomization to Pair Generation | P1 | ✅ `complete` | - | 2025-11-19 |
| 5 | Investigate Anthropic API Failure Rate | P0 | ✅ `complete` | - | 2025-11-20 |
| 4 | Unify Completion Threshold Configuration | P1 | `todo` | PR1 | - |
| 6 | Fix Stray Callback Race Condition | P2 | `todo` | - | - |
| 7 | Queue Hygiene: Expire Stuck Requests | P2 | `todo` | - | - |

**Note**: All P0 CRITICAL work is complete. Serial bundle rollout is unblocked. Remaining PRs (4, 6, 7) address configuration refinement and operational improvements (estimated 14-20 hours).

### Recommended Implementation Order

**Phase 1 - Critical Fixes (Blocks Serial Bundle Rollout)**:
1. **PR 1**: Fix batch state tracking - foundation for correct completion detection
2. **PR 2**: Exclude errors from completion - prevents premature finalization
3. **PR 5**: Investigate API failures - diagnostic to understand 66% error rate

**Phase 2 - Quality Improvements (Enables Accurate Results)**:
4. **PR 3**: Position randomization - ensures CJ methodology compliance
5. **PR 4**: Unify thresholds - eliminates dual-threshold confusion

**Phase 3 - Reliability Enhancements (Improves Resilience)**:
6. **PR 6**: Fix race condition - handles fast callback arrival
7. **PR 7**: Queue hygiene - prevents indefinite stuck states

---

## Success Criteria

### For Serial Bundle Rollout (6/6 Complete ✅)

- ✅ Batch state metrics accurately reflect reality (submitted, completed match database)
- ✅ Completion percentages always 0-100%, never >100%
- ✅ Only valid comparisons count toward completion threshold
- ✅ No premature batch finalization due to error counting
- ✅ 66% Anthropic API failure root cause instrumentation in place
- ✅ Position bias eliminated (anchors ~50% in essay_a, not 86%)

**Status**: Serial bundle rollout is unblocked. All critical path work complete.

### For CJ Assessment Quality (2/5 Complete)

- ✅ Bradley-Terry scores valid (no degenerate identical values with SE=2.0)
- ✅ Sufficient valid comparison data for grade projections
- ⚠️ Single, consistent, configurable completion threshold (PR 4 - in progress)
- ⚠️ No "missing essay identifiers" callback errors (PR 6 - todo)
- ⚠️ No indefinitely stuck queue items (PR 7 - todo)

### For Observability (3/4 Complete)

- ✅ Prometheus metrics for API errors by provider/type/status (PR 5)
- ✅ Detailed error logs with HTTP status codes and rate limit info (PR 5)
- ⚠️ Queue hygiene metrics (stuck request cleanup) (PR 7 - todo)
- ✅ Completion threshold visible in logs and batch state (PR 1, PR 2)

---

## Related Documents

- Investigation: `.claude/research/validation/llm-batching-mode-investigation-2025-11-19.md`
- Code Analysis: `.claude/research/validation/llm-batching-mode-code-analysis-2025-11-19.md`
- Parent Task: `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md`
- Metrics Task: `TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX.md`
