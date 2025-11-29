---
id: 'us-0054-convergence-tests-for-iterative-bundled-mode'
title: 'US-005.4: Convergence tests for iterative bundled mode'
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
# US-005.4: Convergence tests for iterative bundled mode

## Objective

Create a test harness that validates convergence behavior under configurable parameters, verifying stability checks and iteration limits work correctly.

## Context

Part of EPIC-005 (CJ Stability & Reliability). The iterative/bundled mode needs comprehensive testing to ensure convergence behavior matches expectations under various configurations.

## Acceptance Criteria

- [ ] A test harness wires `_process_comparison_iteration` + `_check_iteration_stability` with configurable:
  - `COMPARISONS_PER_STABILITY_CHECK_ITERATION`
  - `MIN_COMPARISONS_FOR_STABILITY_CHECK`
  - `MAX_ITERATIONS`
  - `MAX_PAIRWISE_COMPARISONS`
- [ ] Tests assert that:
  - Stability checks only run after `MIN_COMPARISONS_FOR_STABILITY_CHECK` successful comparisons
  - Additional iterations stop when either:
    - Stability is achieved, or
    - `MAX_PAIRWISE_COMPARISONS` or `MAX_ITERATIONS` is reached
- [ ] The behaviour and intended future wiring for bundled iterative mode is documented in the epic doc

## Implementation Notes

Key files to create/modify:
- `services/cj_assessment_service/tests/integration/test_convergence_harness.py`
- `services/cj_assessment_service/src/comparison_processing.py`

## Related

- Parent epic: [EPIC-005: CJ Stability & Reliability](../../../docs/product/epics/cj-stability-and-reliability.md)
- Related stories: US-005.2 (Score stability semantics)

## Progress (PR-2 snapshot)

- PR-2 implements callback gating, stability checks, and success-rate based failure semantics in the CJ Assessment Service.
- Guardrail tests for zero-success and low-success-rate batches now assert failure finalization (`finalize_failure`) and are passing.
- Integration coverage has been added for small (2-essay) and larger batches to ensure `completion_denominator()` and pending callback logic behave correctly.
- Phase-2 resampling and small-net caps remain out of scope for PR-2 and will be delivered in PR-7.
