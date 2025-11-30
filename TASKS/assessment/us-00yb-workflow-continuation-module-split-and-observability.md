---
id: 'us-00yb-workflow-continuation-module-split-and-observability'
title: 'US-00YB Workflow continuation module split and observability'
type: 'story'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-30'
last_updated: '2025-11-30'
related: ['us-00ya-workflow-continuation-refactor--phase-6']
labels: []
---
# US-00YB: Workflow continuation module split and observability

## Objective

After US-00YA has refactored `workflow_continuation.trigger_existing_workflow_continuation`
internally (without changing semantics), extract the decision and context logic
into dedicated modules and layer on additional observability that reuses
existing BT diagnostics (`bt_se_summary`, `bt_quality_flags`) and coverage
metadata, without altering convergence behaviour.

## Context

- Today, `workflow_continuation.py` owns:
  - Callback completeness checks (`check_workflow_continuation`).
  - The full continuation decision flow (stability vs budget vs success rate).
  - BT diagnostic wiring (`bt_se_summary`, `bt_quality_flags`, Prometheus
    counters).
  - Coverage metadata updates and calls into `BatchFinalizer` and
    `comparison_processing.request_additional_comparisons_for_batch`.
- US-00YA will introduce internal structure (e.g. `ContinuationContext`,
  `ContinuationDecision`, and helpers for metrics/flags), while keeping all
  thresholds and semantics identical.
- To improve SRP and testability, we want a second, clearly scoped step that:
  - Splits “context building” and “decision” into pure, testable modules.
  - Keeps `workflow_continuation` as a thin orchestrator.
  - Adds structured observability around continuation decisions using the
    already persisted diagnostics.

## Plan

- **Module split (SRP)**
  - Extract a `workflow_context` module that:
    - Defines `ContinuationContext`.
    - Normalizes `CJBatchState` + processing metadata into derived counts,
      caps, success rate, stability flags, small-net flags, and coverage
      fields.
    - Builds `metadata_updates` (bt scores, SE summary, quality flags,
      coverage fields) in a JSON-safe way.
  - Extract a `workflow_decision` module that:
    - Defines `ContinuationDecision`.
    - Provides a pure `decide(ctx: ContinuationContext) -> ContinuationDecision`
      function encoding the existing PR‑2/PR‑7 behaviour for:
      - Waiting for callbacks.
      - Stability-first finalization.
      - Low-success-rate failure finalization.
      - Budget/cap interactions.
      - Forward-looking small-net behaviour (kept as “future” guards).
  - Optionally extract `workflow_diagnostics` that:
    - Takes BT scoring results and updates `bt_se_summary`,
      `bt_quality_flags`, and associated Prometheus counters.
    - Avoids any DB or finalizer calls.
  - Update `workflow_continuation.py` to:
    - Delegate context construction to `workflow_context`.
    - Delegate decision computation to `workflow_decision`.
    - Keep only orchestration and calls into `BatchFinalizer` and
      `comparison_processing`.

- **Observability wiring**
  - Add structured logs (single decision log) that include:
    - Decision type (`continue`, `finalize_scoring`, `finalize_failure`,
      `no_op`).
    - Key fields from `ContinuationContext` (callbacks, success rate,
      stability metrics, caps, small-net / quality flags).
  - Add high-level Prometheus metrics:
    - Counters per decision type (e.g.
      `cj_workflow_decisions_total{decision="finalize_scoring"}`).
    - Optional gauges for current success rate and max score change at
      decision time, if consistent with existing metrics strategy.
  - Ensure all new observability elements:
    - Are derived from `ContinuationContext` and existing metadata
      (`bt_se_summary`, `bt_quality_flags`, coverage fields).
    - Do **not** influence decisions (no behaviour changes).

- **Testing and migration**
  - Port existing `test_workflow_continuation.py` cases to use the new modules
    (by import), ensuring:
    - No semantic changes vs the refactored behaviour from US‑00YA.
    - Additional tests cover decision logging and new metrics wiring
      (e.g. via fakes/mocks for Prometheus collectors).
  - Run the full CJ unit suite and targeted BT integration tests to confirm
    behaviour is unchanged.

## Success Criteria

- [ ] `workflow_continuation.py` depends on `workflow_context` and
      `workflow_decision` for all internal logic, focusing only on orchestration
      and side effects (DB + finalizers + pair requests).
- [ ] All decision rules previously in `trigger_existing_workflow_continuation`
      are expressed via a pure `decide(ctx: ContinuationContext)` function,
      covered by unit tests with no external mocks.
- [ ] `workflow_context` builds `ContinuationContext` and metadata updates in a
      JSON-safe, test-backed way that preserves all existing fields
      (`bt_scores`, `bt_se_summary`, `bt_quality_flags`, coverage metadata).
- [ ] New structured logs and Prometheus metrics around continuation decisions
      are present, documented, and verified in tests, and do **not** change
      continuation behaviour.
- [ ] CJ unit and integration tests for workflow continuation and BT scoring
      remain green under the full `services/cj_assessment_service/tests` run.

## Progress

### 2025-11-30

- Implemented the first module-split step for continuation:
  - Added `services/cj_assessment_service/cj_core_logic/workflow_context.py` containing the `ContinuationContext` dataclass.
  - Added `services/cj_assessment_service/cj_core_logic/workflow_decision.py` containing `ContinuationDecision` and the continuation helper functions (`_compute_success_metrics`, `_derive_small_net_flags`, `_build_continuation_context`, `_can_attempt_small_net_resampling`, `_decide_continuation_action`), with `workflow_continuation.py` now importing these instead of defining them inline.
  - Kept `workflow_continuation.trigger_existing_workflow_continuation` as the orchestration shell: it loads batch state, invokes BT scoring via `scoring_ranking.record_comparisons_and_update_scores`, builds/merges processing metadata, and routes to `BatchFinalizer` or `comparison_processing.request_additional_comparisons_for_batch` based on `ContinuationDecision`.
- Observability (this step only):
  - Added a structured decision-summary log in `trigger_existing_workflow_continuation` that records the final `ContinuationDecision` value plus key fields from `ContinuationContext` (callbacks_received, denominator, max_score_change, success_rate, success_rate_threshold, callbacks_reached_cap, budget_exhausted, pairs_remaining, is_small_net, small_net_cap_reached, bt_se_inflated, comparison_coverage_sparse, has_isolated_items).
  - Left thresholds, caps, success-rate semantics, and BT/coverage metadata behaviour unchanged; existing BT SE diagnostics and quality-flag metrics remain wired through the continuation context.
- Validation (tests and quality gates run in this session):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring"` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestAnchorEssayWorkflow"` ✅
  - `pdm run format-all` ✅
  - `pdm run lint-fix --unsafe-fixes` ✅
  - `pdm run typecheck-all` ✅

### 2025-11-30 (US-00YB step 2)

- Decision surface:
  - Introduced a public, pure `decide(ctx: ContinuationContext) -> ContinuationDecision` function in `services/cj_assessment_service/cj_core_logic/workflow_decision.py` that delegates to the existing `_decide_continuation_action` helper and operates solely on the immutable `ContinuationContext` (no logging, metrics, DB access, or event publishing).
- Orchestration refactor:
  - Updated `services/cj_assessment_service/cj_core_logic/workflow_continuation.py::trigger_existing_workflow_continuation` to import and call `decide(ctx)` instead of `_decide_continuation_action`, keeping all PR‑2 stability-first behaviour, PR‑7 small-net semantics, success-rate guards, and BT/coverage thresholds unchanged.
  - Confirmed that `ContinuationContext` still carries the full set of inputs needed for stability, caps/budget, success-rate, small-net, and BT quality/coverage decisions; no new branching or predicates were added to `workflow_continuation`.
- Observability:
  - Left the structured decision-summary log in `trigger_existing_workflow_continuation` in place, now reporting the `ContinuationDecision` returned by `decide(ctx)` together with the existing `ContinuationContext` fields (`callbacks_received`, `denominator`, `max_score_change`, `success_rate`, `success_rate_threshold`, `callbacks_reached_cap`, `budget_exhausted`, `pairs_remaining`, `is_small_net`, `small_net_cap_reached`, `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`).
  - Kept all logging and Prometheus metric updates outside `decide`; `workflow_decision.decide` remains a pure decision entry point while BT SE diagnostics and coverage flags continue to be derived during context construction.
- Validation (tests and quality gates run in this session):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring"` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestAnchorEssayWorkflow"` ✅
  - `pdm run format-all` ✅
  - `pdm run lint-fix --unsafe-fixes` ✅
  - `pdm run typecheck-all` ✅

### 2025-11-30 (US-00YB step 3)

- Context helpers:
  - Added a pure `build_bt_metadata_updates(...)` helper to `services/cj_assessment_service/cj_core_logic/workflow_context.py` that constructs BT-related `metadata_updates` (`bt_scores`, `last_scored_iteration`, `last_score_change`, optional `bt_se_summary`, and `bt_quality_flags`) and derives the three BT batch-quality booleans (`bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`) from an incoming `bt_se_summary` using numeric thresholds that are passed in (already resolved from `Settings`).
  - Kept this helper JSON-safe and side-effect-free: it only returns primitives/dicts used to populate `ContinuationContext.metadata_updates` and BT quality fields; it does not perform any logging, DB access, or Prometheus interactions.
- workflow_decision refactor (structural only):
  - Updated `_build_continuation_context(...)` in `services/cj_assessment_service/cj_core_logic/workflow_decision.py` to delegate BT metadata/flag construction to `build_bt_metadata_updates(...)`, while keeping score-stability computation, success-rate guards, small-net coverage derivation, and the overall `ContinuationContext` shape unchanged.
  - Retained Prometheus diagnostics (`cj_bt_se_inflated_batches_total`, `cj_bt_sparse_coverage_batches_total`) inside `workflow_decision`: after calling `build_bt_metadata_updates(...)`, `_build_continuation_context(...)` still increments these counters based solely on the derived BT flags when `bt_se_summary` is present, preserving existing observability behaviour and thresholds.
- Behaviour and semantics:
  - Confirmed that thresholds, caps, and PR‑2 stability-first success-rate semantics are preserved: stability still depends on `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`, and (when enabled) `MIN_SUCCESS_RATE_THRESHOLD`, and the success-rate failure guard (`should_fail_due_to_success_rate`) is computed exactly as before.
  - Confirmed that PR‑7 small-net semantics and resampling caps are unchanged: `_derive_small_net_flags(...)`, `_can_attempt_small_net_resampling(...)`, and `ContinuationDecision` branching in `decide(ctx)` were not modified in this step.
  - Verified that BT SE quality flags (`bt_quality_flags`) and their JSON-serializable metadata contract remain identical: `bt_se_inflated`, `comparison_coverage_sparse`, and `has_isolated_items` are derived using the same thresholds and are persisted under the same keys in `metadata_updates`, so existing tests and downstream consumers continue to read the same structure.
- Validation (tests and quality gates run in this step):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring"` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestAnchorEssayWorkflow"` ✅
  - `pdm run format-all` ✅
  - `pdm run lint-fix --unsafe-fixes` ✅
  - `pdm run typecheck-all` ✅

### 2025-11-30 (US-00YB step 4)

- Context helpers (small-net / coverage / resampling):
  - Added a pure `build_small_net_context(...)` helper to `services/cj_assessment_service/cj_core_logic/workflow_context.py` that constructs the small-net and coverage-related portion of `ContinuationContext` from:
    - `expected_essay_count` (already derived from `CJBatchState.batch_upload.expected_essay_count`),
    - coverage metadata fields in `processing_metadata` (`max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, `resampling_pass_count`), and
    - optional repository-derived `coverage_metrics` `(max_possible_pairs, successful_pairs_count)` when metadata does not yet populate coverage.
  - The helper returns the exact tuple previously produced by `_derive_small_net_flags(...)`: `expected_essay_count`, `is_small_net`, `max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, `resampling_pass_count`, `small_net_resampling_cap`, `small_net_cap_reached`, and remains JSON-safe and side-effect-free.
- workflow_decision refactor (small-net context extraction only):
  - Updated `_derive_small_net_flags(...)` in `services/cj_assessment_service/cj_core_logic/workflow_decision.py` to:
    - Continue owning the single DB call to `comparison_repository.get_coverage_metrics_for_batch(...)`, invoked only when coverage metadata is effectively empty (both counts are zero and `unique_coverage_complete` is False).
    - Extract raw coverage values from `processing_metadata` exactly as before, then pass `expected_essay_count`, the metadata-derived counts/flags, the optional `coverage_metrics` tuple, and the relevant thresholds (`MIN_RESAMPLING_NET_SIZE`, `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`) into `build_small_net_context(...)`.
    - Return the tuple from `build_small_net_context(...)` unchanged so `_build_continuation_context(...)` and `ContinuationContext` keep the same shape and field semantics.
- Behaviour and semantics (stability / caps / small-net / BT SE & coverage):
  - Confirmed that PR‑2 stability-first behaviour is unchanged: stability is still gated by `MIN_COMPARISONS_FOR_STABILITY_CHECK` and `SCORE_STABILITY_THRESHOLD`, and the success-rate guard (`zero_successes`, `below_success_threshold`, `should_fail_due_to_success_rate`) is unchanged and still derived in `_build_continuation_context(...)` and consumed by `decide(ctx)`.
  - Confirmed that PR‑7 small-net semantics and resampling caps are preserved:
    - `is_small_net` is still computed from `expected_essay_count` and `MIN_RESAMPLING_NET_SIZE`.
    - `small_net_resampling_cap` is still derived from `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` using the same `int(... or 0)` pattern.
    - `small_net_cap_reached` is still triggered only when the net is small, coverage is uniquely complete, and `resampling_pass_count >= small_net_resampling_cap`.
    - `_can_attempt_small_net_resampling(ctx)` and `_decide_continuation_action(ctx)`/`decide(ctx)` remain unchanged.
  - Confirmed that BT SE and coverage semantics (including the `bt_quality_flags` contract) are unchanged:
    - `build_bt_metadata_updates(...)` from step 3 remains the sole place where BT SE diagnostics (`bt_se_summary`) are converted into `bt_quality_flags` and related booleans (`bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`).
    - The new small-net helper only consumes coverage counts/flags and does not alter any BT thresholds or flag semantics.
- Structural/observability prep for `workflow_diagnostics`:
  - Kept all Prometheus metrics (BT SE batch-quality counters) and logging inside `workflow_decision._build_continuation_context(...)` and leave `workflow_context.build_small_net_context(...)` strictly pure; this keeps metrics clearly separated from data transforms.
  - Ensured that all metric-relevant booleans for small-net and coverage (`is_small_net`, `unique_coverage_complete`, `small_net_cap_reached`, plus the BT quality flags already on `ContinuationContext`) are available on `ContinuationContext`, so a future `workflow_diagnostics` module can drive counters and logs based solely on `ContinuationContext` without re-touching the DB.
- Validation (tests and quality gates run in this step):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring"` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestAnchorEssayWorkflow"` ✅
  - `pdm run format-all` ✅
  - `pdm run lint-fix --unsafe-fixes` ✅
  - `pdm run typecheck-all` ✅

### 2025-11-30 (US-00YB step 5)

- Diagnostics module:
  - Introduced `services/cj_assessment_service/cj_core_logic/workflow_diagnostics.py` as a side-effect-only module that observes `ContinuationContext` and updates Prometheus metrics without influencing continuation predicates, thresholds, or caps.
  - Added `record_bt_batch_quality(ctx: ContinuationContext) -> None` to encapsulate BT SE batch-quality diagnostics; it increments `cj_bt_se_inflated_batches_total` and `cj_bt_sparse_coverage_batches_total` counters only when `bt_se_summary` is present on the context and the corresponding `bt_se_inflated` / `comparison_coverage_sparse` flags are True.
  - Added `record_workflow_decision(ctx: ContinuationContext, decision: ContinuationDecision) -> None` to record high-level continuation decisions via a new `cj_workflow_decisions_total{decision=...}` counter derived solely from `ContinuationContext` and the `ContinuationDecision` value.
- Metrics extraction and wiring:
  - Refactored `services/cj_assessment_service/cj_core_logic/workflow_decision.py::_build_continuation_context(...)` to:
    - Keep BT SE and coverage flag derivation pure by continuing to delegate all metadata/flag computation to `build_bt_metadata_updates(...)` and small-net coverage flags to `_derive_small_net_flags(...)`.
    - Remove the direct Prometheus counter lookups and increments for `cj_bt_se_inflated_batches_total` and `cj_bt_sparse_coverage_batches_total`, replacing them with a single call to `record_bt_batch_quality(ctx)` after the `ContinuationContext` is constructed.
  - Extended `services/cj_assessment_service/metrics.py` to define the new `cj_workflow_decisions_total` `Counter("cj_workflow_decisions_total", ..., ["decision"])`, expose it via `_get_existing_metrics()` and `get_business_metrics()`, and kept the existing BT SE batch-quality counters unchanged.
  - Updated `services/cj_assessment_service/cj_core_logic/workflow_continuation.py::trigger_existing_workflow_continuation` to call `record_workflow_decision(ctx, decision)` immediately after `decision = decide(ctx)`, so per-decision metrics are driven from the final `ContinuationDecision` while leaving the decision tree itself pure.
- Behaviour and semantics:
  - Confirmed that PR‑2 stability and success-rate gating remain unchanged: score stability is still computed via `check_score_stability` with `MIN_COMPARISONS_FOR_STABILITY_CHECK` and `SCORE_STABILITY_THRESHOLD`, and `should_fail_due_to_success_rate` is still derived from `zero_successes` / `below_success_threshold` and the cap/budget predicates inside `_build_continuation_context(...)` and consumed only by `decide(ctx)`.
  - Confirmed that PR‑7 small-net semantics are preserved end-to-end:
    - `is_small_net`, `small_net_resampling_cap`, and `small_net_cap_reached` continue to be derived from `MIN_RESAMPLING_NET_SIZE`, `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`, coverage counts, and `resampling_pass_count` exactly as in step 4.
    - `_can_attempt_small_net_resampling(ctx)` and the resampling paths in `trigger_existing_workflow_continuation` remain unchanged; diagnostics only observe the resulting `ContinuationContext`.
  - Confirmed that BT SE and coverage semantics (including `bt_se_summary`, `bt_quality_flags`, `bt_se_inflated`, `comparison_coverage_sparse`, and `has_isolated_items`) are unchanged and continue to be derived exclusively by `build_bt_metadata_updates(...)` in `workflow_context`; `workflow_diagnostics` now owns the Prometheus increments but does not modify metadata or flags.
- Validation (tests and quality gates run in this step):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring"` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestAnchorEssayWorkflow"` ✅
  - `pdm run format-all` ✅
  - `pdm run lint-fix --unsafe-fixes` ✅
  - `pdm run typecheck-all` ✅

### 2025-11-30 (US-00YB step 6)

- Observability consolidation and diagnostics coverage:
  - Added `services/cj_assessment_service/tests/unit/test_workflow_diagnostics.py` to exercise the new diagnostics layer directly, validating that:
    - `record_bt_batch_quality(ctx)` increments `cj_bt_se_inflated_batches_total` and `cj_bt_sparse_coverage_batches_total` only when `bt_se_summary` is present on `ContinuationContext` and the corresponding `bt_se_inflated` / `comparison_coverage_sparse` flags are True.
    - `record_workflow_decision(ctx, decision)` drives `cj_workflow_decisions_total{decision=...}` using the `ContinuationDecision` enum values (`WAIT_FOR_CALLBACKS`, `FINALIZE_SCORING`, `FINALIZE_FAILURE`, `REQUEST_MORE_COMPARISONS`, `NO_OP`) and that all enum values are observed.
  - Updated the CJ runbook (`docs/operations/cj-assessment-runbook.md`) to document the new workflow decision metric:
    - Described `cj_workflow_decisions_total{decision=...}` as a diagnostic-only counter emitted via `workflow_diagnostics.record_workflow_decision(...)` from `workflow_continuation.trigger_existing_workflow_continuation`, using the same decision vocabulary as the structured `Continuation decision evaluated` log.
    - Added an example Grafana panel configuration showing `sum by (decision) (rate(cj_workflow_decisions_total[5m]))` to visualize the mix of continuation outcomes over time (finalize_scoring vs finalize_failure vs request_more_comparisons vs wait/no-op).
  - Extended the CJ Assessment Grafana deep-dive dashboard (`observability/grafana/dashboards/cj-assessment/HuleEdu_CJ_Assessment_Deep_Dive.json`) with a new panel titled “CJ Workflow Decisions (rate by decision)” that charts `sum by (decision) (rate(cj_workflow_decisions_total[5m]))`, keeping the existing BT SE and coverage panels/alerts unchanged.
- Behaviour and semantics (no-op with respect to PR-2/PR-7/BT SE):
  - Confirmed that all continuation metrics and structured logs remain strictly observational:
    - `ContinuationContext` still owns score-stability, success-rate, small-net, BT SE, and coverage flags; `decide(ctx)` and `_can_attempt_small_net_resampling(ctx)` remain pure and unchanged.
    - `workflow_diagnostics` reads `ContinuationContext` and `ContinuationDecision` to update Prometheus counters but does not mutate context, thresholds, caps, or predicates.
  - Re-verified that PR‑2 stability and success-rate gating, PR‑7 small-net semantics (including resampling caps and `_can_attempt_small_net_resampling(ctx)` behaviour), and BT SE / coverage semantics derived by `build_bt_metadata_updates(...)` in `workflow_context` are unchanged; this step only adds tests and documentation around the existing diagnostics surface.
- Validation (tests and quality gates run in this step):
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestBradleyTerryScoring"` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests -k "TestAnchorEssayWorkflow"` ✅
  - `pdm run format-all` ✅
  - `pdm run lint-fix --unsafe-fixes` ✅
  - `pdm run typecheck-all` ✅

## Related

- `TASKS/assessment/us-00ya-workflow-continuation-refactor--phase-6.md`
