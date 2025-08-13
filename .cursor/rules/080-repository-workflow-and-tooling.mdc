---
description: Read before any interaction with pyproject.toml or  git commands
globs: 
alwaysApply: false
---
# 080: Repository Workflow and Tooling

## 1. PDM Monorepo Management

### 1.1. PDM as Sole Dependency Manager
- PDM **MUST** be used for all dependency management
- Use `pdm add`, `pdm update`, `pdm remove` to maintain `pdm.lock`

### 1.2. PDM Scripts
- Standard tasks **MUST** be defined as PDM scripts in `pyproject.toml`
- **MUST** use `pdm run <script_name>` for execution

## 2. Version Control (Git)

### 2.1. Branching Strategy
- Follow standard branching strategy (Gitflow or Trunk-Based Development)
- Create feature branches for new work

### 2.2. Commit Messages
- Write clear, concise commit messages (Conventional Commits recommended)

### 2.3. Code Reviews
- All code changes **MUST** go through code review process

## 3. CI/CD

### 3.1. CI Pipeline
- **SHOULD** automatically run PDM scripts for linting, formatting, type checking, testing
- Successful CI run **REQUIRED** before merging

### 3.2. CD Pipeline
- Services **SHOULD** be deployed automatically upon merge to main branch

## 4. Local Development Environment

### 4.1. PDM Environment
- Work within PDM-managed virtual environment (`pdm shell` or `pdm run`)

## 5. Monorepo Structure

### 5.1. `common/` Directory
- For shared, service-agnostic code (Pydantic models, exceptions, utilities)
- Service-specific logic **MUST NOT** reside in `common/`

### 5.2. Service Directories
- Each service resides in own directory under `services/`
- Contains service-specific code, tests, configuration

## 6. Docker Development Workflow

### 6.1. Development vs Production Builds
- **Development**: Use `Dockerfile.dev` with volume mounts for hot-reload
- **Production**: Use standard `Dockerfile` for optimized deployment images
- **NEVER** use `--no-cache` for development - use optimized layer caching instead

### 6.2. Development Workflow Commands
```bash
# Start development environment with hot-reload
./scripts/dev-workflow.sh dev <service_name>

# Build development version of specific service
./scripts/dev-workflow.sh build dev <service_name>

# Incremental build using cache optimization
./scripts/dev-workflow.sh incremental

# Check what services need rebuilding
./scripts/dev-workflow.sh check
```

### 6.3. Docker Compose Development
```bash
# Use development compose overlay for hot-reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Start specific services in development mode
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up <service_name>
```

### 6.4. Performance Guidelines
- **Incremental builds**: 4-6 seconds (using cache)
- **Clean builds**: 5-7 minutes (without cache)
- **Hot-reload**: Instant code changes via volume mounts
- **Layer caching**: 99%+ cache hit rate for dependencies

### 6.5. Build Optimization Rules
- Dependencies installed before code copying for better caching
- Multi-stage builds: `base` → `development` → `production`
- Dynamic lockfile generation for development flexibility
- Separate volume mounts for shared libraries and service code
