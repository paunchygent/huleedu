---
type: epic
id: EPIC-005
title: CJ Stability & Reliability
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-28
last_updated: 2025-11-29
---

# EPIC-005: CJ Stability & Reliability

## Summary

Harden the CJ Assessment callback and completion flow to ensure safe finalization semantics, proper stability checks, and robust retry handling under failure conditions.

**Business Value**: Prevent premature finalization of batches with insufficient valid comparisons, ensuring reliable ranking quality even under high LLM callback failure rates.

**Scope Boundaries**:
- **In Scope**: Callback-driven continuation, completion gating, score stability semantics, retry processor integration, convergence testing
- **Out of Scope**: Grade projection quality (EPIC-006), developer tooling (EPIC-007)

**Implementation Status (2025‑11‑29)**:
- PR‑1 (test harness & fixtures for CJ) and PR‑2 (stability semantics & completion safety)
  are implemented and merged into `main`. PR‑7 remains planned for Phase‑2 resampling and
  small‑net semantics.

## User Stories

### US-005.1: Callback-driven Continuation and Safe Completion Gating

**As a** system operator
**I want** the CJ workflow to only proceed when all expected callbacks have arrived
**So that** batches are never finalized prematurely with incomplete comparison data.

**Acceptance Criteria**:
- [ ] `check_workflow_continuation` returns `true` only when:
  - `submitted_comparisons > 0`, and
  - `pending_callbacks == 0` (where `pending = submitted - (completed + failed)`),
  - Logs all four counters plus `completion_denominator` for the batch
- [ ] When `pending_callbacks > 0`, continuation is skipped and a structured log line shows `pending_callbacks`, `submitted_comparisons`, `completed_comparisons`, and `failed_comparisons`
- [ ] `CJBatchState.completion_denominator()` is the single source of truth for completion math in both `BatchCompletionChecker` and `BatchCompletionPolicy`:
  - For small batches (e.g. 4 essays → 6 max pairs), completion is measured against the n-choose-2 maximum
  - For large batches, completion is measured against `min(total_budget, max_possible_pairs)`
- [ ] A batch with `completed_comparisons == 0` is **never** finalized as COMPLETE_*:
  - If all attempts fail, the batch ends in an explicit error status and logs a clear error reason
- [ ] Integration tests cover:
  - 2‑essay batch (minimum viable)
  - 100+ essay batch (scalability) with realistic budgets
  - ≥50% callback failures, verifying that the batch is not incorrectly marked complete

**Task**: `TASKS/assessment/cj-us-005-1-callback-continuation-and-completion.md`

---

### US-005.2: Score Stability Semantics & Early Stopping

**As a** system operator
**I want** CJ to apply consistent stability criteria before finalization
**So that** early stopping is predictable and cost-efficient without sacrificing ranking quality.

**Acceptance Criteria**:
- [ ] On each fully-completed callback iteration, `trigger_existing_workflow_continuation`:
  - Recomputes BT scores via `record_comparisons_and_update_scores`
  - Persists `bt_scores`, `last_scored_iteration`, and `last_score_change` into `CJBatchState.processing_metadata`
- [ ] Stability is considered "passed" only when:
  - `callbacks_received >= MIN_COMPARISONS_FOR_STABILITY_CHECK`, and
  - `max_score_change <= SCORE_STABILITY_THRESHOLD`, where `max_score_change` is computed with `check_score_stability`
- [ ] Finalization happens only when **one** of these is true:
  - Stability passed (as above), or
  - `callbacks_received` has reached the `completion_denominator()`, or
  - Global budget is exhausted (`submitted_comparisons >= MAX_PAIRWISE_COMPARISONS`)
- [ ] A high failure‑rate batch with few **successful** comparisons does **not** finalize:
  - Explicit test: "many failed, few successful" keeps the batch in a non-terminal state or moves it to an error state, never COMPLETE_*
- [ ] Phase-2 semantics are explicit:
  - Phase 1: comparison budget is first spent on **unique coverage** of the n-choose-2 graph for the batch (each unordered essay-pair compared at least once, subject to global caps).
  - Phase 2: once unique coverage is complete and stability has not passed, additional budget is spent on **resampling the same pairwise graph** (re-judging existing pairs) until:
    - Stability is achieved, or
    - Global budget or `MAX_ITERATIONS` is reached, with success-rate constraints still enforced.
- [ ] `COMPARISONS_PER_STABILITY_CHECK_ITERATION` is treated as a **cadence hint** (how often we re-check stability), not as a hard per-wave cap:
  - Code does **not** use it to slice or truncate the wave returned by `compute_wave_pairs`
  - Settings docstrings and service docs are updated to reflect this interpretation
- [ ] Docs:
  - `docs/services/cj-assessment-service.md` (or existing service doc) clearly explains:
    - Wave size = `compute_wave_size(n) ≈ n // 2` after odd-count handling
    - `MAX_PAIRWISE_COMPARISONS` = global hard cap
    - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` = approximate number of new comparisons between stability checks
    - Bradley-Terry standard errors are computed analytically in `bt_inference.compute_bt_standard_errors` and capped at `BT_STANDARD_ERROR_MAX = 2.0` for numerical safety and observability only (no change to completion or gating semantics)

---

### PR-3 Notes: BT Standard Error Diagnostics (Observability Only)

- Batch-level BT SE diagnostics are now computed in `record_comparisons_and_update_scores`
  and emitted in structured logs:
  - `mean_se`, `max_se`, `min_se`
  - `item_count`, `comparison_count`
  - `items_at_cap`, `isolated_items`
  - `mean_comparisons_per_item`, `min_comparisons_per_item`, `max_comparisons_per_item`
- Grade projection summaries expose SE diagnostics under
  `GradeProjectionSummary.calibration_info["bt_se_summary"]` with separate aggregates for:
  - `"all"` essays
  - `"anchors"` only
  - `"students"` only
- Workflow continuation persists both:
  - `bt_se_summary` (batch-level BT SE diagnostics), and
  - `bt_quality_flags` – a small set of **observability-only** batch quality indicators:
    - `bt_se_inflated`: True when mean or max BT SE exceeds diagnostic thresholds
    - `comparison_coverage_sparse`: True when mean comparisons per essay falls below a diagnostic floor
    - `has_isolated_items`: True when any essays are isolated in the comparison graph
- These diagnostics are intended for future EPIC-006 quality/health indicators and external
  tooling; they do **not** alter:
  - Completion denominator semantics
  - Stability thresholds (`MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`)
  - Success-rate guard semantics or thresholds

**Task**: `TASKS/assessment/cj-us-005-2-score-stability-and-early-stopping.md`

---

### PR-4: Scoring Core Refactor (BT Inference Robustness) ✅ MERGED

**Purpose:** Make the Bradley–Terry scoring core easier to reason about and safer to extend
for EPIC‑005/EPIC‑006, without changing PR‑2’s completion, stability, or success‑rate
semantics. This work is **merged and in production** as of 2025‑11‑29.

- Introduce a domain-level result object in `scoring_ranking.py`:
  - `BTScoringResult` with:
    - `scores: dict[str, float]` – BT scores (mean-centred) keyed by `els_essay_id`
    - `ses: dict[str, float]` – per‑essay BT standard errors (capped at `BT_STANDARD_ERROR_MAX`)
    - `per_essay_counts: dict[str, int]` – comparison coverage per essay
    - `se_summary: dict[str, float | int]` – batch‑level SE diagnostics (same fields as PR‑3 logs)
- Extract a pure helper:
  - `compute_bt_scores_and_se(all_essays, comparisons) -> BTScoringResult`
  - Responsibilities:
    - Build the BT graph (`choix_comparison_data`, `per_essay_counts`)
    - Call `choix.ilsr_pairwise` + `bt_inference.compute_bt_standard_errors`
    - Mean‑centre scores and assemble `BTScoringResult`
    - Raise the same `raise_cj_insufficient_comparisons` /
      `raise_cj_score_convergence_failed` conditions as the current implementation
  - No session management, no `CJBatchState` writes.
- Refactor `record_comparisons_and_update_scores` so that it:
  - Uses a single `SessionProviderProtocol` session to:
    - Persist new `CJ_ComparisonPair` rows for the current wave
    - Load all valid comparisons for the batch
    - Update `CJ_ProcessedEssay` scores/SEs/counts via `_update_essay_scores_in_database`
  - Delegates BT math to `compute_bt_scores_and_se` and logs `se_summary`
  - Returns `scores` as today so existing callers (including PR‑2) remain unchanged.
- Workflow integration (no behaviour change):
  - `trigger_existing_workflow_continuation` continues to:
    - Recompute scores via `record_comparisons_and_update_scores(...)`
    - Compute `max_score_change` with `check_score_stability`
    - Enforce `MIN_COMPARISONS_FOR_STABILITY_CHECK` and `SCORE_STABILITY_THRESHOLD`
    - Apply the success‑rate guard (`MIN_SUCCESS_RATE_THRESHOLD`) for routing to
      `finalize_scoring` vs `finalize_failure`
    - Persist `bt_scores`, `last_scored_iteration`, and `last_score_change` into
      `CJBatchState.processing_metadata` using its own session.
  - `BatchFinalizer.finalize_scoring` continues to:
    - Call `record_comparisons_and_update_scores(...)` once
    - Build rankings via `get_essay_rankings`
    - Invoke `GradeProjector.calculate_projections` and publish events as before.
- Ownership of batch state:
  - All writes to `CJBatchState` remain in workflow / finalizer / monitor code that already
    owns the transaction; the scoring core no longer issues its own `CJBatchState` updates.
- Forward-looking (EPIC‑006/PR‑7):
  - Orchestrators may later use `BTScoringResult.se_summary` to:
    - Persist SE/coverage metadata on `CJBatchState` in a controlled fashion, or
    - Drive higher-level “batch quality” indicators,
    without changing gating or stability semantics.

**Tasks:**
- `TASKS/assessment/us-0052-score-stability-semantics-and-early-stopping.md`
- `TASKS/assessment/cj-assessment-code-hardening.md`

---

### US-005.3: Retry Semantics and End-of-Batch Fairness

**As a** system operator
**I want** the CJ workflow to retry failed comparisons when budget remains
**So that** high LLM failure rates don't permanently degrade ranking quality.

**Acceptance Criteria**:
- [ ] When `FAILED_COMPARISON_RETRY_THRESHOLD` is reached and comparison budget remains:
  - `trigger_existing_workflow_continuation` invokes the injected `BatchRetryProcessor` at least once before finalization, using either:
    - `process_remaining_failed_comparisons`, or
    - `submit_retry_batch`, depending on the chosen API
- [ ] Retry logic respects:
  - `MAX_PAIRWISE_COMPARISONS` global cap
  - Per-comparison `MAX_RETRY_ATTEMPTS`
- [ ] Tests cover:
  - Scenario with high failure rate and remaining budget, verifying that:
    - A retry batch is submitted
    - No duplicate pairs are created
  - Scenario with no failed comparisons: retry processor is **not** invoked
- [ ] Logs for retry decisions include:
  - `cj_batch_id`, `failed_comparisons`, `retry_batch_size`, and remaining budget
- [ ] Fairness is preserved:
  - Retry batches must not systematically over-sample already heavily-compared essays (validated with simple coverage statistics in tests)

**Task**: `TASKS/assessment/cj-us-005-3-retry-semantics-and-fairness.md`

---

### US-005.4: Convergence Tests for Iterative/Bundled Mode

**As a** developer
**I want** a test harness that validates convergence behavior under configurable parameters
**So that** I can verify stability checks and iteration limits work correctly.

**Acceptance Criteria**:
- [ ] A test harness wires `_process_comparison_iteration` + `_check_iteration_stability` with configurable:
  - `COMPARISONS_PER_STABILITY_CHECK_ITERATION`
  - `MIN_COMPARISONS_FOR_STABILITY_CHECK`
  - `MAX_ITERATIONS`
  - `MAX_PAIRWISE_COMPARISONS`
- [ ] Tests assert that:
  - Stability checks only run after `MIN_COMPARISONS_FOR_STABILITY_CHECK` successful comparisons
  - Additional iterations stop when either:
    - Stability is achieved, or
    - `MAX_PAIRWISE_COMPARISONS` or `MAX_ITERATIONS` is reached
- [ ] Convergence harness explicitly models **two phases**:
  - Phase 1 (unique coverage): waves/batches add new edges until coverage of the n-choose-2 graph is complete or capped by budget.
  - Phase 2 (resampling): waves/batches re-use the same n-choose-2 bundle to add additional judgments on existing pairs until stability or caps are reached.
- [ ] Small-net behaviour is guarded:
  - For batches with fewer than `MIN_RESAMPLING_NET_SIZE` essays, Phase-2 resampling is limited by a dedicated cap (e.g. `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`) to prevent tiny nets from consuming all remaining budget when stability cannot be reliably detected.
- [ ] The behaviour and intended future wiring for bundled iterative mode is documented in the epic doc

**Task**: `TASKS/assessment/cj-us-005-4-iterative-convergence-tests.md`

## PR-2 Completion Notes

PR-2 (US‑005.1, US‑005.2, US‑005.4 foundations) wires the following
behaviour into the CJ Assessment Service:

- Continuation only runs when all callbacks for the current iteration have
  arrived; partial callback waves never trigger scoring.
- BT score stability is evaluated between iterations using
  `check_score_stability`, with `MIN_COMPARISONS_FOR_STABILITY_CHECK` and
  `SCORE_STABILITY_THRESHOLD` enforced.
- A success‑rate guard is applied whenever caps/budgets are hit:
  batches with zero successful comparisons, or with a success‑rate below
  `MIN_SUCCESS_RATE_THRESHOLD`, finalize via `BatchFinalizer.finalize_failure`
  instead of `finalize_scoring`.
- ELS observes explicit CJ failure via `CJAssessmentFailedV1` so that
  essay/batch states move to `CJ_ASSESSMENT_FAILED` rather than remaining in
  an indeterminate pending state.

Phase‑2 resampling semantics and small‑net caps remain **out of scope** for
PR‑2 and are tracked for PR‑7; existing xfail tests document the intended
future behaviour but do not change pair‑generation in this PR.

## PR-7 Phase-2 Resampling Plan (Design Sketch)

PR-7 extends the PR-2 stability and success-rate semantics with explicit
Phase-2 behaviour for small nets and a convergence harness. The key design
decisions are:

- **New settings** (CJ Assessment `Settings`):
  - `MIN_RESAMPLING_NET_SIZE`: Nets with `expected_essay_count` below this are
    treated as *small* and are eligible for special Phase-2 handling.
  - `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`: Maximum number of resampling passes
    allowed for a small net once unique coverage is complete.
- **New metadata in `CJBatchState.processing_metadata`** (no schema changes):
  - `max_possible_pairs`: n-choose-2 upper bound over the **full CJ graph**
    for the batch, i.e. all `ProcessedEssay` nodes that participate in BT
    scoring (students **and** anchors). In PR-7 this implies updating
    `CJBatchState._max_possible_comparisons()` to derive `n` from the actual
    `ProcessedEssay` set rather than from `expected_essay_count` alone.
  - `successful_pairs_count`: number of unordered pairs `(a,b)` in that full
    CJ graph that have at least one successful comparison (`winner` in
    `{"essay_a", "essay_b"}`).
  - `unique_coverage_complete`: `True` when
    `successful_pairs_count >= max_possible_pairs` for nets with `nC2 > 0`.
  - `resampling_pass_count`: how many Phase-2 resampling passes have already
    been performed for this batch (starts at `0`).
- **Ownership of Phase-2 logic**:
  - `workflow_continuation.trigger_existing_workflow_continuation` remains the
    single source of truth for: stability checks, success-rate guards, and
    Phase-1 vs Phase-2 branching.
  - A repository helper on `CJComparisonRepositoryProtocol` will provide
    coverage metrics (e.g. `successful_pairs_count`) at iteration boundaries.
  - Pair generation (`pair_generation.py`) stays agnostic; it receives a
    "mode" (coverage vs resampling) via its inputs but does not manage
    coverage metadata itself.
- **Phase-1 vs Phase-2 semantics**:
  - Phase-1 (coverage) behaviour is unchanged for large nets and still uses
    `completion_denominator()` as the effective coverage cap
    (`min(total_budget, nC2)`), with stability and success-rate checks as in
    PR-2.
  - For small nets (`expected_essay_count < MIN_RESAMPLING_NET_SIZE`), the
    *first* time `callbacks_received >= completion_denominator()` with
    stability not yet passed is treated as a **phase boundary**:
    - `unique_coverage_complete` is set to `True`.
    - `resampling_pass_count` is initialised to `0`.
    - Instead of forcing immediate finalization, continuation may enter
      Phase-2 resampling.
  - In Phase-2 for small nets, `workflow_continuation` will:
    - Continue to honour PR-2 stability and success-rate semantics when
      finalizing.
    - Request additional comparisons (resampling existing pairs) only while:
      `unique_coverage_complete is True`, budget remains, and
      `resampling_pass_count < MAX_RESAMPLING_PASSES_FOR_SMALL_NET`.
    - Increment and persist `resampling_pass_count` each time a new
      resampling wave is triggered.
    - Once the small-net resampling cap is hit (or budget is exhausted), stop
      resampling and finalize using the existing success-rate guard
      (`finalize_scoring` vs `finalize_failure`).
- **Convergence harness (US-005.4)**:
  - A dedicated harness will wire the existing BT scoring routines into a
    configurable loop over synthetic nets, with knobs for:
    `COMPARISONS_PER_STABILITY_CHECK_ITERATION`,
    `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `MAX_ITERATIONS`, and
    `MAX_PAIRWISE_COMPARISONS`.
  - The harness will stop either when stability is achieved (BT deltas below
    threshold) or when iteration/budget caps are reached, and will surface
    which cap fired for diagnostics.

Existing PR-7 xfail tests in `test_workflow_continuation.py` and
`test_convergence_harness.py` encode these behaviours as forward-looking
specs; they will be flipped to passing tests once the implementation matches
this design.

## Technical Architecture

### Data Flows
```
Callback → check_workflow_continuation → trigger_existing_workflow_continuation
    ↓
[if all callbacks received]
    ↓
Recompute BT scores → check_score_stability → Finalize OR request more waves
    ↓
[if high failure rate + budget remaining]
    ↓
BatchRetryProcessor.submit_retry_batch → New comparison wave
```

### Key Services
- **CJ Assessment Service**: `services/cj_assessment_service/`
- **Workflow Continuation**: `services/cj_assessment_service/src/workflow_continuation.py`
- **Batch Callback Handler**: `services/cj_assessment_service/src/batch_callback_handler.py`
- **Batch Completion**: `services/cj_assessment_service/src/batch_completion_checker.py`

### Configuration Points
- `MIN_COMPARISONS_FOR_STABILITY_CHECK`: Minimum successful comparisons before stability check
- `SCORE_STABILITY_THRESHOLD`: Maximum allowed BT score change for stability
- `MAX_PAIRWISE_COMPARISONS`: Global comparison budget cap
- `COMPARISONS_PER_STABILITY_CHECK_ITERATION`: Cadence between stability checks
- `FAILED_COMPARISON_RETRY_THRESHOLD`: Failure count triggering retry logic
- `MAX_RETRY_ATTEMPTS`: Per-comparison retry limit

## Related ADRs
- ADR-0015: CJ Assessment Convergence Tuning Strategy

## Dependencies
- LLM Provider Service (callback source)
- Kafka (event transport)

## Notes
- Runbook: `docs/operations/cj-assessment-runbook.md`
- Related to EPIC-004 (core CJ features)
- Supersedes archived task `TASKS/archive/2025/11/assessment/cj-assessment-pr-review-improvements.md`
