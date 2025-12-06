# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks,
architectural decisions, and patterns live in:

- **README_FIRST.md** – Architectural overview, decisions, service status
- **Service READMEs** – Service-specific patterns, error handling, testing
- **.claude/rules/** – Implementation standards and requirements
- **docs/operations/** – Operational runbooks
- **TASKS/** – Detailed task documentation

Use this file to coordinate what the very next agent should focus on.

---

## 🎯 ACTIVE WORK (2025-12-06)

### Session Summary: DB Integration Test for Per-Pair Orientation Counts

**Current session (continued from prior context compaction):**

| Item | Status |
|------|--------|
| `test_pair_generation_orientation_counts.py` | ✅ Created (7 tests, all pass) |
| typecheck-all | ✅ 1382 source files, no errors |
| CJ service test suite | ⚠️ 747 passed, 3 failed (pre-existing) |

**Test file created:** `services/cj_assessment_service/tests/unit/test_pair_generation_orientation_counts.py`
- Tests `_fetch_per_pair_orientation_counts()` helper against real PostgreSQL (testcontainers)
- Validates AB/BA orientation counting semantics:
  - AB count = times lower-ID essay was in A position
  - BA count = times higher-ID essay was in A position
- Parametrized tests for only-AB, only-BA, mixed orientations
- UUID-format ID test to catch sorting edge cases
- Rule 075/070 compliant: <500 LoC, testcontainers, parametrized

**Integration test failures fixed this session:**

| Test | Root Cause | Fix Applied |
|------|-----------|-------------|
| `test_anchor_positions_are_balanced_in_db` | `_deterministic_fallback` used ID ordering instead of RNG, causing systematic bias | Renamed to `_random_fallback`, now uses RNG for true 50/50 |
| `test_full_batch_lifecycle_with_real_database` | `MagicMock()` without spec/side_effect | Added `spec=PairOrientationStrategyProtocol` + `side_effect` |
| `test_all_failed_comparisons_move_batch_to_error_state` | Same MagicMock issue | Same fix |

**Files modified:**
- `services/cj_assessment_service/cj_core_logic/pair_orientation.py` - `_deterministic_fallback` → `_random_fallback`
- `services/cj_assessment_service/tests/integration/test_real_database_integration.py` - Added import + mock configuration
- `services/cj_assessment_service/tests/unit/test_pair_orientation_strategy.py` - Renamed test + added RNG verification test
- `services/cj_assessment_service/tests/integration/test_llm_payload_construction_integration.py` - Updated assertions to accept any orientation

**Validation:**
- `pdm run typecheck-all`: 1382 source files, no errors
- `pdm run pytest-root services/cj_assessment_service/tests/`: 751 passed, 2 skipped

### Prior Session Summary: CJ Positional Orientation Strategy - Code Review & Fixes

**Commits created prior session:**

| Commit | Type | Description |
|--------|------|-------------|
| `3cd39b0a` | chore | Remove obsolete `task_frontmatter_schema.py` reference |
| `5b04f533` | feat | Add `PairOrientationStrategy` layer (protocol, impl, DI, config) |
| `e2e2f7cc` | feat | Integrate orientation strategy into pair generation |
| `59819b1a` | feat | Generalize RESAMPLING for regular (non-small) batches |
| `0dd4c3e1` | test | Add positional fairness helper for A/B count analysis |
| `8185b384` | test | Expand docker integration tests for continuation and resampling |
| `cb2fc240` | docs | Update CJ task tracking and runbooks for orientation strategy |
| `109c2a01` | fix | Complete orientation_strategy DI wiring and fix argument order |

**Code review findings (all resolved in commit `109c2a01`):**
- Fixed incomplete DI wiring where `orientation_strategy` wasn't threaded through all call paths
- Fixed argument order in `event_processor.py` (grade_projector must come before orientation_strategy)
- Updated 21 files including all affected test files to include `mock_orientation_strategy` fixture
- Added inline comment explaining the combined_skew formula in `pair_orientation.py:61-65`
- `pdm run typecheck-all` passes with no errors (1381→1382 source files after test addition)

---

### CJ Assessment Positional Orientation Strategy Details

- CJ Assessment positional orientation strategy for COVERAGE and RESAMPLING:

  - Current state:
    - Orientation strategy layer:
      - `PairOrientationStrategyProtocol` defined in `services/cj_assessment_service/protocols.py` with:
        - `choose_coverage_orientation(pair, per_essay_position_counts, rng)`.
        - `choose_resampling_orientation(pair, per_pair_orientation_counts, per_essay_position_counts, rng)`.
      - Concrete implementation `FairComplementOrientationStrategy` in
        `services/cj_assessment_service/cj_core_logic/pair_orientation.py`.
      - New setting `PAIR_ORIENTATION_STRATEGY` (default `"fair_complement"`) and existing
        `PAIR_GENERATION_SEED` together control deterministic behaviour in tests vs
        unbiased behaviour in production.
      - DI wiring:
        - `provide_pair_orientation_strategy` in `services/cj_assessment_service/di.py`
          exposes a `PairOrientationStrategyProtocol` instance.
        - `ComparisonBatchOrchestrator` now receives `orientation_strategy` and passes it
          into `pair_generation.generate_comparison_tasks`.
        - `comparison_processing.submit_comparisons_for_async_processing` and
          `request_additional_comparisons_for_batch` accept an optional
          `orientation_strategy`; when omitted, they construct a default
          `FairComplementOrientationStrategy`, preserving backwards compatibility while
          allowing DI to override behaviour.
    - COVERAGE integration:
      - `generate_comparison_tasks(..., mode=COVERAGE)`:
        - Preserves existing matching behaviour (duplicate avoidance, per-wave
          participation, budget caps).
        - Computes per-essay A/B counts via `_fetch_per_essay_position_counts(...)` using
          `ComparisonPair` rows.
        - Delegates A/B ordering to `orientation_strategy.choose_coverage_orientation`,
          which:
          - Uses per-essay skew `(A_e - B_e)` to favour the under-used position.
          - Applies deterministic tie-breakers (essay ID) when skew is equal.
      - Unit coverage:
        - `test_pair_generation_context.py` now injects a real `FairComplementOrientationStrategy`
          and validates that coverage semantics (global caps, budget, no duplicates) are
          preserved.
    - RESAMPLING integration:
      - `generate_comparison_tasks(..., mode=RESAMPLING)`:
        - Continues to select candidate pairs based on comparison counts to favour
          under-sampled essays.
        - Builds:
          - `per_essay_position_counts` via `_fetch_per_essay_position_counts`.
          - `per_pair_orientation_counts[(id_lo,id_hi)] = (count_AB, count_BA)` via
            `_fetch_per_pair_orientation_counts`.
        - Calls `FairComplementOrientationStrategy.choose_resampling_orientation` for each
          candidate, which:
          - Forces the missing complement when only AB or only BA exists.
          - Falls back to the essay-level skew rule once both orientations exist.
      - PR‑2/PR‑7 semantics:
        - `_can_attempt_resampling` and small-net semantics in
          `workflow_decision.py` / `workflow_continuation.py` remain unchanged and are
          still pinned by `test_workflow_small_net_resampling.py` and related tests.
        - `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` and
          `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` continue to cap resampling passes.
    - Positional fairness tests:
      - New `test_pair_orientation_strategy.py` pins:
        - Essay-level skew behaviour for COVERAGE (under-used A position preferred).
        - RESAMPLING complement behaviour for pairs with only AB or only BA history.
      - `test_pair_generation_context.py`:
        - Continues to enforce `MAX_ALLOWED_SKEW = 0.5` in
          `test_resampling_positional_skew_stays_within_band` using the DB-backed
          positional helper, now with the DI-wired orientation strategy in place.
      - `test_pair_generation_randomization.py`:
        - Refactored to use a test-only `RandomOrientationStrategy` that implements
          `PairOrientationStrategyProtocol`, proving that the orientation layer is
          swappable and can recover the previous “random A/B” behaviour when needed.
    - Regression guard:
      - `tests/integration/test_cj_small_net_continuation_docker.py` passes unchanged,
        confirming that ENG5 LOWER5 small-net continuation, PR‑2/PR‑7 semantics, and the
        docker harness remain intact with the new orientation layer active.

  - Known gaps / next opportunities:
    - Regular-batch RESAMPLING docker harness:
      - `tests/integration/test_cj_regular_batch_resampling_docker.py` remains gated with
        an early `pytest.skip`; regular-batch positional fairness is currently validated
        only via unit tests.
    - End-to-end DI usage:
      - Orientation strategy is DI-provided at the CJ service level but still defaults
        to `FairComplementOrientationStrategy` inside
        `comparison_processing.submit_comparisons_for_async_processing` /
        `request_additional_comparisons_for_batch` when not explicitly injected.
        This is sufficient for current behaviour but can be tightened to thread the
        DI-provided strategy all the way through Kafka handlers and workflow
        continuation if future experiments require runtime swapping.
    - LOWER5 positional diagnostics:
      - Docker-level LOWER5 harness currently validates small-net callbacks, coverage,
        and resampling caps but does not yet assert explicit per-essay skew bands; this
        remains a follow-up once acceptable positional skew thresholds are agreed.

  - Current state:
    - Three mock profiles exist and are pinned by unit + docker tests:
      - CJ generic (`cj_generic_batch`) – always-success, winner pinned to Essay A, lightweight token usage aligned with `cj_lps_roundtrip_mock_20251205`.
      - ENG5 full-anchor (`eng5_anchor_gpt51_low`) – hash-biased 35/31 winner split, high token floors, higher latency band aligned with `eng5_anchor_align_gpt51_low_20251201`.
      - ENG5 LOWER5 (`eng5_lower5_gpt51_low`) – hash-biased ~4/6 winner split, LOWER5-specific token floors and latency band aligned with `eng5_lower5_gpt51_low_20251202`.
    - Docker-backed tests:
      - `tests/integration/test_cj_mock_parity_generic.py` – CJ generic parity vs trace + multi-batch coverage/continuation checks.
      - `tests/integration/test_eng5_mock_parity_full_anchor.py` – ENG5 full-anchor parity vs trace.
      - `tests/integration/test_eng5_mock_parity_lower5.py` – LOWER5 parity vs trace + small-net coverage/diagnostics (now including explicit per-pair resampling stability and cross-batch winner proportion checks).
      - `tests/integration/test_eng5_profile_suite.py` – new CJ/ENG5 profile suite harness that orchestrates profiles via `/admin/mock-mode` and delegates to the per-profile docker tests.
    - Ergonomics:
      - `scripts/llm_mgmt/mock_profile_helper.sh` + `pdm run llm-mock-profile <profile>` validate `.env`, recreate `llm_provider_service`, and run the profile’s docker test file under the correct mock profile. Profile correctness for the running container is now enforced by the LPS `/admin/mock-mode` endpoint.
    - LPS admin endpoint:
      - New `GET /admin/mock-mode` endpoint implemented in `services/llm_provider_service/api/admin_routes.py` and wired in `services/llm_provider_service/app.py`.
      - JSON response:
        - `use_mock_llm`: derived from `Settings.USE_MOCK_LLM`.
        - `mock_mode`: string or `null` – `MockMode.DEFAULT` is surfaced as `null`, while CJ/ENG5 profiles return `"cj_generic_batch"`, `"eng5_anchor_gpt51_low"`, or `"eng5_lower5_gpt51_low"`.
        - `default_provider`: string derived from `Settings.DEFAULT_LLM_PROVIDER`.
      - Guarded by `Settings.ADMIN_API_ENABLED`:
        - When `ADMIN_API_ENABLED` is `True` (default in dev/CI), `/admin/mock-mode` returns `200` with the payload above.
        - When `ADMIN_API_ENABLED` is `False`, the endpoint returns `404` with `{"error": "admin_api_disabled"}` to keep the admin surface hidden.
      - API tests live in `services/llm_provider_service/tests/api/test_admin_mock_mode.py` and pin:
        - CJ generic, ENG5 anchor, and ENG5 LOWER5 profiles.
        - DEFAULT mode reporting `mock_mode = null`.
        - The admin-disabled behaviour.
    - Docker tests now use `/admin/mock-mode` as the single source of truth:
      - `tests/integration/test_cj_mock_parity_generic.py`
      - `tests/integration/test_eng5_mock_parity_full_anchor.py`
      - `tests/integration/test_eng5_mock_parity_lower5.py`
      - At the start of each docker test, they:
        - Call `/admin/mock-mode` using the validated `llm_provider_service` `base_url` from `ServiceTestManager`.
        - `pytest.skip` when `use_mock_llm` is `false` or `mock_mode` does not match the expected profile for that test.
        - Use the same `base_url` for the `/api/v1/comparison` HTTP surface.
      - All direct `.env` parsing and process-env vs `.env` dual-guard logic has been removed from these tests; `.env` is still validated by `llm-mock-profile`, but test gating is based solely on HTTP state.

  - Known gap (post-profile-suite and LOWER5 diagnostics refinement):
    - LOWER5 small-net diagnostics now include deterministic per-pair resampling checks and cross-batch winner proportion stability, but they are still expressed at the LPS callback level only (no direct BT SE or coverage-flag assertions yet). Future work can layer CJ-side diagnostics on top of the existing trace summaries.
    - The CJ/ENG5 profile suite currently orchestrates the existing per-profile docker tests; there is room to extend it with additional ENG5 anchor/LOWER5 scenarios (e.g. alternative prompt/trace variants) as new traces are captured.

  - Next steps for the very next session:
    - Deepen LOWER5 parity and coverage alignment:
      - Use the existing `eng5_lower5_gpt51_low_20251202` trace summaries plus CJ-side metadata to introduce BT SE / coverage flag assertions (e.g. `bt_se_inflated`, `comparison_coverage_sparse`) alongside the current LPS-level diagnostics, keeping `/admin/mock-mode` as the gating surface.
      - Consider adding a second LOWER5 scenario (e.g. 006/006 parity with `reasoning_effort="none"`) and mirroring the current docker tests against that trace to pin behaviour under both low and none reasoning-effort settings.
    - Extend the CJ/ENG5 profile suite:
      - Add optional per-profile “sanity” checks for new mock modes or future ENG5 traces by delegating to additional parity/coverage tests as they are introduced.
      - Keep the suite thin and orchestration-focused: it should continue to validate `/admin/mock-mode` state, then hand off to profile-specific tests rather than re-implementing parity logic.
    - Keep `/admin/mock-mode` as the canonical verification mechanism:
      - Any new mock profiles or docker tests MUST gate on `/admin/mock-mode` rather than `.env` heuristics.
      - `mock_profile_helper.sh` should remain the documented path for aligning `.env` with the running container before invoking docker tests.

  - CJ small-net continuation docker tests (ENG5 LOWER5):

  - Current state (updated 2025‑12‑06):
    - Docker-backed CJ continuation tests live in `tests/integration/test_cj_small_net_continuation_docker.py`.
    - The primary test (`test_cj_small_net_continuation_metadata_completed_successful`) now exercises the full ENG5 LOWER5 small-net path end-to-end:
      - Creates a 5-essay ENG5 batch via `ServiceTestManager.create_batch_via_agw(...)`, uploads five ENG5-like essays through AGW/File Service, and waits for `BatchContentProvisioningCompleted` via `KafkaTestManager` to ensure `READY_FOR_PIPELINE_EXECUTION`.
      - Requests the CJ pipeline through AGW and polls CJ’s database (via `CJSettings.DATABASE_URL` + `CJBatchUpload`/`CJBatchState` ORM) for the corresponding batch by `bos_batch_id` until:
        - `CJBatchState.state == COMPLETED`, and
        - `callbacks_received > 0` (no reliance on the BatchMonitor completion sweep).
      - Asserts PR‑2/PR‑7 completion invariants:
        - `failed_comparisons == 0`.
        - `total_comparisons == submitted_comparisons == completed_comparisons`.
        - `callbacks_received <= completion_denominator()` and `total_comparisons <= total_budget` when budget is set.
      - Asserts small-net coverage metadata on `CJBatchState.processing_metadata`:
        - `max_possible_pairs == 10`, `successful_pairs_count == 10`, `unique_coverage_complete is True`.
        - `resampling_pass_count` is an integer equal to `settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET` for the ENG5 LOWER5 docker profile (currently `resampling_pass_count == 3` for 5-essay nets), proving that small-net Phase‑2 resampling runs all the way to the configured cap.
      - Asserts BT quality metadata shape:
        - `bt_se_summary` present with keys `mean_se`, `max_se`, `mean_comparisons_per_item`, `isolated_items`.
        - `bt_quality_flags` present with boolean keys `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`.
      - Recomputes decision-level invariants from the final CJ state:
        - `success_rate ≈ 1.0` (all callbacks succeed under LOWER5 mock profile).
        - `total_comparisons` within the configured comparison budget (`comparison_budget.max_pairs_requested` / `total_budget`).
    - CJ service semantics have been aligned with the ENG5 LOWER5 story definition of “small batch size = 5”:
      - In `build_small_net_context(...)`, nets with `expected_essay_count <= MIN_RESAMPLING_NET_SIZE` are now treated as small nets.
      - With `MIN_RESAMPLING_NET_SIZE=5` in docker, 5-essay ENG5 LOWER5 batches are flagged as `is_small_net=True`.
      - Under this profile, the docker test shows:
        - Phase‑1 coverage: 10 unique pairs (`max_possible_pairs == successful_pairs_count == 10`).
        - Phase‑2 small-net resampling: `resampling_pass_count == settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET` (currently 3), yielding `total_comparisons == submitted_comparisons == completed_comparisons == 40` and `total_comparisons > C(5,2)`, i.e. extra comparisons beyond initial coverage.
        - Finalization via `ContinuationDecision.FINALIZE_SCORING` from the callback-driven continuation path (no dependence on the 5-minute BatchMonitor sweep).
    - Gating remains aligned with the ENG5 mock profile suite:
      - The test uses `ServiceTestManager.get_validated_endpoints()` to verify `llm_provider_service`, `cj_assessment_service`, and `api_gateway_service` health.
      - It calls `GET /admin/mock-mode` on LPS and `pytest.skip`s unless `use_mock_llm=true` and `mock_mode=="eng5_lower5_gpt51_low"`, keeping `/admin/mock-mode` as the only source of truth for profile activation (no `.env` reads).
      - In the current dev stack the test is expected to skip unless `llm_provider_service` is explicitly started in the `eng5_lower5_gpt51_low` profile (same gating behaviour as the existing LOWER5 docker tests).
    - The helper `_wait_for_cj_batch_final_state(...)` is intentionally net-size agnostic and parameterised by `expected_essay_count`; it can be reused later for regular (non-small-net) batches by varying net size and expectations, without changing the test plumbing.

  - CJ RESAMPLING + positional fairness work completed this session:
    - Regular-batch RESAMPLING semantics (non-small nets):
      - Introduced `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` in
        `services/cj_assessment_service/config.py` with a conservative default of `1`
        and documented it in `docs/operations/cj-assessment-runbook.md` and the CJ
        stability epic.
      - Added a general `_can_attempt_resampling(ctx: ContinuationContext) -> bool`
        predicate in `workflow_decision.py` that:
        - Delegates to `_can_attempt_small_net_resampling(ctx)` when `ctx.is_small_net`
          is `True` (small-net semantics unchanged).
        - For regular nets (`ctx.is_small_net is False`), requires
          `callbacks_received > 0`, no success-rate failure, remaining budget, and
          `successful_pairs_count / max_possible_pairs >= 0.6` before allowing
          RESAMPLING, and honours a regular-batch cap derived from
          `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` (clamped to the small-net cap).
      - Wired the new predicate through
        `workflow_continuation.trigger_existing_workflow_continuation` so that:
        - Small nets continue to trigger Phase‑2 RESAMPLING first, bounded by
          `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`.
        - Non-small nets can now request additional comparisons with
          `PairGenerationMode.RESAMPLING` when the general predicate passes, with
          `resampling_pass_count` never exceeding the regular-batch cap.
      - Extended `test_workflow_small_net_resampling.py` with a regular-net scenario
        that pins the new branch (non-small net, coverage fraction ≥0.6) and asserts
        that a RESAMPLING request is issued with `PairGenerationMode.RESAMPLING` and
        `resampling_pass_count` increments to (but not beyond)
        `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH`.
      - Updated the design-only docker skeleton
        `tests/integration/test_cj_regular_batch_resampling_docker.py` to reflect that
        generalised RESAMPLING semantics now exist, while keeping the test skipped
        until we are ready to exercise the path under ENG5/CJ docker profiles.
      - Updated `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md`
        to mark orchestration, settings, and unit-test items as implemented and to keep
        the docker/E2E work explicitly marked as a follow-up.
    - Positional fairness diagnostics (test scaffolding only for now):
      - Implemented a test-side helper
        `get_positional_counts_for_batch(session, cj_batch_id)` in
        `services/cj_assessment_service/tests/helpers/positional_fairness.py` that
        queries `CJComparisonPair` via SQLAlchemy and returns
        `{essay_id: {"A": count_as_A, "B": count_as_B}}`.
      - Added `test_positional_fairness_helper.py` to validate that helper against a
        small synthetic batch, ensuring per-essay A/B counts match expected values.
      - Extended `test_pair_generation_context.py` with
        `test_resampling_positional_skew_stays_within_band`, which:
        - Simulates multiple RESAMPLING waves over a 3‑essay synthetic net using
          `PairGenerationMode.RESAMPLING`.
        - Persists `ComparisonPair` rows for each wave and uses the positional-counts
          helper to compute per‑essay A/B counts.
        - Computes `skew_e = |A_e - B_e| / (A_e + B_e)` per essay and currently enforces
          a generous `MAX_ALLOWED_SKEW=0.5` bound as an initial guardrail (to be
          tightened once ENG5/LOWER5 trace distributions are analysed).
      - Updated `TASKS/assessment/cj-resampling-a-b-positional-fairness.md` and the
        US‑005.1 / PR‑7 task docs to reflect that:
        - The positional-counts helper and first unit-level fairness checks now exist.
        - Docker-level LOWER5 positional fairness remains a follow-up once acceptable
          skew bands are calibrated against real traces.

---

## NEXT SESSION INSTRUCTION (for the next developer)

Role: You are the lead developer and architect of HuleEdu. Your **primary objective**
is to **validate positional fairness via docker harnesses** - this validates the business
requirement that LLM positional bias cannot accumulate across continuation cycles and
corrupt BT rankings.

**Why harness validation is critical:**
- Without fair A/B distribution, essays that consistently land in LLM's "preferred" position
  (typically Essay A) accumulate wins they shouldn't have
- Over multiple comparison waves, this bias compounds and distorts final BT scores
- The `_random_fallback` fix ensures 50/50 orientation when skew is equal, but we need
  harness-level validation that this produces fair distributions in real batch scenarios

Before touching code:
- From repo root, read:
  - `AGENTS.md` (root) to align with monorepo conventions and test structure.
  - `.claude/rules/000-rule-index.md`, `.claude/rules/070-testing-and-quality-assurance.md`, `.claude/rules/075-test-creation-methodology.md`, and `.claude/rules/110-ai-agent-interaction-modes.md` (Coding + Testing mode).
  - `.claude/work/session/handoff.md` (this file) and `.claude/work/session/readme-first.md` for current CJ/ENG5 context.
  - `TASKS/assessment/us-0051-callback-driven-continuation-and-safe-completion-gating.md` (docker LOWER5 continuation semantics and future regular‑batch/fairness goals).
  - `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md` (PR‑7 semantics and caps, including regular‑batch RESAMPLING notes).
  - `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md` (generalised RESAMPLING plan, now partially implemented).
  - `TASKS/assessment/cj-resampling-a-b-positional-fairness.md` (A/B positional fairness requirements, helper status, and open questions, now updated with orientation-strategy status).

Key code and tests to open first:
- Docker + LPS profile gating:
  - `services/llm_provider_service/api/admin_routes.py` (GET `/admin/mock-mode`).
  - `services/llm_provider_service/config.py` and `services/llm_provider_service/implementations/mock_provider_impl.py` (ENG5 profiles, especially LOWER5).
  - `tests/integration/test_eng5_mock_parity_lower5.py` (ENG5 LOWER5 docker parity and diagnostics).
  - `tests/integration/test_cj_small_net_continuation_docker.py` (ENG5 LOWER5 CJ continuation harness and helpers).
  - `tests/integration/test_cj_regular_batch_resampling_docker.py` (regular‑batch RESAMPLING docker skeleton; still skipped).
- CJ continuation, pair generation, and positional fairness:
  - `services/cj_assessment_service/models_db.py` (`CJBatchState`, `CJBatchUpload`, `CJBatchState.completion_denominator`, `ComparisonPair`).
  - `services/cj_assessment_service/cj_core_logic/workflow_context.py` (`ContinuationContext`, `build_small_net_context`, BT metadata helpers).
  - `services/cj_assessment_service/cj_core_logic/workflow_decision.py` and `workflow_continuation.py`
    (continuation decisions, `_can_attempt_small_net_resampling`, `_can_attempt_resampling`,
    regular‑batch caps).
  - `services/cj_assessment_service/cj_core_logic/pair_generation.py` (COVERAGE vs RESAMPLING,
    budget handling, and the new orientation helpers).
  - `services/cj_assessment_service/cj_core_logic/pair_orientation.py` (strategy implementation).
  - `services/cj_assessment_service/tests/unit/test_workflow_small_net_resampling.py`,
    `test_workflow_continuation_orchestration.py`, and
    `test_pair_generation_context.py` (small‑net semantics, regular‑batch RESAMPLING unit
    tests, and positional fairness scaffolding).
  - `services/cj_assessment_service/tests/helpers/positional_fairness.py` and
    `tests/unit/test_positional_fairness_helper.py` (positional counts helper and validation).
  - `services/cj_assessment_service/tests/unit/test_pair_orientation_strategy.py` and
    `tests/unit/test_pair_generation_randomization.py` (orientation-strategy behaviour and DI-swappability).

Concrete objectives for your session:

1. Tighten regular‑batch RESAMPLING positional fairness (unit → docker):
   - Extend unit coverage to include a regular-net RESAMPLING scenario where:
     - Without orientation-aware logic, positional skew would be high.
     - With `FairComplementOrientationStrategy`, per-essay skew shrinks deterministically
       across RESAMPLING waves.
   - Use that scenario as the blueprint for fleshing out
     `tests/integration/test_cj_regular_batch_resampling_docker.py` (still gated by
     `pytest.skip`) so that, once unskipped, it:
     - Uses a regular ENG5/CJ batch with `expected_essay_count > MIN_RESAMPLING_NET_SIZE`.
     - Asserts PR‑2/PR‑7 invariants (completion, caps, coverage) as described in the
       existing skeleton.
     - Computes per-essay A/B counts via the positional helper and asserts a first-pass
       skew band for regular nets (you can start with the same `MAX_ALLOWED_SKEW=0.5`
       used in unit tests and narrow it once behaviour is stable).

2. Promote positional diagnostics into the ENG5 LOWER5 docker harness (design-first):
   - Add a **skipped** or soft-assertion-only test node in
     `tests/integration/test_cj_small_net_continuation_docker.py` (or a sibling module)
     that:
     - Reuses the existing LOWER5 harness to drive the batch to completion.
     - Uses the positional helper to compute per-essay A/B counts and `skew_e`.
     - Logs / comments intended LOWER5 skew bands (likely ≤0.25 per essay) and any
       open questions about stochasticity and trace alignment with real traces, but
       does not yet hard-fail on skew thresholds.
   - Capture the proposed LOWER5 skew thresholds and diagnostic plan in
     `TASKS/assessment/cj-resampling-a-b-positional-fairness.md`, marking which parts of
     the plan are now backed by code vs. still speculative.

3. Tighten end-to-end DI for orientation strategy (optional but recommended):
   - Thread `PairOrientationStrategyProtocol` through:
     - `CJAssessmentKafkaConsumer` → `event_processor.process_single_message` →
       `handle_cj_assessment_request` → `run_cj_assessment_workflow` →
       `comparison_processing.submit_comparisons_for_async_processing`.
     - `event_processor.process_llm_result` → `handle_llm_comparison_callback` →
       `continue_cj_assessment_workflow` → `workflow_continuation.trigger_existing_workflow_continuation` →
       `comparison_processing.request_additional_comparisons_for_batch`.
   - Update or add tests to prove that:
     - The DI-provided strategy is used consistently for both initial COVERAGE and
       continuation RESAMPLING paths.
     - Swapping `PAIR_ORIENTATION_STRATEGY` at settings/DI level would affect both
       paths without changing core workflow logic.

Validation and docs:
- From an env-aware shell (`./scripts/dev-shell.sh` or `source .env` from repo root), prefer:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit -k "workflow_continuation or pair_generation or small_net or positional_fairness" -v`
    while iterating on RESAMPLING semantics and fairness tests.
  - `pdm run pytest-root tests/integration/test_cj_small_net_continuation_docker.py -m "docker and integration" -v`
    when verifying that the LOWER5 harness still passes after changes.
  - Once ready, run the new regular‑batch docker test nodeid from
    `tests/integration/test_cj_regular_batch_resampling_docker.py` under the appropriate
    mock profile via `pdm run llm-mock-profile <profile>`.
- Keep this handoff file’s ACTIVE WORK section and the relevant TASK docs up to date with
  what you actually implement, remaining gaps, and any refinements to the next-session
  objectives for your successor.
