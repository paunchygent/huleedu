---
id: us-0052-score-stability-semantics-and-early-stopping
title: 'US-005.2: Score stability semantics and early stopping'
type: task
status: proposed
priority: medium
domain: assessment
service: cj_assessment_service
owner_team: agents
owner: ''
program: ''
created: '2025-11-28'
last_updated: '2026-02-01'
related: []
labels: []
---
# US-005.2: Score stability semantics and early stopping

## Objective

Apply consistent stability criteria before finalization, ensuring early stopping is predictable and cost-efficient without sacrificing ranking quality.

## Context

Part of EPIC-005 (CJ Stability & Reliability). The current implementation uses BT score changes for stability but may allow finalization under high-failure scenarios where few valid comparisons exist.

## Acceptance Criteria

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
- [ ] `COMPARISONS_PER_STABILITY_CHECK_ITERATION` is treated as a **cadence hint** (how often we re-check stability), not as a hard per-wave cap:
  - Code does **not** use it to slice or truncate the wave returned by `compute_wave_pairs`
  - Settings docstrings and service docs are updated to reflect this interpretation
- [ ] Docs:
  - `docs/services/cj-assessment-service.md` (or existing service doc) clearly explains:
    - Wave size = `compute_wave_size(n) ≈ n // 2` after odd-count handling
    - `MAX_PAIRWISE_COMPARISONS` = global hard cap
    - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` = approximate number of new comparisons between stability checks

## Implementation Notes

Key files to modify:
- `services/cj_assessment_service/src/workflow_continuation.py`
- `services/cj_assessment_service/src/scoring_ranking.py`
- `services/cj_assessment_service/src/config.py`

## Related

- Parent epic: [EPIC-005: CJ Stability & Reliability](../../../docs/product/epics/cj-stability-and-reliability.md)
- Related stories: US-005.1 (Callback continuation), US-005.4 (Convergence tests)

## Progress (PR-2 snapshot)

- PR-2 implements callback gating, stability checks, and success-rate based failure semantics in the CJ Assessment Service.
- Guardrail tests for zero-success and low-success-rate batches now assert failure finalization (`finalize_failure`) and are passing.
- Integration coverage has been added for small (2-essay) and larger batches to ensure `completion_denominator()` and pending callback logic behave correctly.
- Phase-2 resampling and small-net caps remain out of scope for PR-2 and will be delivered in PR-7.

## PR-4 Plan: Scoring Core Refactor (BT Inference)

To support EPIC-005 and EPIC-006 without altering PR-2 semantics, PR-4 will:

- Introduce a `BTScoringResult` domain object in `scoring_ranking.py` capturing:
  - Per-essay BT scores (mean-centred)
  - Per-essay BT standard errors (respecting `BT_STANDARD_ERROR_MAX`)
  - Per-essay comparison counts
  - A batch-level SE summary for observability
- Extract a pure helper `compute_bt_scores_and_se(...) -> BTScoringResult` that:
  - Builds the BT graph from `EssayForComparison` + `CJ_ComparisonPair` rows
  - Delegates to `choix.ilsr_pairwise` and `bt_inference.compute_bt_standard_errors`
  - Raises the same HuleEdu errors (`raise_cj_insufficient_comparisons`, `raise_cj_score_convergence_failed`) as the current implementation.
- Refactor `record_comparisons_and_update_scores(...)` so that it:
  - Owns a single `SessionProviderProtocol` session per call
  - Persists new `CJ_ComparisonPair` rows, loads all valid comparisons, and updates
    `CJ_ProcessedEssay` scores/SEs/counts in one transaction
  - Logs SE diagnostics from `BTScoringResult.se_summary`
  - Returns scores with the same signature used by PR-2.
- Keep all PR-2 stability and completion semantics intact:
  - `trigger_existing_workflow_continuation` remains the only place that:
    - Computes `max_score_change` with `check_score_stability`
    - Applies `MIN_COMPARISONS_FOR_STABILITY_CHECK` and `SCORE_STABILITY_THRESHOLD`
    - Applies the success-rate guard and routes to `finalize_scoring` vs `finalize_failure`
    - Persists `bt_scores`, `last_scored_iteration`, and `last_score_change` into
      `CJBatchState.processing_metadata` via its own session.

This refactor is a precondition for later Phase-2 resampling work (PR-7) and confidence
semantics (EPIC-006), ensuring the scoring core has clear layering and no hidden cross-session
side effects.

## PR-4 Implementation Status (2025-11-29)

- ✅ `BTScoringResult` dataclass added to `scoring_ranking.py` capturing scores, SEs, per-essay counts, and `se_summary`.
- ✅ Pure helper `compute_bt_scores_and_se(all_essays, comparisons) -> BTScoringResult` implemented, delegating to `choix.ilsr_pairwise` and `bt_inference.compute_bt_standard_errors` and raising the existing CJ domain errors on insufficient data or BT convergence failures.
- ✅ `record_comparisons_and_update_scores(...)` now:
  - Uses a single `SessionProviderProtocol` session per call.
  - Persists new `CJ_ComparisonPair` rows, reloads all valid comparisons, and updates `CJ_ProcessedEssay` scores/SEs/counts in one transaction.
  - Delegates all BT math to `compute_bt_scores_and_se` and logs the batch-level SE diagnostics from `BTScoringResult.se_summary`.
  - Returns `dict[str, float]` BT scores with unchanged PR-2 semantics.
- ✅ Workflow and finalizer callers (`trigger_existing_workflow_continuation`, `BatchFinalizer.finalize_scoring`, `batch_monitor`) continue to use `record_comparisons_and_update_scores` as the sole scoring entry point; PR-2 stability and success-rate gating behaviour is unchanged and guarded by existing tests.
- ✅ Tests and quality gates run from repo root:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_bt_inference.py`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_scoring_ranking_bt_helper.py`
  - `pdm run pytest-root services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py`
  - `pdm run pytest-root 'services/cj_assessment_service/tests/integration/test_incremental_scoring_integration.py' -k 'progressive_score_refinement or stability_detection_mechanism or callback_processing_mechanism or batch_completion_at_threshold'`
  - `pdm run pytest-root services/cj_assessment_service/tests`
  - `pdm run format-all`, `pdm run lint-fix --unsafe-fixes`, `pdm run typecheck-all`
- 🔄 Remaining (tracked for PR-7 / EPIC-006, not implemented in PR-4):
  - Persisting SE coverage metadata (`se_summary`) onto `CJBatchState.processing_metadata` from the workflow layer using its existing session.
  - Phase-2 resampling and small-net semantics, convergence harness wiring, and any batch-quality indicators derived from SE diagnostics.
