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

## Model Manifest Integration

### Manifest Query (`model_manifest.py:74-350`)
```python
from services.llm_provider_service.model_manifest import get_model_config, ProviderName

config = get_model_config(ProviderName.ANTHROPIC, "claude-3-5-haiku-20241022")
# Returns: ModelConfig(model_id, display_name, max_tokens, release_date, is_deprecated, ...)
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