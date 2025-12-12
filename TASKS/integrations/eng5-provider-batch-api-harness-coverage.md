---
id: 'eng5-provider-batch-api-harness-coverage'
title: 'ENG5 Provider Batch API Harness Coverage'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'integrations'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-11'
last_updated: '2025-12-11'
related: ['TASKS/integrations/llm-provider-batch-api-phase-2.md']
labels: ['eng5', 'provider-batch-api', 'harness']
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

1. **CJ ENG5 docker variants**
   - Extend the regular ENG5 CJ docker semantics test (e.g. `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py`) with a `provider_batch_api` variant; **small‑net coverage is explicitly out of scope for this task**.
   - Configure trials so that:
     - CJ’s effective batching mode is selected **per batch** via the ENG5 runner (`--llm-batching-mode provider_batch_api`), wired into `BatchConfigOverrides.llm_batching_mode_override` in CJ.
     - LPS queue mode uses `QueueProcessingMode.BATCH_API` via env:
       - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api`
       - Provider‑specific `*_BATCH_API_MODE` flags set per ADR‑0004.
   - Assert CJ metrics:
     - `cj_llm_requests_total{batching_mode="provider_batch_api"} >= 1`
     - `cj_llm_batches_started_total{batching_mode="provider_batch_api"} >= 1`.

2. **ENG5 mock‑profile parity extensions**
   - Add a provider‑batch profile/parameter to `tests/eng5_profiles/*` using the mock provider + ENG5 model pair.
   - Assert LPS queue + job metrics for `batch_api` (keeping Prometheus‑style **seconds** as the canonical time unit, with bucket ranges chosen to cover multi‑hour jobs):
     - `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`
     - `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",result}`
     - `llm_provider_batch_api_jobs_total{provider,model,status}`
     - `llm_provider_batch_api_items_per_job{provider,model}`
     - `llm_provider_batch_api_job_duration_seconds{provider,model}`.

3. **ENG5 runner configuration & observability**
   - Rely on the existing ENG5 → CJ plumbing so that:
     - `--llm-batching-mode` on the ENG5 runner sets `llm_batching_mode_hint` in request metadata, which CJ maps into `CJAssessmentRequestData.batch_config_overrides["llm_batching_mode_override"]` and then into `BatchConfigOverrides.llm_batching_mode_override` / `resolve_effective_llm_batching_mode(...)`.
   - Ensure ENG5 docker/profile harness runs and artefacts clearly label provider‑batch trials (requested batching mode, effective CJ/LPS modes, job metrics snapshot), using the per‑batch override pipeline as a prerequisite rather than re‑implementing it here.

4. **Runbooks and CI lanes**
   - Update `docs/operations/eng5-np-runbook.md` and `docs/operations/cj-assessment-runbook.md`:
     - Document how to run ENG5 provider‑batch trials locally (flags, env, example commands).
     - Clarify which suites exercise `provider_batch_api` vs `serial_bundle`.
   - Plan for a future CI lane that:
     - Uses an **instant‑return mock** for batch jobs (no long‑running “realistic” provider batch tests).
     - Focuses on semantic correctness and metrics invariants rather than end‑to‑end wall‑clock behaviour.
     - Is documented in `.agent/rules/101-ci-lanes-and-heavy-suites.md` once stable.

## Success Criteria

- At least one **regular‑batch** CJ ENG5 docker semantics test (no small‑net) exercises `provider_batch_api` end‑to‑end, with CJ metrics pinned by batching mode.
- ENG5 mock‑profile parity suite includes provider‑batch coverage with stable expectations for `queue_processing_mode="batch_api"` and job‑level metrics (using seconds for durations with appropriate bucket ranges).
- The ENG5 runner supports `--llm-batching-mode provider_batch_api` as a real per‑batch override that reaches CJ’s `BatchConfigOverrides.llm_batching_mode_override`.
- ENG5 runbooks clearly describe how to run and interpret provider‑batch ENG5 trials, including the runner override and env settings.
- `TASKS/integrations/llm-provider-batch-api-phase-2.md` Phase 2.5 checklist items for ENG5 coverage can be marked complete once this task’s work is merged and validated.

## Related

- `TASKS/integrations/llm-provider-batch-api-phase-2.md`
- `TASKS/assessment/cj-llm-provider-batch-api-mode.md`
- `docs/operations/eng5-np-runbook.md`
- `docs/operations/cj-assessment-runbook.md`
