---
id: 'pr-7-phase-2-resampling-and-convergence-harness'
title: 'PR-7 Phase-2 Resampling and Convergence Harness'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-30'
last_updated: '2025-11-30'
related: []
labels: []
---
# PR-7 Phase-2 Resampling and Convergence Harness

## Objective

Deliver PR‑7 under EPIC‑005 by implementing Phase‑2 resampling semantics, small‑net behaviour, coverage‑driven metadata, and a convergence harness for CJ Assessment, while keeping existing PR‑2/PR‑4 invariants intact.

## Context

EPIC‑005 (CJ Stability & Reliability) defines US‑005.1–US‑005.4. PR‑2 and PR‑4 implemented callback‑driven continuation, stability semantics, and BT scoring refactors, but explicitly left Phase‑2 resampling, small‑net caps, and the convergence harness out of scope. The doc `docs/product/epics/cj-stability-and-reliability-epic.md` plus `docs/product/epics/pr-7-phase2-resampling-checklist.md` define the PR‑7 design:

- Phase‑1: spend budget on unique coverage of the n‑choose‑2 comparison graph.
- Phase‑2: once coverage is complete and stability not passed, resample existing pairs.
- Small nets: enforce a dedicated resampling cap and avoid over‑spending budget when stability is hard to detect.
- Convergence harness: drive synthetic nets through Phase‑1 and Phase‑2 using the real BT scoring core to validate stability/budget semantics.

This task connects each section of the PR‑7 checklist to concrete implementation steps and tests.

## Plan

### Phase Overview

- [x] Phase 1 – Coverage metrics & batch metadata (Checklist §2; core helper + wiring implemented).
- [x] Phase 2 – Small‑net Phase‑2 semantics in `workflow_continuation` (Checklist §3; gating + tests implemented).
- [x] Phase 3 – Pair generation – resampling mode (Checklist §4; implemented).
- [x] Phase 4 – Convergence harness (Checklist §5; implemented).
- [x] Phase 5 – Docs, runbook & final sweep (Checklist §6; implemented).
- [ ] Phase 6 – Workflow continuation refactor (Checklist §3.3 follow‑up; planned).

### 1. Coverage Metrics & Batch Metadata (Checklist §2)

Connects to: “Coverage metrics & metadata on CJBatchState”.

1.1 Repository helper:
- [ ] Extend `CJComparisonRepositoryProtocol` with `get_coverage_metrics_for_batch(session, batch_id) -> tuple[int, int]`.
- [ ] Implement in `PostgreSQLCJComparisonRepository` to compute:
  - [ ] `max_possible_pairs = nC2` over `ProcessedEssay` nodes (including anchors).
  - [ ] `successful_pairs_count` as count of distinct unordered `(a,b)` with ≥1 successful comparison (non‑error, winner in allowed set).

1.2 CJBatchState metadata wiring:
- [ ] In `workflow_continuation.trigger_existing_workflow_continuation`:
  - [ ] Resolve coverage metrics, preferring existing `processing_metadata` keys (`max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, `resampling_pass_count`) and falling back to the new helper when absent.
  - [ ] Persist coverage fields via `merge_batch_processing_metadata`:
    - `max_possible_pairs`
    - `successful_pairs_count`
    - `unique_coverage_complete`
    - `resampling_pass_count` (initialised to `0` when missing).

1.3 Tests:
- [x] Add DB‑backed unit test for `get_coverage_metrics_for_batch` using `postgres_comparison_repository` + `postgres_session`:
  - [x] Assert `max_possible_pairs` matches `nC2` for a simple 3‑essay batch.
  - [x] Assert `successful_pairs_count` behaviour is documented against current schema (enum vs string winner); adjust expectation if winner representation is normalised in future.
- [x] Extend `test_workflow_continuation.py` to assert coverage metadata keys are present and updated after a continuation iteration (via small‑net Phase‑2 tests).
- [x] Ensure future tests can be parameterised by net size:
  - [x] Small‑net scenarios (`expected_essay_count <= MIN_RESAMPLING_NET_SIZE`) drive the small‑net Phase‑2 path.
  - [ ] Regular/large‑net scenarios (`expected_essay_count > MIN_RESAMPLING_NET_SIZE`) should be easy to add by reusing the same helpers and assertions, differing only in configuration and expected resampling behaviour.

#### Phase 1 Progress (2025‑11‑30)

- Implemented `get_coverage_metrics_for_batch` on `PostgreSQLCJComparisonRepository` and wired it into `workflow_continuation.trigger_existing_workflow_continuation` with metadata persistence for `max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, and `resampling_pass_count`.
- Added `test_comparison_repository_coverage_metrics.py` to assert `max_possible_pairs` for a 3‑essay batch and to document current `successful_pairs_count` behaviour against the existing winner representation.
- Verified coverage metadata keys are present in `processing_metadata` via the newly enabled small‑net workflow continuation tests.

### 2. Small‑Net Phase‑2 Semantics in `workflow_continuation` (Checklist §3)

Connects to: “Small‑net Phase‑2 semantics in workflow_continuation”.

2.1 Settings:
- [x] Add CJ settings in `config.py: Settings`:
  - [x] `MIN_RESAMPLING_NET_SIZE: int = 10` – nets with `expected_essay_count` below this are treated as small.
  - [x] `MAX_RESAMPLING_PASSES_FOR_SMALL_NET: int = 2` – cap on resampling passes once coverage is complete.
- [x] Document these in the task and in service docs/runbook (see §5).

2.2 Branching logic for small nets:
- [x] Compute `expected = batch_state.batch_upload.expected_essay_count or 0` and `is_small_net = expected < settings.MIN_RESAMPLING_NET_SIZE`.
- [x] Preserve PR‑2 behaviour for large nets (`not is_small_net`) exactly.
- [x] For small nets:
  - [x] Detect Phase‑2 eligibility: `unique_coverage_complete is True`, stability not passed, budget remains, and success‑rate guard does not force failure.
  - [x] If `resampling_pass_count < MAX_RESAMPLING_PASSES_FOR_SMALL_NET`:
    - [x] Increment and persist `resampling_pass_count`.
    - [x] Request additional comparisons via `request_additional_comparisons_for_batch` (coverage mode for now; resampling mode added in Phase 3).
    - [x] Avoid finalization in this branch.
  - [x] If `resampling_pass_count >= MAX_RESAMPLING_PASSES_FOR_SMALL_NET`:
    - [x] Treat the small‑net resampling cap as a finalization reason alongside stability, completion denominator, and budget exhaustion.
    - [x] Delegate to existing stability + success‑rate gating (`finalize_scoring` vs `finalize_failure`).

2.3 Logging:
- [x] Add structured logs:
  - [x] `small_net_phase2_entered` / “Small-net Phase-2 resampling wave triggered” when resampling starts for a batch.
  - [x] “Small-net Phase-2 resampling cap reached; falling back to finalization” when the cap blocks further resampling.

2.4 Tests to enable:
- [x] Flip and make pass the PR‑7 small‑net tests in `test_workflow_continuation.py`:
  - [x] `test_small_net_phase2_requests_additional_comparisons_before_resampling_cap`:
    - [x] Asserts `request_additional_comparisons_for_batch` is invoked and `finalize_scoring` is not when coverage is complete, stability not passed, and budget remains.
  - [x] `test_small_net_phase2_tracks_resampling_pass_count`:
    - [x] Asserts `resampling_pass_count` is incremented and persisted when Phase‑2 resampling is chosen.
  - [x] `test_small_net_resampling_respects_resampling_pass_cap`:
    - [x] Asserts no additional comparisons are requested once the cap is reached and finalization occurs instead.

#### Phase 2 Progress (2025‑11‑30)

- Implemented small‑net detection and Phase‑2 resampling semantics directly in `workflow_continuation.trigger_existing_workflow_continuation`, including resampling pass caps and a small‑net‑specific finalization path that preserves PR‑2 invariants for large nets.
- Enabled and passed all three PR‑7 small‑net tests in `test_workflow_continuation.py`, verifying that small nets resample instead of finalizing immediately at coverage, increment `resampling_pass_count`, and respect the resampling pass cap.
- Ensured success‑rate gating and `completion_denominator()` semantics remain unchanged for large nets by only activating the new branch when `is_small_net` and coverage metadata indicate a Phase‑2 scenario.

### 3. Pair Generation – Resampling Mode (Checklist §4)

Connects to: “Resampling mode in pair generation”.

3.1 API extension:
- [x] Introduce `PairGenerationMode` enum (e.g. `COVERAGE`, `RESAMPLING`) in `pair_generation.py` or a small enums module.
- [x] Extend `generate_comparison_tasks` signature to accept `mode: PairGenerationMode = PairGenerationMode.COVERAGE`.

3.2 Implementation:
- [x] COVERAGE mode:
  - [x] Preserve current behaviour: avoid duplicates, respect global cap, generate new pairs guided by `matching_strategy`.
- [x] RESAMPLING mode:
  - [x] Work entirely off the existing comparison graph for the batch:
    - [x] Do not introduce new essay IDs beyond those already in `ProcessedEssay`.
  - [x] Generate a new wave of pairs reusing existing edges, with simple fairness:
    - [x] Avoid over‑sampling essays with very high `comparison_count`.
    - [x] Prefer pairs that improve coverage of comparison counts per essay.

3.3 Wiring:
- [x] Update `comparison_processing.request_additional_comparisons_for_batch` (and helpers) to:
  - [x] Accept a `mode` hint.
  - [x] Call `generate_comparison_tasks` with `PairGenerationMode.COVERAGE` for Phase‑1 and `PairGenerationMode.RESAMPLING` for Phase‑2 small‑net resampling.

3.4 Tests:
- [x] Extend `test_pair_generation_context.py`:
  - [x] Assert RESAMPLING mode never introduces new essay IDs compared to the batch’s `ProcessedEssay` set.
  - [x] Assert basic fairness (no single essay dominates comparisons across multiple RESAMPLING waves under reasonable settings).
- [ ] Plan for dual-path testing (small-net vs regular batches):
  - [ ] Define parameterised test cases where:
    - [ ] Small-net configurations (e.g. 3–5 essays) exercise the current small-net resampling semantics.
    - [ ] Regular-net configurations (e.g. 20+ essays) can be introduced later to exercise generalised RESAMPLING semantics without changing helper structure.
  - [ ] Keep test helpers (e.g. synthetic nets, builder functions) net-size agnostic so they can be used by both small-net and regular-batch tests.

#### Phase 3 Progress (2025‑11‑30, updated 2025‑12‑06)

- Added `PairGenerationMode` with `COVERAGE` and `RESAMPLING` in `pair_generation.py` and extended `generate_comparison_tasks` to accept a `mode` parameter while preserving existing COVERAGE behaviour (duplicate avoidance, matching‑strategy usage, and global cap enforcement).
- Implemented RESAMPLING mode to build candidate pairs exclusively from existing comparison edges, score them using per‑essay `comparison_count`, and select a capped subset that avoids introducing new essay IDs and favours under‑sampled essays.
- Wired the mode through `comparison_processing.submit_comparisons_for_async_processing` and `request_additional_comparisons_for_batch`, and updated `workflow_continuation.trigger_existing_workflow_continuation` so small‑net Phase‑2 flows invoke RESAMPLING while large‑net/Phase‑1 flows remain on COVERAGE.
- Extended `test_pair_generation_context.py` with a RESAMPLING fairness test and updated `test_workflow_continuation.py` wiring tests to assert the correct mode is used; ran `pdm run pytest-root services/cj_assessment_service/tests/unit/test_pair_generation_context.py` and targeted workflow continuation tests successfully.
- Ran the broader CJ unit suite via `pdm run pytest-root services/cj_assessment_service/tests/unit`; all tests related to pair generation and workflow continuation passed, with one pre‑existing failure remaining in `test_batch_finalizer_scoring_state.py::test_finalize_scoring_transitions_state` (BatchFinalizer dual‑event publishing), which was not modified in this phase.
- Added a docker-backed CJ small-net continuation test (`tests/integration/test_cj_small_net_continuation_docker.py`) that reuses the production ENG5 LOWER5 mock profile and asserts PR‑2/PR‑7 completion, coverage, and small-net metadata invariants from `CJBatchState`, using a net-size-agnostic helper that can later be reused for regular-batch RESAMPLING scenarios without harness rewrites.
- As of 2025‑12‑06, the docker ENG5 LOWER5 configuration (`MIN_RESAMPLING_NET_SIZE=5`, `MAX_RESAMPLING_PASSES_FOR_SMALL_NET=3`) has been aligned with the **“small batch size = 5”** story semantics:
  - Nets with `expected_essay_count <= MIN_RESAMPLING_NET_SIZE` are treated as **small nets** in `build_small_net_context(...)`.
  - The 5‑essay ENG5 LOWER5 docker batch follows the small‑net path:
    - Phase‑1 coverage: `max_possible_pairs == successful_pairs_count == 10`, `unique_coverage_complete is True`.
    - Phase‑2 resampling: `resampling_pass_count` increases up to the configured cap (currently 3), resulting in `total_comparisons ≈ 40`.
    - Finalization: `ContinuationDecision.FINALIZE_SCORING` is taken from the callback‑driven continuation path (no reliance on the BatchMonitor sweep), and `CJBatchState.state` transitions to `COMPLETED` with `failed_comparisons == 0`, `success_rate == 1.0`, and `total_comparisons <= total_budget`.

### 4. Convergence Harness (Checklist §5)

Connects to: “Convergence harness”.

4.1 Harness module:
- [x] Add `services/cj_assessment_service/cj_core_logic/convergence_harness.py` with a small harness that:
  - [x] Accepts configuration:
    - `MIN_COMPARISONS_FOR_STABILITY_CHECK`
    - `MAX_ITERATIONS`
    - `MAX_PAIRWISE_COMPARISONS`
  - [x] Simulates:
    - Phase‑1 waves that add unique edges until coverage or caps.
    - Phase‑2 waves that resample existing edges until stability or caps.
  - [x] Uses the real BT scoring helpers:
    - `compute_bt_scores_and_se(...)`
    - `check_score_stability(...)`
  - [x] Returns a `HarnessResult` with final scores, stability flag, and which cap fired (`stability`, `iterations`, or `budget`).

4.2 Tests:
- [x] Replace the xfail stubs in `test_convergence_harness.py` with real tests:
  - [x] `test_convergence_harness_stops_on_stability_before_max_iterations`:
    - [x] Construct a simple synthetic net where stability is easy to achieve and assert early stop on stability.
  - [x] `test_convergence_harness_stops_after_max_iterations_or_budget`:
    - [x] Construct a net where stability is hard to achieve and assert stop on `MAX_ITERATIONS` or `MAX_PAIRWISE_COMPARISONS` with the correct cap reason.

#### Phase 4 Progress (2025‑11‑30)

- Implemented an in‑memory convergence harness in `services/cj_assessment_service/cj_core_logic/convergence_harness.py` that:
  - Builds the full n‑choose‑2 comparison graph over a synthetic `EssayForComparison` net.
  - Runs Phase‑1 coverage iterations (only unseen pairs) followed by Phase‑2 resampling iterations (reusing existing edges) under configurable iteration and budget caps.
  - Uses the real BT helper (`compute_bt_scores_and_se`) and `check_score_stability` to evaluate convergence between iterations.
  - Returns a typed `HarnessResult` including final BT scores, whether stability was achieved, which cap fired (`stability`, `iterations`, or `budget`), iterations run, total comparisons, and final SE diagnostics.
- Added new unit tests in `services/cj_assessment_service/tests/unit/test_convergence_harness.py` that:
  - Assert the harness stops early on stability when thresholds are permissive and caps are generous.
  - Assert the harness stops on iteration caps when stability checks are effectively disabled by configuration.
- Commands run for Phase 4:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_convergence_harness.py` (2 passed).
  - Follow‑up CJ unit suites and repo‑wide quality gates are planned under Phase 5/6 and will be noted separately.

### 5. Docs, Runbook & Final Sweep (Checklist §6)

Connects to: “Docs, runbook and final sweep”.

5.1 Documentation updates:
- [x] Update `docs/product/epics/cj-stability-and-reliability-epic.md`:
  - [x] Mark PR‑7 items as implemented and align the narrative with the shipped behaviour.
- [x] Update `docs/operations/cj-assessment-runbook.md`:
  - [x] Document small‑net behaviour and the Phase‑1 / Phase‑2 model.
  - [x] Describe the new settings:
    - `MIN_RESAMPLING_NET_SIZE`
    - `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`
  - [x] Explain coverage metadata on `CJBatchState.processing_metadata`:
    - `max_possible_pairs`
    - `successful_pairs_count`
    - `unique_coverage_complete`
    - `resampling_pass_count`

5.2 Final verification:
- [x] Run focused and full CJ tests:
  - [x] `pdm run pytest-root services/cj_assessment_service/tests`
- [x] Run repo‑wide quality gates:
  - [x] `pdm run format-all`
  - [x] `pdm run lint-fix --unsafe-fixes`
  - [x] `pdm run typecheck-all`

#### Phase 5 Progress (2025‑11‑30)

- Documentation:
  - Updated `docs/product/epics/cj-stability-and-reliability-epic.md` to describe PR‑7 Phase‑2 resampling and the convergence harness in implemented terms, including the full knob set (`COMPARISONS_PER_STABILITY_CHECK_ITERATION`, `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `MAX_ITERATIONS`, `MAX_PAIRWISE_COMPARISONS`, `SCORE_STABILITY_THRESHOLD`, and small‑net caps).
  - Updated `docs/operations/cj-assessment-runbook.md` to document small‑net Phase‑2 semantics, coverage metadata on `CJBatchState.processing_metadata`, and the current CJ defaults (`MAX_PAIRWISE_COMPARISONS=300`, `COMPARISONS_PER_STABILITY_CHECK_ITERATION=12`, `MIN_COMPARISONS_FOR_STABILITY_CHECK=12`, `MIN_RESAMPLING_NET_SIZE=10`, `MAX_RESAMPLING_PASSES_FOR_SMALL_NET=2`).
  - Aligned `services/cj_assessment_service/README.md` and ADR‑0015 (`docs/decisions/0015-cj-assessment-convergence-tuning-strategy.md`) with the shipped convergence configuration and completion‑denominator semantics.
- CJ tests executed:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_convergence_harness.py`
  - `pdm run pytest-root 'services/cj_assessment_service/tests/unit -k \"convergence or workflow_continuation or pair_generation\"'`
  - `pdm run pytest-root services/cj_assessment_service/tests`
  - Current status: all convergence, workflow‑continuation, pair‑generation, and BT scoring tests pass in isolation; the full CJ test suite reports two known issues:
    - `services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py::test_finalize_scoring_transitions_state` – BatchFinalizer dual‑event publishing behaviour (out of scope for PR‑7 Phase‑5).
    - `services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py::TestBradleyTerryScoring::test_edge_cases[all_errors-3-comparisons2-True]` – fails when run as part of the full suite but passes when executed in isolation; likely an order‑ or fixture‑interaction issue to be addressed in a follow‑up task.
- Repo‑wide quality gates:
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`

### 6. Workflow Continuation Refactor (Follow-Up, Checklist §3.3)

Connects to: follow‑up refactor bullets added to the PR‑7 checklist.

6.1 Decomposition:
- [ ] Extract a continuation state helper (e.g. `continuation_state.py`) that encapsulates:
  - [ ] Loading `CJBatchState`, computing `callbacks_received`, `denominator`, caps, and stability flags.
  - [ ] Resolving coverage metrics and small‑net flags into a typed context object.
- [ ] Move small‑net Phase‑2 branching into a dedicated function that:
  - [ ] Accepts the continuation context and settings.
  - [ ] Returns a decision (finalize, resample, or no‑op) plus updated metadata.

6.2 Orchestration:
- [ ] Rewrite `trigger_existing_workflow_continuation` to:
  - [ ] Focus on orchestration: session management, DI surfaces, logging, and delegating to the helper and refactored small‑net function.
  - [ ] Keep all public behaviour identical to the PR‑7 implementation (guarded by existing unit tests).

## Success Criteria

- Coverage metrics helper:
  - `get_coverage_metrics_for_batch` is covered by DB‑backed tests and feeds `processing_metadata` without mutating BT semantics or completion denominators for large nets.
- Small‑net Phase‑2 semantics:
  - All three small‑net tests in `test_workflow_continuation.py` pass without xfail markers and large‑net tests remain green.
- Pair generation:
  - `PairGenerationMode` and RESAMPLING mode are wired end‑to‑end, with tests confirming no new essay IDs and basic fairness.
- Convergence harness:
  - `test_convergence_harness.py` uses the real harness and validates stability vs caps behaviour.
- Documentation & quality gates:
  - EPIC doc, runbook, and settings are updated; `pdm run pytest-root services/cj_assessment_service/tests`, `format-all`, `lint-fix --unsafe-fixes`, and `typecheck-all` complete successfully.
- Refactor:
  - `workflow_continuation.py` is reduced in complexity via a continuation state helper and small‑net branching helper, with existing tests guarding behaviour.

## Related

- Epic: `docs/product/epics/cj-stability-and-reliability-epic.md` (EPIC‑005)
- PR‑7 checklist: `docs/product/epics/pr-7-phase2-resampling-checklist.md`
- User stories:
  - `TASKS/assessment/us-0051-callback-driven-continuation-and-safe-completion-gating.md`
  - `TASKS/assessment/us-0052-score-stability-semantics-and-early-stopping.md`
  - `TASKS/assessment/us-0053-retry-semantics-and-end-of-batch-fairness.md`
  - `TASKS/assessment/us-0054-convergence-tests-for-iterative-bundled-mode.md`
