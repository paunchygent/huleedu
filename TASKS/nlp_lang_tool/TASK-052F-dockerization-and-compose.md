# TASK-052F — Dockerization & Compose ✅ PART 1 COMPLETED

## Objective

Create production and development containers for Language Tool Service with Java 17 + Python 3.11.

## Required Files (Pattern Validated)

### 1. pyproject.toml
- No version pinning (except dev tools like `ruff>=0.11.11`)
- Scripts: `start = "hypercorn app:app --config python:hypercorn_config"`
- Resolution overrides for local libs: `file:///app/libs/...`

### 2. hypercorn_config.py
- Service configuration (not main.py)
- Port from env: `LANGUAGE_TOOL_SERVICE_PORT`
- Standard workers, graceful timeout settings

### 3. Dockerfile (Multi-stage)
- Builder stage: Install build deps, PDM, download LanguageTool JAR
- Runtime stage: Java 17 JRE, Python 3.11, non-root user
- Copy from builder, use PDM with `--frozen-lockfile`

### 4. Dockerfile.dev
- Single stage for development
- Java 17 + build tools
- Volume mounts for hot-reload
- PDM install with `--dev`

### 5. docker-compose.yml entries
- Both `language_tool_service` and `language_tool_service_dev`
- Port 8085, health checks, env vars
- Network: huleedu_network

## Validation

```bash
# Build and test locally
pdm lock
docker build -t language-tool-service .
docker run -p 8085:8085 language-tool-service

# Health check
curl http://localhost:8085/health
curl http://localhost:8085/metrics
```

## Pattern Sources

- Reference: services/nlp_service/Dockerfile (multi-stage)
- Reference: services/file_service/pyproject.toml (no pinning)
- Reference: services/file_service/hypercorn_config.py

## Completion Status

✅ **Part 1 Completed** (All containerization files created and pattern-compliant):
- Created `pyproject.toml` with correct PDM structure (fixed: moved build-system to end, removed unused sections)
- Created `hypercorn_config.py` for service startup
- Created multi-stage `Dockerfile` with Java 17 + Python 3.11 (fixed: appuser, QUART_APP/ENV, EXPOSE pattern)
- Created `Dockerfile.dev` for development with hot-reload (fixed: appuser, QUART_APP/ENV)
- Added service entry to `docker-compose.services.yml`
- Added development entry to `docker-compose.dev.yml`
- Added language_tool_service to root `pyproject.toml` (mypy, pytest, pdm dependencies)

**Part 2 Remaining**: Testing Docker build and compose integration