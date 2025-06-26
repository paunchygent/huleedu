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

### 2.1. Service Dockerfile Pattern
**ALL services MUST have Dockerfile following repository pattern:**

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV_TYPE=docker \
    PDM_USE_VENV=false

WORKDIR /app

# Install PDM globally
RUN pip install --no-cache-dir pdm

# Copy shared dependencies first
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/

# Copy service-specific code
COPY services/{service_name}/ /app/services/{service_name}/

# Switch to service directory
WORKDIR /app/services/{service_name}

# Install dependencies
RUN pdm install --prod

# Create non-root user
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Service-specific CMD
CMD ["pdm", "run", "start"]
```

### 2.2. Dual-Mode Services (HTTP + Worker)
Services with both HTTP API and Kafka worker components:
- **MUST** support both modes via different entry points
- **HTTP Mode**: `CMD ["pdm", "run", "start"]` 
- **Worker Mode**: `CMD ["pdm", "run", "start-worker"]`

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
# Clean rebuild (development)
docker compose down --remove-orphans
docker compose build --no-cache
docker compose up -d

# Service-specific rebuild
docker compose build {service_name} --no-cache
docker compose up -d {service_name}
```

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
