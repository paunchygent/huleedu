---
id: llm-batch-strategy-implementation
title: Llm Batch Strategy Implementation
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

# Task: LLM Batching Strategy Implementation

Related reference: docs/operations/cj-assessment-foundation.md

## Context

This task captures the design and implementation plan for improving LLM batching in the CJ Assessment workflow and the LLM Provider Service. The goal is to reduce external HTTP calls, respect provider rate limits, and support larger offline workloads (nightly CJ jobs) without changing the external CJ / RAS contracts.

This document builds on:

- `.claude/tasks/TASK-LLM-BATCH-STRATEGY.md` (high‑level task definition)
- `.claude/research/anthropic-openai-batch.md` (provider batch API research)

## High‑Level Decisions

- **Ownership:**
  - CJ Assessment Service decides *whether* to use advanced batching modes via configuration and per‑request overrides.
  - LLM Provider Service implements the *how* (serial bundling, async batch APIs) and owns all provider‑specific details.
- **Default behaviour:**
  - At the CJ → LLM Provider boundary, keep todays semantics as the default: one queued request per comparison, one provider call per request.
  - Inside CJ, comparison *generation* already uses a **stability‑driven bundling** pattern:
    - `generate_comparison_tasks` is called with `existing_pairs_threshold=settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION`.
    - A global cap is enforced via `MAX_PAIRWISE_COMPARISONS` (see `comparison_processing._resolve_requested_max_pairs`).
    - New comparisons are generated in small bundles per iteration until either the cap or stability criteria are met.
- **Feature flags:**
  - Introduce explicit batching mode enums in both CJ and LPS `Settings` so behaviour can be flipped per environment without code changes, while keeping CJs existing bundling logic as the canonical default.
- **Comparison submission shapes (CJ → LLM Provider):**
  - **Bundled, stability‑driven (current default):**
    - CJ generates comparisons in bundles of up to `COMPARISONS_PER_STABILITY_CHECK_ITERATION` new pairs per call to `generate_comparison_tasks`, respecting `MAX_PAIRWISE_COMPARISONS` as a hard cap.
    - This applies both to the initial submission (`submit_comparisons_for_async_processing`) and to continuation iterations (`request_additional_comparisons_for_batch` / `_process_comparison_iteration`).
  - **Batched, all‑at‑once (future optional):**
    - CJ would generate *all* remaining pairs in a single call (still respecting `MAX_PAIRWISE_COMPARISONS`) so the LLM Provider can use provider‑level batch/discount APIs efficiently.
    - This shape is reserved for a future `LLMBatchingMode.PROVIDER_BATCH_API` path and is **not** the current default.
- **Rollout order (bundling first, batch later):**
  1. **Codify current CJ bundling semantics** as the canonical baseline (no change in behaviour): keep `COMPARISONS_PER_STABILITY_CHECK_ITERATION` + `MAX_PAIRWISE_COMPARISONS` as the way CJ decides *when* and *how many* comparisons to generate per iteration.
  2. **Add configuration enums and metadata wiring** in CJ and LPS (`LLMBatchingMode`, `QueueProcessingMode`, provider batch flags) without changing runtime behaviour: still bundled comparisons in CJ, still per‑request calls in LLM Provider.
  3. **Implement `QueueProcessingMode.SERIAL_BUNDLE` in LLM Provider Service** so multiple queued comparison requests (from CJs bundled submissions) can be handled in a single provider API call, with full metrics and diagnostics.
  4. **Only after serial bundling is stable and observable**, introduce an optional `PROVIDER_BATCH_API` path where:
     - CJ can opt‑in specific workloads to the *batched, all‑at‑once* submission shape, and
     - LLM Provider Service can use provider async batch APIs (OpenAI JSONL batches, Anthropic message batches) behind explicit, environment‑scoped flags.

## Environment Defaults

Unless explicitly overridden, the following defaults should be used for both development and
production environments:

> **Note:** These defaults describe the *target* configuration once
> `QueueProcessingMode.SERIAL_BUNDLE` is implemented and rolled out in LLM Provider Service.
> Existing deployments may still run with `QUEUE_PROCESSING_MODE=per_request` until Phase 2 of
> this task is completed and validated.

- **CJ Assessment Service:**
  - `LLM_BATCHING_MODE = provider_serial_bundle` – signal that provider-side serial bundling is
    allowed for CJ comparison requests.
  - `LLM_BATCH_API_ALLOWED_PROVIDERS = ["openai", "anthropic"]` – constrain any future batch API
    usage to the two providers that support it.

- **LLM Provider Service:**
  - `QUEUE_PROCESSING_MODE = serial_bundle` – enable serial bundling by default.
  - `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL = 4` – use *small* bundles to keep token accounting and
    failure modes understandable.
  - `OPENAI_BATCH_API_MODE = disabled` and `ANTHROPIC_BATCH_API_MODE = disabled` – async batch APIs
    remain opt-in and are off by default until implemented and explicitly enabled.

## Batching mode mapping & trade-offs

The logical CJ `LLMBatchingMode` hint and the LLM Provider Service queue configuration map as
follows:

| CJ `LLMBatchingMode`              | LPS `QueueProcessingMode` | LPS `BatchApiMode`             | Recommended usage & trade-offs |
|-----------------------------------|---------------------------|--------------------------------|--------------------------------|
| `PER_REQUEST`                     | `per_request`             | `DISABLED`                     | **Default for standard BOS/ELS flows.** One queued request per comparison and one provider call per request. Simplest failure surface and debugging story, but highest HTTP call volume and queue round-trips. Metrics focus on per-request latency and error rates. |
| `PROVIDER_SERIAL_BUNDLE`         | `SERIAL_BUNDLE`           | `DISABLED`                     | **Primary candidate for ENG5-heavy workloads.** CJ still generates stability-driven bundles, but LPS groups compatible dequeues into multi-item provider calls. Reduces HTTP calls and queue churn at the cost of shared failure domains per bundle. Operators must watch serial-bundle metrics plus queue latency/expiry to catch regressions. |
| `PROVIDER_BATCH_API`             | `SERIAL_BUNDLE`           | `NIGHTLY` / `OPPORTUNISTIC`    | **Future-facing mode for provider-native async batch APIs.** CJ prefers fully batched submissions while LPS decides when to flip on real batch jobs per provider. Higher operational complexity and delayed error surface (job polling), but best suited for large offline workloads once APIs are stable. |

In all modes, CJ remains responsible for *when* and *how many* comparisons are generated per
iteration, and LLM Provider Service remains the source of truth for the physical batching
strategy, queue-processing mode, and provider-specific batch endpoints.

## CJ Assessment Service Configuration

### New enum: `LLMBatchingMode`

Location: `services/cj_assessment_service/config.py`

```python
class LLMBatchingMode(str, Enum):
    """Strategy for how CJ batches comparison tasks for LLM processing.

    This is a *logical* mode selector; the physical batching behaviour is
    implemented in the LLM Provider Service based on this hint.
    """

    PER_REQUEST = "per_request"
    PROVIDER_SERIAL_BUNDLE = "provider_serial_bundle"
    PROVIDER_BATCH_API = "provider_batch_api"
```

### New `Settings` fields

```python
LLM_BATCHING_MODE: LLMBatchingMode = Field(
    default=LLMBatchingMode.PER_REQUEST,
    description=(
        "CJ-level batching strategy for LLM comparisons.\n"
        "- per_request: current behaviour; each comparison becomes a single\n"
        "  queued request in LLM Provider Service.\n"
        "- provider_serial_bundle: CJ sends one request per comparison, but the\n"
        "  provider service is allowed to bundle multiple queued requests into a\n"
        "  single provider API call.\n"
        "- provider_batch_api: CJ marks requests as eligible for asynchronous\n"
        "  provider batch APIs (OpenAI/Anthropic). Actual job creation/polling\n"
        "  is handled in the LLM Provider Service."
    ),
)

LLM_BATCH_API_ALLOWED_PROVIDERS: list[LLMProviderType] = Field(
    default_factory=lambda: [LLMProviderType.OPENAI, LLMProviderType.ANTHROPIC],
    description=(
        "Subset of providers that CJ is allowed to use with asynchronous batch\n"
        "APIs (e.g. OpenAI JSONL batches, Anthropic /v1/messages/batches).\n"
        "This acts as a guardrail; the LLM Provider Service still enforces\n"
        "provider-specific limits and availability."
    ),
)
```

### Optional per‑request override (BatchConfigOverrides)

Extend `BatchConfigOverrides` to support a per‑batch override:

```python
class BatchConfigOverrides(BaseModel):
    ...
    llm_batching_mode_override: LLMBatchingMode | None = Field(
        default=None,
        description=(
            "Optional override of LLM batching mode for this CJ batch. When set,\n"
            "takes precedence over global LLM_BATCHING_MODE."
        ),
    )
```

CJ resolves the effective mode as:

```python
effective_mode = (
    batch_config_overrides.llm_batching_mode_override
    if batch_config_overrides and batch_config_overrides.llm_batching_mode_override
    else settings.LLM_BATCHING_MODE
)
```

This is compatible with BOS/ELS and the ENG5 runner, which already send `batch_config_overrides` via the CJ request payload.

### Metadata passed to LLM Provider Service

In `LLMInteractionImpl.perform_comparisons`, extend `request_metadata` for each `ComparisonTask`:

- `cj_batch_id: str`  `str(cj_batch_id)`.
- `cj_source: str`  e.g. `"els"`, `"bos"`, `"eng5_runner"`.
- `cj_llm_batching_mode: str`  `effective_mode.value`.
- `cj_request_type: str`  e.g. `"cj_comparison"`, `"cj_retry"`.

These flow into `LLMComparisonRequest.metadata` and then into
`QueuedRequest.request_data.metadata` on the provider side.

> **Important:** The metadata shape is owned by the
> `CJLLMComparisonMetadata` model introduced in the pre-task
> (`TASK-LLM-BATCH-STRATEGY-PRE-CONTRACTS-AND-TESTS`). Any new keys
> added here **must be strictly additive**:
>
> - Existing key names and semantics (at minimum `"essay_a_id"`,
>   `"essay_b_id"`, `"bos_batch_id"`) must remain unchanged.
> - No existing consumer may start treating new fields as required.
>   The legacy metadata shape must continue to validate and behave as
>   before.

Override mapping from CJ to LLM Provider Service must use the
`to_lps_overrides(...)` adapter defined in the pre-task. That adapter is
responsible for bridging `provider_override: str | None` from CJ into
`LLMProviderType | None` expected by the LPS API models, and for
handling unknown provider strings by logging and clearing the override
so that existing default provider resolution stays behaviour-preserving.

## LLM Provider Service Configuration

### New enums

Location: `services/llm_provider_service/config.py`

```python
class QueueProcessingMode(str, Enum):
    """How the queue processor turns queued requests into provider calls."""

    PER_REQUEST = "per_request"
    SERIAL_BUNDLE = "serial_bundle"
    BATCH_API = "batch_api"


class BatchApiMode(str, Enum):
    """Batch API preference for providers that support async batch jobs."""

    DISABLED = "disabled"
    NIGHTLY = "nightly"
    OPPORTUNISTIC = "opportunistic"
```

### New `Settings` fields

```python
QUEUE_PROCESSING_MODE: QueueProcessingMode = Field(
    default=QueueProcessingMode.PER_REQUEST,
    description=(
        "How the queue processor issues provider API calls:\n"
        "- per_request: one provider call per queued request (current behaviour).\n"
        "- serial_bundle: dequeue multiple compatible requests and send them\n"
        "  together in a single provider API call (multi-prompt).\n"
        "- batch_api: eligible requests are grouped into async batch jobs using\n"
        "  provider-specific batch APIs (e.g. OpenAI /v1/batches)."
    ),
)

OPENAI_BATCH_API_MODE: BatchApiMode = Field(
    default=BatchApiMode.DISABLED,
    description=(
        "Batch API mode for OpenAI. Mirrors provider docs and research:\n"
        "- disabled: never use OpenAI batch API; process via chat/completions.\n"
        "- nightly: accumulate large workloads (e.g. nightly CJ runs) into JSONL\n"
        "  and submit them as /v1/batches jobs.\n"
        "- opportunistic: use batch API whenever enough compatible queued\n"
        "  requests are available."
    ),
)

ANTHROPIC_BATCH_API_MODE: BatchApiMode = Field(
    default=BatchApiMode.DISABLED,
    description=(
        "Batch API mode for Anthropic message batches. Semantics mirror\n"
        "OPENAI_BATCH_API_MODE but target /v1/messages/batches."
    ),
)

SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL: int = Field(
    default=8,
    ge=1,
    le=64,
    description=(
        "Maximum number of queued requests to bundle into a single provider API\n"
        "call when using serial bundling (multi-prompt per call)."
    ),
)

BATCH_API_MAX_REQUESTS_PER_JOB: int = Field(
    default=5000,
    ge=1,
    le=10000,
    description=(
        "Maximum number of requests to place into a single provider batch job.\n"
        "Must respect provider-specific limits."
    ),
)

BATCH_API_MAX_BYTES_PER_JOB: int = Field(
    default=180_000_000,
    description=(
        "Maximum payload size in bytes for a single batch job. Should be kept\n"
        "below provider limits (e.g. 200 MB for OpenAI JSONL)."
    ),
)

BATCH_API_POLL_INTERVAL_SECONDS: float = Field(
    default=30.0,
    description="How often to poll batch job status from providers.",
)

BATCH_API_JOB_TTL_HOURS: int = Field(
    default=24,
    description="How long to keep batch job metadata before cleanup.",
)
```

### Provider-side metadata

When `QueueProcessorImpl` resolves provider + model for a `QueuedRequest`, it should add:

- `resolved_provider: str`  e.g. `"openai"`, `"anthropic"`.
- `resolved_model: str`  concrete model id chosen.
- `queue_processing_mode: str`  `settings.QUEUE_PROCESSING_MODE.value`.

These live in `QueuedRequest.request_data.metadata` alongside the CJ keys and support bundling/diagnostics.

## Serial Bundling (Phase 1 Implementation Plan)

Objective: Implement `QueueProcessingMode.SERIAL_BUNDLE` in LLM Provider Service to reduce external HTTP calls without touching provider async batch APIs yet.

### Behaviour

- When `QUEUE_PROCESSING_MODE == SERIAL_BUNDLE`:
  - `QueueProcessorImpl._process_queue_loop` should process multiple compatible `QueuedRequest`s together.
  - Compatibility: same `resolved_provider`, same effective model, and optionally the same `cj_llm_batching_mode`.
- Fallback: if bundling fails or conditions are not met, process the request via the existing per-request path.

### Changes in `QueueProcessorImpl`

1. **Dispatch based on mode**

   In `_process_queue_loop`:

   ```python
   if self.settings.QUEUE_PROCESSING_MODE == QueueProcessingMode.SERIAL_BUNDLE:
       await self._process_request_serial_bundle()
   else:
       request = await self.queue_manager.dequeue()
       if not request:
           await asyncio.sleep(self.settings.QUEUE_POLL_INTERVAL_SECONDS)
           continue
       await self._process_request(request)
   ```

   `_process_request_serial_bundle` will internally dequeue the first request.

2. **New method: `_process_request_serial_bundle`**

   High-level steps:

   - Dequeue the first request.
   - Resolve provider and overrides exactly as `_process_request` does today.
   - Collect up to `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` additional compatible requests.
   - Call a new `ComparisonProcessorImpl.process_comparison_batch` to execute them in one provider API call.
   - For each result, reuse `_handle_request_success` or `_handle_request_hule_error` as appropriate.

3. **New method: `process_comparison_batch`**

   In `ComparisonProcessorImpl`:

   ```python
   async def process_comparison_batch(
       self,
       provider: LLMProviderType,
       requests: list[LLMComparisonRequest],
       correlation_ids: list[UUID],
       overrides: dict[str, Any],
   ) -> list[LLMOrchestratorResponse]:
       """Process a batch of comparison requests using a single provider call when possible.

       Implementations may use provider-specific multi-prompt patterns, but
       must always return one LLMOrchestratorResponse per input request.
       """
   ```

   - For providers that support multi-prompt (OpenAI, Anthropic), this method can use a single API call.
   - For others, or as a first iteration, it can just loop and call `process_comparison` per request (no behavioural change but common code path).

4. **Compatibility criteria for bundling**

   In `_process_request_serial_bundle`, when dequeuing additional requests, only accept those where:

   - `request.request_data.llm_config_overrides` resolves to the same provider/model/temperature/system prompt as the first request, and
   - (Optionally) `request.request_data.metadata.get("cj_llm_batching_mode")` matches.

   This avoids mixing incompatible workloads in a single provider API call.

5. **Metrics**

   Add metrics for observability:

   - `llm_serial_bundle_calls_total{provider, model}`
   - `llm_serial_bundle_items_per_call_bucket{provider, model}`

   These allow comparing serial bundling vs per-request behaviour in practice.

## Batch API Client & Job Manager (Phase 2/3)

These will be implemented later once serial bundling is stable, but the contracts are:

- **BatchApiClient**   provider-specific async batch wrapper (OpenAI JSONL batches, Anthropic message batches).
- **BatchJobRef / BatchItemRequest / BatchItemResult**   *Pydantic* models representing internal batch job contracts.
- **BatchJobManagerProtocol**   coordinates job creation, polling, and fanning results back into the existing callback pipeline.

All batch-related contracts will use Pydantic models (not dataclasses) to maximize validation and type safety, since they are boundary objects between scheduler, watcher, queue processor, and any diagnostics tooling. Dataclasses remain acceptable only for small, purely internal helper types that never cross service boundaries.

## Future Enhancements and Next Steps

- **Multi-prompt batching per provider**  
  Default behaviour for `process_comparison_batch` is to loop and call `process_comparison` once per request (no multi-prompt). Provider-level multi-prompt patterns (OpenAI/Anthropic) are explicitly deferred and should be tracked in `SERVICE_FUTURE_ENHANCEMENTS` when/if needed.

- **Queue manager API surface**  
  Default is to keep the existing `dequeue()` API and implement serial bundling by repeated `dequeue()` calls in `_process_request_serial_bundle`. A richer queue API (`dequeue_many` / `peek`) is also deferred and should be tracked in `SERVICE_FUTURE_ENHANCEMENTS` if evidence emerges that it is needed.

- **Metrics implementation and dashboards**  
  Design decision: CJ exposes only lightweight metrics (`cj_llm_requests_total{batching_mode}` and `cj_llm_batches_started_total{batching_mode}`) and relies on LLM Provider Service metrics for detailed batching behaviour (HTTP calls, tokens, queue latency, bundle sizes). Next steps are to wire these metrics and surface them in ENG5 and CJ monitoring dashboards.

As these enhancements are implemented, this document and the global `SERVICE_FUTURE_ENHANCEMENTS` notes should be updated to reflect the chosen patterns.
