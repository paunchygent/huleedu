---
id: 'llm-provider-batch-api-phase-2'
title: 'LLM Provider Batch API Phase 2'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'integrations'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-10'
last_updated: '2025-12-12'
related: ['docs/decisions/0004-llm-provider-batching-mode-selection.md', 'TASKS/assessment/cj-llm-provider-batch-api-mode.md', 'TASKS/integrations/eng5-provider-batch-api-harness-coverage.md']
labels: []
---
# LLM Provider Batch API Phase 2

## Objective

Design, implement, and validate a **provider‑native batch API path** for CJ ↔ LLM Provider Service (LPS) workloads so that:

- `LLMBatchingMode.PROVIDER_BATCH_API` on the CJ side maps cleanly to `QueueProcessingMode.BATCH_API` in LPS.
- Batch‑API executions reach **parity in robustness and observability** with today’s `serial_bundle` mode for ENG5 / CJ workloads.
- Roll‑out is **feature‑flagged and metrics‑driven**, with a clear compatibility story back to `serial_bundle` and `per_request`.

## Current State & Completed Serial‑Bundle Work (Phase 1)

The following tasks and PRs have already delivered the serial‑bundle baseline that Phase 2 will build on:

- ✅ `TASKS/integrations/llm-batch-strategy-implementation.md` (archived):
  - Introduced the overall CJ ↔ LPS batching strategy, including:
    - `LLMBatchingMode` (CJ) and `QueueProcessingMode` (LPS) enums.
    - High‑level mapping between CJ modes and LPS queue modes.
- ✅ `TASKS/integrations/llm-batch-strategy-lps-implementation.md` (archived):
  - Implemented `QueueProcessingMode.SERIAL_BUNDLE` in LPS:
    - `SerialBundleStrategy` bundles compatible `QueuedRequest`s.
    - `process_comparison_batch` path in `ComparisonProcessorProtocol`.
    - Serial‑bundle metrics:
      - `llm_provider_serial_bundle_calls_total{provider,model}`
      - `llm_provider_serial_bundle_items_per_call{provider,model}`
- ✅ `TASKS/integrations/llm-batch-strategy-cj-config.md` (archived):
  - Added CJ‑side batching configuration and metadata wiring:
    - `Settings.LLM_BATCHING_MODE` and `LLM_BATCH_API_ALLOWED_PROVIDERS`.
    - `BatchConfigOverrides.llm_batching_mode_override`.
    - `build_llm_metadata_context` with `cj_llm_batching_mode` and `preferred_bundle_size` hints.
- ✅ `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md` (in_progress – serial_bundle slice done):
  - Stabilised CJ completion semantics and callback counters.
  - Wired `cj_llm_requests_total{batching_mode}` and `cj_llm_batches_started_total{batching_mode}`.
  - Validated ENG5 serial‑bundle metrics (CJ + LPS) via:
    - `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py`
    - `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py`
    - `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`
  - Added ENG5 mock‑profile LPS metrics guardrails:
    - `tests/eng5_profiles/eng5_lps_metrics_assertions.py`
    - `tests/eng5_profiles/test_cj_mock_parity_generic.py`
    - `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
    - `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`

> From Phase‑1 we **already have**: stable CJ serial‑bundle semantics, serial‑bundle queue behaviour in LPS, and ENG5 Heavy‑C metrics coverage for `queue_processing_mode="serial_bundle"`.

## Context – Phase 2 Provider Batch APIs

ADR‑0004 and `TASKS/assessment/cj-llm-provider-batch-api-mode.md` define `provider_batch_api` as:

- CJ generates **all pairs up to the comparison budget cap** in a **single initial wave**.
- CJ marks the batch with `llm_batching_mode="provider_batch_api"` in processing metadata and per‑request metadata.
- LPS, under `QueueProcessingMode.BATCH_API`, groups compatible `QueuedRequest`s into **provider batch jobs** (e.g. OpenAI Batch API, Anthropic Message Batches).
- CJ **finalizes after the first callback iteration** once callbacks reach the denominator/cap:
  - No stability‑driven resampling.
  - No additional comparison waves in `provider_batch_api` mode.

Phase 2 is where we:

- Turn `QueueProcessingMode.BATCH_API` and `BatchApiMode` from placeholders into a **first‑class execution mode**.
- Keep batch‑API work **behaviour‑compatible** with serial‑bundle callbacks:
  - Still one `LLMComparisonResultV1` per comparison.
  - Same callback topics and metadata envelope.
- Maintain ENG5 Heavy‑C lanes as the primary **validation harness** for `provider_batch_api` roll‑out.

## Phase 2 Scope (Design Level)

### Design Refinements & Constraints

The following refinements are **non‑negotiable guardrails** for the Phase‑2 design:

- **Job state persistence (future‑proofing)**
  - Batch jobs for real providers may run for hours; losing job state on LPS restart is unacceptable.
  - `BatchJobRef` **must** carry enough information to support future persistence and rehydration:
    - `provider_job_id` (OpenAI/Anthropic job id),
    - `provider`, `model`,
    - `created_at` / `completed_at`,
    - `status: BatchJobStatus`.
  - The `BatchJobManagerProtocol` **must** expose `get_job_status(job_ref)` and be designed with the assumption that `job_ref` may later be looked up from a DB‑backed “Job Repository” instead of purely in memory.

- **Error handling granularity (job vs item)**
  - Provider batch APIs distinguish:
    - **Job‑level failures** (upload/validation errors, quota issues).
    - **Item‑level failures** (per‑prompt, per‑comparison errors).
  - `BatchJobRef.status` describes the **job as a whole**; `BatchJobResult.status` describes the **individual item**.
    - A job can be `COMPLETED` even if some `BatchJobResult` entries are `FAILED`.
  - Queue processing must:
    - Mark each `QueuedRequest` based on its corresponding `BatchJobResult`.
    - Ensure metrics reflect both success and failure at the item level while job‑level metrics aggregate overall job health.

- **CJ “one‑shot to cap” semantics**
  - In `provider_batch_api` mode, CJ must:
    - Generate comparison pairs **up to, but never beyond**, `max_pairs_cap`.
    - Use the existing budget resolution path (normalization + `MAX_PAIRWISE_COMPARISONS`) as the **single source of truth**.
  - Changes in `ComparisonBatchOrchestrator.submit_initial_batch(...)` must be validated to ensure:
    - `max_pairs_cap` is respected even for very large nets (no unbounded pair generation).
    - The combination of `max_pairs_cap` + `completion_denominator()` remains mathematically consistent with continuation logic.

### CJ – PROVIDER_BATCH_API Behaviour

When the **effective CJ batching mode** is `LLMBatchingMode.PROVIDER_BATCH_API`:

- **Initial submission (single wave):**
  - `ComparisonBatchOrchestrator.submit_initial_batch(...)`:
    - Generates **all pairs up to `max_pairs_cap`** in one call to `generate_comparison_tasks(...)`.
    - Uses `preferred_bundle_size = len(comparison_tasks)` (capped at 64) in metadata.
    - Persists `"llm_batching_mode": "provider_batch_api"` into `CJBatchState.processing_metadata`.
    - Emits `cj_llm_requests_total{batching_mode="provider_batch_api"}` and
      `cj_llm_batches_started_total{batching_mode="provider_batch_api"}`.
  - `build_llm_metadata_context(...)`:
    - Always includes `"cj_llm_batching_mode": "provider_batch_api"` in `request_metadata` when hints are enabled.

- **Continuation / finalization semantics:**
  - `trigger_existing_workflow_continuation(...)`:
    - Resolves effective mode from processing metadata:
      - `effective_mode = LLMBatchingMode.PROVIDER_BATCH_API` when `"llm_batching_mode": "provider_batch_api"`.
    - In `provider_batch_api` mode:
      - Treats completion as **“all‑at‑once to cap”**:
        - Finalize when `callbacks_received >= completion_denominator()` or budget exhausted.
        - Ignore stability‑driven resampling; no additional comparison waves are scheduled.
      - `BatchFinalizer` is invoked once callbacks hit the cap; `request_additional_comparisons_for_batch(...)` is **not** called.
    - In non‑`provider_batch_api` modes, existing serial‑bundle / per‑request semantics remain unchanged.

- **ENG5 expectations (CJ side):**
  - ENG5 trials running with `LLMBatchingMode.PROVIDER_BATCH_API` will pin:
    - `cj_llm_requests_total{batching_mode="provider_batch_api"}`
    - `cj_llm_batches_started_total{batching_mode="provider_batch_api"}`.
  - No additional iteration metadata (resampling passes) should appear for these batches.

### LPS – QueueProcessingMode.BATCH_API Responsibilities

Under `QueueProcessingMode.BATCH_API` in the **LPS queue processor**:

- **Unit of work – jobs:**
  - The queue processor groups compatible `QueuedRequest`s into **batch jobs**:
    - Same resolved provider (`LLMProviderType`).
    - Same resolved model (manifest / overrides).
    - Compatible CJ hints:
      - `cj_llm_batching_mode="provider_batch_api"`.
      - Optional `preferred_bundle_size` used as a soft cap.
  - A **job** is the unit submitted to the provider batch API and tracked in job‑level metrics.

- **Job formation:**
  - For each dequeued request eligible for batch APIs:
    - Collect up to `BATCH_API_MAX_REQUESTS_PER_JOB` compatible items.
    - Build provider‑specific batch payloads (OpenAI JSONL, Anthropic message batches).
    - Persist a job reference (e.g. `batch_job_id`, provider/model, item IDs).
  - Non‑eligible requests (wrong provider/model/hints) are processed via existing `PER_REQUEST` / `SERIAL_BUNDLE` strategies.

- **Result mapping back to queued requests:**
  - Provider batch results are mapped back to the original `QueuedRequest`s by:
    - Job‑item identifiers (custom IDs in JSONL, `custom_id` in Anthropic/OpenAI batch APIs).
    - Each item yields **exactly one** `LLMComparisonResultV1`, preserving existing callback contracts.
  - Queue status transitions remain:
    - `QUEUED → PROCESSING → COMPLETED | FAILED | EXPIRED`.

- **Job‑level failure semantics:**
  - Job duties include:
    - Handling partial failures (some items succeed, some fail).
    - Applying retry policies at **job level** and/or **item level**.
  - On job‑level failure:
    - Items may be retried (subject to retry budget) or marked failed.
    - Queue metrics must expose failure modes (`result="failure"` and job status labels).

- **Batch‑API metrics (design targets):**
  - Job‑level:
    - `llm_provider_batch_api_jobs_total{provider,model,status}`:
      - `status ∈ {scheduled, succeeded, failed, expired, cancelled}`.
    - `llm_provider_batch_api_job_duration_seconds{provider,model}`:
      - Job wall‑clock durations, including provider queueing time.
    - `llm_provider_batch_api_items_per_job{provider,model}`:
      - Histogram of item counts per job (align caps with `BATCH_API_MAX_REQUESTS_PER_JOB`).
  - Item‑level:
    - Reuse existing queue metrics:
      - `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`
      - `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",result}`
      - `llm_provider_queue_expiry_total{provider,queue_processing_mode="batch_api",expiry_reason}`.

### Providers – OpenAI / Anthropic Batch Job Integration Shape

High‑level (implementation will be split into sub‑tasks):

- **OpenAI:**
  - Use the official Batch API for JSONL jobs.
  - Represent each CJ comparison as a JSONL line with:
    - `custom_id` mapping back to `QueuedRequest.queue_id` or a stable item key.
    - Request body mirroring the existing `LLMComparisonRequest`.
  - Poll for job completion; map results back to items and then to callbacks.

- **Anthropic:**
  - Use `/v1/messages/batches` for message batches.
  - Similar `custom_id` / item mapping semantics as OpenAI.

- **Common job manager responsibilities:**
  - Encapsulate provider‑specific job creation, polling, and cancellation.
  - Surface unified job‑level metrics back to LPS (`jobs_total`, `job_duration_seconds`, `items_per_job`).

### ENG5 Heavy Suites – Batch API Coverage (Future)

Once Phase‑2 BATCH_API execution is implemented:

- ENG5 CJ docker semantics tests (`tests/functional/cj_eng5/test_cj_*_docker.py`) should gain **provider_batch_api** variants that:
  - Run with:
    - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=provider_batch_api`
    - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api`
    - Provider‑specific `*_BATCH_API_MODE` set (e.g. OpenAI or Anthropic).
  - Assert:
    - CJ metrics by `batching_mode="provider_batch_api"`.
    - LPS queue metrics by `queue_processing_mode="batch_api"`.
    - Job‑level metrics (`llm_provider_batch_api_jobs_total`, `items_per_job`, `job_duration_seconds`).
- ENG5 mock profiles (`tests/eng5_profiles/*`) should eventually mirror these checks using mock providers and synthetic job IDs.

## Phase 2 Checklist (2.x)

> Status markers:  
> `[x]` = done in this repo, `[~]` = partially done, `[ ]` = planned.

- **Phase 2.1 – BATCH_API compatibility scaffolding (this session)**
  - [x] Make `QueueProcessingMode.BATCH_API` a first‑class mode in `QueueProcessingLoop`:
    - Explicit branch that routes through a dedicated Batch API execution path rather than `SerialBundleStrategy`.
    - Uses a distinct `queue_processing_mode="batch_api"` label in metrics.
  - [x] Ensure `QueueProcessorMetrics` and `get_queue_metrics()` treat `"batch_api"` like other modes:
    - `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",...}`.
    - `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",...}`.
  - [x] Add LPS tests:
    - Unit: construct `QueueProcessorImpl` with `queue_processing_mode=QueueProcessingMode.BATCH_API` and assert:
      - Completion metrics use `queue_processing_mode="batch_api"`.
    - Integration: reuse the serial‑bundle integration harness but set `QUEUE_PROCESSING_MODE=batch_api`, checking that:
      - `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api"}` samples exist.

- **Phase 2.2 – Internal job models and mock job manager**
  - [x] Introduce internal job models and status enums:
    - `BatchJobStatus`, `BatchJobRef`, `BatchJobItem`, `BatchJobResult`.
  - [x] Add `BatchJobManagerProtocol` describing:
    - `schedule_job(...) -> BatchJobRef`
    - `get_job_status(...) -> BatchJobRef`
    - `collect_results(...) -> list[BatchJobResult]`
    - `cancel_job(...) -> None`
  - [x] Implement an **in‑memory “instant completion” BatchJobManager**:
    - Stores jobs/items in memory.
    - Treats `schedule_job(...)` + `collect_results(...)` as a synchronous pipeline backed by `ComparisonProcessorProtocol`.
    - Serves as the default for tests and early wiring without real provider calls.

- **Phase 2.3 – LPS QueueProcessingMode.BATCH_API execution path**
  - [x] Implement true `BATCH_API` queue strategy using the job manager:
    - Job formation (grouping compatible `QueuedRequest`s based on provider, model, and `cj_llm_batching_mode`).
    - Job submission via `BatchJobManagerProtocol.schedule_job(...)`.
    - Mapping `BatchJobResult` entries back to per‑request callbacks and queue status transitions.
    - Extended unit coverage for error paths:
      - `test_batch_api_strategy_handles_collect_results_exception` exercises the job‑manager failure guard.
      - `test_execute_batch_api_handles_job_manager_error` ensures executor‑level outcomes remain per‑request failures.
  - [x] Wire job‑level metrics (initially using the mock manager, then real providers):
    - `llm_provider_batch_api_jobs_total{provider,model,status}`.
    - `llm_provider_batch_api_items_per_job{provider,model}`.
    - `llm_provider_batch_api_job_duration_seconds{provider,model}`.

- **Phase 2.4 – CJ provider_batch_api semantics**
  - [x] Persist `llm_batching_mode` into `CJBatchState.processing_metadata` on initial submission.
  - [x] Ensure single‑wave generation up to `max_pairs_cap` for `provider_batch_api`.
  - [x] Adjust continuation logic to:
    - Finalize when callbacks hit the denominator/cap.
    - Never schedule additional comparison waves in `provider_batch_api` mode.
  - [x] Accept per‑batch LLM batching overrides from ENG5 runner metadata:
    - Thread `llm_batching_mode_hint` from ENG5 request metadata into `CJAssessmentRequestData.batch_config_overrides["llm_batching_mode_override"]` via the CJ request transformer.
    - Normalize hints to `LLMBatchingMode` string values and feed them into `BatchConfigOverrides.llm_batching_mode_override` and `resolve_effective_llm_batching_mode(...)`.

- **Phase 2.5 – ENG5 Heavy‑C coverage and runbooks**
  - [x] Extend ENG5 docker semantics tests with `provider_batch_api` variants.
  - [x] Extend ENG5 mock profile parity suite with `queue_processing_mode="batch_api"` metrics.
  - [x] Update:
    - `docs/operations/eng5-np-runbook.md` (batch_api section).
    - `docs/operations/cj-assessment-runbook.md` (CJ modes table).
    - Any relevant CI lane docs (`.agent/rules/101-ci-lanes-and-heavy-suites.md`, ADR‑0004).
  - Note: ENG5 harness coverage is complete and validated locally via:
    - `pdm run eng5-cj-docker-suite batch-api`
    - `pdm run llm-mock-profile cj-generic-batch-api`
    - Stability fixes are tracked in `TASKS/integrations/eng5-provider-batch-api-harness-coverage.md`.

## Recommended Implementation Sequence (Developer Checklist)

To minimise refactors and keep the implementation aligned with the architecture, follow this sequence for Phase‑2 development:

1. **Domain modelling first**
   - Add `BatchJobStatus`, `BatchJobRef`, `BatchJobItem`, `BatchJobResult` to the LPS internal models.
   - Define `BatchJobManagerProtocol` in `services/llm_provider_service/protocols.py`.
2. **In‑memory job manager**
   - Implement a simple in‑memory `BatchJobManager` that:
     - Schedules jobs, immediately marks them as completed, and returns synthetic `BatchJobResult` entries.
     - Stores enough metadata on `BatchJobRef` to support future DB persistence.
3. **Wire QueueProcessingMode.BATCH_API**
   - Change the queue processor so `QueueProcessingMode.BATCH_API`:
     - Dequeues compatible requests and forms jobs.
     - Uses the job manager instead of `SerialBundleStrategy`.
     - Maps `BatchJobResult` back to per‑request callbacks and queue status.
4. **Metrics continuity**
   - Ensure existing queue metrics continue to work for `"batch_api"`:
     - `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`.
     - `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",result}`.
   - Add initial job‑level metrics:
     - `llm_provider_batch_api_jobs_total{provider,model,status}`.
     - `llm_provider_batch_api_items_per_job{provider,model}`.
5. **CJ & ENG5 alignment**
   - Implement CJ `provider_batch_api` metadata persistence and continuation semantics as described in `TASKS/assessment/cj-llm-provider-batch-api-mode.md`.
   - Only after LPS jobs are stable, add ENG5 `provider_batch_api` variants for:
     - CJ docker semantics tests.
     - ENG5 mock profile parity suites.

## Success Criteria

- CJ:
  - `LLMBatchingMode.PROVIDER_BATCH_API`:
    - Generates all comparisons up to the budget cap in a single wave.
    - Persists `llm_batching_mode="provider_batch_api"` into processing metadata.
    - Finalizes without resampling once callbacks reach the denominator/cap.
  - CJ metrics:
    - `cj_llm_requests_total{batching_mode="provider_batch_api"} >= 1` for ENG5 trials.
    - `cj_llm_batches_started_total{batching_mode="provider_batch_api"} >= 1`.

- LPS:
  - `QueueProcessingMode.BATCH_API` is observable and diagnosable:
    - Queue metrics label `queue_processing_mode="batch_api"` for wait‑time and callbacks.
    - Job‑level metrics exist and are exercised in tests.
  - Batch‑API executions preserve callback contracts:
    - One `LLMComparisonResultV1` per comparison.
    - No ENG5 artefact schema changes required.

- ENG5:
  - Heavy‑C suites have **serial_bundle** and **batch_api** configurations:
    - Serial‑bundle continues to pass with existing invariants.
    - Batch‑API mode passes with additional job‑level metric assertions.

## Related

- ADRs / Runbooks:
  - `docs/decisions/0004-llm-provider-batching-mode-selection.md`
  - `docs/operations/cj-assessment-runbook.md`
  - `docs/operations/eng5-np-runbook.md`
- Tasks:
  - `TASKS/integrations/llm-batch-strategy-implementation.md` (archived)
  - `TASKS/integrations/llm-batch-strategy-lps-implementation.md` (archived)
  - `TASKS/integrations/llm-batch-strategy-cj-config.md` (archived)
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`
  - `TASKS/assessment/cj-llm-provider-batch-api-mode.md`
