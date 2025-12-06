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

- LLM Provider Service mock profiles + CJ/ENG5 parity and profile verification:

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

  - Current state:
    - New docker-backed CJ continuation test added in `tests/integration/test_cj_small_net_continuation_docker.py`.
    - The test creates a 5-essay ENG5 batch via `ServiceTestManager.create_batch_via_agw(...)`, uploads five ENG5-like essays through AGW/File Service, and then:
      - Polls CJ’s database (via `CJSettings.DATABASE_URL` + `CJBatchUpload`/`CJBatchState` ORM) to locate the corresponding CJ batch by `bos_batch_id`.
      - Waits until `CJBatchState.state` reaches a terminal state (`COMPLETED`/`FAILED`/`CANCELLED`) or a hard 60s timeout, asserting that callbacks have been received before treating the batch as final.
      - Asserts PR‑2 completion invariants (`callbacks_received == completion_denominator()`, `failed_comparisons == 0`, `total_comparisons == submitted == completed <= total_budget` when budget is set).
      - Asserts small-net coverage metadata on `CJBatchState.processing_metadata`:
        - `max_possible_pairs == 10`, `successful_pairs_count == 10`, `unique_coverage_complete is True`.
        - `resampling_pass_count` is an integer with `resampling_pass_count >= 0` (small-net Phase‑2 resampling friendly).
      - Asserts BT quality metadata shape:
        - `bt_se_summary` present with keys `mean_se`, `max_se`, `mean_comparisons_per_item`, `isolated_items`.
        - `bt_quality_flags` present with boolean keys `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`.
      - Recomputes decision-level invariants from the final CJ state:
        - `success_rate ≈ 1.0` (all callbacks succeed under LOWER5 mock profile).
        - Derives `callbacks_reached_cap`, `pairs_remaining`, and `budget_exhausted` from comparison budget metadata.
        - Uses `build_small_net_context(...)` to recompute `is_small_net`, `small_net_max_pairs`, `small_net_resampling_cap`, and `small_net_cap_reached` from persisted metadata, asserting that at least one of `callbacks_reached_cap`, `budget_exhausted`, or `small_net_cap_reached` is `True` and that there is no `failed_reason` marker in metadata.
    - Gating is aligned with the ENG5 mock profile suite:
      - The test uses `ServiceTestManager.get_validated_endpoints()` to verify `llm_provider_service`, `cj_assessment_service`, and `api_gateway_service` health.
      - It calls `GET /admin/mock-mode` on LPS and `pytest.skip`s unless `use_mock_llm=true` and `mock_mode=="eng5_lower5_gpt51_low"`, keeping `/admin/mock-mode` as the only source of truth for profile activation (no `.env` reads).
      - In the current dev stack the test is expected to skip unless `llm_provider_service` is explicitly started in the `eng5_lower5_gpt51_low` profile (same gating behaviour as the existing LOWER5 docker tests).
    - The helper `_wait_for_cj_batch_final_state(...)` is intentionally net-size agnostic and parameterised by `expected_essay_count`; it can be reused later for regular (non-small-net) batches by varying net size and expectations, without changing the test plumbing.

  - Gaps / follow-ups:
    - The new test currently covers only the “completed-successful small net” path; it does not yet assert that CJ exercises `REQUEST_MORE_COMPARISONS` before finalization for LOWER5 (i.e. no docker verification yet that resampling / extra iterations occur before the final decision).
    - The helper polls CJ’s database directly; if we later add a CJ admin/status HTTP surface that exposes `CJBatchState`/coverage metadata, future work could migrate the polling to that API to avoid DB coupling in tests.
    - There is no docker test yet for regular-sized nets exercising generalized RESAMPLING semantics (see PR‑7 task); current helpers are structured to support this but additional tests still need to be added.

  - Next steps for the very next session (CJ side):
    - Implement a second docker test, `test_cj_small_net_continuation_requests_more_before_completion`, that:
      - Uses the same harness to create a LOWER5 batch under the `eng5_lower5_gpt51_low` mock profile.
      - Demonstrates at least one LOWER5 run where `submitted_comparisons_final` and `total_comparisons_final` are strictly greater than the first small-net wave (≈10 comparisons), while `failed_comparisons_final == 0` and `completed_comparisons_final == total_comparisons_final`.
      - Confirms via metadata that `resampling_pass_count >= 1` while coverage fields still show `max_possible_pairs == successful_pairs_count == 10`.
    - Decide whether that second test should be hard-asserted or initially marked `xfail` depending on how reliably the current docker ENG5 LOWER5 configuration produces an extra iteration before finalization.
    - Begin planning the extension of this harness to regular-sized nets:
      - Reuse `_wait_for_cj_batch_final_state(...)` and the metadata assertion scaffolding.
      - Thread configuration knobs (e.g. `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` once implemented) into expectations so that PR‑7’s generalized RESAMPLING semantics can be exercised without major harness rewrites.

---

## NEXT SESSION INSTRUCTION (for the next developer)

Role: You are the lead developer and architet of HuleEdu. Your scope is to extend the new docker-backed CJ small-net continuation harness for ENG5 LOWER5 so that it (a) proves that CJ can request additional comparisons before finalization for at least one LOWER5 scenario, and (b) is ready to be lifted to regular (non-small-net) batches and generalized RESAMPLING semantics under PR‑7.

Before touching code:
- From repo root, read:
  - `AGENTS.md` (root) to align with monorepo conventions and test structure.
  - `.claude/rules/000-rule-index.md`, `.claude/rules/070-testing-and-quality-assurance.md`, `.claude/rules/075-test-creation-methodology.md`, and `.claude/rules/110-ai-agent-interaction-modes.md` (Coding + Testing mode).
  - `.claude/work/session/handoff.md` (this file) and `.claude/work/session/readme-first.md` for current CJ/ENG5 context.
  - `TASKS/assessment/us-0051-callback-driven-continuation-and-safe-completion-gating.md` (focus on the Test 2 checklist for small-net continuation) and `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md` (PR‑7 semantics and caps).
  - `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md` to understand how small-net vs regular-batch RESAMPLING is expected to diverge.

Key code and tests to open first:
- Docker + LPS profile gating:
  - `services/llm_provider_service/api/admin_routes.py` (GET `/admin/mock-mode`).
  - `services/llm_provider_service/config.py` and `services/llm_provider_service/implementations/mock_provider_impl.py` (ENG5 LOWER5 mock behaviour).
  - `tests/integration/test_eng5_mock_parity_lower5.py` (ENG5 LOWER5 docker parity and diagnostics).
  - `tests/integration/test_cj_small_net_continuation_docker.py` (new CJ continuation test and helpers).
- CJ continuation and small-net semantics:
  - `services/cj_assessment_service/models_db.py` (`CJBatchState`, `CJBatchUpload`, `completion_denominator`).
  - `services/cj_assessment_service/cj_core_logic/workflow_context.py` (`build_small_net_context`, BT metadata helpers).
  - `services/cj_assessment_service/cj_core_logic/workflow_decision.py` and `workflow_continuation.py` (continuation decisions, small-net resampling predicate, metadata merge).
  - `services/cj_assessment_service/cj_core_logic/pair_generation.py` (COVERAGE vs RESAMPLING).
  - `services/cj_assessment_service/tests/unit/test_workflow_small_net_resampling.py`, `test_workflow_continuation_orchestration.py`, and `test_pair_generation_context.py` for reference semantics.

Concrete objectives for your session:
1. Extend `tests/integration/test_cj_small_net_continuation_docker.py` with `test_cj_small_net_continuation_requests_more_before_completion`:
   - Reuse the existing `ServiceTestManager` and `_wait_for_cj_batch_final_state(...)` helpers (do not introduce new plumbing).
   - Under the `eng5_lower5_gpt51_low` profile, identify a configuration/path where at least one LOWER5 batch performs extra comparisons beyond the initial 10 coverage pairs before finalization.
   - In the final CJ state, assert:
     - `submitted_comparisons_final` and/or `total_comparisons_final` are `> 10`.
     - `completed_comparisons_final == total_comparisons_final` and `failed_comparisons_final == 0`.
     - `resampling_pass_count >= 1` while `max_possible_pairs == successful_pairs_count == 10` and `unique_coverage_complete is True`.
   - If the current docker ENG5 LOWER5 configuration cannot reliably produce this path, mark the test `xfail` with a clear reason and leave a TODO pointing at the relevant TASKS entries; otherwise, keep it as a normal passing test.

2. Keep the harness net-size agnostic:
   - Where you need additional helpers (e.g. for comparing multiple continuation snapshots), parameterise them by `expected_essay_count` and any relevant comparison budget caps rather than baking in LOWER5 constants.
   - Avoid new cross-service imports; follow the existing pattern of:
     - Using `ServiceTestManager` for HTTP surfaces and health.
     - Using CJ’s own config (`CJSettings.DATABASE_URL`) and ORM models for direct state inspection.

3. Prepare for regular-batch RESAMPLING tests:
   - Sketch (but do not yet implement) how the same helpers could be applied to a regular-sized ENG5 or generic CJ batch once PR‑7’s generalized RESAMPLING knobs (`MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH`, etc.) land in `cj_assessment_service.config`.
   - Capture these notes by updating:
     - `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md` (testing subsection).
     - `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md` (Plan section).

Validation and docs:
- From an env-aware shell (`./scripts/dev-shell.sh` or `source .env` from repo root), run:
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`
  - `pdm run pytest-root tests/integration/test_cj_small_net_continuation_docker.py -m "docker and integration" -v`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit -k "workflow_continuation or pair_generation or small_net" -v`
- Update:
  - `TASKS/assessment/us-0051-callback-driven-continuation-and-safe-completion-gating.md` (mark Test 2 checklist entries as you wire them in).
  - `TASKS/assessment/pr-7-phase-2-resampling-and-convergence-harness.md` and `TASKS/assessment/cj-resampling-mode-generalization-for-all-batch-sizes.md` with any new assumptions or harness details.
  - This handoff file’s ACTIVE WORK section with what you actually implemented, remaining gaps, and a fresh NEXT SESSION instruction for your successor.
