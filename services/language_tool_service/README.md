# Language Tool Service

## Purpose

The Language Tool Service is a stateless HTTP microservice that provides fine-grained grammar categorization for text analysis in the HuleEdu platform. It integrates with the open-source LanguageTool Java library to detect and categorize grammar errors, excluding spelling/typo categories which are handled by the Spellchecker Service.

## Architecture

- **Type**: Pure HTTP microservice (no Kafka worker, no database)
- **Port**: 8085
- **Framework**: Quart with Dishka DI
- **Integration**: LanguageTool Java process wrapper

## Key Domain Entities

- **GrammarError**: Enhanced error model with context (from `common_core.events.nlp_events`)
- **GrammarCheckRequest/Response**: HTTP contracts (from `common_core.api_models.language_tool`)

## API Endpoints

### Health & Monitoring

- `GET /healthz` - Service health check with dependency status
- `GET /metrics` - Prometheus metrics exposition

### Grammar Analysis (Pending Implementation)

- `POST /v1/check` - Analyze text for grammar errors
  - Request: `{ text: str, language: str }`
  - Response: `{ errors: list, total_grammar_errors: int, category_counts: dict }`

## Events

This service does not produce or consume Kafka events. It operates as a synchronous HTTP service called by the NLP Service.

## Environment Variables

```bash
# Service Configuration
LANGUAGE_TOOL_SERVICE_HTTP_PORT=8085        # HTTP server port
LANGUAGE_TOOL_SERVICE_LOG_LEVEL=INFO        # Logging level

# LanguageTool Configuration (Future)
LANGUAGE_TOOL_SERVICE_JAVA_HEAP_SIZE=2G     # JVM heap size
LANGUAGE_TOOL_SERVICE_LANGUAGETOOL_TIMEOUT=30  # Request timeout in seconds
LANGUAGE_TOOL_SERVICE_LANGUAGETOOL_MODE=embedded  # embedded|external
```

## Local Development

### Prerequisites

- Python 3.11+
- PDM package manager
- Java 11+ (for LanguageTool integration)

### Setup

```bash
# Install dependencies
pdm install

# Run the service
cd services/language_tool_service
pdm run python -m quart run --host 0.0.0.0 --port 8085
```

### Testing

```bash
# Run unit tests
pdm run pytest services/language_tool_service/tests/unit/ -v

# Test health endpoint
curl http://localhost:8085/healthz

# Test metrics endpoint
curl http://localhost:8085/metrics
```

## Implementation Status

- ✅ Service foundation (Quart app, DI, health endpoints)
- ✅ Contract definitions in `common_core`
- ✅ Stub implementation for development
- ⏳ Java LanguageTool wrapper integration
- ⏳ Grammar check API endpoint
- ⏳ NLP Service integration
- ⏳ Docker containerization
- ⏳ Production observability

## Integration with Other Services

- **NLP Service**: Primary consumer via HTTP POST to `/v1/check`
- **No direct database access**: Stateless operation
- **No Kafka integration**: Pure synchronous HTTP

## References

- Task: `TASKS/TASK-052-language-tool-service-implementation.md`
- Rules: 041 (HTTP Blueprint), 042 (Async/DI), 043.2 (Correlation), 048 (Error Handling)
- LanguageTool: https://languagetool.org/