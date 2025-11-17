# Docker Build Optimization Guide

## Overview

This guide documents the optimized Docker build scripts added to the HuleEdu platform, incorporating 2025 best practices for BuildKit, parallel builds, and PDM integration.

## Key Optimizations Implemented

### 1. **BuildKit Enablement**
All optimized scripts now use:
- `COMPOSE_DOCKER_CLI_BUILD=1` - Enables Docker Compose BuildKit support
- `DOCKER_BUILDKIT=1` - Ensures BuildKit is used for builds

BuildKit provides:
- Parallel stage execution
- Advanced caching mechanisms
- Better build performance
- Improved layer caching

### 2. **Parallel Build Support**
The `--parallel` flag enables concurrent building of multiple services, utilizing all available CPU cores.

### 3. **PDM Integration with --frozen-lockfile**
All Dockerfiles now use `pdm install --prod --frozen-lockfile` to:
- Skip lockfile generation (avoiding segmentation faults)
- Ensure reproducible builds
- Improve build performance

## Available Optimized Commands

### No-Cache Builds (Your Current Use Case)

```bash
# Build all services fresh with parallel execution
pdm run dev-fresh

# Build single service without cache
pdm run dev-fresh-single file_service

# Build with detailed output for debugging
pdm run dev-fresh-verbose
```

### Performance-Optimized Builds

```bash
# Maximum parallel build (uses cache)
pdm run build-parallel

# Update base images and build in parallel
pdm run build-parallel-pull

# Build specific service with BuildKit optimization
pdm run build-service content_service
```

### Complete Workflows

```bash
# Full rebuild with optimizations
pdm run dev-rebuild

# Complete system reset with optimized rebuild
pdm run docker-reset
```

### Cache Management

```bash
# Clean BuildKit cache (when running out of disk space)
pdm run docker-builder-prune

# Clean all Docker resources
pdm run docker-clean
```

## Performance Comparison

### Before Optimization
```bash
docker compose build --no-cache
```
- Sequential builds
- No BuildKit optimization
- Slower dependency resolution

### After Optimization
```bash
COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker compose build --no-cache --parallel
```
- Parallel service builds
- BuildKit caching and optimization
- Faster builds (typically 40-60% improvement)

## Best Practices for Dockerfile Optimization

### 1. **Layer Ordering**
Place frequently changing content (application code) at the end:
```dockerfile
# Dependencies first (cached)
COPY pyproject.toml pdm.lock ./
RUN pdm install --prod --frozen-lockfile

# Application code last (changes frequently)
COPY . .
```

### 2. **Multi-Stage Builds**
Consider using multi-stage builds for smaller images:
```dockerfile
# Build stage
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml pdm.lock ./
RUN pip install pdm && pdm install --prod --frozen-lockfile

# Runtime stage
FROM python:3.11-slim
COPY --from=builder /app/.venv /app/.venv
COPY . /app
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
```

### 3. **Cache Mounts (Advanced)**
For even better performance, use BuildKit cache mounts:
```dockerfile
# Example with pip cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install pdm

# Example with PDM cache
RUN --mount=type=cache,target=/root/.cache/pdm \
    pdm install --prod --frozen-lockfile
```

## Monitoring Build Performance

To see detailed build timing:
```bash
# Use plain progress for detailed output
pdm run dev-fresh-verbose
```

To check BuildKit status:
```bash
docker buildx ls
```

## Troubleshooting

### If builds are still slow
1. Check available disk space: `docker system df`
2. Clean BuildKit cache: `pdm run docker-builder-prune`
3. Ensure Docker has enough CPU/memory allocated (Docker Desktop settings)

### If parallel builds fail
1. Try building services individually first
2. Check for port conflicts between services
3. Ensure all base images are accessible

### PDM-specific issues
1. Ensure pdm.lock exists in the repository
2. If segmentation faults occur, verify --frozen-lockfile is used
3. Consider using `pdm sync --prod` instead of `pdm install` for guaranteed lock-free operation

## Future Optimizations

### 1. **External Cache Backend**
Consider using registry-based caching for CI/CD:
```bash
docker buildx build --cache-to type=registry,ref=myregistry/myapp:buildcache
```

### 2. **Platform-Specific Builds**
For deployment optimization:
```bash
docker buildx build --platform linux/amd64,linux/arm64
```

### 3. **PDM Sync Migration**
Consider migrating from `pdm install --frozen-lockfile` to `pdm sync --prod` for better guarantees.

## Conclusion

These optimizations should significantly improve your Docker build times, especially for no-cache builds. The combination of BuildKit, parallel execution, and proper PDM integration provides a modern, efficient build pipeline for the HuleEdu platform.
