# LLM Provider Service

Centralized LLM provider abstraction and **queue-first** gateway for CJ Assessment and other HuleEdu workloads.

## Overview

- Asynchronous only: `POST /api/v1/comparison` always returns **202 + queue_id**; results are delivered via Kafka to the caller-supplied `callback_topic` as `LLMComparisonResultV1` envelopes.
- Resilient queueing: Redis-backed queue with automatic fallback to an in-process local queue plus optional `serial_bundle` draining for efficiency.
- Manifest-driven provider/model selection with structured output enforcement and prompt hashing (`prompt_sha256`) for replay/analytics.
- Prompt caching only (provider-side prompt reuse); **response caching is forbidden** to protect psychometric validity.
- Circuit breakers, OpenTelemetry tracing, and token/cost metrics on every request.

## Key Features

- **Callback delivery**: Results published to Kafka `callback_topic` (supplied per request); no HTTP polling endpoints.
- **Queue resilience**: Redis → Local fallback with circuit-breaker-aware queue admission and `serial_bundle` mode for compatible requests.
- **Prompt metadata integrity**: Provider implementations compute and echo `prompt_sha256` into callbacks; caller `metadata` is preserved verbatim with additive timing/usage fields.
- **Model manifest**: `model_manifest.py` is the single source of truth; callers should resolve models via manifest helpers before sending overrides.
- **Observability**: Prometheus metrics for queue depth/wait time, prompt-cache usage, serial-bundle counts, and callback outcomes; full OTEL traces.

## Architecture (at a glance)

- Quart API: `/api/v1/comparison`, `/providers`, `/providers/{provider}/test`, `/healthz`, `/metrics`.
- Queue Processor drains Redis/local queues and invokes provider implementations (Anthropic, OpenAI, Google, OpenRouter, Mock) via orchestrator.
- Callback Publisher emits `EventEnvelope[LLMComparisonResultV1]` to the request's `callback_topic`; queue entries are removed on publish.
- Shared connection pools + prompt-cache utilities; no response cache is ever used.

## API Endpoints

- `POST /api/v1/comparison` — Enqueue comparison, requires `callback_topic`; returns `LLMQueuedResponse` (202).
- `GET /api/v1/providers` — List configured providers and circuit breaker state.
- `POST /api/v1/providers/{provider}/test` — Connectivity test for a specific provider.
- `GET /healthz`, `GET /metrics` — Health and Prometheus metrics.

## Response Contracts

### 202 Enqueue Response (`LLMQueuedResponse`)
```json
{
  "queue_id": "uuid",
  "status": "queued",
  "message": "Request queued for processing. Result will be delivered via callback to topic: <topic>",
  "estimated_wait_minutes": 1
}
```

### Kafka Callback (`LLMComparisonResultV1`)
```json
{
  "request_id": "queue uuid",
  "correlation_id": "uuid",
  "winner": "essay_a",
  "justification": "...",
  "confidence": 4.3,
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "response_time_ms": 1234,
  "token_usage": {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020},
  "cost_estimate": 0.0021,
  "requested_at": "2025-11-25T00:00:00Z",
  "completed_at": "2025-11-25T00:00:01Z",
  "request_metadata": {
    "essay_a_id": "...",
    "essay_b_id": "...",
    "prompt_sha256": "...",
    "bos_batch_id": "..."
  }
}
```
Errors use the same envelope with `error_detail` set and winner/justification/confidence omitted.

## Configuration (env vars, prefix `LLM_PROVIDER_SERVICE_`)

```bash
# Service identity
LLM_PROVIDER_SERVICE_PORT=8080
LLM_PROVIDER_SERVICE_LOG_LEVEL=INFO
LLM_PROVIDER_SERVICE_ENVIRONMENT=development

# Core dependencies
LLM_PROVIDER_SERVICE_REDIS_URL=redis://localhost:6379/0
LLM_PROVIDER_SERVICE_KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Queue + batching
LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=per_request      # per_request | serial_bundle | batch_api
LLM_PROVIDER_SERVICE_SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL=8  # 1-64
LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled                # disabled | nightly | opportunistic

# Prompt caching (prompt blocks only, never responses)
LLM_PROVIDER_SERVICE_ENABLE_PROMPT_CACHING=true
LLM_PROVIDER_SERVICE_PROMPT_CACHE_TTL_SECONDS=3600
LLM_PROVIDER_SERVICE_USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS=false

# Providers
LLM_PROVIDER_SERVICE_ANTHROPIC_API_KEY=...
LLM_PROVIDER_SERVICE_OPENAI_API_KEY=...
LLM_PROVIDER_SERVICE_GOOGLE_API_KEY=...
LLM_PROVIDER_SERVICE_OPENROUTER_API_KEY=...
LLM_PROVIDER_SERVICE_USE_MOCK_LLM=false

# Circuit breakers
LLM_PROVIDER_SERVICE_CIRCUIT_BREAKER_ENABLED=true
LLM_PROVIDER_SERVICE_LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
LLM_PROVIDER_SERVICE_LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=120
```

**Model family tracking**: Configure `LLM_PROVIDER_SERVICE_ACTIVE_MODEL_FAMILIES='{"anthropic":["claude-haiku","claude-sonnet"],...}'` to drive the model checker CLI exit codes.

### Queue Processing Mode

`LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE` determines how dequeued requests flow
through the comparison processor:

- `per_request` (default): call `process_comparison` exactly once per dequeued item.
- `serial_bundle`: dequeue the leading request plus up to
  `LLM_PROVIDER_SERVICE_SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` compatible follow-ups,
  then invoke `process_comparison_batch` once for the entire group. Requests are
  considered compatible when the resolved provider, model override, and optional
  `cj_llm_batching_mode` hint all match. This keeps provider calls sequential
  while dramatically reducing queue round-trips.
- `batch_api` (previously labeled `provider_batch_api` in CJ hints): reserved for
  native provider batch endpoints. Until that lands, it behaves the same as
  `serial_bundle` but remains separately configurable via
  `LLM_PROVIDER_SERVICE_BATCH_API_MODE` (disabled/nightly/opportunistic).

Use `LLM_PROVIDER_SERVICE_SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` (default `8`, range
`1-64`) to cap how many compatible queued items can be drained per bundle. Each
bundle is processed within a single queue-loop iteration, and an incompatible
request is held in-memory so it becomes the next iteration's lead item rather
than being re-enqueued.

The queue processor logs `queue_processing_mode` for every dequeued request and the
callback payload is identical in all modes, so you can safely flip the flag in
development to validate future batching paths.

### Serial bundle observability

When `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle` (or
`provider_batch_api`) is enabled, the queue processor now emits dedicated metrics:

- `llm_provider_queue_depth{queue_type="total"|"queued"}` — instantaneous queue size.
- `llm_provider_queue_wait_time_seconds{queue_processing_mode="serial_bundle",result="success"|"failure"|"expired"}` — time spent waiting in the queue before a callback is published.
- `llm_provider_comparison_callbacks_total{queue_processing_mode, result}` — processed comparison throughput split by outcome.
- `llm_provider_serial_bundle_calls_total{provider, model}` — total serial-bundle comparison calls.
- `llm_provider_serial_bundle_items_per_call{provider, model}` — number of items per serial-bundle call.

In addition to the Prometheus metrics, a `queue_metrics_snapshot` log line is
written every 30 seconds whenever a non-`per_request` mode is active. This log
includes the queue depth, usage percentage, whether the queue is still accepting
new requests, and (for serial bundles) the bundle size/provider metadata so you
can correlate rollouts with Redis/local backlog changes.

#### Rolling out `serial_bundle` safely (ENG5-first sketch)

- Start in **development** or ENG5-only environments by setting:
  - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
  - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
- Verify serial-bundle behaviour via tests:
  - `pdm run pytest-root services/llm_provider_service/tests/integration/test_serial_bundle_integration.py`
- During trial runs, watch:
  - `llm_provider_serial_bundle_calls_total{provider,model}` and `llm_provider_serial_bundle_items_per_call{provider,model}`
  - `llm_provider_queue_wait_time_seconds{queue_processing_mode="serial_bundle",result=...}`
- To roll back, set `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=per_request` and redeploy; callbacks and HTTP contracts remain unchanged across modes.

## Development

### Local Setup

```bash
# Install dependencies
pdm install

# Run service locally (hot reload)
pdm run dev

# Run tests for this service
pdm run pytest-root services/llm_provider_service/tests
```

### Docker Build

```bash
# Build image
docker build -t llm-provider-service .

# Run container
docker run -p 8080:8080 llm-provider-service
```

## Integration

### Request Format (LLMComparisonRequest)

```json
{
  "user_prompt": "Full comparison prompt (essays embedded)",
  "prompt_blocks": [ { "role": "system", "content": "..." }, { "role": "user", "content": "..." } ],
  "callback_topic": "huleedu.llm_provider.comparison_result.v1",
  "llm_config_overrides": {
    "provider_override": "anthropic",      // Required
    "model_override": "claude-haiku-4-5-20251001",
    "temperature_override": 0.1,
    "system_prompt_override": "..."
  },
  "correlation_id": "uuid-string",         // Optional
  "user_id": "optional-user-id",
  "metadata": { "essay_a_id": "...", "essay_b_id": "...", "bos_batch_id": "..." }
}
```

> **Prompt hash source of truth**: The queue processor appends `prompt_sha256` to every callback—success and error alike. Downstream consumers must treat this hash as authoritative and avoid recomputing prompt digests locally.

### Integration Example (enqueue + consume callback)

```python
from common_core import LLMComparisonRequest
from common_core.events.llm_provider_events import LLMComparisonResultV1

payload = LLMComparisonRequest(
    user_prompt=rendered_prompt,
    prompt_blocks=prompt_blocks,
    callback_topic="huleedu.llm_provider.comparison_result.v1",
    llm_config_overrides=overrides,
    metadata={"essay_a_id": essay_a_id, "essay_b_id": essay_b_id},
)

resp = await http_client.post("http://llm-provider-service:8080/api/v1/comparison", json=payload.model_dump())
assert resp.status == 202
queue_id = (await resp.json())["queue_id"]

async for envelope in kafka_consumer:  # subscribed to callback_topic
    result = LLMComparisonResultV1.model_validate(envelope.data)
    if result.request_id == str(queue_id):
        handle_result(result)
        break
```

## Model Manifest

### Structure (Modularized)
```
manifest/
  types.py          # ModelConfig, ProviderName, StructuredOutputMethod
  openai.py         # 9 OpenAI models + validators
  anthropic.py      # 2 Claude models + validators
  google.py         # 1 Gemini model + validators
  openrouter.py     # 1 OpenRouter model + validators
  __init__.py       # Aggregator + helper functions
model_manifest.py   # Backward-compatible re-export layer
```

### Parameter Compatibility (NEW)
```python
# ModelConfig now includes parameter support flags
config.supports_temperature         # bool - GPT-5: False, GPT-4.1/4o: True
config.supports_top_p               # bool
config.supports_frequency_penalty   # bool
config.supports_presence_penalty    # bool
config.uses_max_completion_tokens   # bool - reasoning models: True
```

### Provider Implementation
```python
# OpenAI provider conditionally sends parameters based on model capabilities
# openai_provider_impl.py:173-241
model_config = get_model_config(ProviderName.OPENAI, model)
if model_config.supports_temperature:
    payload["temperature"] = temperature  # GPT-5: omitted
else:
    logger.info("Omitting temperature - model does not support")
```

### Query API
```python
from services.llm_provider_service.model_manifest import get_model_config, ProviderName

config = get_model_config(ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001")
# Returns: ModelConfig with all capabilities, pricing, performance metadata
```

### Admin CLI
```bash
# List models with parameter compatibility
pdm run llm-admin list-models --provider openai

# Show detailed capabilities for specific model
pdm run llm-admin show-capabilities --provider openai --model gpt-5-mini-2025-08-07

# Dry-run: preview API payload (no network call)
pdm run llm-admin dry-run-payload --provider openai --model gpt-5-mini-2025-08-07 --temperature 0.7

# Test model with real API call (requires OPENAI_API_KEY)
pdm run llm-admin call --provider openai --model gpt-4o-mini-2024-07-18 --essay-a "A" --essay-b "B"
```

### Building LLMConfigOverrides
```python
from common_core.events.cj_assessment_events import LLMConfigOverrides

overrides = LLMConfigOverrides(
    provider_override=LLMProviderType.ANTHROPIC,
    model_override=config.model_id,  # From manifest
    temperature_override=0.3,
    system_prompt_override="Custom CJ prompt",
)
```

### Event Integration Flow
```
CLI/Service → validate_llm_overrides() → ELS_CJAssessmentRequestV1(llm_config_overrides)
  → Kafka → CJ Service → HTTP POST /api/v1/comparison → LLM Provider Service
  → LLMComparisonResultV1 callback (includes actual model/provider/cost)
```

**Files**:
- Manifest: `services/llm_provider_service/model_manifest.py`
- Client: `services/cj_assessment_service/implementations/llm_provider_service_client.py:44-234`
- CLI validation: `scripts/cj_experiments_runners/eng5_np/cli.py:45-169`
- Tests: `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py`

## Callback Contract & Metadata Echo

- Every queued comparison request becomes exactly one callback:
  `_publish_callback_event()` and `_publish_callback_event_error()` set
  `LLMComparisonResultV1.request_id = str(queue_id)` and remove the queue entry
  immediately after publishing. Queue completion/removal behaviour is exercised by
  `tests/integration/test_queue_processor_completion_removal.py`.
- The queue processor **never mutates** CJ metadata. `request_data.metadata` is copied
  into `LLMComparisonResultV1.request_metadata` verbatim and only receives additive keys:
  - `prompt_sha256` is appended on success (from provider metadata) or recomputed on error.
  - Future batching hints (e.g., `cj_llm_batching_mode`, `comparison_iteration`) are passed
    straight through because `CJLLMComparisonMetadata` marks them as additive.
  - Prompt cache usage from provider metadata (`cache_read_input_tokens`,
    `cache_creation_input_tokens`, `usage`) is appended when present without overwriting
    caller-supplied keys.
- Tests in `tests/unit/test_callback_publishing.py` lock this behaviour by asserting
  that `essay_a_id`, `essay_b_id`, and `bos_batch_id` survive success/error callbacks.

Use this section when wiring new batching fields: as long as the caller adds them to
`LLMComparisonRequest.metadata`, the queue processor will echo them back without altering
the existing contract.

## Anthropic operational notes (rate limits, overloads, caching)

- 429 responses now respect `Retry-After` and bubble a retryable error; 529/`overloaded_error` and 5xx codes are treated as transient server errors for the retry manager.
- `stop_reason=max_tokens` triggers a structured external-service error so callers can raise limits instead of silently using truncated tool payloads.
- Requests include `metadata.correlation_id` and `prompt_sha256` for Anthropic-side traceability.
- Prompt caching: the system prompt and tool schema are sent as `cache_control.type=ephemeral` blocks; TTL defaults to 5m (extended to `PROMPT_CACHE_TTL_SECONDS`, default 3600s, when `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS=true`) and can be disabled with `ENABLE_PROMPT_CACHING=false`.

## Updating LLM Models

### Manual Update Workflow

This workflow is used to check for new models from providers and update the model manifest when new compatible models become available.

#### 1. Check for New Models

Run the model version checker CLI to discover newly available models from provider APIs:

```bash
# Check specific provider
pdm run llm-check-models --provider anthropic

# Check all providers
pdm run llm-check-models --provider all

# Generate compatibility report
pdm run llm-check-models --provider anthropic --report compatibility_report.json
```

**Exit codes**:
- `0`: All up-to-date (no changes needed)
- `2`: API error or authentication failure
- `3`: Breaking changes detected (requires manual intervention)
- `4`: In-family updates (new model variants in tracked families - actionable)
- `5`: Untracked families detected (informational only)

**Note**: Exit codes prioritize actionable issues. Code 4 (tracked family updates) takes precedence over code 5 (untracked families). Use `ACTIVE_MODEL_FAMILIES` configuration to control which families trigger actionable alerts.

#### 2. Review Compatibility Report

When the CLI returns exit code `3`, `4`, or `5`, review the generated report:

**JSON Report** (for CI/CD automation):
```json
{
  "check_date": "2025-11-09T02:30:00Z",
  "provider": "anthropic",
  "current_model": {
    "model_id": "claude-haiku-4-5-20251001",
    "status": "compatible"
  },
  "discovered_models": [
    {
      "model_id": "claude-sonnet-4-5-20250929",
      "compatibility_status": "unknown",
      "recommendation": "requires_testing"
    }
  ],
  "breaking_changes": []
}
```

**Markdown Report** (for human review):
```bash
pdm run llm-check-models --provider anthropic --report report.md --format markdown
```

#### 3. Run Compatibility Tests

Before adding new models to the manifest, validate they work correctly with CJ assessment prompts:

```bash
# Run integration tests with new model checking enabled
CHECK_NEW_MODELS=1 pdm run pytest-root services/llm_provider_service/tests/integration/test_model_compatibility.py -v -m "financial"
```

**WARNING**: These tests make real API calls and incur costs. Tests validate:
- Structured output parsing (winner, justification, confidence)
- Response quality and format compliance
- Error handling and API compatibility

#### 4. Update Model Manifest

If compatibility tests pass, add the new model to `model_manifest.py`:

```python
# services/llm_provider_service/model_manifest.py

ANTHROPIC_MODELS = [
    # Existing models...

    # Add new model
    ModelConfig(
        model_id="claude-3-5-sonnet-20250101",  # From compatibility report
        provider=ProviderName.ANTHROPIC,
        display_name="Claude 3.5 Sonnet (January 2025)",
        api_version="2023-06-01",
        structured_output_method=StructuredOutputMethod.TOOL_USE,
        capabilities={
            "tool_use": True,
            "vision": True,
            "function_calling": True,
            "json_mode": True,
        },
        max_tokens=8192,
        context_window=200_000,
        supports_streaming=True,
        release_date=date(2025, 1, 1),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.0008,  # Check provider pricing
        cost_per_1k_output_tokens=0.004,
        recommended_for=["comparison", "analysis"],
        notes="Updated Sonnet model with improved reasoning.",
    ),
]

# Optionally update default model
SUPPORTED_MODELS = ModelRegistry(
    models={...},
    default_models={
        ProviderName.ANTHROPIC: "claude-3-5-sonnet-20250101",  # New default
        ...
    },
)
```

#### 5. Update Configuration (if changing default)

If switching the default model, update environment variables:

```bash
# .env or production secrets
LLM_PROVIDER_SERVICE_ANTHROPIC_MODEL_ID=claude-3-5-sonnet-20250101
```

**Note**: The manifest takes precedence. Environment variables are only used for debugging/overrides.

#### 6. Validate Changes

```bash
# Run typecheck
pdm run typecheck-all

# Run all LLM provider service tests
pdm run pytest-root services/llm_provider_service/tests/unit/ -v
pdm run pytest-root services/llm_provider_service/tests/integration/ -v -k "not financial"

# Verify manifest integration tests pass
pdm run pytest-root services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py -v
```

#### 7. Deploy and Monitor

After deploying the updated manifest:

1. **Health Check**: Verify service starts correctly
   ```bash
   curl http://llm-provider-service:8090/healthz
   ```

2. **Grafana Dashboards**: Monitor for anomalies
   - LLM request error rates
   - Response time percentiles (p50, p95, p99)
   - Token usage and cost trends
   - Circuit breaker state

3. **Structured Output Parsing**: Watch for validation failures
   ```
   llm_structured_output_failures_total{provider="anthropic", model="..."}
   ```

4. **Initial Production Testing**: Run a small batch comparison (see
   `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` for the end-to-end checklist)
  ```bash
  # Use ENG5 batch runner with specific model
  pdm run eng5-np submit --llm-model claude-3-5-sonnet-20250101 --batch-size 10
  ```

#### Breaking Changes

If the CLI reports breaking changes (exit code `3`), **DO NOT** proceed automatically:

1. **Review breaking changes** in the compatibility report
2. **Update provider implementations** if API contracts changed
3. **Update integration tests** to reflect new behavior
4. **Coordinate deployment** with dependent services

Common breaking changes:
- API version requirements change
- Structured output method changes (json → tool_use)
- Default model deprecation
- Maximum token limits reduced
- New required authentication headers

## Monitoring

### Prometheus Metrics

- `llm_requests_total` - Total LLM requests by provider and status
- `llm_response_duration_seconds` - Response time histogram
- `llm_tokens_used_total` - Token usage by provider
- `llm_cost_dollars_total` - Cumulative cost by provider
- `llm_circuit_breaker_state` - Circuit breaker states
- `llm_provider_queue_expiry_total{provider, queue_processing_mode, expiry_reason}` - Dedicated counter for expired queue requests.
- `llm_provider_queue_expiry_age_seconds{provider, queue_processing_mode}` - Histogram of request age at expiry.
- `llm_provider_serial_bundle_calls_total{provider, model}` - Total serial-bundle comparison calls.
- `llm_provider_serial_bundle_items_per_call{provider, model}` - Items-per-call histogram for serial bundling.

`expiry_reason="ttl"` is emitted from `QueueProcessorImpl` when a dequeued request has passed its TTL; `expiry_reason="cleanup"` is emitted from `ResilientQueueManagerImpl.cleanup_expired()` when Redis/local cleanup purges entries that never reached the processor (using `provider="unknown"` to avoid extra lookup and cardinality).

### Kafka Events

- `huleedu.llm_provider.request_started.v1`
- `huleedu.llm_provider.request_completed.v1`
- `huleedu.llm_provider.failure.v1`

## Testing

```bash
pdm run pytest-root services/llm_provider_service/tests/unit/ -v       # Unit tests
pdm run pytest-root services/llm_provider_service/tests/integration/ -v  # Integration tests
```
