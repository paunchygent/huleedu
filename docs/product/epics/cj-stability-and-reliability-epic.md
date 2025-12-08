---
type: epic
id: EPIC-005
title: CJ Stability & Reliability
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-28
last_updated: 2025-12-07
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

Bundling and wave semantics for CJ ↔ LLM Provider are documented in:
- `docs/decisions/0017-cj-assessment-wave-submission-pattern.md` (ADR‑0017: wave-based
  submission & `preferred_bundle_size` hints).
- `docs/operations/cj-assessment-runbook.md` and
  `services/llm_provider_service/README.md` (serial bundling, `preferred_bundle_size`,
  and `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` default 64). Future work on resampling,
  retry semantics, or provider batch APIs should treat these documents as the
  source of truth for the CJ↔LPS bundling contract.

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
- [ ] `CJBatchState.completion_denominator()` is the single source of truth for **budget-based** completion math in both `BatchCompletionChecker` and `BatchCompletionPolicy` (see ADR-0020):
  - For all batches, `completion_denominator()` reflects the per-batch comparison budget (`total_budget`), derived from either a per-request override or `MAX_PAIRWISE_COMPARISONS`.
  - Small-net coverage semantics (`nC2` over the comparison graph) and Phase-2 resampling behaviour are driven by explicit small-net metadata (`max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, `resampling_pass_count`, `small_net_resampling_cap`), not by clamping the denominator to `nC2`.
  - Follow-up hardening: see `TASKS/assessment/cj-completion-semantics-v2-enforce-total_budget-and-remove-nc2-fallback.md` for removing legacy `nC2`/`total_comparisons` fallbacks from `completion_denominator()` and treating missing `total_budget` as a strict error.
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
- [ ] Wave size is treated as emergent (from batch size, matching strategy, and caps) rather than a dedicated per-wave setting; stability is controlled via thresholds and caps instead of a fixed comparisons-per-iteration parameter.
- [ ] Docs:
  - `docs/services/cj-assessment-service.md` (or existing service doc) clearly explains:
    - Wave size = `compute_wave_size(n) ≈ n // 2` after odd-count handling
    - `MAX_PAIRWISE_COMPARISONS` = global hard cap
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

### US-005.4: Convergence Tests for Iterative/Bundled Mode ✅ PR‑7 HARNESS IMPLEMENTED

**As a** developer
**I want** a test harness that validates convergence behavior under configurable parameters
**So that** I can verify stability checks and iteration limits work correctly.

**Acceptance Criteria**:
- [x] A test harness wires the BT scoring helper and stability check into a configurable loop over synthetic nets with:
  - `MIN_COMPARISONS_FOR_STABILITY_CHECK`
  - `MAX_ITERATIONS`
  - `MAX_PAIRWISE_COMPARISONS`
- [x] Tests assert that:
  - Stability checks only run after `MIN_COMPARISONS_FOR_STABILITY_CHECK` successful comparisons
  - Additional iterations stop when either:
    - Stability is achieved, or
    - `MAX_PAIRWISE_COMPARISONS` or `MAX_ITERATIONS` is reached
- [x] Convergence harness explicitly models **two phases**:
  - Phase 1 (unique coverage): waves/batches add new edges until coverage of the n-choose-2 graph is complete or capped by budget.
  - Phase 2 (resampling): waves/batches re-use the same n-choose-2 bundle to add additional judgments on existing pairs until stability or caps are reached.
- [x] Small-net behaviour is guarded:
  - For batches with fewer than `MIN_RESAMPLING_NET_SIZE` essays, Phase-2 resampling is limited by a dedicated cap (e.g. `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`) to prevent tiny nets from consuming all remaining budget when stability cannot be reliably detected.
- [x] The behaviour for bundled/wave-style convergence is documented in the epic doc and backed by unit tests, with convergence owned by `workflow_continuation` + `BatchFinalizer` in production and the convergence harness remaining a synthetic, test-only loop.

**Implementation Notes (PR‑7 snapshot)**:
- Harness module: `services/cj_assessment_service/cj_core_logic/convergence_harness.py`
  - Uses `compute_bt_scores_and_se(...)` and `check_score_stability(...)` over in‑memory `EssayForComparison` nets and synthetic `CJ_ComparisonPair` objects.
  - Encodes Phase‑1 vs Phase‑2 behaviour directly:
    - Phase‑1: only previously unseen pairs are scheduled until n‑choose‑2 coverage or `MAX_PAIRWISE_COMPARISONS` is hit.
    - Phase‑2: once coverage completes, subsequent iterations resample from the full pair set subject to budget and iteration caps.
  - Surfaces convergence outcome via a typed `HarnessResult`:
    - `final_scores`, `stability_achieved`, `cap_reason` (`stability`, `iterations`, `budget`), `iterations_run`, `total_comparisons`, and final SE diagnostics.
- Tests: `services/cj_assessment_service/tests/unit/test_convergence_harness.py`
  - `test_convergence_harness_stops_on_stability_before_max_iterations`:
    - Synthetic 4‑essay net with easily separable “true” scores and permissive stability threshold; asserts early stop on stability.
  - `test_convergence_harness_stops_after_max_iterations_or_budget`:
    - Same net but with `MIN_COMPARISONS_FOR_STABILITY_CHECK` set above any reachable comparison count; asserts stop on iteration caps.
  - These tests complement the small‑net Phase‑2 semantics in `test_workflow_continuation.py` by exercising the pure convergence loop.

**Task**: `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`

---

### US-005.X: RESAMPLING A/B Positional Fairness and Mode Generalization

**As a** psychometrics-aware platform owner  
**I want** RESAMPLING mode to (a) maintain fair A/B positional usage per essay and per unordered pair and (b) be available as a controlled continuation tool for non‑small‑net batches  
**So that** large-scale comparison statistics remain unbiased and convergence behaviour is consistent across batch sizes.

**Acceptance Criteria (positional fairness)**:
- [x] RESAMPLING mode’s pair generation (`PairGenerationMode.RESAMPLING`) is **pair-history aware** and enforces, where budget allows, that each unordered pair `{e1, e2}` is observed in both orientations `(A=e1,B=e2)` and `(A=e2,B=e1)` at least once. (With `MAX_PAIRWISE_COMPARISONS=552` in regular batches, all 276 unordered pairs are complemented AB+BA; with the production budget `MAX_PAIRWISE_COMPARISONS=288`, only ~4.3% of pairs are resampled, yielding a residual ≈0.167 skew that is expected from incomplete complement coverage, not an algorithm defect.)
- [x] COVERAGE mode’s orientation decisions actively work to balance per‑essay A/B positional counts over time, using persisted `ComparisonPair` history rather than pure randomness.
- [x] Over multiple COVERAGE + RESAMPLING waves on a stable net, each essay’s A/B positional share converges toward 50/50 within an agreed tolerance band (e.g. ≤ 1–3 percentage points drift for ENG5/LOWER5), verified by unit tests and docker harness runs (LOWER5 now observes 0.0 skew with `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`).
- [x] Docker/E2E validation demonstrates that for an ENG5 LOWER5 small net under mock profiles, A/B positional skew per essay stays within the configured band across resampling passes, and that per‑pair AB/BA complements are realised when budget and caps permit.

**Acceptance Criteria (mode generalization)**:
- [ ] RESAMPLING mode can be invoked for larger/non‑small‑net batches under well-defined conditions (e.g. after a minimum coverage/stability cadence), not only when `ContinuationContext.is_small_net` is true.
- [ ] Configuration includes distinct caps:
  - `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` (existing) for small nets.
  - `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (new) for larger batches.
- [ ] Orchestration logic in `workflow_continuation.trigger_existing_workflow_continuation`:
  - Continues to route small nets through the existing small‑net Phase‑2 resampling path.
  - Introduces a general‑resampling branch for non‑small‑net batches that respects the new regular‑batch resampling cap and overall budget.
- [ ] Unit tests cover:
  - Small‑net resampling semantics (unchanged in spirit from PR‑7, but now tested alongside positional fairness).
  - RESAMPLING behaviour for larger nets, including adherence to the regular‑batch resampling cap.

**Tasks**:
- `TASKS/assessment/cj-resampling-a-b-positional-fairness.md`
- `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md`
- `TASKS/assessment/cj-positional-orientation-strategy-for-coverage-and-resampling.md`

---

### US-005.6: BatchMonitor Separation of Concerns

**As a** system maintainer
**I want** BatchMonitor to delegate all finalization logic to BatchFinalizer
**So that** monitoring and finalization responsibilities are cleanly separated per DDD principles.

**Context**:
The `BatchMonitor` class currently violates SRP by mixing monitoring (detecting stuck batches) with finalization (implementing a full scoring pipeline via `_trigger_scoring()`). This duplicates ~200 lines of logic already present in `BatchFinalizer.finalize_scoring()` and creates state semantics divergence (`COMPLETE_STABLE` vs `COMPLETED`).

**Acceptance Criteria**:
- [ ] `BatchMonitor._trigger_scoring()` is removed (~200 lines)
- [ ] `_handle_stuck_batch()` delegates to `BatchFinalizer.finalize_scoring()` for progress >= 80%
- [ ] New `COMPLETE_FORCED_RECOVERY` status distinguishes monitor-forced completions
- [ ] Identical events are published for both callback-driven and monitor-forced paths
- [ ] Unit tests verify BatchFinalizer delegation in monitor path
- [ ] Integration tests confirm event parity between paths

**Task**: `TASKS/assessment/batchmonitor-separation-of-concerns.md`
**ADR**: `docs/decisions/0022-batchmonitor-separation-of-concerns.md`

---

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
PR‑2 and are delivered in PR‑7. The original xfail tests documenting the intended
behaviour have been replaced with passing tests once the implementation matched
the design.

## PR-7 Phase-2 Resampling Plan (Design Sketch)

PR-7 extends the PR-2 stability and success-rate semantics with explicit
Phase-2 behaviour for small nets and a convergence harness. The key design
decisions (now implemented) are:

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
  - Phase-1 (coverage) behaviour is unchanged for large nets and uses
    `completion_denominator()` (`total_budget` per ADR-0020 v2) for completion
    gating, with stability and success-rate checks as in PR-2. Coverage metrics
    (`max_possible_pairs`, `successful_pairs_count`) are handled via explicit
    metadata, not by clamping the denominator.
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
  - A dedicated harness wires the existing BT scoring routines into a
    configurable loop over synthetic nets, with knobs for:
    `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `MAX_ITERATIONS`,
    `MAX_PAIRWISE_COMPARISONS`, and `SCORE_STABILITY_THRESHOLD`.
  - The harness stops either when stability is achieved (BT deltas below
    threshold) or when iteration/budget caps are reached, and will surface
    which cap fired for diagnostics.

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
