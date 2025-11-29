---
id: 'us-0071-matching-strategy-test-helpers-and-fairness-coverage'
title: 'US-007.1: Matching strategy test helpers and fairness coverage'
type: 'task'
status: 'in_progress'
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
# US-007.1: Matching strategy test helpers and fairness coverage

## Objective

Create reusable test helpers for matching strategy behavior, enabling reliable tests without recreating complex mock setups.

## Context

Part of EPIC-007 (Developer Experience & Testing). Tests currently use bare `MagicMock(spec=PairMatchingStrategyProtocol)` which doesn't delegate to real matching behavior, leading to tests that pass but don't validate actual fairness semantics.

## Acceptance Criteria

- [ ] A shared helper module exists, e.g. `services/cj_assessment_service/tests/helpers/matching_strategies.py`, providing:
  - `make_real_matching_strategy_mock()` - returns a protocol-shaped mock that delegates `handle_odd_count`, `compute_wave_pairs`, and `compute_wave_size` to a real `OptimalGraphMatchingStrategy`
  - `make_deterministic_anchor_student_strategy()` - deterministic strategy used for DB randomization tests (e.g. always anchor-student pairs)
- [ ] All integration and pipeline tests that depend on real wave semantics use these helpers rather than raw `MagicMock(spec=PairMatchingStrategyProtocol)` without delegation
- [ ] Unit tests for `OptimalGraphMatchingStrategy` cover:
  - Odd-count handling (highest comparison count excluded, deterministic tie-break on id)
  - Fairness weighting (low comparison_count essays are preferred across multiple waves)
  - BT proximity weighting (close BT scores are paired more often than distant ones)
  - Exclusion of `existing_pairs` and correct use of `compute_wave_size(n) == n // 2`
- [ ] Multi-wave fairness tests track per-essay `comparison_count` across several synthetic waves and assert:
  - Over-sampled essays appear less frequently in later waves than under-sampled essays
- [ ] Naming for matching weights is consistent:
  - Code, settings, and docs all use `MATCHING_WEIGHT_COMPARISON_COUNT` and `MATCHING_WEIGHT_BT_PROXIMITY` (or a clearly-documented alias)

## Implementation Notes

Key files to create/modify:
- `services/cj_assessment_service/tests/helpers/matching_strategies.py` (new)
- `services/cj_assessment_service/tests/unit/test_optimal_graph_matching_strategy.py`
- Various integration tests to update

## Related

- Parent epic: [EPIC-007: Developer Experience & Testing](../../../docs/product/epics/cj-developer-experience-and-testing.md)
- Related stories: US-005.3 (Retry fairness), US-007.4 (Test architecture guardrails)
