---
id: 'us-0074-test-architecture-guardrails-and-strategy-extension-guide'
title: 'US-007.4: Test architecture guardrails and strategy extension guide'
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
# US-007.4: Test architecture guardrails and strategy extension guide

## Objective

Establish clear guidelines for testing matching strategies, preventing brittle mock-based tests and ensuring best practices are followed.

## Context

Part of EPIC-007 (Developer Experience & Testing). Without guidelines, developers may create tests that pass but don't validate real behavior. This story establishes guardrails and documents the extension pattern for new strategies.

## Acceptance Criteria

- [ ] A short developer-facing note exists, e.g. `services/cj_assessment_service/tests/ARCHITECTURE_NOTES.md` or `docs/decisions/000X-matching-strategy-testing-rules.md`, stating:
  - Real algorithms (e.g. `OptimalGraphMatchingStrategy`) are used as units under test
  - Protocol-based mocks are used only at external boundaries (LLM, Kafka, Content)
  - Bare `MagicMock(spec=PairMatchingStrategyProtocol)` must not be used where real matching behaviour matters
- [ ] New matching strategies follow a documented pattern:
  - Implement `PairMatchingStrategyProtocol` in `matching_strategies/`
  - Register in `provide_pair_matching_strategy` in `di.py`
  - Provide a dedicated unit test suite
  - Optionally add a small pair_generation-level test illustrating behavioural differences
- [ ] A lightweight grep-based CI check (or equivalent) enforces:
  - If tests use `MagicMock(spec=PairMatchingStrategyProtocol)`, they either:
    - Call a shared helper (delegating to real strategy), or
    - Are clearly documented as intentionally fully stubbed
- [ ] A small integration test verifies metrics expectations, e.g.:
  - Submitting a known number of pairs increments `cj_comparisons_total` (and other relevant metrics) as expected

## Implementation Notes

Key files to create/modify:
- `services/cj_assessment_service/tests/ARCHITECTURE_NOTES.md` (update existing or create)
- `docs/decisions/000X-matching-strategy-testing-rules.md` (optional ADR)
- CI check script (e.g. in `.github/workflows/` or as a pre-commit hook)

## Related

- Parent epic: [EPIC-007: Developer Experience & Testing](../../../docs/product/epics/cj-developer-experience-and-testing.md)
- Related stories: US-007.1 (Test helpers), US-007.2 (Documentation)
