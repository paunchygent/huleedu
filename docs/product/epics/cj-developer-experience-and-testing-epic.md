---
type: epic
id: EPIC-007
title: Developer Experience & Testing
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-28
last_updated: 2025-11-28
---

# EPIC-007: Developer Experience & Testing

## Summary

Improve CJ Assessment Service test infrastructure, documentation, and developer tooling to enable efficient development and reliable testing of the comparative judgment pipeline.

**Business Value**: Faster development cycles, fewer regressions, and clearer onboarding for developers working on CJ features.

**Scope Boundaries**:
- **In Scope**: Test helpers, fairness coverage tests, configuration documentation, dev runner, Kafka wrapper, test architecture guardrails
- **Out of Scope**: Stability/reliability (EPIC-005), grade projection quality (EPIC-006)

## User Stories

### US-007.1: Matching Strategy Test Helpers & Fairness Coverage

**As a** developer
**I want** reusable test helpers for matching strategy behavior
**So that** I can write reliable tests without recreating complex mock setups.

**Acceptance Criteria**:
- [ ] A shared helper module exists, e.g. `services/cj_assessment_service/tests/helpers/matching_strategies.py`, providing:
  - `make_real_matching_strategy_mock()` – returns a protocol-shaped mock that delegates `handle_odd_count`, `compute_wave_pairs`, and `compute_wave_size` to a real `OptimalGraphMatchingStrategy`
  - `make_deterministic_anchor_student_strategy()` – deterministic strategy used for DB randomization tests (e.g. always anchor–student pairs)
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

**Task**: `TASKS/assessment/cj-us-007-1-matching-strategy-helpers-and-fairness-tests.md`

---

### US-007.2: Documentation for Matching, Budgets, and Stability Cadence

**As a** developer
**I want** clear documentation of CJ configuration parameters
**So that** I understand how wave sizing, budgets, and stability checks interact.

**Acceptance Criteria**:
- [ ] `docs/services/cj-assessment-service.md` (or equivalent) is updated to:
  - Describe the responsibilities split:
    - Matching strategy: "Given essays and history, choose best wave; typical wave size ≈ n // 2."
    - Orchestration: "Decides how often to recheck stability and when to request more waves."
  - Define:
    - `MAX_PAIRWISE_COMPARISONS` as global hard cap
    - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` as cadence target, **not** wave size
- [ ] Older docs that imply "wave size must equal `COMPARISONS_PER_STABILITY_CHECK_ITERATION`" are corrected or removed
- [ ] A short reference doc exists, compliant with `docs/` rules, e.g.: `docs/reference/cj-assessment-config.md` describing:
  - All CJ-relevant settings from `Settings`
  - Expected ranges and operational impact for each (especially budgets and stability thresholds)
- [ ] All new doc filenames use kebab-case and live under allowed directories (`product/`, `services/`, `reference/`)

**Task**: `TASKS/assessment/cj-us-007-2-matching-and-stability-docs.md`

---

### US-007.3: Dev Runner & Kafka Wrapper for CJ Workflows

**As a** developer
**I want** simple utilities to run CJ workflows locally
**So that** I can test changes without full Kafka/Docker infrastructure.

**Acceptance Criteria**:
- [ ] An in-process dev runner exists, e.g. `clients/python/cj_runner.py`, that:
  - Accepts an `AsyncEngine` or DSN
  - Instantiates `CJAssessmentServiceProvider`
  - Exposes a single `run_cj_assessment_workflow_in_process(request_data, correlation_id)` helper
- [ ] A small Kafka client wrapper exists, e.g. `clients/python/cj_kafka_client.py`, that:
  - Takes `ELS_CJAssessmentRequestV1`-shaped data
  - Publishes to `CJ_ASSESSMENT_REQUEST_TOPIC`
  - Returns the correlation ID and any useful tracing metadata
- [ ] Example usage is provided under `examples/`, showing:
  - How another service or script submits a batch via Kafka
  - How to run an end-to-end in-process test with the dev runner
- [ ] A how-to document exists under `docs/how-to/`, e.g. `docs/how-to/run-cj-assessment-locally.md`, describing:
  - Setup (DB, Kafka, env vars)
  - How to use the dev runner and Kafka client
  - How to inspect results

**Task**: `TASKS/assessment/cj-us-007-3-dev-runner-and-kafka-wrapper.md`

---

### US-007.4: Test Architecture Guardrails & Strategy Extension Guide

**As a** developer
**I want** clear guidelines for testing matching strategies
**So that** I follow best practices and don't introduce brittle mock-based tests.

**Acceptance Criteria**:
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

**Task**: `TASKS/assessment/cj-us-007-4-test-architecture-guardrails-and-strategy-guide.md`

## Technical Architecture

### Test Helper Structure
```
services/cj_assessment_service/tests/
├── helpers/
│   ├── __init__.py
│   └── matching_strategies.py    # make_real_matching_strategy_mock, etc.
├── ARCHITECTURE_NOTES.md         # Testing guidelines
├── unit/
├── integration/
└── ...
```

### Dev Runner Structure
```
clients/python/
├── cj_runner.py           # In-process workflow runner
└── cj_kafka_client.py     # Kafka publish wrapper

examples/
└── cj_assessment/
    ├── submit_batch.py    # Kafka submission example
    └── run_in_process.py  # Dev runner example
```

### Key Services
- **CJ Assessment Service**: `services/cj_assessment_service/`
- **Matching Strategies**: `services/cj_assessment_service/src/matching_strategies/`
- **DI Provider**: `services/cj_assessment_service/src/di.py`

### Configuration Points
- `MATCHING_WEIGHT_COMPARISON_COUNT`: Weight for fairness in matching (default: 1.0)
- `MATCHING_WEIGHT_BT_PROXIMITY`: Weight for BT proximity in matching (default: 0.5)

## Related ADRs
- (To be created) ADR-000X: Matching Strategy Testing Rules

## Dependencies
- pytest, pytest-asyncio
- Optional: testcontainers for integration tests

## Notes
- Existing `ARCHITECTURE_NOTES.md` at `services/cj_assessment_service/tests/ARCHITECTURE_NOTES.md` should be reviewed and updated
- Related to EPIC-004 (core CJ features), EPIC-005 (stability), EPIC-006 (grade projection)
