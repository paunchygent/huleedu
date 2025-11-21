---
id: llm-batch-strategy-lps-implementation
title: Llm Batch Strategy Lps Implementation
type: task
status: archived
priority: high
domain: integrations
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: llm_provider_service
owner: ''
program: ''
related: []
labels: []
---

# Task: LLM Batching Strategy – LLM Provider Service Implementation

Related reference: docs/operations/cj-assessment-foundation.md

This task focuses specifically on the LLM Provider Service (LPS) configuration, serial bundling, and
metrics for the LLM batching strategy. It is a child task of:

- `TASK-LLM-BATCH-STRATEGY.md` (high-level goal)
- `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` (overall design)

It is a sibling to:

- `TASK-LLM-BATCH-STRATEGY-CJ-CONFIG.md` (CJ Assessment Service configuration)

It should be used together with:

- `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md` (developer checklist)

---

## Scope

Implement the LLM Provider Service changes needed to:

- Respect CJ batching mode hints while maintaining compatibility with existing queue behaviour.
- Support serial bundling (`QueueProcessingMode.SERIAL_BUNDLE`) with small bundles.
- Prepare the codebase for future provider-level async batch APIs (OpenAI JSONL batches, Anthropic
  Message Batches) without committing to them yet.
- Expose detailed batching metrics (HTTP calls, bundle sizes, queue behaviour).

CJ configuration, per-batch overrides, and CJ-side metrics are handled in
`TASK-LLM-BATCH-STRATEGY-CJ-CONFIG.md` and must be completed first to avoid boundary churn.

## Design Decisions (LPS-side)

- **Environment defaults:**
  - `QUEUE_PROCESSING_MODE = serial_bundle` for both dev and prod.
  - `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 4` – small bundles for understandable failure modes and
    token accounting.
  - `OPENAI_BATCH_API_MODE = disabled`, `ANTHROPIC_BATCH_API_MODE = disabled` – batch APIs remain
    opt-in and are off by default.
- **Compatibility with CJ:**
  - CJ signals mode via `LLM_BATCHING_MODE` and per-batch overrides, and tags each request with
    `cj_llm_batching_mode` in metadata.
  - LPS uses these hints for grouping and diagnostics but does not assume that CJ has changed its
    external contracts.
- **Serial bundling behaviour:**
  - `QueueProcessingMode.SERIAL_BUNDLE` causes the queue processor to dequeue multiple compatible
    requests and process them together via a `process_comparison_batch` path.
  - Initial implementation of `process_comparison_batch` loops and calls `process_comparison` for
    each request (no provider multi-prompt). Provider-level multi-prompt is a future enhancement.
- **Queue API stability:**
  - No changes to the queue manager API initially; bundling uses repeated `dequeue()` calls.
- **Type system:**
  - Batch-related boundary models (future `BatchJobRef`, `BatchItemRequest`, `BatchItemResult`) will
    use Pydantic models for validation and type safety. Dataclasses are reserved for small, internal
    helpers only.

These decisions mirror the parent task and CJ config task and should not diverge.

---

## Implementation Plan

### 1. Add LPS batching configuration to `Settings`

**File:** `services/llm_provider_service/config.py`

1.1 **Define `QueueProcessingMode` and `BatchApiMode` enums**

- `QueueProcessingMode` values:
  - `PER_REQUEST`
  - `SERIAL_BUNDLE`
  - `BATCH_API`

- `BatchApiMode` values:
  - `DISABLED`
  - `NIGHTLY`
  - `OPPORTUNISTIC`

1.2 **Add queue/batch fields to `Settings` with defaults**

- Fields:

  - `QUEUE_PROCESSING_MODE: QueueProcessingMode = QueueProcessingMode.SERIAL_BUNDLE`
  - `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL: int = 4` (bounded between 1 and 64).
  - `OPENAI_BATCH_API_MODE: BatchApiMode = BatchApiMode.DISABLED`
  - `ANTHROPIC_BATCH_API_MODE: BatchApiMode = BatchApiMode.DISABLED`

- Ensure descriptions reference the environment defaults documented in the parent task.
- Confirm env var naming aligns with `env_prefix="LLM_PROVIDER_SERVICE_"`.

### 2. Dispatch based on `QUEUE_PROCESSING_MODE` in queue processor

**File:** `services/llm_provider_service/implementations/queue_processor_impl.py`

2.1 **Branch in `_process_queue_loop`**

- When `QUEUE_PROCESSING_MODE == SERIAL_BUNDLE`, use a dedicated path:

  - Introduce `_process_request_serial_bundle()` that internally handles dequeuing and bundling.
  - Keep `_process_request(request)` unchanged for `PER_REQUEST` and `BATCH_API` modes (BATCH_API
    will later be wired to job scheduling logic).

2.2 **Implement `_process_request_serial_bundle` for serial bundling**

- Behaviour:
  - Dequeue the first `QueuedRequest` via `self.queue_manager.dequeue()`.
  - Resolve provider and overrides exactly as in `_process_request`.
  - Repeatedly call `dequeue()` to collect up to `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL - 1` additional
    **compatible** requests.

- Compatibility criteria (initial):
  - Same resolved provider (e.g. OPENAI vs ANTHROPIC).
  - Same resolved model (from overrides/manifest).
  - Optionally: same `cj_llm_batching_mode` when present in `request_data.metadata`.

- Once a bundle is formed:
  - Pass the list of `(QueuedRequest, LLMComparisonRequest)` pairs into a new
    `ComparisonProcessorImpl.process_comparison_batch` method.

### 3. Add `process_comparison_batch` to `ComparisonProcessorImpl`

**File:** `services/llm_provider_service/implementations/comparison_processor_impl.py`

3.1 **Define batch-processing method**

- Signature (conceptual):

  ```python
  async def process_comparison_batch(
      self,
      provider: LLMProviderType,
      requests: list[LLMComparisonRequest],
      correlation_ids: list[UUID],
      **overrides: Any,
  ) -> list[LLMOrchestratorResponse]:
      """Process a batch of comparison requests.

      Initial implementation may loop over `process_comparison`. Future enhancements can
      introduce provider-level multi-prompt patterns behind feature flags.
      """
  ```

3.2 **Initial implementation (no multi-prompt)**

- Loop over `requests` and call `process_comparison` for each, building a list of
  `LLMOrchestratorResponse`.
- This ensures a single code path for serial-bundle and per-request modes without changing provider
  semantics.

3.3 **Future multi-prompt (tracked outside this task)**

- Once stable, and when `SERVICE_FUTURE_ENHANCEMENTS` is actioned, `process_comparison_batch` can be
  extended to use provider-specific multi-prompt calls for small bundles (<= 4) while preserving the
  one-result-per-request contract.

### 4. Map batch results back to queue handlers

**File:** `services/llm_provider_service/implementations/queue_processor_impl.py`

4.1 **Use existing success/error paths**

- For each `(QueuedRequest, LLMOrchestratorResponse)` pair in the batch results:
  - On success, reuse `_handle_request_success(request, result)`.
  - On failure, wrap errors in `HuleEduError` and reuse `_handle_request_hule_error(request, error)`.

4.2 **Maintain queue semantics**

- Ensure that:
  - Status transitions (`QUEUED` → `PROCESSING` → `COMPLETED`/`FAILED`) remain consistent.
  - Requests are still removed from the queue after completion or permanent failure.
  - Callback events (`LLMComparisonResultV1`) are identical to the `PER_REQUEST` path.

### 5. Enrich provider-side metadata

**Files:**

- `services/llm_provider_service/implementations/queue_processor_impl.py`
- `services/llm_provider_service/queue_models.py` (for reference only)

5.1 **Inject resolved metadata post-selection**

- After resolving provider and model for a `QueuedRequest` (in `_process_request` or
  `_process_request_serial_bundle`), enrich `request.request_data.metadata` with:

  - `resolved_provider: str` – `provider.value`.
  - `resolved_model: str` – actual model id used.
  - `queue_processing_mode: str` – `self.settings.QUEUE_PROCESSING_MODE.value`.

5.2 **Use metadata for diagnostics and grouping**

- Ensure logs and metrics can use these fields to:
  - Group requests by provider, model, and processing mode.
  - Diagnose issues with specific bundles or providers.

### 6. LPS metrics for batching

**File:** `services/llm_provider_service/metrics.py` (or equivalent)

6.1 **Define serial-bundling metrics**

- Prometheus metrics (suggested):

  - `llm_serial_bundle_calls_total{provider, model}` – incremented once per call to
    `process_comparison_batch`.
  - `llm_serial_bundle_items_per_call_bucket{provider, model}` – histogram of bundle sizes.

6.2 **Instrument metric updates**

- After each successful `process_comparison_batch` call:
  - Increment `llm_serial_bundle_calls_total`.
  - Observe bundle size in `llm_serial_bundle_items_per_call_bucket`.

6.3 **Rely on existing usage/cost metrics for deeper analysis**

- Continue to rely on existing `LLMOrchestratorResponse`-driven metrics for token usage and cost,
  combining them with the new bundle metrics to analyse cost/latency trade-offs.

### 7. Tests

**Files:**

- `services/llm_provider_service/tests/unit/test_queue_processor_serial_bundle.py` (new)
- `services/llm_provider_service/tests/unit/test_comparison_processor_batch.py` (new)

7.1 **Queue processor tests**

- Cover:
  - `QUEUE_PROCESSING_MODE = SERIAL_BUNDLE` with a mix of compatible and incompatible
    `QueuedRequest`s.
  - Assert that compatible requests are processed together and incompatible ones are left for a
    later batch.
  - Verify that status transitions and callback events match the per-request behaviour.

7.2 **Comparison processor batch tests**

- Cover:
  - `process_comparison_batch` looping over `process_comparison` and returning one
    `LLMOrchestratorResponse` per request.
  - Error propagation semantics (e.g. one failing provider call does not corrupt others).

7.3 **Metadata tests**

- Verify that `resolved_provider`, `resolved_model`, and `queue_processing_mode` are correctly set in
  `LLMComparisonRequest.metadata` after provider selection.

---

## Dependencies and Ordering

To minimize churn and boundary miscommunication:

- Complete `TASK-LLM-BATCH-STRATEGY-CJ-CONFIG.md` (CJ configuration and metadata propagation) before
  changing any LPS behaviour that depends on `cj_llm_batching_mode` or new CJ metrics.
- Treat `LLM_BATCHING_MODE` and CJ metadata as the *source of truth* for what CJ expects; LPS should
  remain backwards compatible with older CJ deployments where batching metadata might be absent.

Future enhancements (provider multi-prompt, queue API changes, async batch APIs) remain out of scope
for this task and are tracked in `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` and
`SERVICE_FUTURE_ENHANCEMENTS`.
