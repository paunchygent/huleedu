---
id: 'us-0053-retry-semantics-and-end-of-batch-fairness'
title: 'US-005.3: Retry semantics and end-of-batch fairness'
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
# US-005.3: Retry semantics and end-of-batch fairness

## Objective

Enable the CJ workflow to retry failed comparisons when budget remains, preventing high LLM failure rates from permanently degrading ranking quality.

## Context

Part of EPIC-005 (CJ Stability & Reliability). The retry infrastructure exists (`BatchRetryProcessor`, `RetryManager`) but is not wired into the continuation flow. This story integrates retry logic while preserving fairness semantics.

## Acceptance Criteria

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

## Implementation Notes

Key files to modify:
- `services/cj_assessment_service/src/workflow_continuation.py`
- `services/cj_assessment_service/src/batch_retry_processor.py`
- `services/cj_assessment_service/src/di.py`

## Related

- Parent epic: [EPIC-005: CJ Stability & Reliability](../../../docs/product/epics/cj-stability-and-reliability.md)
- Related stories: US-005.1 (Callback continuation), US-007.1 (Fairness coverage tests)
