# LLM Provider Service

Centralized LLM provider abstraction and management service for HuleEdu platform.

## Overview

The LLM Provider Service provides a unified interface for interacting with multiple LLM providers (Anthropic, OpenAI, Google, OpenRouter) with built-in resilience, caching, and observability.

## Key Features

- **Multi-Provider Support**: Anthropic/Claude, OpenAI/GPT, Google/Gemini, OpenRouter
- **Circuit Breaker Protection**: Automatic failure detection and recovery
- **Response Caching**: Redis-based caching to reduce costs and latency
- **Event-Driven Observability**: Publishes usage events for monitoring and analytics
- **Cost Tracking**: Token usage and cost estimation per request
- **Distributed Tracing**: Full OpenTelemetry integration

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

### Administrative Endpoints

- `GET /api/v1/cache/stats` - Cache performance metrics
- `POST /api/v1/cache/clear` - Clear cache (admin only)
- `GET /api/v1/usage/summary` - Usage analytics
- `GET /api/v1/circuit-breakers` - Circuit breaker states

### Health & Monitoring

- `GET /healthz` - Service health check
- `GET /metrics` - Prometheus metrics

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

### From CJ Assessment Service

```python
# HTTP client call to LLM Provider Service
async with session.post(
    "http://llm-provider-service:8080/api/v1/comparison",
    json={
        "provider": "anthropic",
        "user_prompt": prompt,
        "essay_a": essay_a_content,
        "essay_b": essay_b_content,
        "correlation_id": str(correlation_id),
        "model_override": "claude-3-opus-20240229",
        "temperature_override": 0.7,
    }
) as response:
    result = await response.json()
```

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
# Unit tests
pdm run test-unit

# Integration tests
pdm run test-integration

# Test coverage
pdm run test-coverage
```

## Migration from CJ Assessment

1. Deploy LLM Provider Service
2. Update CJ Assessment to use HTTP client instead of direct provider calls
3. Monitor both services during transition
4. Remove LLM code from CJ Assessment once stable