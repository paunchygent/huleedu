---
id: 'us-0052-score-stability-semantics-and-early-stopping'
title: 'US-005.2: Score stability semantics and early stopping'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-28'
last_updated: '2025-11-28'
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
