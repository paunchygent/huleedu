# TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION – Developer Checklist

This checklist is a child document for `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` and the high-level
planning task `TASK-LLM-BATCH-STRATEGY.md`.

It is intended for the engineer implementing the CJ + LLM Provider Service batching strategy and
verifying that both normal BOS/ELS flows and ENG5 runner flows behave correctly under the new
configuration.

---

## Implementation Status (Updated 2025-11-17)

**Overall Progress**: ~40% complete (Phase 1 ✅, Phase 2/3 pending)

### Phase Breakdown

- **Phase 1 (CJ Configuration)**: ✅ COMPLETE
  - `LLMBatchingMode` + `LLM_BATCHING_MODE` shipped
  - `BatchConfigOverrides.llm_batching_mode_override` + `resolve_effective_llm_batching_mode()` in production with provider guardrails
  - Metadata now includes `cj_batch_id`, `cj_source`, `cj_request_type`, and always reflects the effective batching mode
  - Tests cover config resolution, metadata adapter behaviour, LLM interaction metadata, retry metadata, and continuation persistence

- **Phase 2 (LPS Serial Bundling)**: 6 complete, 3 partial, 4 incomplete
  - ✅ `process_comparison_batch` method wired end-to-end
  - ✅ Result mapping to callbacks implemented
  - ✅ Basic + targeted serial bundle unit tests exist
  - ✅ Queue config + `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` enforcement live in Settings/README
  - ✅ Serial bundle path now drains multiple compatible requests per loop iteration with fairness + pending-request handoff
  - ⚠️ Metadata enrichment + diagnostics still WIP (Phase 3 dependency)
  - ❌ Missing: provider-side metadata echo, batch metrics, and production rollout docs

- **Phase 3 (Metrics)**: 0 complete, 0 partial, 8 incomplete
  - ❌ No metrics implemented

### Critical Gaps

1. **LLM Provider metadata trail still thin** – need to enrich queued requests + callbacks with `resolved_provider`, `resolved_model`, and `queue_processing_mode` for diagnostics/tests.
2. **Observability gap** – serial bundle metrics (bundle size, per-provider counts) still missing pending Phase 3 work.
3. **Rollout/runbook guidance** – need ENG5-first rollout plan + doc updates before enabling serial bundling in production.

**Related tasks:**
 - `.claude/work/tasks/TASK-LLM-QUEUE-EXPIRY-METRICS-FIX.md` – LLM queue expiry metrics and observability.
 - `.claude/work/tasks/TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX.md` – Serial bundle metadata, metrics, integration tests, and rollout diagnostics.

### Next Steps

Focus on Phase 2 (LLM Provider serial bundling) now that CJ configuration + metadata are complete.

---

## CJ comparison submission modes and LLM batching

CJ has two **comparison submission shapes**:

- **Batched (all comparisons at once, future optional)**  
  - *Planned* mode for workloads that should hand the full comparison budget to LLM Provider in one go (e.g. for provider-level batch/discount APIs).
  - CJ would generate *all* remaining comparison pairs for a batch in one call to [generate_comparison_tasks](cci:1://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/cj_core_logic/pair_generation.py:27:0-139:27), up to `MAX_PAIRWISE_COMPARISONS`.  
  - Call pattern (conceptual):

    ```python
    comparison_tasks = await generate_comparison_tasks(
        essays_for_comparison=essays_for_api_model,
        db_session=session,
        cj_batch_id=cj_batch_id,
        existing_pairs_threshold=settings.MAX_PAIRWISE_COMPARISONS,
        max_pairwise_comparisons=settings.MAX_PAIRWISE_COMPARISONS,
        correlation_id=correlation_id,
    )
    ```

  - Intended only when `LLMBatchingMode.PROVIDER_BATCH_API` is enabled and the LLM Provider
    Service has batch APIs configured for the target provider.

- **Bundled (iterative, stability-driven, current default)**  
  - **Current behaviour** in CJ Assessment for both initial submissions and continuation runs.
  - CJ generates comparison pairs in **small bundles** per iteration, recomputes Bradley–Terry
    scores, and checks for stability between iterations.
  - Bundle size is controlled by `COMPARISONS_PER_STABILITY_CHECK_ITERATION`; total budget is
    capped by `MAX_PAIRWISE_COMPARISONS` via the comparison budget logic in
    `comparison_processing._resolve_requested_max_pairs`.
  - Call pattern (per iteration):

    ```python
    comparison_tasks_for_llm = await generate_comparison_tasks(
        essays_for_comparison=essays_for_api_model,
        db_session=session,
        cj_batch_id=cj_batch_id,
        existing_pairs_threshold=settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION,
        max_pairwise_comparisons=settings.MAX_PAIRWISE_COMPARISONS,
        correlation_id=correlation_id,
    )
    ```

  - After each bundle is processed, CJ:
    - recomputes scores,
    - applies the stability check (`MIN_COMPARISONS_FOR_STABILITY_CHECK` and
      `SCORE_STABILITY_THRESHOLD`), and
    - either requests another bundle or finalizes the batch.

### Relationship to `LLMBatchingMode`

The `LLMBatchingMode` enum in CJ config (values: `PER_REQUEST`, `PROVIDER_SERIAL_BUNDLE`,
`PROVIDER_BATCH_API`) is treated as a **hint** that shapes *both*:

- how CJ structures comparison submission (batched vs bundled), and  
- how the LLM Provider Service is expected to choose its internal batching strategy.

A typical mapping is:

- `LLMBatchingMode.PER_REQUEST`  
  - CJ may still use the **bundled, stability-driven** mode, but each comparison or small
    bundle is expected to be sent as individual provider calls.

- `LLMBatchingMode.PROVIDER_SERIAL_BUNDLE`  
  - CJ uses the **bundled** mode and hands small comparison bundles to the provider, which may
    group them into its own serial bundles.

- `LLMBatchingMode.PROVIDER_BATCH_API`  
  - CJ prefers the **batched** mode, generating all comparisons up front (within
    `MAX_PAIRWISE_COMPARISONS`) so the provider can call its batch/discount API efficiently.

In all cases, the LLM Provider Service remains the **source of truth** for physical batching;
CJ only controls *when* and *how many* `ComparisonTask`s are generated and handed off.

#### Batching mode mapping matrix (sketch)

| CJ `LLMBatchingMode`       | Typical LPS `QueueProcessingMode` | Typical LPS `BatchApiMode` | Notes |
|----------------------------|-----------------------------------|----------------------------|-------|
| `PER_REQUEST`              | `per_request`                     | `disabled`                 | Default for most BOS/ELS flows. CJ may still generate small bundles per stability loop, but each comparison is expected to be an independent provider call. |
| `SERIAL_BUNDLE`            | `serial_bundle`                   | `disabled`                 | CJ uses bundled, stability-driven submission while LPS groups compatible dequeues into serial bundles. Primary candidate for ENG5-heavy workloads once metrics look healthy. |
| `PROVIDER_BATCH_API`       | `serial_bundle`                   | `nightly` / `opportunistic`| Future-facing mode for provider-native batch APIs. CJ prefers fully batched submissions; LPS decides when to flip on true batch endpoints per provider. |

---

For the full implementation plan and design rationale, see  
`TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md`.

---

## Phase 1 – CJ configuration & feature flags ✅ COMPLETE

### 1. Add CJ batching configuration enums & fields

- [x] **Introduce `LLMBatchingMode` enum in CJ config** ✅ COMPLETE
  - File: `libs/common_core/src/common_core/config_enums.py:29-34`
  - Enum values: `PER_REQUEST`, `SERIAL_BUNDLE`, `PROVIDER_BATCH_API`
  - Ensure the enum is used only as a *hint*; LLM Provider Service owns the physical batching.

- [x] **Add `LLM_BATCHING_MODE` to CJ `Settings`** ✅ COMPLETE
  - File: `services/cj_assessment_service/config.py:118-124`
  - Default: `LLMBatchingMode.PER_REQUEST` (preserves current behaviour) ✅
  - Description: explains each mode and explicitly states that provider service implements the
    actual batching strategy.
  - Confirm env var mapping via `env_prefix="CJ_ASSESSMENT_SERVICE_"` still works as expected.

- [x] **Add `LLM_BATCH_API_ALLOWED_PROVIDERS` to CJ `Settings`**
  - Default: `[LLMProviderType.OPENAI, LLMProviderType.ANTHROPIC]`.
  - Guardrail: CJ now auto-falls back when a provider isn’t in the allow-list (empty list means "no restriction"; documented here for ops awareness).
  - Verified via unit tests + manual inspection that non-batch flows are unaffected.

### 2. Wire per-request overrides (BatchConfigOverrides)

- [x] **Extend `BatchConfigOverrides` with `llm_batching_mode_override`**
  - File: `services/cj_assessment_service/cj_core_logic/batch_config.py`.
  - Field: `llm_batching_mode_override: LLMBatchingMode | None`.
  - Behaviour: when set, it must take precedence over `Settings.LLM_BATCHING_MODE`.

- [x] **Resolve effective batching mode in comparison processing**
  - File: `services/cj_assessment_service/cj_core_logic/comparison_processing.py`.
  - In `submit_comparisons_for_async_processing` (and any retry paths that submit batches):
    - Compute `effective_mode` from `batch_config_overrides.llm_batching_mode_override` or
      `settings.LLM_BATCHING_MODE`.
    - Pass `effective_mode` into logging context (`log_extra`) to make debugging easy.
  - Ensure ENG5 runner and BOS/ELS can drive overrides via existing
    `batch_config_overrides` shape without schema changes at the API boundary.

### 3. Propagate batching metadata to LLM Provider Service

- [x] **Extend metadata in `LLMInteractionImpl.perform_comparisons`**
  - File: `services/cj_assessment_service/implementations/llm_interaction_impl.py`.
  - Status: `CJLLMComparisonMetadata` model exists in `models_api.py:52-77`
  - For each `ComparisonTask`, enrich `request_metadata` with:
    - `cj_batch_id: str` – forwarded via metadata_context + adapter.
    - `cj_source: str` – derived from request data/continuations (`els` default, `cj_retry` path inherits snapshot data).
    - `cj_llm_batching_mode: str` – now reflects the *effective* resolved mode.
    - `cj_request_type: str` – distinguishes initial (`cj_comparison`) vs retry submissions.
  - Confirm that these keys are present in `LLMComparisonRequest.metadata` in the provider service
    (via a small integration or unit test).
  - Ensure `request_metadata` is built via `CJLLMComparisonMetadata`
    only, and that this model remains **strictly additive**:
    existing keys (`"essay_a_id"`, `"essay_b_id"`,
    `"bos_batch_id"`) must keep their current names and semantics so
    that legacy consumers continue to work. ✅ CONFIRMED

### 4. CJ-side tests & validation

- [x] **Unit tests for `LLMBatchingMode` resolution**
  - Add a focused test module, e.g.
    `services/cj_assessment_service/tests/unit/test_llm_batching_config.py`.
  - Cover:
    - Default: no overrides → `effective_mode == settings.LLM_BATCHING_MODE`.
    - Override set in `batch_config_overrides` → `effective_mode` equals override.
    - Invalid values are rejected at Pydantic validation time (enum enforcement).
  - NOTE: Cannot be tested until `resolve_effective_llm_batching_mode()` function exists

- [x] **Unit tests for metadata propagation**
  - File: `services/cj_assessment_service/tests/unit/test_llm_metadata_adapter.py:35-46` ✅
  - Use a small test double for `LLMProviderProtocol` to capture `LLMComparisonRequest` objects.
  - Assertions:
    - `metadata["cj_batch_id"]`, `metadata["cj_source"]`, `metadata["cj_request_type"]`, and `metadata["cj_llm_batching_mode"]` asserted in unit tests, plus integration coverage for persistence/continuation flows.
    - `metadata["cj_llm_batching_mode"]` matches the resolved `effective_mode`. ✅ TESTED
    - `metadata["cj_source"]` and `metadata["cj_request_type"]` are present and sensible. ❌ NOT TESTED (fields don't exist)

---

## Phase 2 – LLM Provider Service serial bundling (no async batch APIs yet)

### 1. Add queue processing modes and serial-bundle limits

- [x] **Introduce `QueueProcessingMode` and `BatchApiMode` enums in LPS config** ✅ COMPLETE (2025-11-17)
  - File: `services/llm_provider_service/config.py` now defines `QueueProcessingMode` (`per_request`, `serial_bundle`, `batch_api`) and `BatchApiMode` (`disabled`, `nightly`, `opportunistic`).
  - `QueueProcessorImpl` and DI wiring no longer import or depend on CJ's `LLMBatchingMode`; the CJ hint remains metadata-only and is mapped internally to the LPS-specific enum.
  - This unblocks future per-service evolution without leaking CJ enums into LPS internals.

- [x] **Extend LPS `Settings` with queue/batch fields** ✅ COMPLETE (2025-11-17)
  - `QUEUE_PROCESSING_MODE` now uses the new enum while keeping the default `per_request` value and env prefix.
  - Added `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL: int = 8` with a validator that clamps inputs to `[1, 64]`.
  - Added `BATCH_API_MODE: BatchApiMode = disabled` as a Phase-2 placeholder for later provider batch rollout.

### 2. Implement `QueueProcessingMode.SERIAL_BUNDLE`

- [x] **Dispatch to serial-bundle path in `_process_queue_loop`** ✅ COMPLETE (2025-11-18)
  - File: `services/llm_provider_service/implementations/queue_processor_impl.py:110-180` now
    drains `_pending_request` before touching Redis/local queues and branches to
    `_process_request_serial_bundle` whenever the configured mode is not
    `per_request`.
  - After each bundle the loop yields (`await asyncio.sleep(0)`) to avoid starving
    other providers/models.

- [x] **Implement `_process_request_serial_bundle`** ✅ COMPLETE (2025-11-18)
  - Behaviour:
    - Seeds a bundle with the lead request, marks it `PROCESSING`, and records a
      per-request processing timer.
    - Dequeues additional requests until hitting
      `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` (default 8) or the first incompatible
      entry. Compatibility requires matching provider, identical override dict,
      and, when present, identical `cj_llm_batching_mode`. The first
      incompatible request is stored in `_pending_request` so the queue loop can
      process it on the next iteration without re-enqueueing.
    - Expired dequeues are handled inline (status update + metrics) without
      breaking the bundle.
    - Invokes `comparison_processor.process_comparison_batch(items)` once per
      bundle. Results are length-checked, fed back through
      `_handle_request_success`, and metrics are tagged with the correct mode.
    - Provider errors bubble as `HuleEduError`; the queue processor now fans that
      failure out to every queued request so callbacks/state stay consistent even
      though partial successes cannot yet be separated.

- [x] **Add `ComparisonProcessorImpl.process_comparison_batch`** ✅ COMPLETE
  - File: `services/llm_provider_service/protocols.py` (protocol definition)
  - File: `services/llm_provider_service/implementations/comparison_processor_impl.py` (implementation)
  - Signature (conceptual):
    - `async def process_comparison_batch(provider, requests, correlation_ids, **overrides)`.
  - First iteration:
    - Implement as a simple loop calling `process_comparison` per request. ✅ IMPLEMENTED
    - This gives a single code path for both serial-bundle and per-request modes without changing
      external behaviour.
  - **During the pre-task phase, `QueueProcessorImpl._process_queue_loop`
    must continue to use the existing per-request path only.** The
    switch to use `QueueProcessingMode.SERIAL_BUNDLE` and the
    corresponding serial-bundle dispatch is part of the main batching
    implementation task, not the pre-contract hardening.

- [x] **Map batch results back to queue handlers** ✅ COMPLETE
  - File: `services/llm_provider_service/implementations/queue_processor_impl.py:234-241`
  - For each `(QueuedRequest, LLMOrchestratorResponse)` pair in the batch:
    - Reuse `_handle_request_success` for success cases. ✅ IMPLEMENTED
    - Wrap errors in `HuleEduError` and reuse `_handle_request_hule_error` for failure cases. ✅ IMPLEMENTED
  - Ensure that queue status transitions and callback events are identical to the
    `QueueProcessingMode.PER_REQUEST` path.

### 3. LPS-side metadata & diagnostics

- [ ] **Enrich queued requests with provider-side metadata** ❌ MISSING
  - After resolving provider/model in `_process_request` / `_process_request_serial_bundle`, add:
    - `resolved_provider` to `request.request_data.metadata`. ❌ NOT IMPLEMENTED
    - `resolved_model` to `request.request_data.metadata`. ❌ NOT IMPLEMENTED
    - `queue_processing_mode` to `request.request_data.metadata`. ❌ NOT IMPLEMENTED
  - These fields should be visible in logs and can be used for bundle grouping and diagnostics.

- [~] **Serial-bundling tests** ⚠️ PARTIAL (expanded 2025-11-18)
  - File: `services/llm_provider_service/tests/unit/test_queue_processor_error_handling.py`
    now covers multi-request bundles, incompatibility deferral, and bundle-wide error handling.
  - Still pending: integration-level coverage that exercises redis/local queue interplay and
    per-request telemetry once metadata enrichment lands (targeted for PR 4/5).

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
