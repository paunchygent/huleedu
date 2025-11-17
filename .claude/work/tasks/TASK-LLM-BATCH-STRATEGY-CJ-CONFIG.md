# Task: LLM Batching Strategy – CJ Configuration Implementation

This task focuses specifically on the CJ Assessment Service configuration and wiring for the LLM
batching strategy. It is a child task of:

- `TASK-LLM-BATCH-STRATEGY.md` (high-level goal)
- `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` (overall design)

It should be used together with:

- `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md` (developer checklist)

---

## Scope

Implement the CJ-side changes required to support LLM batching modes while preserving existing
override plumbing (BOS/ELS → CJ → LPS, ENG5 runner → CJ → LPS) and without changing external
contracts.

Specifically, this task covers:

- Adding LLM batching configuration to CJ `Settings`.
- Extending `BatchConfigOverrides` with an optional `llm_batching_mode_override`.
- Resolving the effective batching mode per batch.
- Propagating batching metadata into LLM Provider Service requests.
- Adding minimal CJ metrics for batching mode usage.
- Adding unit tests for configuration resolution and metadata propagation.


## Design Decisions (CJ-side)

- **Environment defaults:**
  - `LLM_BATCHING_MODE = provider_serial_bundle` for both dev and prod.
  - `LLM_BATCH_API_ALLOWED_PROVIDERS = ["openai", "anthropic"]`.
- **Override plumbing:**
  - `llm_config_overrides` remains the source of provider/model/temperature/system prompt overrides.
  - `BatchConfigOverrides` is extended with `llm_batching_mode_override` to allow per-batch control.
- **Effective mode resolution:**
  - Per batch, `effective_mode` is computed as:
    - `BatchConfigOverrides.llm_batching_mode_override` when present, otherwise
    - `Settings.LLM_BATCHING_MODE`.
- **Metadata propagation:**
  - Batching mode and CJ context are passed into `LLMComparisonRequest.metadata` so LPS can use them
    for bundling/logging.
- **Metrics:**
  - CJ exposes only lightweight batching metrics and relies on LPS for detailed batching metrics.

These decisions are mirrored in `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` and should not diverge.

---

## Implementation Plan

### 1. Add CJ batching configuration to `Settings`

**File:** `services/cj_assessment_service/config.py`

1.1 **Define `LLMBatchingMode` enum**

- Add an enum near the top of `config.py`:

  - Values: `PER_REQUEST`, `PROVIDER_SERIAL_BUNDLE`, `PROVIDER_BATCH_API`.
  - Docstring: explain that this is a *logical* mode selector and that LLM Provider Service
    implements the actual batching behaviour.

1.2 **Add `LLM_BATCHING_MODE` and `LLM_BATCH_API_ALLOWED_PROVIDERS` to `Settings`**

- Fields:

  - `LLM_BATCHING_MODE: LLMBatchingMode = LLMBatchingMode.PROVIDER_SERIAL_BUNDLE`
  - `LLM_BATCH_API_ALLOWED_PROVIDERS: list[LLMProviderType] = [LLMProviderType.OPENAI, LLMProviderType.ANTHROPIC]`

- Ensure descriptions match the environment defaults documented in the parent task.
- Confirm env var naming aligns with `env_prefix="CJ_ASSESSMENT_SERVICE_"`.


### 2. Extend `BatchConfigOverrides` with per-batch override

**File:** `services/cj_assessment_service/cj_core_logic/batch_config.py`

2.1 **Add optional field**

- Extend `BatchConfigOverrides` with:

  - `llm_batching_mode_override: LLMBatchingMode | None = Field(default=None, ...)`.

2.2 **(Optional) Helper for effective mode resolution**

- Add a helper function:

  ```python
  def get_effective_batching_mode(
      settings: Settings,
      overrides: BatchConfigOverrides | None,
  ) -> LLMBatchingMode:
      if overrides and overrides.llm_batching_mode_override is not None:
          return overrides.llm_batching_mode_override
      return settings.LLM_BATCHING_MODE
  ```

This keeps the resolution logic centralized and testable.


### 3. Resolve effective batching mode in comparison processing

**File:** `services/cj_assessment_service/cj_core_logic/comparison_processing.py`

3.1 **Compute `batch_config_overrides` as today**

- Maintain the current pattern of extracting `batch_config_overrides` from `request_data` if present.

3.2 **Compute and log `effective_mode`**

- Use `get_effective_batching_mode(settings, batch_config_overrides)`.
- Add `"llm_batching_mode": effective_mode.value` into `log_extra` so logs show the mode per batch.

3.3 **(Initial phase) Use `effective_mode` for logging/metrics/metadata only**

- Do not change `BatchProcessor.submit_comparison_batch` signature initially.
- Use `effective_mode` when incrementing CJ metrics and when populating metadata for LPS (see below).
- This avoids a large signature change until there is a concrete need for LPS to receive per-batch
  mode as a first-class parameter.


### 4. Propagate batching metadata into LLM Provider Service

**File:** `services/cj_assessment_service/implementations/llm_interaction_impl.py`

4.1 **Derive batching mode inside `LLMInteractionImpl` (initially from `Settings`)**

- In `perform_comparisons`, obtain batching mode from `self.settings.LLM_BATCHING_MODE`.
- Later, this can be extended to accept an optional `batching_mode: LLMBatchingMode | None` parameter
  to reflect per-batch overrides.

4.2 **Enrich `request_metadata` per ComparisonTask**

- When constructing `request_metadata` for `provider.generate_comparison`, add:

  - `cj_batch_id: str` – `str(cj_batch_id)`.
  - `cj_source: str` – e.g. `"els"`, `"bos"`, `"eng5_runner"` (derived from `request_data`).
  - `cj_llm_batching_mode: str` – `self.settings.LLM_BATCHING_MODE.value` (or `effective_mode.value`
    once per-batch propagation is wired).
  - `cj_request_type: str` – e.g. `"cj_comparison"` or `"cj_retry"` for retry flows.

- These fields will appear in `LLMComparisonRequest.metadata` and then in `QueuedRequest.request_data.metadata` on the LPS side.


### 5. CJ metrics for batching mode

**File:** `services/cj_assessment_service/metrics.py` (or equivalent)

5.1 **Define metrics**

- Add Prometheus counters:

  - `cj_llm_requests_total{batching_mode}` – increment once per comparison sent to LPS.
  - `cj_llm_batches_started_total{batching_mode}` – increment once per CJ batch when comparisons are
    submitted.

5.2 **Wire metrics**

- In `submit_comparisons_for_async_processing`:
  - Increment `cj_llm_batches_started_total` with label `batching_mode=effective_mode.value`.
- In `LLMInteractionImpl.perform_comparisons`:
  - Increment `cj_llm_requests_total` for each ComparisonTask using
    `batching_mode=self.settings.LLM_BATCHING_MODE.value` (or `effective_mode.value` once per-batch
    propagation is added).

This matches the design decision that CJ exposes only lightweight batching metrics; LPS will be
responsible for detailed HTTP/token/queue metrics.


### 6. Tests

**File (new):** `services/cj_assessment_service/tests/unit/test_llm_batching_config.py`

6.1 **Configuration resolution tests**

- Cover:
  - Global default: `LLM_BATCHING_MODE=PROVIDER_SERIAL_BUNDLE`, no override →
    `effective_mode == PROVIDER_SERIAL_BUNDLE`.
  - Override: `BatchConfigOverrides.llm_batching_mode_override=PER_REQUEST` →
    `effective_mode == PER_REQUEST`.
  - Invalid env for `LLM_BATCHING_MODE` triggers Pydantic validation error.

6.2 **Metadata propagation tests**

- Use a fake `LLMProviderProtocol` implementation to capture `LLMComparisonRequest` instances.
- Assert that for a sample batch:
  - `metadata["cj_batch_id"]` matches the CJ batch id used.
  - `metadata["cj_llm_batching_mode"] == settings.LLM_BATCHING_MODE.value`.
  - `metadata["cj_source"]` and `metadata["cj_request_type"]` are present and correct.

These tests ensure that configuration and metadata wiring remains correct even if the code is
modified by automated tools or future refactors.

---

## Out of Scope (Tracked in Parent Task)

The following items are explicitly **out of scope** for this CJ-specific task and are tracked in
`TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` / `SERVICE_FUTURE_ENHANCEMENTS`:

- Provider-level multi-prompt patterns inside LLM Provider Service `process_comparison_batch`.
- Queue manager API expansions such as `dequeue_many` / `peek`.
- Provider async batch API implementations (`BatchApiClient`, `BatchJobManager`, OpenAI/Anthropic
  batch jobs). These are LPS responsibilities.

CJ remains responsible for configuration, per-batch overrides, minimal metrics, and metadata
propagation only.
