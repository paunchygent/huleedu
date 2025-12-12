---
id: 101-ci-lanes-and-heavy-suites
type: standards
created: '2025-12-09'
last_updated: '2025-12-12'
scope: all
---
# 101: CI Lanes and Heavy Suites

## Purpose

Define standardized CI test lanes and rules for heavy suites (including ENG5 docker/profile tests) so that:
- Fast PR pipelines remain stable and resource-light.
- Heavy, environment-driven tests run in isolated lanes with clear orchestration rules.
- .env-driven configuration and container restarts are only used where architecturally justified.

This rule underpins ADR-0024 and EPIC-011 and complements `070-testing-and-quality-assurance.md` by focusing on **orchestration and CI pipelines** rather than test implementation details.

## 1. CI Test Lanes

### 1.1 Lane A – Fast PR Pipeline
- **Scope**: Unit tests, contract tests, and light service-local integration tests.
- **Characteristics**:
  - No docker-compose stack startup.
  - No `.env` mutation.
  - No dependence on ENG5 profiles or heavy harnesses.
  - Targets fast (<10–15 minutes) end-to-end runtime.
- **Allowed Commands** (examples):
  - `pdm run pytest-root services/<service>/tests/unit`
  - `pdm run pytest-root tests/contract`

### 1.2 Lane B – Walking Skeleton / Infra Smoke
- **Scope**: Minimal end-to-end smoke validation of the dockerized stack.
- **Characteristics**:
  - Uses docker-compose to bring up core services.
  - Runs only health checks and thin smoke tests (no ENG5 semantics).
  - Must remain relatively fast and stable; used to catch infra/config drift.
- **Implementation Reference**:
  - `.github/workflows/walking-skeleton-smoke-test.yml`

### 1.3 Lane C – ENG5 Heavy Suites (Heavy C-lane)
- **Scope**: High-cost, high-fidelity validation for CJ ↔ LPS serial bundling and ENG5 mock parity.
- **Characteristics**:
  - May start dockerized services and restart specific containers between runs.
  - May rely on `.env` configuration for:
    - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM`
    - `LLM_PROVIDER_SERVICE_MOCK_MODE` (e.g. `cj_generic_batch`, `eng5_anchor_gpt51_low`, `eng5_lower5_gpt51_low`)
    - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE`, `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS`
    - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE`, `LLM_PROVIDER_SERVICE_BATCH_API_MODE`
  - Treats services as **immutable black boxes per run**:
    - Configuration is applied via `.env` + container restart.
    - Tests use `/admin/mock-mode` and `/metrics` for introspection and **never** mutate mode at runtime.
  - Triggered via:
    - `workflow_dispatch` and/or `schedule` only (not default push/pull_request).
- **Implementation References**:
  - `.github/workflows/eng5-heavy-suites.yml`
  - `scripts/llm_mgmt/eng5_cj_docker_suite.sh`
  - `scripts/llm_mgmt/mock_profile_helper.sh`
  - `tests/integration/test_cj_*_docker.py`
  - `tests/eng5_profiles/*`

## 2. .env and Harness Rules

### 2.1 .env Mutation (CI and Local)
- **ALLOWED ONLY IN LANE C**:
  - `.env` edits for ENG5 profiles and serial_bundle configuration.
  - Container restarts via:
    - `pdm run dev-recreate llm_provider_service`
    - `pdm run dev-recreate cj_assessment_service`
  - Scripts:
    - `pdm run eng5-cj-docker-suite [all|small-net|regular]`
    - `pdm run llm-mock-profile <profile>`
- **FORBIDDEN**:
  - `.env` mutation in Lane A or Lane B workflows.
  - Tests that modify `.env` directly; only CI workflows / harness scripts may do so.

### 2.2 Runtime Introspection and Skips
- Heavy tests **MUST**:
  - Use `/admin/mock-mode` to verify active mock configuration:
    - Skip if `use_mock_llm` is `false` or `mock_mode` does not match the expected profile.
  - Use `/metrics` endpoints for Prometheus assertions where relevant.
- This pattern:
  - Ensures tests fail fast when CI/dotenv drift occurs.
  - Prevents “hidden dependence” on incorrect profiles.

## 3. ENG5 Heavy Suite Placement

### 3.1 CJ Docker Semantics Tests
- **Location**: `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`, `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py`, `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py`, `tests/functional/cj_eng5/test_cj_regular_batch_provider_batch_api_docker.py`
- **Lane**: C only.
- **Execution**:
  - Local:
    - `pdm run eng5-cj-docker-suite`
    - `pdm run eng5-cj-docker-suite regular`
    - `pdm run eng5-cj-docker-suite small-net`
    - `pdm run eng5-cj-docker-suite batch-api`
  - CI:
    - `eng5-cj-docker-regular-and-small-net` job in `.github/workflows/eng5-heavy-suites.yml`

### 3.2 ENG5 Mock Profile Parity Tests
- **Location**: `tests/eng5_profiles/test_cj_mock_parity_generic.py`, `tests/eng5_profiles/test_cj_mock_batch_api_metrics_generic.py`, `test_eng5_mock_parity_full_anchor.py`, `test_eng5_mock_parity_lower5.py`, `test_eng5_profile_suite.py`
- **Lane**: C only.
- **Execution**:
  - Local:
    - `pdm run llm-mock-profile cj-generic`
    - `pdm run llm-mock-profile cj-generic-batch-api`
    - `pdm run llm-mock-profile eng5-anchor`
    - `pdm run llm-mock-profile eng5-lower5`
  - CI:
    - `eng5-profile-parity-suite` job in `.github/workflows/eng5-heavy-suites.yml`
    - Future: matrix split per profile (`{cj-generic, eng5-anchor, eng5-lower5}`) with fixed `LLM_PROVIDER_SERVICE_MOCK_MODE` per matrix entry.

## 4. Future CI Orchestration Enhancements

The following are **recommended but not mandatory** improvements for EPIC-011:

- **Parallel profiles (matrix strategy)**:
  - Convert `eng5-profile-parity-suite` into a matrix over profiles, each with:
    - Its own `LLM_PROVIDER_SERVICE_MOCK_MODE` in env.
    - A call to `pdm run llm-mock-profile <profile>`.
- **Test-only healthcheck tuning**:
  - For CI test profiles, reduce healthcheck intervals and start periods to lower container startup time while keeping production settings conservative.
- **C-lane stability gate**:
  - Override selected stability-related env vars (e.g. `CJ_ASSESSMENT_SERVICE_SCORE_STABILITY_THRESHOLD`) only in Lane C to make heavy suites canaries for subtle instability.

## 5. Relationship to Other Rules and Docs

- **070-testing-and-quality-assurance.md**:
  - Defines **what** to test (pyramid, patterns, timeouts).
  - Rule 101 defines **where and how** those tests run in CI.
- **ADR-0024**:
  - Captures the architectural decision to keep ENG5 heavy suites env-driven and restart-based rather than adding test-only runtime mock switches.
- **EPIC-011**:
  - Owns execution of this rule: CI restructuring, matrix jobs, and healthcheck tuning.
