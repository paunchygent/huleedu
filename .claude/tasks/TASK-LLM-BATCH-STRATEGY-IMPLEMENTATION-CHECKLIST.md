# TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION – Developer Checklist

This checklist is a child document for `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` and the high-level
planning task `TASK-LLM-BATCH-STRATEGY.md`.

It is intended for the engineer implementing the CJ + LLM Provider Service batching strategy and
verifying that both normal BOS/ELS flows and ENG5 runner flows behave correctly under the new
configuration.

---

## Phase 1 – CJ configuration & feature flags

### 1. Add CJ batching configuration enums & fields

- [ ] **Introduce `LLMBatchingMode` enum in CJ config**
  - File: `services/cj_assessment_service/config.py`
  - Enum values:
    - `PER_REQUEST`
    - `PROVIDER_SERIAL_BUNDLE`
    - `PROVIDER_BATCH_API`
  - Ensure the enum is used only as a *hint*; LLM Provider Service owns the physical batching.

- [ ] **Add `LLM_BATCHING_MODE` to CJ `Settings`**
  - Default: `LLMBatchingMode.PER_REQUEST` (preserve current behaviour).
  - Description: explains each mode and explicitly states that provider service implements the
    actual batching strategy.
  - Confirm env var mapping via `env_prefix="CJ_ASSESSMENT_SERVICE_"` still works as expected.

- [ ] **Add `LLM_BATCH_API_ALLOWED_PROVIDERS` to CJ `Settings`**
  - Default: `[LLMProviderType.OPENAI, LLMProviderType.ANTHROPIC]`.
  - Guardrail: CJ must not opt into provider batch APIs for providers not listed here.
  - Verify that changing this set does not break existing non-batch flows.

### 2. Wire per-request overrides (BatchConfigOverrides)

- [ ] **Extend `BatchConfigOverrides` with `llm_batching_mode_override`**
  - File: `services/cj_assessment_service/cj_core_logic/batch_config.py`.
  - Field: `llm_batching_mode_override: LLMBatchingMode | None`.
  - Behaviour: when set, it must take precedence over `Settings.LLM_BATCHING_MODE`.

- [ ] **Resolve effective batching mode in comparison processing**
  - File: `services/cj_assessment_service/cj_core_logic/comparison_processing.py`.
  - In `submit_comparisons_for_async_processing` (and any retry paths that submit batches):
    - Compute `effective_mode` from `batch_config_overrides.llm_batching_mode_override` or
      `settings.LLM_BATCHING_MODE`.
    - Pass `effective_mode` into logging context (`log_extra`) to make debugging easy.
  - Ensure ENG5 runner and BOS/ELS can drive overrides via existing
    `batch_config_overrides` shape without schema changes at the API boundary.

### 3. Propagate batching metadata to LLM Provider Service

- [ ] **Extend metadata in `LLMInteractionImpl.perform_comparisons`**
  - File: `services/cj_assessment_service/implementations/llm_interaction_impl.py`.
  - For each `ComparisonTask`, enrich `request_metadata` with:
    - `cj_batch_id: str` – `str(cj_batch_id)`.
    - `cj_source: str` – e.g. `"els"`, `"bos"`, `"eng5_runner"` (derived from request data).
    - `cj_llm_batching_mode: str` – `effective_mode.value`.
    - `cj_request_type: str` – e.g. `"cj_comparison"`, `"cj_retry"`.
  - Confirm that these keys are present in `LLMComparisonRequest.metadata` in the provider service
    (via a small integration or unit test).

### 4. CJ-side tests & validation

- [ ] **Unit tests for `LLMBatchingMode` resolution**
  - Add a focused test module, e.g.
    `services/cj_assessment_service/tests/unit/test_llm_batching_config.py`.
  - Cover:
    - Default: no overrides → `effective_mode == settings.LLM_BATCHING_MODE`.
    - Override set in `batch_config_overrides` → `effective_mode` equals override.
    - Invalid values are rejected at Pydantic validation time (enum enforcement).

- [ ] **Unit tests for metadata propagation**
  - Use a small test double for `LLMProviderProtocol` to capture `LLMComparisonRequest` objects.
  - Assertions:
    - `metadata["cj_batch_id"]` matches the CJ batch id used in test.
    - `metadata["cj_llm_batching_mode"]` matches the resolved `effective_mode`.
    - `metadata["cj_source"]` and `metadata["cj_request_type"]` are present and sensible.

---

## Phase 2 – LLM Provider Service serial bundling (no async batch APIs yet)

### 1. Add queue processing modes and serial-bundle limits

- [ ] **Introduce `QueueProcessingMode` and `BatchApiMode` enums in LPS config**
  - File: `services/llm_provider_service/config.py`.
  - `QueueProcessingMode` values:
    - `PER_REQUEST`
    - `SERIAL_BUNDLE`
    - `BATCH_API`
  - `BatchApiMode` values:
    - `DISABLED`
    - `NIGHTLY`
    - `OPPORTUNISTIC`

- [ ] **Extend LPS `Settings` with queue/batch fields**
  - Add:
    - `QUEUE_PROCESSING_MODE: QueueProcessingMode = PER_REQUEST`.
    - `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL: int` (default ~8, constrained within [1, 64]).
  - Keep batch API mode fields present but initially unused for behaviour changes in this phase.

### 2. Implement `QueueProcessingMode.SERIAL_BUNDLE`

- [ ] **Dispatch to serial-bundle path in `_process_queue_loop`**
  - File: `services/llm_provider_service/implementations/queue_processor_impl.py`.
  - When `QUEUE_PROCESSING_MODE == SERIAL_BUNDLE`:
    - Use a new helper method (e.g. `_process_request_serial_bundle`) instead of
      `_process_request(request)`.

- [ ] **Implement `_process_request_serial_bundle`**
  - Behaviour:
    - Dequeue the first `QueuedRequest`.
    - Resolve provider + overrides exactly as in `_process_request`.
    - Dequeue additional requests until either:
      - `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` is reached, or
      - No more compatible requests are available.
    - Compatibility criteria:
      - Same resolved provider and model.
      - Optionally same `cj_llm_batching_mode` when present in `request_data.metadata`.
    - Invoke a batch processing method on `ComparisonProcessorImpl`.

- [ ] **Add `ComparisonProcessorImpl.process_comparison_batch`**
  - File: `services/llm_provider_service/implementations/comparison_processor_impl.py`.
  - Signature (conceptual):
    - `async def process_comparison_batch(provider, requests, correlation_ids, **overrides)`.
  - First iteration:
    - Implement as a simple loop calling `process_comparison` per request.
    - This gives a single code path for both serial-bundle and per-request modes without changing
      external behaviour.

- [ ] **Map batch results back to queue handlers**
  - For each `(QueuedRequest, LLMOrchestratorResponse)` pair in the batch:
    - Reuse `_handle_request_success` for success cases.
    - Wrap errors in `HuleEduError` and reuse `_handle_request_hule_error` for failure cases.
  - Ensure that queue status transitions and callback events are identical to the
    `QueueProcessingMode.PER_REQUEST` path.

### 3. LPS-side metadata & diagnostics

- [ ] **Enrich queued requests with provider-side metadata**
  - After resolving provider/model in `_process_request` / `_process_request_serial_bundle`, add:
    - `resolved_provider` to `request.request_data.metadata`.
    - `resolved_model` to `request.request_data.metadata`.
    - `queue_processing_mode` to `request.request_data.metadata`.
  - These fields should be visible in logs and can be used for bundle grouping and diagnostics.

- [ ] **Serial-bundling tests**
  - Add unit tests for `_process_request_serial_bundle` that:
    - Simulate a queue with multiple compatible and incompatible requests.
    - Assert that compatible requests are processed together and incompatible ones are left for a
      later batch or processed separately.
    - Verify that per-request callbacks and queue status updates remain correct.

---

## Phase 3 – Metrics, diagnostics & observability

### 1. Serial-bundling metrics

- [ ] **Add Prometheus metrics for serial bundling**
  - New metrics (suggested):
    - `llm_serial_bundle_calls_total{provider, model}`.
    - `llm_serial_bundle_items_per_call_bucket{provider, model}`.
  - Instrumentation points:
    - After each successful call to `process_comparison_batch` in LPS.

- [ ] **Compare serial-bundle vs per-request behaviour**
  - Use metrics dashboards to check:
    - External HTTP calls / comparisons ratio.
    - Error rates in serial-bundle mode vs per-request.
    - Queue latency and throughput.

### 2. CJ exposure of batching metrics

- [ ] **Add CJ-level counters/gauges for LLM usage by batching mode**
  - File: `services/cj_assessment_service/metrics.py` (or equivalent).
  - Metrics examples:
    - `cj_llm_requests_total{batching_mode}`.
    - `cj_llm_batches_started_total{batching_mode}`.
  - Ensure ENG5 runner can correlate its runs with batching mode via logs or metrics labels.

- [ ] **Update diagnostics scripts/docs for batching**
  - Extend relevant scripts (e.g. ENG5 diagnostics, batch inspection tooling) to:
    - Show the `LLM_BATCHING_MODE` used for a CJ batch.
    - Summarize LLM calls and/or external call counts if available from LPS metrics.

### 3. Documentation and runbooks

- [ ] **Document batching modes and trade-offs**
  - Update `.claude/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` or related docs to:
    - Explain when to choose `PER_REQUEST`, `PROVIDER_SERIAL_BUNDLE`, or `PROVIDER_BATCH_API`.
    - Capture any provider-specific caveats discovered during testing.

- [ ] **Update runbooks with new failure modes**
  - Extend existing CJ / LLM Provider Service runbooks to cover:
    - Debugging a stuck or failing serial-bundle run.
    - Rolling back from `SERIAL_BUNDLE` to `PER_REQUEST` in case of issues.
    - How to selectively enable serial bundling for ENG5 or other heavy workloads.

---

## Final success checklist (matches parent task)

- [ ] CJ `Settings` exposes `LLM_BATCHING_MODE` and optional per-request overrides
      (`llm_batching_mode_override`) without breaking existing BOS/ELS/ENG5 flows.
- [ ] CJ correctly tags outgoing LLM requests with batching metadata
      (`cj_batch_id`, `cj_source`, `cj_llm_batching_mode`, `cj_request_type`).
- [ ] LLM Provider Service supports `QueueProcessingMode.SERIAL_BUNDLE` and can process compatible
      queued requests in grouped calls without changing external CJ/RAS contracts.
- [ ] Metrics confirm that serial bundling reduces external HTTP calls per comparison without
      materially increasing error rates or queue latency.
- [ ] Diagnostics and runbooks are updated so that engineers can see which batching mode was used
      for a given CJ batch and know how to toggle/revert modes safely.
