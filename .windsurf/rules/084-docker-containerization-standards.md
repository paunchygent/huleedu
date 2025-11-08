---
description: rules for correct docker containerization patterns
globs: 
alwaysApply: false
---
# 084: Docker Containerization Standards

## 1. Docker Environment Requirements

### 1.1. Python Path Configuration
- **MUST** ensure `PYTHONPATH=/app` in service Dockerfiles for module resolution
- **Critical**: Missing PYTHONPATH causes import failures, not import pattern issues
- **Runtime Import Flexibility**: Services with proper PYTHONPATH can use mixed import patterns

### 1.2. Import Pattern Requirements by Context
**Runtime Services (Docker)**: Can use mixed import patterns when properly configured
- Relative imports work within service context due to `PYTHONPATH=/app`
- Service configuration issues are primary concern, not import patterns

**Test Environment (pytest)**: Requires absolute imports for disambiguation
- Tests run from repository root, cannot distinguish identically-named files across services
- Any file in test import chain needs absolute paths: `from services.{service_name}.{module} import`
- Includes: test files, implementation files imported by tests, transitively imported dependencies

### 1.3. Service Configuration Priority
**Before investigating import patterns, verify**:
- Dockerfile has correct `PYTHONPATH=/app` environment variable
- Health check ports match actual service configuration
- Environment variables align with service `env_prefix` patterns
- DI container usage vs manual instantiation
- Framework configuration methods (e.g., Hypercorn config loading)

## 2. Dockerfile Requirements

### 2.1. Shared Dependency Image
- The repo root owns `Dockerfile.deps`. It copies `pyproject.toml`, `pdm.lock`, and every shared library (`libs/common_core`, `libs/huleedu_service_libs`, `libs/huleedu_nlp_shared`) plus service `pyproject.toml` metadata, then runs `pdm install --dev --frozen-lockfile` from `/app` and owns the tree as `appuser`.
- `scripts/compute_deps_hash.py` hashes `pyproject.toml`, `pdm.lock`, `Dockerfile.deps`, and shared lib sources. `scripts/dev.sh` uses this hash to tag the deps image (`huledu-deps:<hash>`) and rebuilds it exactly once per dependency change or whenever `pdm run dev-build-clean …` is invoked.

### 2.2. Service Dockerfiles
- Generated via `scripts/update_service_dockerfiles.py`. Each Dockerfile **MUST**:
  - Declare `ARG DEPS_IMAGE=huledu-deps:dev` and `FROM ${DEPS_IMAGE}`.
  - Set the standard env block (`PYTHONUNBUFFERED`, `PYTHONDONTWRITEBYTECODE`, `PDM_USE_VENV=false`, `PYTHONPATH=/app`, etc.).
  - Copy service code with `COPY --chown=appuser:appuser services/<service>/ /app/services/<service>/`.
  - Only add service-specific OS packages or data directories (e.g., LanguageTool JRE, content store folder). **FORBIDDEN**: running `pdm install` or recreating `appuser` per service.
  - Drop legacy `__pypackages__` mounts—dependencies live exclusively in the deps image.
  - `USER appuser` and set `WORKDIR /app` before the final `CMD` (which still uses `pdm run -p /app …`).

### 2.3. Dual-Mode Services (HTTP + Worker)
Services with both HTTP API and Kafka worker components **MUST** expose both entry points (e.g., `python services/.../app.py` vs `python services/.../worker_main.py`). All container commands run through `pdm run -p /app …` to ensure the shared deps environment is active.

## 3. Environment Configuration

### 3.1. Port Configuration Standards
- **HTTP Port**: Service internal port via environment variable
- **Container Mapping**: External port mapped in docker-compose.yml
- **Prefix Consistency**: Environment variable prefix MUST match config.py `env_prefix`

### 3.2. Required Environment Variables
```yaml
environment:
  - ENV_TYPE=docker
  - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
  - {SERVICE_PREFIX}_HTTP_PORT={internal_port}
  - LOG_LEVEL=INFO
```

## 4. Development vs Container Consistency

### 4.1. Module Loading Context
- **Development**: `pdm run` executes as package context
- **Container**: `python app.py` executes as script context
- **Requirement**: Code MUST work in both contexts

### 4.2. Testing Requirements
- **MUST** test services in both development and container environments
- **MUST** verify service configuration in Docker builds (DI, health checks, environment variables)
- **Blueprint patterns MUST preserve functionality across contexts**

## 5. Container Build Standards

### 5.1. Build Commands
```bash
# Normal rebuild (uses cached deps image)
pdm run dev-build <service_a> <service_b>

# Force deps image + services to rebuild
pdm run dev-build-clean <service_a> <service_b>

# Start containers using previously built images
pdm run dev-start

# Start without rebuilding (images must already exist)
pdm run dev-start-nobuild
```
`dev-build` and `dev-build-clean` automatically compute the dependency hash, rebuild Dockerfile.deps when needed, and pass the resulting `DEPS_IMAGE_TAG` to `docker compose build` for the requested services.

### 5.2. Dependency Order
**MUST respect startup dependencies:**
1. Infrastructure: `zookeeper`, `kafka`
2. Topic Setup: `kafka_topic_setup`
3. Core Services: `content_service`
4. Dependent Services: All others

## 6. Validation Requirements

### 6.1. Container Health Verification
```bash
# Health endpoint validation
curl -f http://localhost:{port}/healthz

# Metrics endpoint validation  
curl -f http://localhost:{port}/metrics

# Container status check
docker compose ps
```

### 6.2. Service Configuration Validation
- **Service setup testing**: Verify DI container usage, not manual instantiation
- **Configuration validation**: Test framework configuration methods work correctly
- **Runtime verification**: All health endpoints accessible with correct ports

## 7. Troubleshooting Guide

### 7.1. Configuration Issues (Check First)
**Service configuration problems often manifest as "import errors"**:

```bash
# Check PYTHONPATH in container
docker exec <container> env | grep PYTHONPATH

# Verify health check ports match service ports
curl -f http://localhost:<external_port>/healthz

# Check DI container resolution
# Add debug output to verify dependencies resolve correctly

# Test import patterns in runtime context
docker exec <container> python -c "from protocols import SomeProtocol; print('Import OK')"
```

**Import vs Configuration Debugging Priority**:
1. **First**: Verify service configuration (PYTHONPATH, DI, ports, environment variables)
2. **Second**: Check import patterns if configuration is correct
3. **Test failures**: Use absolute imports in test chain files for disambiguation

### 7.2. Container Debug Commands
```bash
# View service logs
docker compose logs {service_name} --tail=20

# Execute inside container
docker compose exec {service_name} /bin/bash

# Rebuild specific service
docker compose build {service_name} --no-cache
```

---
**Critical**: Service configuration validation is essential for microservice containerization success. See [044-service-debugging-and-troubleshooting.md](mdc:044-service-debugging-and-troubleshooting.md) for debugging priority guidelines.
