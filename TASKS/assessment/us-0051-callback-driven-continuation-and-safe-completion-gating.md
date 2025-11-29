---
id: 'us-0051-callback-driven-continuation-and-safe-completion-gating'
title: 'US-005.1: Callback-driven continuation and safe completion gating'
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
# US-005.1: Callback-driven continuation and safe completion gating

## Objective

Ensure the CJ workflow only proceeds when all expected callbacks have arrived, preventing premature finalization with incomplete comparison data.

## Context

Part of EPIC-005 (CJ Stability & Reliability). The current implementation may finalize batches prematurely when callback counts are miscalculated or when high failure rates inflate the received count without sufficient valid comparisons.

## Acceptance Criteria

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

## Implementation Notes

Suggested task doc path: `TASKS/assessment/cj-stab-1-callback-continuation-and-completion.md`

Key files to modify:
- `services/cj_assessment_service/src/workflow_continuation.py`
- `services/cj_assessment_service/src/batch_completion_checker.py`
- `services/cj_assessment_service/src/batch_completion_policy.py`
- `services/cj_assessment_service/src/models/cj_batch_state.py`

## Related

- Parent epic: [EPIC-005: CJ Stability & Reliability](../../../docs/product/epics/cj-stability-and-reliability.md)
- Related story: US-005.2 (Score stability semantics)

## Progress (PR-2 snapshot)

- PR-2 implements callback gating, stability checks, and success-rate based failure semantics in the CJ Assessment Service.
- Guardrail tests for zero-success and low-success-rate batches now assert failure finalization (`finalize_failure`) and are passing.
- Integration coverage has been added for small (2-essay) and larger batches to ensure `completion_denominator()` and pending callback logic behave correctly.
- Phase-2 resampling and small-net caps remain out of scope for PR-2 and will be delivered in PR-7.
