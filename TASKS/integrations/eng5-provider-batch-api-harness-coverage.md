---
id: eng5-provider-batch-api-harness-coverage
title: ENG5 Provider Batch API Harness Coverage
type: task
status: done
priority: medium
domain: integrations
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-12-11'
last_updated: '2026-02-01'
related:
- TASKS/integrations/llm-provider-batch-api-phase-2.md
labels:
- eng5
- provider-batch-api
- harness
---
# ENG5 Provider Batch API Harness Coverage

## Objective

Design and implement ENG5‑focused harness coverage for `LLMBatchingMode.PROVIDER_BATCH_API` ↔ `QueueProcessingMode.BATCH_API`, so that CJ + LPS provider‑batch semantics are exercised via realistic ENG5 flows and guarded by metrics‑based assertions.

## Context

- Phase‑2 provider batch API semantics are implemented and unit‑tested in:
  - CJ (`provider_batch_api` initial submission, single‑wave generation up to cap, continuation without additional waves).
  - LPS (`QueueProcessingMode.BATCH_API` via `BatchApiStrategy` + `BatchJobManager`, with job‑level metrics).
  - CJ now accepts per‑batch LLM batching overrides from ENG5 by threading `llm_batching_mode_hint` in ENG5 request metadata into `BatchConfigOverrides.llm_batching_mode_override` via the CJ request transformer and comparison request normalizer.
- The primary gap is **ENG5 Heavy‑C validation**:
  - CJ ENG5 docker semantics tests currently only cover `serial_bundle`.
  - ENG5 mock‑profile parity suites pin `queue_processing_mode="serial_bundle"` metrics only.
  - Runbooks describe provider‑batch behaviour and metrics, but there is no end‑to‑end ENG5 coverage proving those expectations.
- This task is a child/companion to `TASKS/integrations/llm-provider-batch-api-phase-2.md` and focuses exclusively on the ENG5 harness layer (not new core semantics).

## Plan

1. **CJ ENG5 docker variants** ✅
   - Added a provider-batch regular-batch docker semantics test using ENG5 runner semantics:
     - `tests/functional/cj_eng5/test_cj_regular_batch_provider_batch_api_docker.py`
   - Harness entrypoint:
     - `pdm run eng5-cj-docker-suite batch-api` (wired in `scripts/llm_mgmt/eng5_cj_docker_suite.sh`)
   - Assertions:
     - `cj_llm_requests_total{batching_mode="provider_batch_api"} >= 1`
     - `cj_llm_batches_started_total{batching_mode="provider_batch_api"} >= 1`
     - `CJBatchState.processing_metadata["llm_batching_mode"] == "provider_batch_api"`
     - Stored original request contains `batch_config_overrides.llm_batching_mode_override == "provider_batch_api"`

2. **ENG5 mock‑profile parity extensions** ✅
   - Added a batch_api metrics-focused suite for `cj_generic_batch`:
     - `tests/eng5_profiles/test_cj_mock_batch_api_metrics_generic.py`
   - Added shared assertions:
     - `tests/eng5_profiles/eng5_lps_metrics_assertions.py::assert_lps_batch_api_metrics_for_mock_profile`
   - Added a helper profile to run it:
     - `pdm run llm-mock-profile cj-generic-batch-api` (in `scripts/llm_mgmt/mock_profile_helper.sh`)

3. **ENG5 runner configuration & observability** ✅
   - Reused the existing pipe (`--llm-batching-mode` → `llm_batching_mode_hint` → CJ overrides) without re-implementation.
   - Provider-batch docker semantics test validates the stored override payload to ensure the pipe is actually used.

4. **Runbooks and CI lanes** ✅
   - Updated runbooks:
     - `docs/operations/eng5-np-runbook.md`
     - `docs/operations/cj-assessment-runbook.md`
   - Updated CI + lane docs:
     - `.github/workflows/eng5-heavy-suites.yml` (adds provider_batch_api + batch_api mock profile steps)
     - `.agent/rules/101-ci-lanes-and-heavy-suites.md`

## Success Criteria

- At least one **regular‑batch** CJ ENG5 docker semantics test (no small‑net) exercises `provider_batch_api` end‑to‑end, with CJ metrics pinned by batching mode.
- ENG5 mock‑profile parity suite includes provider‑batch coverage with stable expectations for `queue_processing_mode="batch_api"` and job‑level metrics (using seconds for durations with appropriate bucket ranges).
- The ENG5 runner supports `--llm-batching-mode provider_batch_api` as a real per‑batch override that reaches CJ’s `BatchConfigOverrides.llm_batching_mode_override`.
- ENG5 runbooks clearly describe how to run and interpret provider‑batch ENG5 trials, including the runner override and env settings.
- `TASKS/integrations/llm-provider-batch-api-phase-2.md` Phase 2.5 checklist items for ENG5 coverage can be marked complete once this task’s work is merged and validated.

## Stabilization Notes (2025-12-12)

- Fixed `tests/eng5_profiles/test_cj_mock_batch_api_metrics_generic.py` to read the 202 response body inside the `aiohttp` response context manager (previously raised `ClientConnectionError: Connection closed`).
- Hardened `tests/functional/conftest.py` Redis cleanup to:
  - wait for Redis readiness via bounded `PING`, and
  - use `SCAN` iteration instead of `KEYS` for deleting `test:*` / `ws:*` prefixed keys.
- Deliberate scope limit: kept batch_api Heavy‑C coverage limited to `cj_generic_batch` to avoid expanding runtime with additional ENG5 profiles (anchor/lower5).
- Local validation (host-driven, Docker-backed):
  - `pdm run eng5-cj-docker-suite batch-api`
  - `pdm run llm-mock-profile cj-generic-batch-api`
- CI parity check (local): provider_batch_api docker semantics also passes with `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=false` (matches `.github/workflows/eng5-heavy-suites.yml`).

## Related

- `TASKS/integrations/llm-provider-batch-api-phase-2.md`
- `TASKS/assessment/cj-llm-provider-batch-api-mode.md`
- `docs/operations/eng5-np-runbook.md`
- `docs/operations/cj-assessment-runbook.md`
