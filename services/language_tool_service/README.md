# Language Tool Service

HTTP service providing grammar and style checking via managed LanguageTool Java process.

## Service Overview

- **Port**: 8085 (HTTP), 8081 (internal LanguageTool)
- **Purpose**: Grammar + spelling insights with optional rule tuning (picky mode, category filters)
- **Architecture**: Quart HTTP + Java subprocess management
- **Mode**: Dual-mode (stub for dev/test, real for production)

## API

### POST /v1/check

```json
// Request
{
    "text": "Intro clause missing comma should be caught.",
    "language": "en-US",
    "level": "picky",                     // optional: enable stricter rules
    "enabledCategories": ["GRAMMAR", "PUNCTUATION"],
    "enabledOnly": true                    // optional: run only listed categories
}

// Response (200 OK)
{
    "errors": [...],
    "total_grammar_errors": 2,
    "grammar_category_counts": {"GRAMMAR": 1, "PUNCTUATION": 1},
    "language": "en-US",
    "processing_time_ms": 120
}
```

> Typo categories are preserved so downstream services can reconcile spelling coverage with the Spellchecker Service. Only whitespace-only findings are filtered out.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGUAGE_TOOL_SERVICE_HTTP_PORT` | 8085 | HTTP API port |
| `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT` | 8081 | LanguageTool server port |
| `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_JAR_PATH` | /app/languagetool/languagetool-server.jar | JAR location |
| `LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE` | 512m | JVM heap size |
| `USE_STUB_LANGUAGE_TOOL` | false | Force stub mode |

## Development

### Running Locally

```bash
# Stub mode (no JAR required)
USE_STUB_LANGUAGE_TOOL=true pdm run dev

# Real mode (requires JAR)
pdm run dev
```

### Testing

```bash
# Run all tests (213 total: 167 unit + 46 integration)
pdm run test-all

# Unit tests only
pdm run test-unit

# Integration tests only  
pdm run test-integration
```

### Test Structure

```
tests/
├── unit/                     # 167 tests - mock Java process
│   ├── test_language_tool_manager.py
│   ├── test_language_tool_wrapper.py
│   └── ...
└── integration/              # 46 tests - real HTTP, stub LanguageTool
    ├── conftest.py          # Shared fixtures
    ├── test_languagetool_process_lifecycle.py
    ├── test_grammar_analysis_pipeline.py
    ├── test_metrics_emission.py
    ├── test_environment_configuration.py
    ├── test_configuration_validation.py
    └── test_configuration_di_integration.py
```

## Docker

### Building

```bash
# Development (with hot-reload)
pdm run dev build dev language_tool_service

# Production
docker compose build language_tool_service
```

### JAR Acquisition

The LanguageTool JAR is downloaded during Docker build:

```dockerfile
RUN wget https://languagetool.org/download/LanguageTool-6.3.zip && \
    unzip LanguageTool-6.3.zip && \
    mv LanguageTool-6.3/languagetool-server.jar /app/languagetool/
```

## Monitoring

- **Health**: GET /healthz
- **Metrics**: GET /metrics (Prometheus format)
- **JVM Health**: GET /health/jvm

### Key Metrics

- `wrapper_duration_seconds{language}`: Processing time
- `api_errors_total{endpoint,error_type}`: Error counts

## Known Limitations

### Apostrophe Detection
- **Detects**: Misplaced apostrophes (e.g., "two week's time" → "two weeks' time")
- **Does NOT detect**: Missing apostrophes (e.g., "weeks time" is not flagged)
- **Works**: Common contractions (e.g., "its" → "it's")

### Comma Detection
- Introductory phrases of 4 words or fewer may not trigger comma rules
- Example: "In a week's time" may not suggest a comma

### Configuration Note
- Category filtering has been removed (previously blocked TYPOS category)
- All LanguageTool categories are now passed through
- Only whitespace-only issues are filtered at the wrapper level

## Architecture Decisions

1. **Dual-mode operation**: Automatic fallback from real → stub when JAR missing
2. **Category filtering**: No categories blocked, only whitespace issues filtered
3. **Process management**: Health checks, auto-restart, graceful shutdown
4. **Resource cleanup**: Async context managers prevent leaks
5. **Stub mode**: Full functionality for testing without Java dependency
