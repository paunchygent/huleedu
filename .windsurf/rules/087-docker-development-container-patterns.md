---
description: Docker development container patterns and optimization standards
globs: 
alwaysApply: false
---
# 087: Docker Development Container Patterns

## 1. Purpose
Docker containerization patterns for HuleEdu microservices development, focusing on layer caching optimization, PDM integration, and hot-reload capability.

Model service: `@identity_service/`

**Related Rules**:
- [040-service-implementation-guidelines.mdc](mdc:040-service-implementation-guidelines.mdc) - Core service patterns  
- [084-docker-containerization-standards.mdc](mdc:084-docker-containerization-standards.mdc) - General Docker standards

## 2. Multi-Stage Build Structure

### 2.1. Required Stages
```dockerfile
# Development-optimized Dockerfile with improved layer caching
FROM python:3.11-slim AS base
# Base stage: environment variables and system dependencies

FROM base AS development
# Development stage: volume mounts for hot-reload

FROM base AS production  
# Production stage: optimized for deployment
```

### 2.2. Base Stage Pattern
```dockerfile
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false \
    ENV_TYPE=docker \
    PYTHONPATH=/app

# Service-specific environment variables
ENV QUART_APP=app:app \
    QUART_ENV=production \
    SERVICE_LOG_LEVEL=INFO \
    SERVICE_HTTP_PORT=7005 \
    SERVICE_PROMETHEUS_PORT=9097 \
    SERVICE_HOST=0.0.0.0

# Install system dependencies (rarely change - good cache layer)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install PDM (rarely changes - good cache layer)
RUN pip install --no-cache-dir pdm

WORKDIR /app
```

## 3. Dependency Installation Optimization

### 3.1. Layer Caching Strategy
```dockerfile
# Copy only dependency files first (better caching)
COPY libs/common_core/pyproject.toml /app/libs/common_core/pyproject.toml
COPY libs/huleedu_service_libs/pyproject.toml /app/libs/huleedu_service_libs/pyproject.toml
COPY services/SERVICE_NAME/pyproject.toml /app/services/SERVICE_NAME/pyproject.toml

# Generate lockfile if it doesn't exist
WORKDIR /app/services/SERVICE_NAME
RUN pdm lock --lockfile pdm.lock.docker || echo "Lock generation failed, will install without lock"

# Copy shared library source (changes less frequently than service code)
COPY libs/common_core/src/ /app/libs/common_core/src/
COPY libs/huleedu_service_libs/src/ /app/libs/huleedu_service_libs/src/

# Install dependencies (caches well if pyproject.toml doesn't change)
RUN if [ -f "pdm.lock.docker" ]; then \
        pdm install --prod --lockfile pdm.lock.docker; \
    else \
        pdm install --prod; \
    fi
```

### 3.2. PDM Integration Patterns
- **Lock Generation**: Create Docker-specific lockfile to avoid conflicts
- **Production Install**: Use `--prod` flag to skip dev dependencies
- **Fallback Handling**: Install normally if lock generation fails
- **Shared Libraries**: Install as local packages via pyproject.toml dependencies

## 4. Development Stage Patterns

### 4.1. Development Stage Structure
```dockerfile
FROM base AS development

# Create user first
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Copy service code (this layer changes most frequently)
COPY services/SERVICE_NAME/ /app/services/SERVICE_NAME/

# Set permissions
RUN chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/SERVICE_NAME

# Expose the ports the app runs on
EXPOSE ${SERVICE_HTTP_PORT} ${SERVICE_PROMETHEUS_PORT}

# Use pdm run for development
CMD ["pdm", "run", "start"]
```

### 4.2. Volume Mount Strategy
```yaml
# docker-compose.override.yml - For development
volumes:
  - ./services/SERVICE_NAME:/app/services/SERVICE_NAME:ro
  - ./libs:/app/libs:ro
  # Mount source directories for hot-reload capability
```

## 5. Production Stage Patterns

### 5.1. Production Optimization
```dockerfile
FROM base AS production

# Copy service code for production build
COPY services/SERVICE_NAME/ /app/services/SERVICE_NAME/

# Create user and set permissions in single layer
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/SERVICE_NAME

# Expose the ports the app runs on
EXPOSE ${SERVICE_HTTP_PORT} ${SERVICE_PROMETHEUS_PORT}

CMD ["pdm", "run", "start"]
```

## 6. Environment Variable Standards

### 6.1. Required Environment Variables
```dockerfile
# Core Python configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDM_USE_VENV=false \
    ENV_TYPE=docker \
    PYTHONPATH=/app

# Service-specific configuration (customize per service)
ENV SERVICE_LOG_LEVEL=INFO \
    SERVICE_HTTP_PORT=7005 \
    SERVICE_PROMETHEUS_PORT=9097 \
    SERVICE_HOST=0.0.0.0
```

### 6.2. Framework-Specific Variables
```dockerfile
# Quart services
ENV QUART_APP=app:app \
    QUART_ENV=production

# FastAPI services  
ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=${SERVICE_HTTP_PORT}
```

## 7. Security Patterns

### 7.1. Non-Root User Pattern
```dockerfile
# MUST create and use non-root user
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Set ownership before switching users
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser
```

### 7.2. Minimal System Dependencies
```dockerfile
# Install only required system packages
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
```

## 8. Port Management

### 8.1. Port Assignment Strategy
- **HTTP Port**: Service-specific (7001-7020 range)
- **Prometheus Port**: HTTP port + 2092 (e.g., 7005 → 9097)
- **Database Port**: Service-specific (5441-5460 range)

### 8.2. Port Exposure Pattern
```dockerfile
# Use environment variables for flexible port configuration
EXPOSE ${SERVICE_HTTP_PORT} ${SERVICE_PROMETHEUS_PORT}
```

## 9. Build Optimization Checklist

### 9.1. Layer Caching Optimization
- [ ] System dependencies installed before application code
- [ ] PDM installed in separate layer  
- [ ] Dependency files copied before source code
- [ ] Shared libraries copied before service-specific code
- [ ] Service code copied last (changes most frequently)

### 9.2. Development Features
- [ ] Development stage for hot-reload capability
- [ ] Volume mount points for source directories
- [ ] Non-root user for security
- [ ] Proper environment variable configuration

### 9.3. Production Readiness
- [ ] Production stage optimized for deployment
- [ ] Minimal attack surface (no dev dependencies)
- [ ] Proper user permissions and security
- [ ] Environment-specific configuration

## 10. Common Docker Patterns

### 10.1. Health Check Integration
```dockerfile
# Optional: Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${SERVICE_HTTP_PORT}/health || exit 1
```

### 10.2. Signal Handling
```dockerfile
# Use pdm run which properly handles signals
CMD ["pdm", "run", "start"]

# Ensure your start script in pyproject.toml handles SIGTERM
# [tool.pdm.scripts]
# start = "python -m quart --app app:app run --host 0.0.0.0 --port ${SERVICE_HTTP_PORT}"
```

## 11. Development Workflow Integration

### 11.1. Docker Compose Integration
```yaml
# docker-compose.yml
services:
  service_name:
    build:
      context: .
      dockerfile: services/SERVICE_NAME/Dockerfile.dev
      target: development
    environment:
      - SERVICE_HTTP_PORT=7005
      - SERVICE_PROMETHEUS_PORT=9097
    ports:
      - "7005:7005"
      - "9097:9097"
```

### 11.2. Build Commands
```bash
# Development build with cache
docker build --target development -t SERVICE_NAME:dev .

# Production build
docker build --target production -t SERVICE_NAME:latest .

# Clean build (no cache)
docker build --no-cache --target development -t SERVICE_NAME:dev .
```
