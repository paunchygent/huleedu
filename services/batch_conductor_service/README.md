# Batch Conductor Service (BCS)

## Overview **Internal pipeline dependency resolution and intelligent pipeline generation**

The Batch Conductor Service (BCS) is an internal Quart-based microservice responsible for analyzing batch states and resolving pipeline dependencies. It provides intelligent pipeline construction based on essay lifecycle states and processing requirements.

## Architecture

- **Framework**: Quart + Hypercorn (internal service consistency)
- **Communication**: Internal HTTP API for BOS integration
- **Dependencies**: Essay Lifecycle Service (ELS) for batch state analysis
- **Port**: 4002 (internal only)

## Key Responsibilities

1. **Pipeline Dependency Resolution**: Determines required preprocessing steps
2. **Batch State Analysis**: Queries ELS for current essay statuses
3. **Intelligent Pipeline Generation**: Constructs optimized processing pipelines
4. **Error Handling**: Graceful degradation when dependencies are unavailable

## API Endpoints

### Internal API

- `POST /internal/v1/pipelines/define` - Pipeline dependency resolution
- `GET /healthz` - Health check
- `GET /metrics` - Prometheus metrics

## Development

### Requirements

- Python 3.11+
- PDM for dependency management
- Docker for containerization

### Local Development

```bash
# Install dependencies
pdm install

# Run service locally
pdm run dev

# Run tests
pdm run test

# Lint and format
pdm run lint
pdm run format
```

### Docker

```bash
# Build image
docker build -t huleedu/batch-conductor-service .

# Run container
docker run -p 4002:4002 huleedu/batch-conductor-service
```

## Configuration

Environment variables (prefix: `BCS_`):

- `BCS_HTTP_HOST`: Server host (default: 0.0.0.0)
- `BCS_HTTP_PORT`: Server port (default: 4002)
- `BCS_LOG_LEVEL`: Logging level (default: INFO)
- `BCS_ESSAY_LIFECYCLE_SERVICE_URL`: ELS base URL
- `BCS_HTTP_TIMEOUT`: HTTP client timeout (default: 30s)

## Pipeline Rules

Current dependency rules:

- `ai_feedback` → requires `spellcheck`
- `cj_assessment` → requires `spellcheck`
- `spellcheck` → no dependencies

## Service Integration

**Consumed by**: Batch Orchestrator Service (BOS)  
**Depends on**: Essay Lifecycle Service (ELS)

## Monitoring

- Health checks via `/healthz`
- Prometheus metrics via `/metrics`
- Structured logging with correlation IDs

---

**Status**: Phase 1 - Architectural Foundation Complete  
**Next Phase**: Phase 2 - Core Implementation
