---
id: 'cj-resampling-mode-generalization-for-all-batch-sizes'
title: 'CJ RESAMPLING mode generalization for all batch sizes'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-06'
last_updated: '2025-12-06'
related: ['EPIC-005', 'pr-7-phase-2-resampling-and-convergence-harness']
labels: ['cj', 'resampling', 'continuation', 'eng5', 'llm-provider']
---
# CJ RESAMPLING mode generalization for all batch sizes

## Objective

Generalize `PairGenerationMode.RESAMPLING` from “small-net only” orchestration to a first-class continuation tool for all batch sizes, with independent configuration knobs for small nets vs regular batches.

## Context

- PR‑7 introduced Phase‑2 small-net resampling semantics and wired RESAMPLING mode only via `_can_attempt_small_net_resampling(ctx)` in `workflow_continuation.trigger_existing_workflow_continuation`.
- In the current orchestration, RESAMPLING is only reachable when `ContinuationContext.is_small_net` is true and `unique_coverage_complete` is true; large/regular batches never enter RESAMPLING mode even when additional comparisons would help stability.
- We expect RESAMPLING to be useful for:
  - Small nets (LOWER5, small classroom batches) where complete coverage is cheap, and a few extra passes improve stability.
  - Larger nets where targeted resampling of under-sampled pairs can improve fairness and convergence without exploding budget.
- Today, the resampling cap is tied to small-net settings (`MAX_RESAMPLING_PASSES_FOR_SMALL_NET`); this is too rigid when we want different behaviour for small vs regular batches.

Connects to:
- EPIC‑005: CJ Stability & Reliability.
- PR‑7: `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`.

## Plan

1. **Requirements & design**
   - [ ] Clarify desired semantics of RESAMPLING for:
     - [ ] Small nets (e.g. LOWER5: 5–10 essays).
     - [ ] Regular/larger batches (30+ essays).
   - [ ] Decide whether non-small nets:
     - [ ] Use RESAMPLING only after some minimum coverage and/or stability attempts, or
     - [ ] Can mix COVERAGE and RESAMPLING in a more flexible pattern (e.g. occasional resampling waves).
   - [ ] Define separate configuration knobs:
     - [ ] `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` (existing).
     - [ ] `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (new).
     - [ ] Optional: per-batch overrides via `batch_config_overrides`.

2. **Orchestration changes**
   - [ ] Update `_can_attempt_small_net_resampling(ctx)` or introduce a more general predicate (e.g. `_can_attempt_resampling(ctx)`) that:
     - [ ] Retains current small-net semantics when `is_small_net` is true.
     - [ ] Adds a general-resampling branch for larger batches, gated by:
       - [ ] `callbacks_received > 0` and not failing on success rate.
       - [ ] Sufficient budget remaining.
       - [ ] A configurable max resampling pass cap for regular batches.
   - [ ] Adjust `workflow_continuation.trigger_existing_workflow_continuation` so that:
     - [ ] Small nets continue to use the existing small-net resampling caps.
     - [ ] Larger nets can enter RESAMPLING mode under well-defined conditions, before falling back to `REQUEST_MORE_COMPARISONS` / `FINALIZE_SCORING`.

3. **Configuration & settings**
   - [ ] Add new settings to `services/cj_assessment_service/config.py`:
     - [ ] `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (with a sensible default, e.g. 0 or 1).
   - [ ] Ensure these settings are documented in:
     - [ ] `docs/operations/cj-assessment-runbook.md`.
     - [ ] CJ Stability & Reliability epic.
   - [ ] Consider exposing per-program or per-pipeline defaults for ENG5 vs generic CJ.

4. **Testing**
   - [ ] Extend unit tests in `services/cj_assessment_service/tests/unit/test_workflow_small_net_resampling.py` or add a new test module to cover:
     - [ ] RESAMPLING invoked for a non-small-net batch once certain conditions are met (e.g. coverage threshold, iterations, or budget state).
     - [ ] Respect for `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (no more than N resampling passes).
   - [ ] Add unit tests in `test_pair_generation_context.py` to confirm RESAMPLING remains fair and budget-aware for larger nets.

5. **Docker/E2E validation (follow-up)**
   - [ ] After unit semantics are stable, add or extend integration tests (potentially a second test in `tests/integration/test_cj_small_net_continuation_docker.py` or a new `test_cj_regular_batch_resampling_docker.py`) to:
     - [ ] Run a realistic CJ batch (non-small-net) under ENG5 or generic CJ configuration.
     - [ ] Verify that:
       - [ ] RESAMPLING is invoked at least once (e.g. via metadata, counts, or metrics).
       - [ ] The batch still finalizes correctly when caps or stability conditions are met.
   - Note: a LOWER5-focused small-net continuation harness already exists in `tests/integration/test_cj_small_net_continuation_docker.py`; it is structured to be net-size agnostic so that regular-batch RESAMPLING tests can reuse the same helpers once the generalized settings and orchestration changes are in place.

## Success Criteria

- RESAMPLING mode is no longer limited to small nets in orchestration; larger batches can use RESAMPLING under controlled conditions.
- Separate configuration knobs exist for small nets vs regular batches, allowing tuning in production without conflating the two regimes.
- Unit tests cover RESAMPLING behaviour for both small and regular nets (including caps and basic fairness).
- Docker/E2E tests (ENG5 and/or generic CJ) demonstrate that:
  - RESAMPLING is exercised on non-small-net batches.
  - Finalization semantics (stability vs caps vs budget) remain correct.

## Related

- EPIC‑005: `docs/product/epics/cj-stability-and-reliability-epic.md`
- PR‑7: `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`
- Mock provider parity: `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`
