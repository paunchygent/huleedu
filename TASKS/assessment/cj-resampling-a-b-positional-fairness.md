---
id: 'cj-resampling-a-b-positional-fairness'
title: 'CJ RESAMPLING A/B positional fairness'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-06'
last_updated: '2025-12-07'
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
   - [ ] Use the new ENG5 LOWER5 docker small‑net continuation path (5 essays, small-net resampling to cap with `total_comparisons ≈ 40`) as one of the primary empirical baselines for positional usage under RESAMPLING.
   - [x] Treat the LOWER5 docker harness as the initial “shape” for fairness diagnostics: 5 essays, 10 coverage pairs, 3 resampling passes, ~40 total comparisons with deterministic CJ/LPS mock profiles.

2. **Design positional fairness strategy**
   - [x] Define a target fairness notion for A/B positions (e.g. per essay, proportion of A vs B appearances stays within a configurable band over all comparisons).
     - For each essay `e`, let `A_e` and `B_e` denote the number of times `e`
       appears in positions A and B, respectively, across all comparisons in
       a batch. Define positional skew
       `skew_e = |A_e - B_e| / (A_e + B_e)` (0 → perfectly balanced).
     - For LOWER5 small nets (5 essays, 40 total comparisons), aim for
       `skew_e <= 0.25` (i.e. per‑essay A/B counts within a ±25% band) as an
       initial docker guardrail, to be refined once empirical distributions
       from traces are available.
     - For larger nets, the same definition applies, but acceptable skew
       bands can be tighter thanks to higher sample sizes; the band should be
       configurable via settings or test parameters.
   - [x] Decide whether fairness is enforced:
     - Over cumulative comparisons for the batch (preferred); per‑wave
       fairness may be used as a diagnostic but not a hard requirement.
   - [ ] Align this with the existing matching strategy abstractions so we do not duplicate logic.

3. **Implement fairness-aware RESAMPLING**
   - [x] Extend `PairGenerationMode.RESAMPLING` path in `pair_generation.py` to:
     - [x] Incorporate per-essay position counts into the scoring/selection process (via participation cap and randomized tie-breaker).
     - [x] Ensure that, when randomization is applied, the long-run distribution per essay approaches 50/50 A/B within a tolerable band (achieved via `FairComplementOrientationStrategy`).
   - [x] Add configuration knobs if needed (sensible defaults: `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH`, participation cap formula).
   - [x] Implement a helper to compute per‑essay A/B positional counts for a CJ batch (test-side only for now):
     - Helper shape (test‑ and repository‑friendly):
       - `async def get_positional_counts_for_batch(session: AsyncSession, cj_batch_id: int) -> dict[str, dict[str, int]]`
       - Returns a mapping: `{essay_id: {"A": count_as_A, "B": count_as_B}}`.
     - Implementation:
       - Live in `services/cj_assessment_service/tests/helpers/positional_fairness.py`.
       - Queries `ComparisonPair` rows for the given `cj_batch_id`.
       - Groups by `essay_a_els_id` and `essay_b_els_id` separately to derive
         counts per position using SQLAlchemy aggregation (no raw SQL).
       - Normalises into the `{essay_id: {"A": ..., "B": ...}}` structure.
     - Ownership options:
       - Starts as a small, pure helper in CJ tests to avoid changing service
         code while diagnostics are experimental.
       - Can be promoted to `CJComparisonRepositoryProtocol` later (e.g.
         `get_positional_counts_for_batch(...)`) if service‑level metrics or
         observability endpoints need the same data.

4. **Testing and observability**
   - [x] Add unit tests (or extend existing ones) under `services/cj_assessment_service/tests/unit/test_pair_generation_context.py` to:
     - [x] Simulate multiple RESAMPLING waves and assert that per-essay A/B counts remain within a configurable fairness band (currently a generous `MAX_ALLOWED_SKEW=0.5` for a 3‑essay synthetic net; to be tightened once ENG5/LOWER5 trace data is analysed).
   - [ ] Optionally extend `test_workflow_small_net_resampling.py` with a scenario that inspects persisted comparison pairs to validate positional fairness in a small-net setting.
   - [ ] Add basic logging in RESAMPLING mode (debug level) to help diagnose positional skew if tests fail.
   - [x] Implement LOWER5 docker‑level fairness check in `test_cj_small_net_continuation_docker.py`:
     - [x] Added `test_lower5_positional_fairness_after_continuation` test method.
     - [x] Uses `eng5_lower5_gpt51_low` mock profile.
     - [x] Queries `ComparisonPair` via `get_positional_counts_for_batch()` helper.
     - [x] Computes `skew_e = |A_e - B_e| / (A_e + B_e)` per essay.
     - [x] Asserts `skew_e <= MAX_ALLOWED_SKEW` (0.5 initial threshold).
     - [x] Asserts each essay appears in both A and B positions.

5. **Docker/E2E validation (follow-up)**
   - [x] LOWER5 small-net positional fairness harness implemented:
     - [x] `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py::test_lower5_positional_fairness_after_continuation`
     - [x] Gates on `eng5_lower5_gpt51_low` mock profile.
     - [x] Uses `MAX_ALLOWED_SKEW=0.5` (to be tightened based on empirical data).
     - [x] Per-pair complement assertions (resampled pairs have AB + BA).
   - [x] Regular-batch (24 essays) positional fairness harness implemented:
     - [x] `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py::test_cj_regular_batch_resampling_metadata_completed_successful`
     - [x] Gates on `cj_generic_batch` mock profile.
     - [x] Validates PR-2/PR-7 invariants + resampling cap for regular batches.
     - [x] Includes positional fairness assertions with same `MAX_ALLOWED_SKEW=0.5` threshold.
     - [x] Per-pair complement assertions (resampled pairs have AB + BA).
   - [x] Helper extended for per-pair orientation counts:
     - [x] `get_pair_orientation_counts_for_batch()` added to `positional_fairness.py`.
     - [x] Returns `{(min_id, max_id): (AB_count, BA_count)}` for complement validation.
   - [x] Mock profile marker and helper script:
     - [x] Added `@pytest.mark.mock_profile(profile)` marker for profile-dependent tests.
     - [x] Updated `pdm run llm-mock-profile` to support CJ continuation/fairness tests.
     - [x] Tests skip gracefully if wrong profile is active.
   - [x] Tighten skew thresholds based on empirical distribution data:
     - [x] LOWER5: `MAX_ALLOWED_SKEW = 0.1` (achieves 0% skew)
     - [x] Regular batch: `MAX_ALLOWED_SKEW = 0.2` (achieves ~0.17 max skew)

6. **Incremental Position Counting Fix (2025-12-06)**
   - **Root cause identified**: `pair_generation.py` fetched position counts once per wave, then used stale data for all pair decisions within that wave
   - **Fix**: Track planned assignments locally within each wave, updating counts after each orientation decision
   - **File modified**: `services/cj_assessment_service/cj_core_logic/pair_generation.py:276-346`
   - **Result**: Perfect 0% skew achieved (was 12.5%)

7. **Regular-Batch Participation Cap Fix (2025-12-06)**
   - **Root cause identified**: RESAMPLING selection used lexicographic tie-breaker, causing systematic ID bias
   - **Fix components**:
     1. Randomized tie-breaker in RESAMPLING selection (`pair_generation.py:231-237`)
     2. Per-essay participation cap (`pair_generation.py:257-279`) ensures each essay appears at most once per RESAMPLING wave
     3. Full coverage threshold (1.0) before RESAMPLING triggers (`workflow_decision.py:419`)
   - **Result**: All 24 essays achieve exactly 24 participation (23 COVERAGE + 1 RESAMPLING)
   - **Max skew**: 0.167 (natural A/B orientation variance, not participation imbalance)

8. **Empirical Results (2025-12-06)**
   - LOWER5 (5 essays, 40 comparisons, 3 resampling passes):
     - Before fix: `max_observed_skew: 0.125` (12.5% deviation)
     - After fix: `max_observed_skew: 0.0` (perfect balance)
     - All essays: A=8, B=8 (perfect 50/50 split)
     - `resampled_pair_count: 10` (all pairs resampled)
     - `pairs_missing_complement: 0` (all pairs have AB + BA)
   - Regular batch (24 essays, 288 comparisons, 1 resampling pass):
     - Before fix: `max_observed_skew: 0.13` (13%), participation 23-27 per essay
     - After fix: `max_observed_skew: 0.167` (17%), participation exactly 24 per essay
     - `resampled_pair_count: 12` (budget-constrained)
     - `pairs_missing_complement: 0` (all resampled pairs have AB + BA)

9. **Full Complement Coverage Validation (2025-12-07)**
   - **Root cause of 16.7% skew**: Incomplete resampling (12/276 pairs = 4.3%)
   - **Hypothesis**: With full complement coverage, skew should approach 0%
   - **Test configuration**: `MAX_PAIRWISE_COMPARISONS=552` (276 COVERAGE + 276 RESAMPLING)
   - **Results** (24 essays, 552 comparisons, 1 resampling pass):
     - `max_observed_skew: 0.0` (perfect balance)
     - All essays: A=23, B=23, total=46 (perfect 50/50 split)
     - `resampled_pair_count: 276` (100% of pairs resampled)
     - `pairs_missing_complement: 0` (all pairs have AB + BA)
   - **Conclusion**: The `FairComplementOrientationStrategy` achieves 0% skew when all pairs
     receive complement coverage. The 16.7% skew with budget=288 was from incomplete
     resampling (greedy orientation on 4.3% of pairs), not an algorithm defect.

10. **Per-Mode Observability Column (2025-12-07)**
   - **Purpose**: Enable filtering positional fairness diagnostics by pair generation mode (COVERAGE vs RESAMPLING)
   - **Schema change**:
     - Added `pair_generation_mode` column to `ComparisonPair` model (`models_db.py:210-216`)
     - Type: `String(20)`, nullable, indexed
     - Values: `"coverage"` (Phase-1) or `"resampling"` (Phase-2)
   - **Migration**:
     - File: `alembic/versions/20251207_0136_2ea57f0f8b9d_add_pair_generation_mode_to_comparison_.py`
     - Adds column and creates index `ix_cj_comparison_pairs_pair_generation_mode`
   - **Write path**:
     - `create_tracking_records()` now accepts `pair_generation_mode` parameter
     - Threaded through: `submit_batch_chunk()` → `batch_processor.submit_comparison_batch()` → `orchestrator.submit_initial_batch()`
     - Default: `"coverage"` when mode is None
   - **Test helpers extended**:
     - `get_positional_counts_for_batch(session, cj_batch_id, mode=None)` - optional mode filter
     - `get_pair_orientation_counts_for_batch(session, cj_batch_id, mode=None)` - optional mode filter
     - `get_positional_fairness_report(session, cj_batch_id, mode=None)` - includes mode in report
   - **Migration test**: `test_pair_generation_mode_migration.py` (6 tests covering column type, nullability, index, valid values, idempotency)
   - **Unit tests**: 2 new tests in `test_positional_fairness_helper.py` for mode filtering
   - **Ancillary fix**: Added `__table_args__` to `EventOutbox` model to fix drift with `idx_outbox_unique_unpublished` index

## Success Criteria

- Unit tests demonstrate that across multiple RESAMPLING waves, each essay’s A/B positional count remains within the configured fairness band.
- For small nets (e.g. LOWER5) and representative ENG5 batches, positional skew (A vs B) per essay is empirically constrained to the agreed 1–3% band or better.
- No regressions are observed in existing PR‑7 small-net resampling tests or convergence harness behaviour.
- The implementation works transparently with existing matching strategies and does not require callers to be aware of positional fairness internals.

## Related

- EPIC‑005: `docs/product/epics/cj-stability-and-reliability-epic.md`
- PR‑7: `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md`
- Mock provider parity: `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`
