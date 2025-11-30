---
id: 'us-00ya-workflow-continuation-refactor--phase-6'
title: 'US-00YA Workflow continuation refactor – Phase 6'
type: 'story'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-30'
last_updated: '2025-11-30'
related: ['us-00xz-batchfinalizer-dual-event-semantics-and-bt-edge-case-test-isolation', 'us-00xy-cleanup-unused-comparison-processing-code-paths']
labels: []
---
# US-00YA: Workflow continuation refactor – Phase 6

## Objective

Refactor `workflow_continuation.trigger_existing_workflow_continuation` so it
becomes the single, clear owner of the “continue vs finalize” decision for CJ
callbacks, while preserving all existing convergence thresholds, caps, and
success-rate semantics from EPIC‑005 / PR‑7. The refactor should:

- Make continuation decisions easier to reason about (explicit conditions for
  requesting more comparisons vs finalizing via `BatchFinalizer`).
- Keep small‑net / resampling semantics ready for activation (Phase‑2 knobs) but
  **not** change production behaviour yet.
- Ensure that `bt_se_summary` and coverage metadata written into
  `processing_metadata` remain consistent and test‑backed.

## Context

As of PR‑7 Phases 1–5:

- `record_comparisons_and_update_scores` and `compute_bt_scores_and_se` are the
  single scoring entry point and BT core, and they already return structured
  SE diagnostics.
- `workflow_continuation.trigger_existing_workflow_continuation` is responsible
  for:
  - Recomputing BT scores once callbacks for an iteration are complete.
  - Deriving stability vs budget vs success‑rate semantics.
  - Deciding whether to:
    - Request more comparisons (`comparison_processing.request_additional_comparisons_for_batch`),
    - Finalize via `BatchFinalizer.finalize_scoring`, or
    - Finalize via `BatchFinalizer.finalize_failure` (low success rate).
- Tests in `test_workflow_continuation.py` already cover:
  - Callback completeness and simple continuation checks.
  - Stability‑first early finalization vs budget.
  - Low‑success‑rate finalization (`finalize_failure`).
  - Forward‑looking small‑net Phase‑2 semantics (`xfail` specs for resampling
    and `resampling_pass_count`).
  - SE diagnostics and `bt_quality_flags` + Prometheus counters.

However, the control flow inside `trigger_existing_workflow_continuation` has
grown complex, and the Phase‑2 semantics for small nets are only partially
expressed in tests/commentary. This story refactors the continuation logic and
brings the tests up to a clear, behaviour‑first specification, without tuning
thresholds or changing the production math.

## Plan

- Extract and clarify continuation decision steps inside
  `trigger_existing_workflow_continuation`:
  - Callback completeness/pending checks.
  - Stability vs budget vs success‑rate evaluation.
  - Small‑net coverage/resampling semantics (guarded behind existing settings).
- Tighten and extend `test_workflow_continuation.py` to encode the intended
  behaviour for:
  - Stable vs unstable batches (with and without remaining budget).
  - Low‑success‑rate failure finalization when caps are hit.
  - Small‑net Phase‑2 behaviour using the existing forward‑looking tests as the
    spec for when resampling should be preferred over immediate finalization.
- Keep `bt_se_summary` and `bt_quality_flags` handling intact, but ensure tests
  explicitly cover:
  - JSON‑safe metadata (no `inf`/`NaN`).
  - Quality flags and any associated Prometheus counters.
- Run the full CJ unit suite and a targeted subset of integration tests under
  `services/cj_assessment_service/tests` to confirm no behavioural regressions.
- Capture any additional observability opportunities (e.g. logging or metrics
  around continuation decisions) as a follow‑up story rather than part of this
  refactor.

## Success Criteria

- [ ] `trigger_existing_workflow_continuation` control flow is structured into
      clearly named internal steps/blocks (or helpers) for:
      - Callback completeness checks.
      - Stability and success‑rate evaluation.
      - Budget/cap evaluation (including small‑net coverage metadata).
      - Finalization vs “request more comparisons” decisions.
- [ ] Existing behaviour for:
      - Stability‑first early finalization,
      - Low‑success‑rate failure finalization, and
      - Budget/cap handling
      remains unchanged and fully covered by updated/extended unit tests.
- [ ] Forward‑looking small‑net Phase‑2 tests in
      `test_workflow_continuation.py` are either:
      - Clearly marked as future expectations (xfail or explicit comments), or
      - Brought into alignment with the refactored implementation if Phase‑2
        semantics are activated as part of this story (only if explicitly
        agreed in EPIC‑005).
- [ ] `bt_se_summary`, `bt_quality_flags`, and coverage metadata
      (`max_possible_pairs`, `successful_pairs_count`,
      `unique_coverage_complete`, `resampling_pass_count`) continue to be
      written into `CJBatchState.processing_metadata` in a JSON‑safe way, with
      tests validating both contents and serializability.
- [ ] `services/cj_assessment_service/tests/unit/test_workflow_continuation.py`
      and the BT scoring integration suite remain green under the full CJ
      service test run.

## Concrete test cases to cover (unit, in `test_workflow_continuation.py`)

1. Callback completeness
- `check_workflow_continuation` returns:
  - `True` when `submitted_comparisons > 0` and `completed + failed == submitted`.
  - `False` when there are pending callbacks or nothing has been submitted.

2. Stability‑first scoring finalization (already present, to be kept tight)
- Given:
  - `callbacks_received >= MIN_COMPARISONS_FOR_STABILITY_CHECK`,
  - `max_score_change <= SCORE_STABILITY_THRESHOLD`,
  - success rate above threshold (or guard disabled),
  - budget remaining,
- Expect:
  - `BatchFinalizer.finalize_scoring` is invoked exactly once.
  - No additional comparisons are requested.
  - `merge_batch_processing_metadata` includes updated `bt_scores`,
    `last_scored_iteration`, and `last_score_change`.

3. Low‑success‑rate failure finalization (PR‑2 semantics)
- Scenario where:
  - `callbacks_received` has hit `completion_denominator()` and/or budget cap.
  - `success_rate < MIN_SUCCESS_RATE_THRESHOLD` (including the zero‑success
    case for production semantics, even though the “all errors” case is mainly
    covered in the integration suite).
- Expect:
  - `BatchFinalizer.finalize_failure` is called once with a `failure_reason`
    of `"low_success_rate"` and details containing callbacks, success rate, and
    cap/budget flags.
  - `request_additional_comparisons_for_batch` is not invoked.

4. Budget/cap reached without stability, but success‑rate ok
- Scenario where:
  - `callbacks_received >= completion_denominator()` *or* global cap reached,
  - Stability has not passed (`max_score_change > SCORE_STABILITY_THRESHOLD`),
  - Success rate is above threshold.
- Expect:
  - Current PR‑2 behaviour (finalization vs resubmission) is exercised and
    locked down by explicit assertions around `finalize_scoring` vs additional
    requests (depending on how caps are intended to interact with instability).

5. Small‑net Phase‑2 resampling behaviour (forward‑looking)
- Use the existing small‑net tests as behavioural specs for when:
  - `unique_coverage_complete=True`,
  - `resampling_pass_count < MAX_RESAMPLING_PASSES_FOR_SMALL_NET`,
  - Small net (`expected_essay_count < MIN_RESAMPLING_NET_SIZE`),
- Expect in the future (documented clearly in tests):
  - Additional comparisons requested (`request_additional_comparisons_for_batch`)
    instead of immediate finalization once caps are considered in the
    small‑net context.
  - `resampling_pass_count` incremented and persisted in metadata when
    resampling occurs.

6. SE diagnostics and quality flags (existing tests, to be kept/extended)
- Confirm that:
  - `bt_se_summary` is present in `metadata_updates`.
  - `bt_quality_flags` is derived correctly for:
    - Normal SE and coverage.
    - Inflated SE.
    - Sparse coverage.
    - Isolated items.
  - `metadata_updates` is JSON‑serializable for all these cases.
  - When present, Prometheus counters for inflated SE and sparse coverage are
    incremented appropriately.

7. Robustness when BT scoring fails
- When `record_comparisons_and_update_scores` raises `HuleEduError`:
  - Continuation should treat the batch as unstable, keep or fall back to
    previous scores, and let caps/success‑rate semantics decide between
    resubmission and failure finalization.
  - Tests should confirm that no unexpected exceptions leak and that metadata
    remains consistent.

## Follow-up observability story (outline only)

- A follow‑up story (e.g. `US‑00YB: Workflow continuation observability`) could:
  - Add structured logs summarizing:
    - The decision taken (`continue`, `finalize_scoring`, `finalize_failure`),
    - Key inputs (callbacks_received, success_rate, stability metrics, caps,
      small‑net flags, quality flags).
  - Introduce high‑level Prometheus metrics for continuation decisions:
    - Counters for each decision type.
    - Gauges for current stability and success rate at the point of decision.
  - Ensure any new observability wiring uses `bt_se_summary` and
    `bt_quality_flags` already persisted in `processing_metadata` rather than
    recomputing diagnostics.

This follow‑up should be strictly additive and must not change continuation
semantics; it can reference the refactored `trigger_existing_workflow_continuation`
as the single source of truth for all convergence‑related decisions.

## Progress (2025-11-30)

- Introduced internal `ContinuationContext` dataclass and `ContinuationDecision` enum in
  `workflow_continuation.py` to capture all derived continuation metrics and decision types.
- Factored existing inline logic into helpers:
  - `_compute_success_metrics` for success-rate and threshold semantics.
  - `_derive_small_net_flags` for small-net and coverage/resampling flags.
  - `_build_continuation_context` to aggregate stability, caps/budget, coverage, and diagnostics.
  - `_can_attempt_small_net_resampling` and `_decide_continuation_action` to make the
    continuation vs finalization decision explicit.
- Reshaped `trigger_existing_workflow_continuation` to:
  - Early-return on missing batch state or pending callbacks.
  - Recompute BT scores via `scoring_ranking.record_comparisons_and_update_scores` and
    thread `bt_se_summary` into `processing_metadata`.
  - Build a `ContinuationContext`, then merge BT/coverage metadata via
    `merge_batch_processing_metadata`.
  - Use `ContinuationDecision` to route to `BatchFinalizer.finalize_scoring`,
    `BatchFinalizer.finalize_failure`, or
    `comparison_processing.request_additional_comparisons_for_batch` (coverage or
    small-net resampling).
- Semantics for thresholds, caps, success-rate guards, and small-net Phase‑2 behaviour
  remain unchanged; existing unit tests in
  `services/cj_assessment_service/tests/unit/test_workflow_continuation.py` still pass,
  including small-net resampling scenarios and BT diagnostics.
- Fixed the BT scoring integration regression in
  `TestBradleyTerryScoring::test_edge_cases[all_errors-3-comparisons2-True]` by aligning
  `ComparisonResult.error_detail` with the canonical
  `common_core.models.error_models.ErrorDetail` type and removing the redundant local
  error model, so the `all_errors` edge-case can construct valid `ComparisonResult`
  instances without changing BT scoring or continuation semantics.
- Re-ran the full CJ unit + integration suite after the model fix and confirmed all CJ
  tests are now green with continuation thresholds, caps, and success-rate logic
  unchanged.
- Commands run (2025-11-30, across both phases):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py`
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring and all_errors"`
  - `pdm run pytest-root services/cj_assessment_service/tests`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_pool_management.py::TestFailedComparisonPoolModels::test_failed_comparison_entry_creation`
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`
