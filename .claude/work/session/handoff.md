# HANDOFF: Current Session Context

## Purpose

This document contains ONLY what the next developer needs to pick up work.
All completed work, patterns, and decisions live in:

- **TASKS/** – Detailed task documentation with full implementation history
- **readme-first.md** – Sprint-critical patterns, ergonomics, quick start
- **AGENTS.md** – Workflow, rules, and service conventions
- **.agent/rules/** – Implementation standards

---

## CURRENT STATUS (2025-12-12)

### Teacher Dashboard Live Data Integration (Planning Complete)

Created inside-out roadmap with 7 new stories (Phases 4-10) for backend→frontend integration:
- `TASKS/programs/teacher_dashboard_integration/HUB.md` — updated with new phases
- 7 new TASK files created, all status `blocked` pending prioritization
- Task alignment updates applied:
  - `current_phase` semantics clarified: `PhaseName | null`, only during pipeline execution (avoid “next phase” UX ambiguity)
  - CMS validation endpoint specified as bulk (avoid N+1), using `pending_validation` semantics
  - WebSocket updates specified via existing `TeacherNotificationRequestedV1` forwarding (no new contract)
- **No code changes** — planning/documentation only
- **Entry point:** Phase 4 `ras-processing-phase-derivation.md` (RAS current_phase fix)

### ENG5 Heavy‑C provider_batch_api (Stabilized + Locally Validated)

ENG5 Heavy‑C **provider_batch_api** harness coverage + metrics assertions are implemented:

- CJ regular-batch docker semantics now has a provider_batch_api variant using the ENG5 runner metadata hint pipe.
- ENG5 mock profile parity now includes a batch_api queue + job-metrics suite.
- Harness scripts + CI workflow are extended to run both serial_bundle and batch_api slices.
- TASK docs + runbooks are updated to reflect the new harness behavior.
- Local validation (2025-12-12): both required slices pass repeatedly:
  - `pdm run eng5-cj-docker-suite batch-api`
  - `pdm run llm-mock-profile cj-generic-batch-api`
- CI parity: provider_batch_api docker semantics passes with `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=false` (matches `.github/workflows/eng5-heavy-suites.yml`).

Source-of-truth trackers:
- `TASKS/integrations/llm-provider-batch-api-phase-2.md` (Phase 2.5 complete)
- `TASKS/integrations/eng5-provider-batch-api-harness-coverage.md` (completed)
- `TASKS/assessment/cj-llm-provider-batch-api-mode.md`

---

## What Changed

**New tests**
- `tests/functional/cj_eng5/test_cj_regular_batch_provider_batch_api_docker.py`
  - Publishes an `ELS_CJAssessmentRequestV1` using ENG5 runner request composition with `llm_batching_mode_hint="provider_batch_api"`.
  - Asserts:
    - `CJBatchState.processing_metadata["llm_batching_mode"] == "provider_batch_api"`
    - Stored original request contains `batch_config_overrides.llm_batching_mode_override == "provider_batch_api"`
    - `cj_llm_requests_total{batching_mode="provider_batch_api"} >= 1`
    - `cj_llm_batches_started_total{batching_mode="provider_batch_api"} >= 1`
    - LPS batch_api queue/job metrics are emitted.
- `tests/eng5_profiles/test_cj_mock_batch_api_metrics_generic.py`
  - Sends CJ-shaped requests directly to LPS under `QUEUE_PROCESSING_MODE=batch_api`.
  - Asserts queue + job-level metrics via shared helper.

**Updated helpers / harness**
- `tests/eng5_profiles/eng5_lps_metrics_assertions.py`
  - Adds `assert_lps_batch_api_metrics_for_mock_profile(...)` with:
    - `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`
    - `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",result}`
    - `llm_provider_batch_api_jobs_total{provider,model,status}`
    - `llm_provider_batch_api_items_per_job{provider,model}`
    - `llm_provider_batch_api_job_duration_seconds{provider,model}`
- `scripts/llm_mgmt/eng5_cj_docker_suite.sh`
  - Adds `batch-api` scenario: `pdm run eng5-cj-docker-suite batch-api`.
- `scripts/llm_mgmt/mock_profile_helper.sh`
  - Adds `cj-generic-batch-api` profile and validates `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api`.
- `tests/functional/conftest.py`
  - Stabilises functional suite Redis cleanup:
    - Bounded Redis readiness check (PING with retries).
    - Uses `SCAN` instead of `KEYS` when deleting `test:*` / `ws:*` keys.
- `tests/eng5_profiles/test_cj_mock_batch_api_metrics_generic.py`
  - Fix: reads the 202 response body inside the `aiohttp` response context manager (prevents `ClientConnectionError: Connection closed`).
- `.github/workflows/eng5-heavy-suites.yml`
  - Adds provider_batch_api docker step and cj-generic-batch-api profile step.
- `.agent/rules/101-ci-lanes-and-heavy-suites.md`
  - Updated test and harness references.
- Runbooks:
  - `docs/operations/eng5-np-runbook.md`
  - `docs/operations/cj-assessment-runbook.md`
- Session context:
  - `.claude/work/session/readme-first.md` updated with new commands and status.

**Lint gate**
- `colab_ml_training/demo_notebook_patterns.ipynb`: replaced an overly-long fake key with `sk-proj-REDACTED` to satisfy ruff line-length checks.

---

## How To Run (Local)

### CJ docker semantics: provider_batch_api regular batch

Pre-req `.env` (and service recreate):
- `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
- `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`
- `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api`
- `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`

Run:
```bash
pdm run eng5-cj-docker-suite batch-api
```

### LPS mock profile: batch_api metrics

Pre-req `.env` (and service recreate):
- `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
- `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch`
- `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api`

Run:
```bash
pdm run llm-mock-profile cj-generic-batch-api
```

### Troubleshooting (Local)

- If you see `Connection reset by peer` talking to Redis/Kafka/Postgres from the host (common with long-lived Docker Desktop infra), restart the affected containers and retry:
  - `docker restart huleedu_redis`
  - `docker restart huleedu_kafka`
  - `docker restart huleedu_cj_assessment_db`

---

## NEXT SESSION INSTRUCTION

Role: You are the lead developer and architect of HuleEdu. The scope of the next session is **stabilization** of the batch_api heavy suites.

### Focus
1. Run the updated `ENG5 Heavy CJ/ENG5 Suites` CI workflow and confirm the new batch_api steps are green.
2. If anything is flaky:
   - Prefer reducing request counts / timeouts in the new tests over adding retries.
   - Keep serial_bundle tests unchanged.
3. Keep batch_api Heavy‑C coverage limited to `cj_generic_batch` for now (avoid long-running profile expansion until we have stability + runtime budget).
4. Optional observability polish:
   - Extend `scripts/cj_experiments_runners/eng5_np/logging_support.py::print_batching_metrics_hints` to include batch_api job metric PromQL hints.
5. Keep `TASKS/` + runbooks aligned with any adjustments.
