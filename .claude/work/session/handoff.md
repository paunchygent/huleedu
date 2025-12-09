# HANDOFF: Current Session Context

## Purpose

This document contains ONLY what the next developer needs to pick up work.
All completed work, patterns, and decisions live in:

- **TASKS/** – Detailed task documentation with full implementation history
- **readme-first.md** – Sprint-critical patterns, ergonomics, quick start
- **AGENTS.md** – Workflow, rules, and service conventions
- **.claude/rules/** – Implementation standards

---

## NEXT SESSION INSTRUCTION

Role: You are the lead developer and architect of HuleEdu.

### Scope: CJ ↔ LPS serial bundling metrics, ENG5 heavy CI hardening, and next-step parity refinements

**Completed this session (2025-12-09):**
- **US-005.6 – BatchMonitor separation of concerns closed:**
  - Reviewed `services/cj_assessment_service/batch_monitor.py` and `cj_core_logic/batch_finalizer.py` plus unit tests to confirm:
    - BatchMonitor only decides + annotates stuck batches (80% threshold, forced-to-SCORING metadata, or FAILED + `CJAssessmentFailedV1`).
    - BatchFinalizer owns all completion state transitions, `CJBatchUpload.completed_at`, and dual event publishing, including `COMPLETE_FORCED_RECOVERY`.
  - Re-ran and validated:
    - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_monitor_unit.py`
    - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py`
  - Updated `TASKS/assessment/batchmonitor-separation-of-concerns.md`:
    - `status: 'completed'`, success criteria aligned with the event parity test and migration test.
    - Implementation files now reference:
      - `services/cj_assessment_service/enums_db.py` (`COMPLETE_FORCED_RECOVERY`)
      - `services/cj_assessment_service/alembic/versions/20251208_1200_cj_forced_recovery_status.py`
      - `services/cj_assessment_service/tests/unit/test_batch_monitor_unit.py`
      - `services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py`
      - `services/cj_assessment_service/tests/unit/test_batch_finalizer_idempotency.py`
      - `services/cj_assessment_service/tests/integration/test_cj_batch_status_forced_recovery_migration.py`
- **ENG5 heavy CI staging added (kept out of default fast CI path):**
  - Created `.github/workflows/eng5-heavy-suites.yml` with two jobs:
    - `ENG5 CJ Docker Semantics (regular + small-net)` (`eng5-cj-docker-regular-and-small-net`):
      - Runs ENG5 CJ docker semantics under serial_bundle + batching hints via:
        - `pdm run eng5-cj-docker-suite regular`
        - `pdm run eng5-cj-docker-suite small-net`
      - Assumes `.env` provides:
        - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
        - `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`
        - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
        - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
        - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true`
    - `ENG5 Mock Profile Parity Suite` (`eng5-profile-parity-suite`):
      - Uses `.env` + `pdm run llm-mock-profile <profile>` to run docker-backed ENG5 parity tests for:
        - `cj-generic` → `tests/eng5_profiles/test_cj_mock_parity_generic.py`
        - `eng5-anchor` → `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
        - `eng5-lower5` → `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
      - CI steps explicitly rewrite `LLM_PROVIDER_SERVICE_MOCK_MODE` in `.env` per profile:
        - `cj_generic_batch`, `eng5_anchor_gpt51_low`, `eng5_lower5_gpt51_low`
      - All runs are isolated to this heavy workflow; no default PR push/pull_request triggers.
- **Docs and TASKs aligned with ENG5 CI staging:**
  - `docs/operations/eng5-np-runbook.md`:
    - Added **“CI / validation for ENG5 heavy suites”** section documenting:
      - Workflow file name.
      - Job names.
      - Commands each job runs.
      - Local reproduction commands (copy-pasteable `pdm run eng5-cj-docker-suite` / `pdm run llm-mock-profile` / `pytest-root` examples).
  - `.claude/work/session/readme-first.md`:
    - Under “Mock Profiles & ENG5 Suites”, added explicit mapping from CI jobs to local reproduction commands and clarified that these suites live in a separate CI stage.
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`:
    - Added progress entry for 2025-12-09 describing the new ENG5 heavy CI workflow and how it validates serial-bundle semantics under `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`.
  - `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`:
    - Noted that the ENG5 mock profile parity suite now runs in `eng5-profile-parity-suite` as an opt-in heavy CI stage.

**Next session – recommended focus: ENG5 metrics & parity hardening**
1. **Add metrics-level assertions for CJ ↔ LPS serial bundling in docker tests**
   - Goal: ensure docker semantics tests validate Prometheus metrics as well as behaviour.
   - Files/tests to extend:
     - `tests/integration/test_cj_regular_batch_callbacks_docker.py`
     - `tests/integration/test_cj_regular_batch_resampling_docker.py`
     - `tests/integration/test_cj_small_net_continuation_docker.py`
   - Metrics/fields to assert (non-exhaustive, guided by `.claude/rules/071.2-prometheus-metrics-patterns.md` and CJ/LLM docs):
     - CJ-side: `cj_llm_requests_total{batching_mode="serial_bundle"}`, `cj_llm_batches_started_total{batching_mode}`, `cj_batch_state`, `cj_batch_progress_percentage`.
     - LPS-side: `llm_provider_serial_bundle_calls_total{provider,model}`, `llm_provider_serial_bundle_items_per_call{provider,model}`, queue expiry/wait-time metrics for `queue_processing_mode="serial_bundle"`.
   - Runner:
     - Locally: `pdm run eng5-cj-docker-suite regular` and `small-net` with serial_bundle settings in `.env`.
     - CI: rely on `eng5-cj-docker-regular-and-small-net` job in `eng5-heavy-suites.yml`.
2. **Refine ENG5 mock profile parity suite for queue semantics and batch diagnostics**
   - Goal: extend profile parity tests beyond callback shape/latency/token parity to include:
     - Queue wait-time distributions for ENG5 traces.
     - Serial-bundle vs per-request behaviour toggles (where applicable).
   - Files/tests to extend:
     - `tests/eng5_profiles/test_cj_mock_parity_generic.py`
     - `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
     - `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
     - Optionally orchestrator: `tests/eng5_profiles/test_eng5_profile_suite.py`
   - Tie back to TASKs:
     - `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md` (document new parity dimensions and metrics).
     - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md` (record which metrics are now pinned by ENG5 suites).
3. **(Optional stretch) Prepare follow-up work for provider `batch_api` mode tests**
   - Scope to hand off:
     - Identify where `LLM_PROVIDER_SERVICE_BATCH_API_MODE` and `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=provider_batch_api` should be exercised in docker tests once real batch APIs are available.
     - Outline candidate tests and metrics in the relevant TASK docs without changing code yet.

**Key files for next session:**
- CJ docker semantics & metrics:
  - `tests/integration/test_cj_small_net_continuation_docker.py`
  - `tests/integration/test_cj_regular_batch_resampling_docker.py`
  - `tests/integration/test_cj_regular_batch_callbacks_docker.py`
- ENG5 mock parity:
  - `tests/eng5_profiles/test_cj_mock_parity_generic.py`
  - `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
  - `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
  - `tests/eng5_profiles/test_eng5_profile_suite.py`
- Orchestration scripts & CI:
  - `scripts/llm_mgmt/mock_profile_helper.sh`
  - `scripts/llm_mgmt/eng5_cj_docker_suite.sh`
  - `.github/workflows/eng5-heavy-suites.yml`
- CI and testing rules/epic:
  - `.claude/rules/070-testing-and-quality-assurance.md`
  - `.claude/rules/101-ci-lanes-and-heavy-suites.md`
  - `docs/decisions/0024-eng5-heavy-c-lane-ci-strategy.md` (ADR-0024)
  - `docs/product/epics/ci-test-lanes-and-eng5-heavy-suites.md` (EPIC-011)
- BatchMonitor / BatchFinalizer (for reference only; US-005.6 is now closed):
  - `services/cj_assessment_service/batch_monitor.py`
  - `services/cj_assessment_service/cj_core_logic/batch_finalizer.py`
- Active TASKs to update as you progress:
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`
  - `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`

---

## CMS Batch Class Info Internal Endpoint (2025-12-09)

**COMPLETED:** `GET /internal/v1/batches/class-info` endpoint for batch→class lookup.

**Endpoint:** `GET /internal/v1/batches/class-info?batch_ids=<uuid1>,<uuid2>,...`

**Response:**
```json
{
  "<batch_id>": {"class_id": "<uuid>", "class_name": "Class Name"},
  "<batch_id_without_association>": null
}
```

**Files modified:**
- `services/class_management_service/protocols.py` - Added `get_class_info_for_batches()` to both protocols
- `services/class_management_service/implementations/class_repository_postgres_impl.py` - Repository method with metrics
- `services/class_management_service/implementations/class_repository_mock_impl.py` - Mock implementation
- `services/class_management_service/implementations/class_management_service_impl.py` - Service method
- `services/class_management_service/api/internal_routes.py` - `before_request` auth hook + route handler
- `services/class_management_service/tests/unit/test_batch_class_info.py` - 9 unit tests

**Authentication:** Uses RAS-canonical `before_request` hook pattern with `X-Internal-API-Key` + `X-Service-ID` headers.

**Task:** `TASKS/programs/teacher_dashboard_integration/cms-batch-class-info-internal-endpoint.md` (status: completed)

**Unblocks:** BFF Teacher Dashboard can now call CMS for class name enrichment.

---

## BFF Teacher Service (2025-12-08)

**New service added:** `services/bff_teacher_service/`
- FastAPI serving Vue 3 static assets at port 4101
- Docker compose integrated with volume mount for dev
- PDM scripts: `bff-build`, `bff-start`, `bff-logs`, `bff-restart`
- See frontend handoff for details: `frontend/.claude/work/session/handoff.md`

---

## API Gateway: BFF Teacher Proxy Tests (2025-12-08)

**Completed:**
- Created `services/api_gateway_service/tests/test_bff_teacher_routes.py` with 9 unit tests
- Tests cover: GET/POST success, identity header injection (X-User-ID, X-Correlation-ID, X-Org-ID), error handling (502), status code preservation, query param forwarding
- All tests pass, typecheck-all and lint pass

**Test pattern:** Uses `respx_mock` for HTTP mocking, `AuthTestProvider` + `InfrastructureTestProvider` from `test_provider.py`, mirrors `test_class_routes.py` pattern exactly.

---

## API Gateway: GET /v1/batches & Batch Routes Refactor (2025-12-08)

**Completed:**
- Refactored bloated `batch_routes.py` (787 LoC) into 4 SRP-compliant modules:
  - `_batch_utils.py` (129 LoC) – Shared utilities, status mapping, Pydantic models
  - `batch_commands.py` (159 LoC) – `POST /batches/register`, `PATCH /batches/{batch_id}/prompt`
  - `batch_pipelines.py` (206 LoC) – `POST /batches/{batch_id}/pipelines` (Kafka publishing)
  - `batch_queries.py` (167 LoC) – `GET /batches` (new listing endpoint)
- Added **internal auth headers** (`X-Internal-API-Key`, `X-Service-ID`) to RAS calls in `status_routes.py`
- Updated `app/main.py`, `tests/conftest.py`, `tests/test_batch_preflight.py`
- All 74 API Gateway tests pass

**New endpoint: `GET /v1/batches`:**
- JWT authentication (user_id from token)
- Pagination (`limit`, `offset`)
- Status filtering (client-facing values: `pending_content`, `ready`, `processing`, etc.)
- Proxies to RAS `/internal/v1/batches/user/{user_id}` with auth headers

**Next session – remaining work:**
1. **Add tests for `GET /v1/batches`** – Create `tests/test_batch_queries.py`:
   - `test_list_batches_success`
   - `test_list_batches_pagination`
   - `test_list_batches_status_filter_valid/invalid`
   - `test_list_batches_status_mapping`
   - `test_list_batches_ras_error`
   - `test_list_batches_auth_headers`
2. **Update API Gateway README** – Add endpoint docs, update file structure
3. **Update Frontend Integration Guide** – Add batch listing example (optional)

**Key files:**
- `services/api_gateway_service/routers/_batch_utils.py`
- `services/api_gateway_service/routers/batch_commands.py`
- `services/api_gateway_service/routers/batch_pipelines.py`
- `services/api_gateway_service/routers/batch_queries.py`
- `services/api_gateway_service/routers/status_routes.py` (fixed auth headers)

**Known limitation:** Status filter uses first internal status when client status maps to multiple (e.g., `processing` → 4 internal values). Full multi-status filtering would require RAS enhancement.

---

## Cross-Reference

- **Frontend session context:** `frontend/.claude/work/session/handoff.md`
- **Git strategy & build:** See `readme-first.md` or `frontend/.claude/work/session/readme-first.md`
