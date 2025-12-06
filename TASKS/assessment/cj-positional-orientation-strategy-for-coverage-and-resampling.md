---
id: 'cj-positional-orientation-strategy-for-coverage-and-resampling'
title: 'CJ positional orientation strategy for coverage and resampling'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-06'
last_updated: '2025-12-06'
related: []
labels: []
---
# CJ positional orientation strategy for coverage and resampling

## Objective

Define and implement a simple, DI‑friendly positional orientation strategy for CJ pair generation that:

- Balances per‑essay A/B positional usage during COVERAGE.
- Ensures RESAMPLING uses pair‑history to present each unordered pair `{e1, e2}` in both AB and BA orientations where budget allows.
- Minimises LLM judge positional bias at the input level to BT scoring without overcomplicating continuation or matching logic.

## Context

- Current COVERAGE orientation chooses A/B positions via a 50/50 random swap (`_should_swap_positions`), with no memory of:
  - Per‑essay A/B usage.
  - Per‑pair orientation history.
- RESAMPLING mode today:
  - Selects from existing unordered pairs, but orientation is still random.
  - Does not guarantee that a pair observed as `(A=e1,B=e2)` in coverage will ever be seen as `(A=e2,B=e1)`.
- Psychometric goal:
  - LLM‑as‑judge may have systematic A/B bias.
  - The most robust mitigation is to ensure each unordered pair is judged from both positions, feeding “balanced” evidence into BT, and to keep per‑essay A/B usage roughly balanced across the batch.
- Architectural constraints:
  - We want the positional rules to be **configurable and swappable** via DI/settings (no touching core `pair_generation` or continuation logic when tuning behaviour).
  - Behaviour should be driven entirely by persisted `ComparisonPair` history and lightweight in‑memory aggregates.

This task refines the EPIC‑level US‑005.X requirements (“RESAMPLING A/B Positional Fairness and Mode Generalization”) into a concrete orientation‑strategy design and implementation plan.

## Plan

1. **Introduce orientation strategy protocol**
   - [ ] Add `PairOrientationStrategyProtocol` in the CJ core logic (e.g. `pair_orientation.py` or adjacent to `pair_generation.py`) with:
     - `choose_coverage_orientation(pair, per_essay_position_counts, rng) -> (essay_a, essay_b)`.
     - `choose_resampling_orientation(pair, per_pair_orientation_counts, rng) -> (essay_a, essay_b)`.
   - [ ] Add `PAIR_ORIENTATION_STRATEGY: str` to `CJ Assessment Settings` with a default name (e.g. `"fair_complement"`).
   - [ ] Wire a DI provider in `services/cj_assessment_service/di.py` that:
     - Resolves the configured strategy name.
     - Provides a `PairOrientationStrategyProtocol` instance to `pair_generation.generate_comparison_tasks`.

2. **Implement a single FairComplementOrientationStrategy**
   - [ ] Implement `FairComplementOrientationStrategy` that handles both COVERAGE and RESAMPLING:
     - COVERAGE:
       - Uses `per_essay_position_counts[essay_id] = (A_e, B_e)` derived from existing `ComparisonPair` rows.
       - For each new unordered pair `(e1, e2)`, orients essays such that the essay with higher `(A_e - B_e)` skew is more likely placed in B, and vice versa, with a deterministic tie‑breaker (e.g. essay ID).
     - RESAMPLING:
       - Uses `per_pair_orientation_counts[(id_lo,id_hi)] = (count_AB, count_BA)` built from existing `ComparisonPair` rows.
       - For each unordered pair:
         - If only AB seen → orient BA.
         - If only BA seen → orient AB.
         - If both AB and BA seen → fall back to the same essay‑level skew rule or a simple deterministic default.
   - [ ] Ensure the implementation remains **pure and side‑effect free** aside from consuming counts and emitting orientation decisions (no DB access inside strategy).

3. **Integrate strategy into COVERAGE path**
   - [ ] In `generate_comparison_tasks(..., mode=COVERAGE)`:
     - Keep existing matching logic for unordered pair selection.
     - Before building `ComparisonTask`s:
       - Compute `per_essay_position_counts` once for the batch using a small helper and the current DB session (`ComparisonPair` counts for A and B positions).
       - For each unordered pair `(essay_a, essay_b)`, call `orientation_strategy.choose_coverage_orientation(...)` and use the returned `(A,B)` order.
   - [ ] Maintain current coverage invariants:
     - No unordered pair duplicates within a batch.
     - Each essay appears at most once per wave (modulo odd essay handling).
     - Caps/budgets unchanged.

4. **Integrate strategy into RESAMPLING path**
   - [ ] In `generate_comparison_tasks(..., mode=RESAMPLING)`:
     - Keep existing candidate selection (based on `existing_pairs` and `comparison_counts`), or wrap it behind a small `ResamplingSelectionStrategyProtocol` if needed for clarity.
     - Before orientation:
       - Build `per_pair_orientation_counts` for unordered pairs based on the current `ComparisonPair` rows.
       - For each selected unordered pair `(essay_a, essay_b)`, call `orientation_strategy.choose_resampling_orientation(...)` and use the returned `(A,B)` order.
   - [ ] Confirm integration with:
     - Small‑net resampling caps (`MAX_RESAMPLING_PASSES_FOR_SMALL_NET`).
     - Regular‑batch resampling caps (`MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH`).
     - Existing continuation predicates.

5. **Update and extend tests**
   - [ ] Unit tests:
     - Extend `test_pair_generation_context.py` to simulate multiple COVERAGE waves and assert per‑essay A/B counts move toward balanced usage (`skew_e` within a generous band).
     - Extend RESAMPLING tests to confirm:
       - For a pair seen only in one orientation in COVERAGE, the first RESAMPLING wave flips orientation deterministically.
       - Subsequent RESAMPLING waves do not break convergence or existing CJ semantics.
   - [ ] Integration tests (follow‑up, coordinated with related tasks):
     - Use the ENG5 LOWER5 docker harness to:
       - Compute per‑essay A/B positional counts via the positional helper.
       - Soft‑assert that skew remains within a target band once orientation strategy is active (exact thresholds to be calibrated against real traces).

6. **Document behaviour and configuration**
   - [ ] Update `docs/product/epics/cj-stability-and-reliability-epic.md` (already partially done) to describe:
     - Pair‑level complement in RESAMPLING.
     - Essay‑level A/B balancing in COVERAGE via an injected orientation strategy.
   - [ ] Update `docs/operations/cj-assessment-runbook.md` to:
     - Explain `PAIR_ORIENTATION_STRATEGY` and its effect on coverage/resampling.
     - Clarify that random orientation is no longer the default and that positional fairness is intentional.

## Success Criteria

- Orientation logic is fully encapsulated in `PairOrientationStrategyProtocol` and implemented by a single `FairComplementOrientationStrategy` that serves both COVERAGE and RESAMPLING.
- COVERAGE mode:
  - Continues to satisfy existing coverage and budget invariants.
  - Demonstrably reduces per‑essay A/B positional skew over multiple waves in unit tests.
- RESAMPLING mode:
  - Ensures that, when budget and caps allow, each unordered pair `{e1,e2}` is observed in both AB and BA orientations at least once.
  - Works correctly for both small nets and regular nets under existing resampling caps.
- No regressions in PR‑2/PR‑7 semantics or ENG5 LOWER5 docker harness behaviour; new docker tests (or extensions) validate positional fairness in real scenarios.
- Configuration of positional behaviour is done via settings/DI only; no core CJ workflow or matching logic needs to be edited to swap strategies.

## Related

- EPIC: `docs/product/epics/cj-stability-and-reliability-epic.md` (US‑005.X positional fairness and mode generalization).
- Tasks:
  - `TASKS/assessment/cj-resampling-a-b-positional-fairness.md`
  - `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md`
  - `TASKS/assessment/us-0051-callback-driven-continuation-and-safe-completion-gating.md`
  - `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`
