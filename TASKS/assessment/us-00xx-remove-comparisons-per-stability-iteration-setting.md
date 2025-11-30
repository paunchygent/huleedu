---
id: 'us-00xx-remove-comparisons-per-stability-iteration-setting'
title: 'Remove COMPARISONS_PER_STABILITY_CHECK_ITERATION setting from CJ service'
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
# US-00XX: Remove COMPARISONS_PER_STABILITY_CHECK_ITERATION Setting from CJ Service

## Objective

Remove `COMPARISONS_PER_STABILITY_CHECK_ITERATION` as a first-class CJ setting and
clarify that iteration cadence is emergent from batch size, matching strategy, and
comparison budgets. Stability should be governed solely by:

- `MIN_COMPARISONS_FOR_STABILITY_CHECK`
- `SCORE_STABILITY_THRESHOLD`
- `MAX_PAIRWISE_COMPARISONS`
- Coverage/small-net metadata

## Acceptance Criteria

- [ ] `services/cj_assessment_service/config.py` no longer declares
      `COMPARISONS_PER_STABILITY_CHECK_ITERATION`, and no env var is consumed.
- [ ] `BatchingModeService.is_iterative_batching_online()` in
      `cj_core_logic/llm_batching_service.py` determines iterative mode without
      referencing `COMPARISONS_PER_STABILITY_CHECK_ITERATION`.
- [ ] Production convergence logic (`workflow_continuation`, `comparison_processing`)
      has no dependency (direct or indirect) on `COMPARISONS_PER_STABILITY_CHECK_ITERATION`.
- [ ] Convergence harness treats `comparisons_per_iteration` as a harness-only
      parameter; docs no longer claim a direct mapping to the removed setting.
- [ ] All docs/ADRs/epics/runbooks referencing
      `COMPARISONS_PER_STABILITY_CHECK_ITERATION` are updated to reflect the new
      model (stability thresholds + caps, emergent wave size).
- [ ] ENG5 and runner docs no longer instruct tuning
      `COMPARISONS_PER_STABILITY_CHECK_ITERATION`; they reference stability
      thresholds and comparison budgets instead.
- [ ] CJ tests and repo-wide typecheck remain green after the removal.

## Notes

- Prototype repo / no-legacy policy: the setting is removed outright rather
  than deprecated.
- If a future need arises for a wave-size hint, it will be introduced as a
  derived, per-batch value tied to coverage and budgets, not as a global
  configuration setting.
