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

## 🎯 ACTIVE WORK (2025-12-05)

- LLM Provider Service mock profiles + CJ/ENG5 parity and profile verification:

  - Current state:
    - Three mock profiles exist and are pinned by unit + docker tests:
      - CJ generic (`cj_generic_batch`) – always-success, winner pinned to Essay A, lightweight token usage aligned with `cj_lps_roundtrip_mock_20251205`.
      - ENG5 full-anchor (`eng5_anchor_gpt51_low`) – hash-biased 35/31 winner split, high token floors, higher latency band aligned with `eng5_anchor_align_gpt51_low_20251201`.
      - ENG5 LOWER5 (`eng5_lower5_gpt51_low`) – hash-biased ~4/6 winner split, LOWER5-specific token floors and latency band aligned with `eng5_lower5_gpt51_low_20251202`.
    - Docker-backed tests:
      - `tests/integration/test_cj_mock_parity_generic.py` – CJ generic parity vs trace + multi-batch coverage/continuation checks.
      - `tests/integration/test_eng5_mock_parity_full_anchor.py` – ENG5 full-anchor parity vs trace.
      - `tests/integration/test_eng5_mock_parity_lower5.py` – LOWER5 parity vs trace + small-net coverage/diagnostics.
    - Ergonomics:
      - `scripts/llm_mgmt/mock_profile_helper.sh` + `pdm run llm-mock-profile <profile>` validate `.env`, recreate `llm_provider_service`, and run the profile’s docker test file under the correct mock profile.

  - Known gap (this stream’s focus):
    - Profile correctness inside the running container is currently inferred from process env and `.env` heuristics in tests; this is brittle because pytest env can be changed without recreating the container.
    - Decision for next work: introduce a dedicated admin endpoint on LPS that reports the active mock mode, and have the docker tests assert directly against that, instead of trying to infer container state from `.env`.

  - Next steps for the very next session:
    - Add a small `GET /admin/mock-mode` endpoint on `llm_provider_service` that returns a JSON payload such as:
      - `{"use_mock_llm": bool, "mock_mode": "<mode-name>", "default_provider": "<provider-name>"}` based on the actual `Settings` instance used by DI.
    - Add LPS API tests (e.g. under `services/llm_provider_service/tests/api/`) to pin this endpoint for:
      - `cj_generic_batch`, `eng5_anchor_gpt51_low`, and `eng5_lower5_gpt51_low` profiles.
      - `USE_MOCK_LLM=true` vs `false`.
    - Refactor the three docker test files above so that, at the start of each test:
      - They call `/admin/mock-mode` via the `llm_provider_service` base URL from `ServiceTestManager`.
      - They `pytest.skip` if `use_mock_llm` is `false` or `mock_mode` does not match the expected profile for that test.
      - They no longer parse `.env` directly or depend on process-only env overrides to decide whether to run.
    - Keep `llm-mock-profile` as the recommended way to switch profiles and run tests, but treat `/admin/mock-mode` as the single source of truth for what mock mode the container is actually running.
