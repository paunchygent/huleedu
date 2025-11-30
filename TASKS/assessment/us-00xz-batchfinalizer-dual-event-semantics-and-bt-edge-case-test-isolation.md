---
id: 'us-00xz-batchfinalizer-dual-event-semantics-and-bt-edge-case-test-isolation'
title: 'US-00XZ BatchFinalizer dual-event semantics and BT edge-case test isolation'
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
related: ['us-00xy-cleanup-unused-comparison-processing-code-paths']
labels: []
---
# US-00XZ: BatchFinalizer dual-event semantics and BT edge-case test isolation

## Objective

Align CJ BatchFinalizer scoring-state behaviour and BT edge-case tests with the
current production intent so that:

- Successful scoring paths publish the expected dual assessment events and drive
  the correct CJ batch state transitions.
- The "all errors, zero successes" BT scenario reliably surfaces a CJ domain
  error in both isolated and full-suite runs, without changing scoring or
  convergence thresholds.

## Context

US-00XY removed unused comparison-processing helpers and updated CJ docs to
anchor convergence semantics on `workflow_continuation` +
`BatchFinalizer`. Two CJ tests remain flaky or failing:

- `test_batch_finalizer_scoring_state.py::test_finalize_scoring_transitions_state`
  currently stubs essays without `is_anchor`, causing
  `BatchFinalizer.finalize_scoring` to treat the batch as malformed and skip
  dual-event publishing.
- `test_bt_scoring_integration.py::TestBradleyTerryScoring::test_edge_cases[all_errors-3-comparisons2-True]`
  passes in isolation but fails in the full suite, indicating fixture/order
  issues around database isolation for the "all errors, zero successes" case.

This task hardens those tests and any minimal supporting fixtures so they
accurately reflect production behaviour without altering BT scoring semantics or
convergence thresholds defined in EPIC-005 / PR-7.

## Acceptance Criteria

- [x] `test_batch_finalizer_scoring_state.py::test_finalize_scoring_transitions_state`
      uses essay stubs that match the minimum `CJ_ProcessedEssay` shape,
      including `is_anchor`, and passes reliably.
- [x] The BatchFinalizer scoring-state unit test asserts that a successful
      scoring path:
      - Transitions the CJ batch state from SCORING to COMPLETED, and
      - Invokes `publish_dual_assessment_events` exactly once with realistic
        payloads or argument shapes.
- [x] `test_bt_scoring_integration.py::TestBradleyTerryScoring::test_edge_cases[all_errors-3-comparisons2-True]`
      deterministically exercises the "all errors, zero successes" domain-error
      path by ensuring its CJ batch and comparisons are isolated from other
      tests and that `record_comparisons_and_update_scores` raises the expected
      `HuleEduError`.
- [x] No changes are made to production convergence thresholds, success-rate
      guards, or BT scoring semantics; only tests and, if absolutely necessary,
      fixtures/helpers are updated to align with current behaviour.
- [ ] The CJ service test suite (`services/cj_assessment_service/tests`) passes
      with these two tests green and no new CJ failures introduced.

## Plan

- Analyze `BatchFinalizer.finalize_scoring` and the existing unit test to
  confirm the expected dual-event publishing and state transition behaviour.
- Update the BatchFinalizer scoring-state unit test to use realistic essay
  stubs (including `is_anchor`) and strengthen assertions around
  `publish_dual_assessment_events`.
- Investigate the BT all-errors edge-case integration test fixtures and
  database behaviour when run under the full CJ suite; introduce targeted
  isolation (e.g. unique batch IDs or stricter cleanup) so the "all errors,
  zero successes" scenario is not contaminated by prior comparisons.
- Re-run focused CJ tests and then the full CJ test suite via
  `pdm run pytest-root services/cj_assessment_service/tests` to confirm all
  acceptance criteria.

## Progress (2025-11-30)

- Task created as US-00XZ under `TASKS/assessment/` to track BatchFinalizer
  dual-event semantics and BT edge-case test isolation as a follow-up to
  US-00XY.
- Updated `test_batch_finalizer_scoring_state.py::test_finalize_scoring_transitions_state`
  to use essay stubs that include `is_anchor` and to assert that
  `BatchFinalizer.finalize_scoring`:
  - Transitions the fine-grained CJ state from SCORING to COMPLETED via
    `update_batch_state`, and
  - Invokes `publish_dual_assessment_events` exactly once with a
    `DualEventPublishingData` payload containing the expected BOS batch ID,
    CJ batch ID, assignment, course code, and identity threading.
- Hardened `test_bt_scoring_integration.py::TestBradleyTerryScoring::test_edge_cases`
  by:
  - Updating `_create_test_batch` to generate a per-call UUID BOS batch_id when
    none is provided, avoiding cross-test reuse of `"test-batch"` against the
    shared Postgres container.
  - Verifying that the `all_errors` scenario logs “Stored 0 new comparison
    pairs” and raises the expected `HuleEduError` in both isolated and full
    file runs.
- Commands run:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py`
  - `pdm run pytest-root 'services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py -k all_errors'`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py`
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`

## Related

- `TASKS/assessment/us-00xy-cleanup-unused-comparison-processing-code-paths.md`
