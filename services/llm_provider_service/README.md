# LLM Provider Service

Centralized LLM provider abstraction and management service for HuleEdu platform.

## Overview

Centralized LLM provider abstraction with queue-based resilience, model manifest management, and NO response caching (preserves psychometric validity).

## Key Features

- **Multi-Provider Support**: Anthropic, OpenAI, Google, OpenRouter with manifest-based model selection
- **Queue Resilience**: Redis → Local queue fallback with 200/202 response pattern
- **Circuit Breaker Protection**: Automatic provider failure detection and recovery
- **Model Manifest**: Centralized single source of truth for all model versions
- **NO Caching**: Fresh LLM responses for every request (psychometric validity)
- **Cost Tracking**: Token usage and cost estimation per request
- **OpenTelemetry**: Full distributed tracing across queue operations

## Architecture

```
┌─────────────────────┐
│   API Gateway       │
└──────────┬──────────┘
           │ HTTP
┌──────────▼──────────┐     ┌─────────────┐
│  LLM Provider       │────▶│    Redis    │
│    Service          │     │   (Cache)   │
└──────────┬──────────┘     └─────────────┘
           │
           ├─────────────┐
           │             │
     ┌─────▼───┐   ┌─────▼───┐
     │Anthropic│   │ OpenAI  │  ...
     └─────────┘   └─────────┘
```

## API Endpoints

### Core Endpoints

- `POST /api/v1/comparison` - Generate LLM comparison for two essays
- `GET /api/v1/providers` - List available providers and their status
- `POST /api/v1/providers/{provider}/test` - Test provider connectivity

### Health & Monitoring

- `GET /healthz` - Service health check with dependency status
- `GET /metrics` - Prometheus metrics

### Response Format (CJ Assessment Compatible)

The service returns responses in a format compatible with CJ Assessment Service:

```json
{
  "winner": "Essay A",         // or "Essay B"
  "justification": "...",      // Reasoning for the choice
  "confidence": 4.5,           // 1-5 scale
  "provider": "anthropic",     // Actual provider used
  "model": "claude-3-haiku",   // Actual model used
  "cached": false,             // Whether from cache
  "response_time_ms": 1500,    // Response time
  "correlation_id": "...",     // Request correlation ID
  "token_usage": {...},        // Token usage details
  "cost_estimate": 0.002       // Estimated cost in USD
}

## Configuration

The service is configured via environment variables with the prefix `LLM_PROVIDER_SERVICE_`:

```bash
# Service Configuration
LLM_PROVIDER_SERVICE_PORT=8080
LLM_PROVIDER_SERVICE_LOG_LEVEL=INFO

# Provider API Keys
LLM_PROVIDER_SERVICE_ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER_SERVICE_OPENAI_API_KEY=sk-...
LLM_PROVIDER_SERVICE_GOOGLE_API_KEY=...
LLM_PROVIDER_SERVICE_OPENROUTER_API_KEY=...

# Circuit Breaker Settings
LLM_PROVIDER_SERVICE_CIRCUIT_BREAKER_ENABLED=true
LLM_PROVIDER_SERVICE_LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
LLM_PROVIDER_SERVICE_LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=120

# Cache Configuration
LLM_PROVIDER_SERVICE_LLM_CACHE_ENABLED=true
LLM_PROVIDER_SERVICE_LLM_CACHE_TTL=3600
```

## Development

### Local Setup

```bash
# Install dependencies
pdm install

# Run service locally
pdm run dev

# Run tests
pdm run test
```

### Docker Build

```bash
# Build image
docker build -t llm-provider-service .

# Run container
docker run -p 8080:8080 llm-provider-service
```

## Integration

### Request Format

The service expects requests with the following structure:

```json
{
  "user_prompt": "Compare these two essays...",
  "essay_a": "First essay content...",
  "essay_b": "Second essay content...",
  "llm_config_overrides": {
    "provider_override": "anthropic",        // Required: no default
    "model_override": "claude-3-haiku",      // Optional
    "temperature_override": 0.1,             // Optional
    "system_prompt_override": "...",         // Optional
    "max_tokens_override": 1000              // Optional
  },
  "correlation_id": "uuid-string",           // Optional
  "metadata": {}                             // Optional
}
```

### Integration Example (CJ Assessment Service)

```python
# HTTP client call to LLM Provider Service
async with session.post(
    "http://llm-provider-service:8090/api/v1/comparison",
    json={
        "user_prompt": "Compare these two essays",
        "essay_a": essay_a_content,
        "essay_b": essay_b_content,
        "llm_config_overrides": {
            "provider_override": "anthropic",  # Required
            "model_override": "claude-3-5-haiku-20241022",
            "temperature_override": 0.1,
        },
        "correlation_id": str(correlation_id),
    }
) as response:
    result = await response.json()
    # result contains: winner, justification, confidence (1-5 scale)
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
- `1`: New models available (non-breaking updates)
- `2`: API error or authentication failure
- `3`: Breaking changes detected (requires manual intervention)

#### 2. Review Compatibility Report

When the CLI returns exit code `1` or `3`, review the generated report:

**JSON Report** (for CI/CD automation):
```json
{
  "check_date": "2025-11-09T02:30:00Z",
  "provider": "anthropic",
  "current_model": {
    "model_id": "claude-3-5-haiku-20241022",
    "status": "compatible"
  },
  "discovered_models": [
    {
      "model_id": "claude-3-5-sonnet-20250101",
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

### Kafka Events

- `huleedu.llm_provider.request_started.v1`
- `huleedu.llm_provider.request_completed.v1`
- `huleedu.llm_provider.failure.v1`

## Testing

```bash
pdm run pytest-root services/llm_provider_service/tests/unit/ -v       # Unit tests
pdm run pytest-root services/llm_provider_service/tests/integration/ -v  # Integration tests
```
