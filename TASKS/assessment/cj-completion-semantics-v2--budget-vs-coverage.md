---
id: 'cj-completion-semantics-v2--budget-vs-coverage'
title: 'CJ completion semantics v2 – budget vs coverage'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-02'
last_updated: '2025-12-02'
related: []
labels: []
---
# CJ completion semantics v2 – budget vs coverage

## Objective

Define and implement a simplified, budget-first completion model for CJ
Assessment where `CJBatchState.total_budget` is the single source of truth for
`completion_denominator()`, and small-net coverage (`nC2`) is handled via
explicit metadata instead of being entangled with the denominator. This task
owns the core service semantics and ADR; ENG5/LOWER5 and reasoning-plumbing
stories build on this work.

## Context

Current completion semantics use:

```python
completion_denominator = min(
    total_budget or total_comparisons,
    nC2(actual_processed_essays),
)
```

This made sense when CJ had no explicit small-net metadata, but it creates
pathological behaviour for small nets with explicit budgets (e.g. LOWER5:
`n=5`, budget=60, but denominator=10) and obscures the config story (global
budget + per-request override). We now have:

- Global/default budget: `Settings.MAX_PAIRWISE_COMPARISONS`.
- Per-request overrides: `comparison_budget.max_pairs_requested`.
- Small-net metadata: `max_possible_pairs`, `successful_pairs_count`,
  `unique_coverage_complete`, `resampling_pass_count`,
  `small_net_resampling_cap`.

The agreed mental model (see ADR-0020
`docs/decisions/0020-cj-assessment-completion-semantics-v2.md`) is:

- `total_budget` is mandatory for real batches and drives completion math.
- `completion_denominator()` should simply return `total_budget`.
- `nC2` is used for coverage and small-net semantics, not as a cap.

This story formalizes and implements that model in CJ core logic and docs.

## Plan

- Confirm all CJ batch creation paths:
  - Identify where `CJBatchState` is created/updated (e.g. batch preparation,
    request normalization).
  - Ensure `total_budget` is set for every real batch as:
    - `comparison_budget.max_pairs_requested` if provided, else
    - `Settings.MAX_PAIRWISE_COMPARISONS`.
- Update `CJBatchState.completion_denominator()` in
  `services/cj_assessment_service/models_db.py` to:
  - Return `total_budget` directly.
  - Raise/log a hard error if `total_budget` is missing or non-positive in
    production code paths (fixtures/tests must set it explicitly).
- Ensure `_max_possible_comparisons()` and `max_possible_pairs` are only used:
  - As coverage metadata for small nets.
  - In diagnostics and convergence harnesses (not in denominator math).
- Adjust continuation and completion helpers to treat denominator as budget:
  - `workflow_continuation._build_continuation_context(...)`:
    - Carry both `denominator` (budget_cap) and `max_possible_pairs`
      (coverage_cap).
  - `batch_completion_checker`, `batch_completion_policy`,
    `batch_monitor`:
    - Confirm they interpret denominator as budget, not min(budget, nC2).
- Update documentation to reflect the new model:
  - `docs/architecture/cj-assessment-service-map.md`.
  - `docs/operations/cj-assessment-runbook.md`.
  - `docs/product/epics/cj-stability-and-reliability-epic.md`.
  - Cross-link ADR-0020 where completion semantics are described.
- Update and extend tests:
  - Fix unit/integration tests that assert `min(total_budget, nC2)` semantics
    (e.g. `test_completion_threshold.py`, workflow continuation and monitor
    tests).
  - Add targeted tests asserting:
    - Batches without `total_budget` are rejected in core paths.
    - Large-net behaviour remains budget-driven and stable.

## Success Criteria

- [ ] All real CJ batches have `CJBatchState.total_budget > 0` set at creation
      time; missing/zero budget is treated as a bug in code and tests.
- [ ] `completion_denominator()` returns `total_budget` only; there is no
      remaining `min(..., nC2)` logic in the codebase.
- [ ] `_max_possible_comparisons()` / `max_possible_pairs` are used only for
      coverage/small-net metadata and diagnostics, not in denominator math.
- [ ] Updated docs (architecture map, runbook, stability epic) reflect the v2
      semantics and reference ADR-0020.
- [ ] CJ unit + integration tests are updated and green, with at least one
      explicit test asserting the new denominator semantics.

## Related

- ADR-0020 `docs/decisions/0020-cj-assessment-completion-semantics-v2.md`
- `TASKS/assessment/cj-batch-state-and-completion-fixes.md`
- `TASKS/assessment/us-0051-callback-driven-continuation-and-safe-completion-gating.md`
- `TASKS/assessment/us-00ya-workflow-continuation-refactor--phase-6.md`
