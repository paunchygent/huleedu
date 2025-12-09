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
   - [x] Clarify desired semantics of RESAMPLING for:
     - [x] Small nets (e.g. LOWER5: 5–10 essays).
       - Completed coverage is an invariant for small nets when budget allows:
         `unique_coverage_complete is True` and `successful_pairs_count == max_possible_pairs`
         at finalization.
       - Phase‑2 RESAMPLING is allowed only when `is_small_net is True`,
         `unique_coverage_complete is True`, success‑rate gates pass, and budget remains.
       - For ENG5 LOWER5 in docker (5 essays), the reference path is:
         10 coverage pairs + `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` resampling passes
         (currently 3) → `total_comparisons ≈ 40`, `failed_comparisons == 0`,
         `success_rate == 1.0`.
     - [x] Regular/larger batches (e.g. 20–30+ essays).
       - For regular nets we do **not** require complete coverage before finalization;
         instead, we target a “high but configurable” coverage band plus a small number
         of RESAMPLING passes when stability still has not passed.
       - A future `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` cap must be strictly
         ≤ `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` so that large nets cannot consume
         disproportionate budget via Phase‑2.
       - RESAMPLING for regular nets should only be considered once:
         `callbacks_received > 0`, success‑rate gates pass, sufficient budget remains,
         and either
           - `successful_pairs_count` exceeds a configurable fraction of
             `max_possible_pairs` (e.g. 60–80%), or
           - a minimum number of stability iterations has been attempted.
   - [ ] Decide whether non-small nets:
     - [x] Use RESAMPLING only after some minimum coverage and/or stability attempts, or
     - [ ] Can mix COVERAGE and RESAMPLING in a more flexible pattern (e.g. occasional resampling waves).
   - [x] Define separate configuration knobs:
     - [x] `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` (existing).
     - [x] `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (new).
     - [ ] Optional: per-batch overrides via `batch_config_overrides`.
   - [ ] Use the ENG5 LOWER5 small‑net docker configuration as the baseline reference for small‑net behaviour:
     - [x] `MIN_RESAMPLING_NET_SIZE=5` and `expected_essay_count <= MIN_RESAMPLING_NET_SIZE` → small net.
     - [x] Coverage semantics pinned by docker: `max_possible_pairs == successful_pairs_count == 10`, `unique_coverage_complete is True` for 5‑essay LOWER5.
     - [x] Phase‑2 resampling semantics pinned by docker: `resampling_pass_count` reaches the configured small‑net cap (currently 3) with `total_comparisons ≈ 40`, `failed_comparisons == 0`, and `success_rate == 1.0`.

2. **Orchestration changes**
   - [x] Update `_can_attempt_small_net_resampling(ctx)` or introduce a more general predicate (e.g. `_can_attempt_resampling(ctx)`) that:
     - [x] Retains current small-net semantics when `is_small_net` is true.
     - [x] Adds a general-resampling branch for larger batches, gated by:
       - [x] `callbacks_received > 0` and not failing on success rate.
       - [x] Sufficient budget remaining.
       - [x] A configurable max resampling pass cap for regular batches.
   - [x] Adjust `workflow_continuation.trigger_existing_workflow_continuation` so that:
     - [x] Small nets continue to use the existing small-net resampling caps.
     - [x] Larger nets can enter RESAMPLING mode under well-defined conditions, before falling back to `REQUEST_MORE_COMPARISONS` / `FINALIZE_SCORING`.

3. **Configuration & settings**
   - [x] Add new settings to `services/cj_assessment_service/config.py`:
     - [x] `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (with a sensible default, e.g. 0 or 1).
   - [x] Ensure these settings are documented in:
     - [x] `docs/operations/cj-assessment-runbook.md`.
     - [x] CJ Stability & Reliability epic.
   - [ ] Consider exposing per-program or per-pipeline defaults for ENG5 vs generic CJ.

4. **Testing**
   - [x] Extend unit tests in `services/cj_assessment_service/tests/unit/test_workflow_small_net_resampling.py` or add a new test module to cover:
     - [x] RESAMPLING invoked for a non-small-net batch once certain conditions are met (e.g. coverage threshold, iterations, or budget state).
     - [x] Respect for `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (no more than N resampling passes).
   - [x] Add unit tests in `test_pair_generation_context.py` to confirm RESAMPLING remains fair and budget-aware for larger nets.

5. **Docker/E2E validation (follow-up)**
   - [ ] After unit semantics are stable, add or extend functional/docker tests (potentially a second test in `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py` or the `test_cj_regular_batch_resampling_docker.py` skeleton in `tests/functional/cj_eng5/`) to:
     - [x] Sketch a realistic CJ regular‑batch scenario under ENG5 or generic CJ configuration in a new docker test module that reuses the LOWER5 helpers.
     - [ ] Run the regular‑batch scenario once RESAMPLING orchestration for non-small nets is implemented and stabilised under docker.
     - [ ] Verify that:
       - [ ] RESAMPLING is invoked at least once (e.g. via metadata, counts, or metrics).
       - [ ] The batch still finalizes correctly when caps or stability conditions are met.
   - Note: a LOWER5-focused small-net continuation harness already exists in `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`; it is structured to be net-size agnostic so that regular-batch RESAMPLING tests can reuse the same helpers once the generalized settings and orchestration changes are in place. As of 2025‑12‑06, this harness verifies:
     - Small‑net classification for 5‑essay ENG5 LOWER5 batches (`expected_essay_count <= MIN_RESAMPLING_NET_SIZE`).
     - Coverage metadata (`max_possible_pairs == successful_pairs_count == 10`, `unique_coverage_complete is True`).
     - Phase‑2 small‑net resampling hitting the configured cap (`resampling_pass_count == MAX_RESAMPLING_PASSES_FOR_SMALL_NET`, `total_comparisons ≈ 40`) and finalization via `FINALIZE_SCORING` with `success_rate == 1.0` and `failed_comparisons == 0`.
   - Design sketch (2025‑12‑06): `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py`
     outlines a future regular‑batch docker test using:
     - `expected_essay_count ≈ 24` (so `is_small_net is False` under default thresholds).
     - The shared `_wait_for_cj_batch_final_state(...)` helper to assert completion.
     - Parameterised expectations for `total_comparisons`, coverage metadata, and
       `resampling_pass_count <= MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` once that
       setting and orchestration branch exist.

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
