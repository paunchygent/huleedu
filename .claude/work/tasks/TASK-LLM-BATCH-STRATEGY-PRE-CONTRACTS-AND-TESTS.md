# Task: LLM Batching Strategy – CJ/LPS Contracts & Pre‑Tests

## Context & Relationship to Main Task

This is a **pre‑task** to:

- `.claude/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md`
- `.claude/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md`

Goal: prepare and harden the **CJ ↔︎ LLM Provider** boundary *before* enabling provider‑side serial bundling or batch APIs by:

- Making the CJ → LPS metadata and override contracts explicit and validated.
- Clarifying which cross‑service contracts must live in `common_core`.
- Adding contract tests and end‑to‑end infrastructure tests that lock in the desired behaviour.

This task is **behaviour‑preserving**: it should not change runtime semantics of comparison requests or callbacks. It only clarifies contracts and adds tests plus small refactors that pave the way for `QueueProcessingMode.SERIAL_BUNDLE` and future batch APIs.

---

## Cross‑Service Contracts (Must Live in `common_core`)

The following contracts are cross‑service and, by design, should live in `common_core` as the canonical source of truth.

### 1. LLM Provider Event Contracts

Location: `libs/common_core/src/common_core/events/llm_provider_events.py`

- **`LLMRequestStartedV1`**  
  Direction: LLM Provider Service → observability / analytics consumers.  
  Purpose: marks the start of a provider request (`request_type="comparison" | "generation" | ...`).

- **`LLMRequestCompletedV1`**  
  Direction: LLM Provider Service → observability / analytics consumers.  
  Purpose: marks completion of provider request with `success`, `response_time_ms`, `token_usage`, `cost_estimate`.

- **`LLMProviderFailureV1`**  
  Direction: LLM Provider Service → monitoring/alerting consumers.  
  Purpose: records provider‑level failures (`failure_type`, `circuit_breaker_opened`, `metadata`).

- **`LLMUsageAnalyticsV1`**  
  Direction: metrics aggregation / reporting.  
  Purpose: periodic rollup of usage, tokens and cost across providers.

- **`LLMCostAlertV1`**  
  Direction: alerting pipeline.  
  Purpose: notifies when cost thresholds are exceeded.

- **`LLMCostTrackingV1`**  
  Direction: LLM Provider Service → billing/analytics services.  
  Purpose: per‑request cost record keyed by `correlation_id`, with `token_usage`, `cost_estimate_usd`, `user_id`, `organization_id`, `service_name`.

- **`TokenUsage`**  
  Re‑used by multiple events and by `LLMComparisonResultV1` for a consistent token accounting shape.

- **`LLMComparisonResultV1`**  
  Direction: **LLM Provider Service → CJ Assessment Service (and any other consumers)**.  
  Purpose: asynchronous callback for comparison results.  
  This is the critical CJ/LPS boundary contract:

  - `request_id: str` – LPS queue id (`QueuedRequest.queue_id`).
  - `correlation_id: UUID` – CJ correlation id for tracing; must match the id CJ provided per comparison where available.
  - Success fields: `winner: EssayComparisonWinner`, `justification: str`, `confidence: float (1–5)`.
  - Error field: `error_detail: ErrorDetail | None` (mutually exclusive with success fields).
  - Common metadata: `provider: LLMProviderType`, `model: str`, `response_time_ms`, `token_usage: TokenUsage`, `cost_estimate: float`.
  - Timestamps: `requested_at`, `completed_at`.
  - Tracing: `trace_id: str | None`.
  - **`request_metadata: dict[str, Any]`** – opaque to LPS but **authoritative** for CJ to identify the comparison and batch context.

### 2. CJ Assessment Event Contracts

Location: `libs/common_core/src/common_core/events/cj_assessment_events.py`

- **`ELS_CJAssessmentRequestV1`**  
  Direction: ELS/BOS → CJ Assessment Service.  
  Purpose: canonical incoming request for a CJ batch, including `bos_batch_id`, essay payload, and `llm_config_overrides` / `batch_config_overrides`.

> Any other CJ request/response event variants that cross service boundaries must also live here. Service‑local models in `services/cj_assessment_service/models_api.py` are *internal* and should not be used as cross‑service contracts.

### 3. Shared Enums and Models

- **`LLMProviderType`**  
  Location: `common_core.config_enums`.  
  Purpose: shared enumeration of supported LLM providers (OpenAI, Anthropic, etc.).

- **`EssayComparisonWinner`**  
  Location: `common_core.domain_enums`.  
  Purpose: shared domain enum for comparison outcomes (`essay_a`, `essay_b`, `tie` if allowed).

- **`ErrorDetail`** and **`ErrorCode`**  
  Location: `common_core.models.error_models`, `common_core.error_enums`.  
  Purpose: shared structured error reporting across services, used inside `LLMComparisonResultV1.error_detail` and CJ error flows.

- **Trace identifiers (`trace_id`)**  
  Currently encoded as `str` in events. Semantics and propagation are shared, but the concrete type remains `str`.

> **Design rule:** Any **event** or **enum/model** used across multiple services must be defined in `common_core` and versioned there. Service‑local API/request models (`LLMComparisonRequest`, `QueuedRequest`, `LLMOrchestratorResponse`, `CJAssessmentRequestData`, etc.) are owned by their respective services and must not be used as cross‑service contracts.

---

## Pre‑Task Implementation Steps (Behaviour‑Preserving)

These steps can be implemented and merged independently of serial bundling or batch APIs.

### Step 1 – CJ Canonical Metadata Model

**Goal:** Define a typed CJ metadata model for comparison requests and ensure it is the only way CJ constructs `request_metadata` for LPS.

**Location:** `services/cj_assessment_service/models_api.py` (or new `metadata_models.py`).

**Actions:**

1. Introduce `CJLLMComparisonMetadata` (Pydantic model) with fields:
   - `essay_a_id: str`, `essay_b_id: str` (required).
   - `bos_batch_id: str | None`.
   - `cj_batch_id: str | None`.
   - `cj_request_type: str | None` (e.g. `"cj_comparison"`, `"cj_retry"`).
   - `cj_llm_batching_mode: str | None` (CJ’s effective `LLMBatchingMode.value`).
   - `assignment_id: str | None`, `course_code: str | None`, `language: str | None`.
   - `user_id: str | None`, `org_id: str | None`.
   - `extra: dict[str, Any] = {}` for future namespaced flags.

   **Initial implementation MUST be strictly additive:**
   - Preserve existing key names and semantics for current metadata
     (at minimum `"essay_a_id"`, `"essay_b_id"`, `"bos_batch_id"`).
   - No existing consumer may start treating new fields as required.
     Tests should confirm that the legacy metadata shape remains valid
     when only the original fields are populated.

2. Add `as_metadata_dict()` helper that returns `model_dump(exclude_none=True)`.

3. In `LLMInteractionImpl.perform_comparisons`, replace the ad‑hoc `request_metadata = { ... }` with a helper:
   - `_build_metadata_for_task(task, request_data, cj_batch_id, batching_mode, request_type) -> dict[str, Any]` which constructs and serializes `CJLLMComparisonMetadata`.

4. Ensure `request_metadata` is passed unchanged into the CJ→LPS client that builds `LLMComparisonRequest.metadata`.

**Outcome:** CJ→LPS metadata contract is explicit, validated, and ready to carry batching hints without changing LPS.

### Step 2 – CJ → LPS Override Adapter

**Goal:** Centralize mapping between CJ’s `LLMConfigOverrides` (from `common_core.events.cj_assessment_events`) and LPS’s `LLMConfigOverrides` (from `services/llm_provider_service/api_models`).

**Location:** CJ’s LPS client implementation (where `LLMComparisonRequest` is constructed).

**Actions:**

1. Implement `to_lps_overrides(overrides: CJOverrides | None) -> LPSOverrides | None` that:
   - Returns `None` if input is `None`.
   - Copies fields: `provider_override`, `model_override`, `temperature_override`,
     `system_prompt_override`, `max_tokens_override`.
   - **Bridge `provider_override` types explicitly:** CJ’s
     `provider_override` is a `str | None`, while LPS expects
     `LLMProviderType | None`. The adapter must:
     - Convert non-`None` strings to `LLMProviderType` by matching
       the enum `value`.
     - If the string does not match any known `LLMProviderType`, log a
       warning and set `provider_override=None` so that the existing
       default provider resolution continues to apply (behaviour-
       preserving).
   - The adapter itself must not introduce any new defaulting rules;
     it only maps or clears fields. Default provider/model selection
     stays in the existing call sites.

2. Replace any direct construction of `LPSOverrides` from CJ data with this adapter.

3. Add unit tests to ensure mapping is 1–1 for all fields (see Tests section below).

**Outcome:** A single, well‑tested mapping point for override semantics, making it safe to add future override fields.

### Step 3 – LPS Batch Interface (No Behaviour Change)

**Goal:** Introduce an internal batch interface that preserves the existing **1 request ↔ 1 callback** invariant and can later be backed by real provider multi‑prompt or batch APIs.

**Location:** `services/llm_provider_service/internal_models.py`, `protocols.py`, `implementations/comparison_processor_impl.py`.

**Actions:**

1. Add `BatchComparisonItem` model (internal):
   - `provider: LLMProviderType`.
   - `user_prompt: str`.
   - `correlation_id: UUID`.
   - `overrides: LLMConfigOverrides | None`.

2. Extend `ComparisonProcessorProtocol` with:

   ```python
   async def process_comparison_batch(
       self,
       items: list[BatchComparisonItem],
   ) -> list[LLMOrchestratorResponse]:
       """Process multiple comparison requests.

       Contract:
       - len(results) == len(items)
       - results[i].correlation_id == items[i].correlation_id
       - i-th result belongs to i-th input item.
       """
   ```

3. Implement a **default loop** in `ComparisonProcessorImpl.process_comparison_batch` that simply calls `process_comparison` once per item. No new provider behaviour yet; this is a refactor only.

4. (Optional prework) Add an internal helper in `QueueProcessorImpl` that can construct `BatchComparisonItem` instances from `QueuedRequest` plus `LLMComparisonRequest.llm_config_overrides`, but keep the main loop calling the existing per‑request path until serial bundling is actually implemented.

**Outcome:** A stable internal contract for batched processing with enforced invariants, but unchanged external behaviour. In this pre-task, `QueueProcessorImpl._process_queue_loop` MUST continue to process one `QueuedRequest` at a time via the existing per-request path; any dispatch on `QueueProcessingMode` and actual serial bundling behaviour is owned by the main batching implementation task.

### Step 4 – Document & Assert Invariants

**Goal:** Make the following invariants explicit and test‑backed before bundling:

- **Cardinality:** 1 `QueuedRequest` → 1 `LLMComparisonResultV1` event.
- **Identity:** Each result’s `correlation_id` and `request_id` uniquely identify exactly one comparison.
- **Metadata:** `request_data.metadata` from `LLMComparisonRequest` is preserved (plus `prompt_sha256`) in `LLMComparisonResultV1.request_metadata`.

**Actions:**

1. Codify these invariants in docstrings and comments around:
   - `LLMComparisonResultV1` in `common_core`.
   - `QueueProcessorImpl._publish_callback_event`.
   - `ComparisonProcessorImpl.process_comparison_batch`.

2. Add tests described in the next section to enforce these invariants.

---

## Contract Tests (Unit / Contract Level)

These tests should live close to the relevant services and `common_core`, and use `pdm run pytest-root` via the existing test harness.

### 1. CJ Metadata Contract Tests

Suggested location: `services/cj_assessment_service/tests/unit/test_cj_llm_metadata_contract.py`.

**Tests:**

- **`test_cj_llm_metadata_minimal_fields`**  
  Create `CJLLMComparisonMetadata` with only required fields (`essay_a_id`, `essay_b_id`) and assert:
  - `as_metadata_dict()` contains those keys and nothing else.

- **`test_cj_llm_metadata_full_fields_roundtrip`**  
  Build with all optional fields and ensure `as_metadata_dict()` preserves field names and values, excluding `None`.

- **`test_llm_interaction_impl_uses_metadata_builder`**  
  Patch `LLMInteractionImpl` to use a fake provider, call `perform_comparisons` with a single `ComparisonTask` and a representative `CJAssessmentRequestData`, and assert that the constructed `request_metadata` matches `CJLLMComparisonMetadata.as_metadata_dict()`.

### 2. Override Adapter Contract Tests

Suggested location: `services/cj_assessment_service/tests/unit/test_llm_overrides_adapter_contract.py`.

**Tests:**

- **`test_to_lps_overrides_none`**  
  `to_lps_overrides(None)` returns `None`.

- **`test_to_lps_overrides_field_mapping`**  
  Given a `CJOverrides` with all fields set, assert the resulting `LPSOverrides` has identical values for each supported field (`provider_override`, `model_override`, `temperature_override`, `system_prompt_override`, `max_tokens_override`).

- **`test_to_lps_overrides_partial`**  
  For partially filled overrides, ensure unset fields remain `None` and no unexpected defaults are introduced.

### 3. LLM Provider Batch Interface Tests

Suggested location: `services/llm_provider_service/tests/unit/test_comparison_processor_batch_contract.py`.

**Tests:**

- **`test_process_comparison_batch_single_item_delegates_to_process_comparison`**  
  Patch/stub `process_comparison` to record calls. Call `process_comparison_batch` with one `BatchComparisonItem` and assert:
  - `process_comparison` called exactly once with corresponding args.
  - Returned list has length 1.

- **`test_process_comparison_batch_multiple_items_preserves_order_and_ids`**  
  Feed `N` items with distinct `correlation_id`s, stub `process_comparison` to return `LLMOrchestratorResponse` objects with matching `correlation_id`. Assert:
  - `len(results) == N`.
  - `results[i].correlation_id == items[i].correlation_id` for all `i`.

### 4. Callback Event Contract Tests

Suggested location: `services/llm_provider_service/tests/unit/test_callback_event_contract.py`.

**Tests:**

- **`test_publish_callback_event_preserves_request_metadata`**  
  Build a `QueuedRequest` with a known `request_data.metadata` (matching `CJLLMComparisonMetadata.as_metadata_dict()`), create a minimal `LLMOrchestratorResponse`, call `_publish_callback_event`, and inspect the produced `LLMComparisonResultV1`:
  - `request_metadata` includes all original keys.
  - `prompt_sha256` is added if present in `result.metadata`.

- **`test_llm_comparison_result_v1_success_vs_error_invariants`**  
  Validate that constructing `LLMComparisonResultV1` with both success fields and `error_detail` raises, and that at least one of them must be present.

---

## Behavioural / Infrastructure Tests

These tests should exercise the **real pipeline** across CJ and LPS using the existing functional / integration test harnesses. They may be slower and should be marked appropriately (e.g. `@pytest.mark.integration`).

### 1. CJ → LPS → CJ Metadata Roundtrip

Suggested location: `tests/integration/pipeline/test_cj_llm_metadata_roundtrip.py`.

**Scenario:**

1. Use the existing pipeline harness to submit an `ELS_CJAssessmentRequestV1` with:
   - Multiple essays, producing at least 2 comparison tasks.
   - Non‑trivial `llm_config_overrides` and `batch_config_overrides`.

2. Let CJ generate comparison tasks and send them to LPS.

3. Simulate completion from LPS (or run against the real queue processor, depending on test environment) so that CJ consumes `LLMComparisonResultV1` callbacks.

**Assertions:**

- For each comparison result observed in CJ:
  - `request_metadata` contains `essay_a_id`, `essay_b_id`, `cj_batch_id`, `cj_llm_batching_mode`, and any other fields defined in `CJLLMComparisonMetadata`.
  - Essay ids in `request_metadata` match the essays used in CJ’s `ComparisonTask`.
  - Exactly one callback is received per comparison.

### 2. Non‑Regressive Behaviour Test (Per‑Request Mode)

Suggested location: `tests/functional/test_llm_batching_prework_non_regression.py`.

**Scenario:**

- Set CJ and LPS configs to `LLM_BATCHING_MODE=per_request`, `QUEUE_PROCESSING_MODE=per_request`.
- Run an existing functional test that drives a small CJ batch end‑to‑end.

**Assertions:**

- Number of LPS queued requests (and callbacks) matches number of comparison tasks.
- No changes to external APIs or error codes compared to baseline (use golden‑file or snapshot if available).

### 3. Future Serial Bundling Behaviour Test (Placeholder)

This test is **not part of the pre‑task implementation**, but the pre‑task should describe it so it can later prove the serial bundling design without changing contracts.

Suggested location: `tests/functional/test_llm_serial_bundling_behaviour.py`.

**Scenario (once `QueueProcessingMode.SERIAL_BUNDLE` is implemented):**

- Configure LPS with `QUEUE_PROCESSING_MODE=serial_bundle` and a small `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`.
- Submit a CJ batch that generates multiple comparison tasks with compatible overrides.

**Assertions:**

- There are **fewer provider HTTP calls** than comparisons (bundle effect), measured via LPS metrics or HTTP client spy.
- Still exactly one `LLMComparisonResultV1` per `QueuedRequest` and per comparison.
- `request_metadata` and `correlation_id` invariants continue to hold.

---

## Definition of Done for This Pre‑Task

- **Contracts clarified:**
  - Cross‑service event and enum/model contracts documented and confirmed to live in `common_core`.
  - CJ and LPS internal models clearly separated from cross‑service contracts.

- **Pre‑work implemented:**
  - `CJLLMComparisonMetadata` introduced and wired into `LLMInteractionImpl.perform_comparisons`.
  - `to_lps_overrides` adapter implemented and used for mapping CJ overrides to LPS overrides.
  - `BatchComparisonItem` and `process_comparison_batch` added with a behaviour‑preserving default implementation.

- **Tests in place:**
  - Unit/contract tests for metadata, override adapter, batch interface, and callback invariants are green.
  - At least one integration / functional test validates CJ → LPS → CJ metadata roundtrip without regression.

- **Ready for main task:**
  - With these contracts and tests in place, `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION` can safely implement `QueueProcessingMode.SERIAL_BUNDLE` and later provider batch APIs, with strong guarantees that CJ ↔︎ LPS contracts remain stable.
