---
id: 'us-00xy-cleanup-unused-comparison-processing-code-paths'
title: 'Clean up unused code paths in comparison_processing.py'
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
related: []
labels: []
---
# US-00XY: Clean up Unused Code Paths in comparison_processing.py

## Objective

Remove unused or scaffolding-only code paths from
`services/cj_assessment_service/cj_core_logic/comparison_processing.py` and
align documentation so that only the callback-first continuation loop and
currently supported batching patterns are described.

## Acceptance Criteria

- [x] Identify and remove unused helpers that are not wired into the current
      workflow, including (but not limited to):
      - `_process_comparison_iteration` (bundled iteration submission helper).
      - `_check_iteration_stability` (iteration-level stability helper).
- [x] Ensure that any behaviour covered by these helpers is either:
      - Already implemented in `workflow_continuation.trigger_existing_workflow_continuation`,
        or
      - Explicitly tracked as a future enhancement in TASKS/ or ADRs.
- [x] Update or remove any TODOs/tests that refer to the unused helpers as if
      they were production behaviour (e.g. comments in
      `test_incremental_scoring_integration.py`).
- [x] Update CJ service docs and ADRs (PR-7 notes, wave submission ADR) to refer
      to the callback-first continuation loop and current batching model only,
      without promising unused code paths.
- [ ] CJ unit and integration tests remain green after the cleanup, and no test
      imports removed symbols.

## Notes

- This cleanup should follow US-00XX (removal of
  `COMPARISONS_PER_STABILITY_CHECK_ITERATION`) so the convergence and
  batching story is already simplified.
- The goal is to keep the prototype repo free of legacy scaffolding and make
  the current production-intent pipeline the only behaviour visible in code
  and docs.

## Progress (2025-11-30)

- Removed unused `_process_comparison_iteration` and `_check_iteration_stability` helpers from `comparison_processing.py` and confirmed no remaining references in service code or tests.
- Updated tests and comments to reflect callback-first convergence: adjusted `test_incremental_scoring_integration.py` TODO to point at `workflow_continuation` + convergence harness rather than the removed helpers; verified unit tests around `request_additional_comparisons_for_batch` and budget/normalizer behaviour do not depend on the deleted functions.
- Aligned CJ docs with the current convergence model: updated the CJ assessment runbook, EPIC-005 stability epic, and ADR-0017 wave submission pattern to describe entry points (`submit_comparisons_for_async_processing` and `workflow_continuation.trigger_existing_workflow_continuation → comparison_processing.request_additional_comparisons_for_batch`) and convergence via thresholds/caps + small-net metadata only.
- Commands run:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_convergence_harness.py`
  - `pdm run pytest-root services/cj_assessment_service/tests`
  - `pdm run pytest-root 'services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py::TestBradleyTerryScoring::test_edge_cases[all_errors-3-comparisons2-True]'`

### Test status and known issues

- `services/cj_assessment_service/tests/unit/test_convergence_harness.py`: all tests passed, confirming the synthetic convergence harness matches the documented thresholds/caps semantics.
- Full CJ service test suite: all tests passed except the two previously known issues:
  - `test_bt_scoring_integration.py::TestBradleyTerryScoring::test_edge_cases[all_errors-3-comparisons2-True]` – passes in isolation but fails when run as part of the full suite; current behaviour of `record_comparisons_and_update_scores` and `compute_bt_scores_and_se` is to treat “all errors, zero successes” as a CJ domain error via `raise_cj_insufficient_comparisons`, which matches production intent. The failure pattern points to fixture/order-dependent database state rather than a scoring bug and should be addressed in the PR‑7/US‑0054 convergence test follow-up work.
  - `test_batch_finalizer_scoring_state.py::test_finalize_scoring_transitions_state` – unit test stubs `get_essays_for_cj_batch` with `SimpleNamespace` objects that do not provide an `is_anchor` attribute, causing `BatchFinalizer.finalize_scoring` to raise `AttributeError` when constructing `EssayForComparison`. In production, CJ uses `CJ_ProcessedEssay` rows which always include `is_anchor`, and `BatchFinalizer` is expected to publish dual assessment events once scoring and grade projections complete. This test now needs to be updated to include `is_anchor` (and potentially stronger assertions around the dual-event semantics) as part of a dedicated BatchFinalizer/ELS integration story.
