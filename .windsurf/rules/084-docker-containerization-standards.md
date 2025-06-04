---
description: 
globs: 
alwaysApply: false
---

---
description: 
globs: 
alwaysApply: false
---
# 084: Docker Containerization Standards

## 1. Critical Import Requirements

### 1.1. Import Context Compatibility
- **MUST** use absolute imports for intra-service modules
- **FORBIDDEN**: Relative imports (`from .api`, `from .config`) in containerized services
- **Reason**: Docker containers run services as scripts, breaking relative import resolution

### 1.2. Import Pattern Standards
```python
# ✅ CORRECT - Works in both development and containers
from api.health_routes import health_bp
from config import settings
from protocols import ServiceProtocol

# ❌ FORBIDDEN - Fails in Docker containers
from .api.health_routes import health_bp
from .config import settings
from .protocols import ServiceProtocol
```

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
- **MUST** verify import resolution in Docker builds
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

### 6.2. Import Issue Prevention
- **Pre-container testing**: Verify imports work with `python -c "from api import health_routes"`
- **Build validation**: No import errors in container logs
- **Runtime verification**: All endpoints accessible

## 7. Troubleshooting Guide

### 7.1. Common Import Errors
```python
# Error: "attempted relative import with no known parent package"
# Fix: Change from .module to module

# Error: "No module named 'api'"
# Fix: Verify WORKDIR in Dockerfile is correct service directory
```

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
**Critical**: Import context consistency is essential for microservice containerization success.