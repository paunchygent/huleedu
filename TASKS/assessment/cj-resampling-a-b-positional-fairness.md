---
id: 'cj-resampling-a-b-positional-fairness'
title: 'CJ RESAMPLING A/B positional fairness'
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
labels: ['cj', 'resampling', 'fairness', 'llm-bias', 'eng5']
---
# CJ RESAMPLING A/B positional fairness

## Objective

Ensure RESAMPLING mode maintains fair A/B positional usage for essays across all resampling waves so that LLM-as-a-judge decisions are not systematically skewed by position bias.

## Context

- Current pair generation (`PairGenerationMode.RESAMPLING`) reuses existing comparison edges and randomizes essay order per pair (`_should_swap_positions`), but does not explicitly enforce positional fairness per essay across resampling waves.
- Empirical ENG5 experiments show that A/B position can influence win-rates by ~1–3 percentage points, which is non-trivial at scale and affects both statistics and analytics for large comparison tasks.
- PR‑7 introduced small-net Phase‑2 semantics and RESAMPLING mode for small nets; this story extends that work by:
  - Making A/B positional fairness an explicit requirement for RESAMPLING mode.
  - Providing observability and tests that guard against regressions.

Connects to:
- EPIC‑005: CJ Stability & Reliability.
- PR‑7: Phase‑2 resampling and convergence harness (`TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`).
-

## Plan

1. **Baseline analysis**
   - [ ] Quantify current A/B positional distributions in RESAMPLING mode using existing ENG5/LOWER5 traces (e.g. via a small analysis script or convergence harness extensions).
   - [ ] Document any observed skews for typical small-net and medium-sized batches.

2. **Design positional fairness strategy**
   - [ ] Define a target fairness notion for A/B positions (e.g. per essay, proportion of A vs B appearances stays within a configurable band over all comparisons).
   - [ ] Decide whether fairness is enforced:
     - Per resampling wave, or
     - Over cumulative comparisons (preferred).
   - [ ] Align this with the existing matching strategy abstractions so we do not duplicate logic.

3. **Implement fairness-aware RESAMPLING**
   - [ ] Extend `PairGenerationMode.RESAMPLING` path in `pair_generation.py` to:
     - [ ] Incorporate per-essay position counts into the scoring/selection process.
     - [ ] Ensure that, when randomization is applied (`_should_swap_positions`), the long-run distribution per essay approaches 50/50 A/B within a tolerable band.
   - [ ] Add configuration knobs if needed (e.g. max tolerated positional skew per essay) but keep sensible defaults for ENG5/LOWER5.

4. **Testing and observability**
   - [ ] Add unit tests (or extend existing ones) under `services/cj_assessment_service/tests/unit/test_pair_generation_context.py` to:
     - [ ] Simulate multiple RESAMPLING waves and assert that per-essay A/B counts remain within the configured fairness band.
   - [ ] Optionally extend `test_workflow_small_net_resampling.py` with a scenario that inspects persisted comparison pairs to validate positional fairness in a small-net setting.
   - [ ] Add basic logging in RESAMPLING mode (debug level) to help diagnose positional skew if tests fail.

5. **Docker/E2E validation (follow-up)**
   - [ ] Once ENG5 docker profiles are stable, add an integration test (or extend `test_eng5_mock_parity_lower5.py`) to:
     - [ ] Run at least one LOWER5 small-net batch through RESAMPLING.
     - [ ] Fetch comparison pairs from CJ and assert that A/B positional counts per essay do not diverge beyond the agreed tolerance.

## Success Criteria

- Unit tests demonstrate that across multiple RESAMPLING waves, each essay’s A/B positional count remains within the configured fairness band.
- For small nets (e.g. LOWER5) and representative ENG5 batches, positional skew (A vs B) per essay is empirically constrained to the agreed 1–3% band or better.
- No regressions are observed in existing PR‑7 small-net resampling tests or convergence harness behaviour.
- The implementation works transparently with existing matching strategies and does not require callers to be aware of positional fairness internals.

## Related

- EPIC‑005: `docs/product/epics/cj-stability-and-reliability-epic.md`
- PR‑7: `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`
- Mock provider parity: `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`
