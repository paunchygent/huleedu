# Docker Compose Modernization Glossary

## Overview

Complete mapping of all deprecated Docker Compose v1 (`docker-compose`) syntax to modern Docker Compose v2 (`docker compose`) equivalents found across the HuleEdu codebase.

**Status**: MODERNIZATION REQUIRED  
**Scope**: Repository-wide transformation  
**Current State**: Mixed (some files already modernized, others still using deprecated syntax)

## Current State Analysis

### Already Modernized Files ✅
- `pyproject.toml` - PDM scripts already use modern syntax
- Documentation/TASKS/GITHUB_ACTIONS_DOCKER_COMPOSE_V2_MODERNIZATION.md - Contains modern examples

### Files Requiring Modernization ❌

## Command Syntax Transformation Table

| Deprecated v1 Syntax | Modern v2 Syntax | Usage Count | Impact |
|----------------------|------------------|-------------|---------|
| `docker-compose up -d` | `docker compose up -d` | 8+ | High |
| `docker-compose down` | `docker compose down` | 6+ | High |
| `docker-compose ps` | `docker compose ps` | 4+ | Medium |
| `docker-compose logs` | `docker compose logs` | 10+ | High |
| `docker-compose config` | `docker compose config` | 3+ | Medium |
| `docker-compose build` | `docker compose build` | 3+ | Medium |
| `docker-compose exec` | `docker compose exec` | 4+ | Medium |
| `docker-compose restart` | `docker compose restart` | 2+ | Low |

## File-by-File Modernization Map

### 1. GitHub Actions Workflow
**File**: `.github/workflows/walking-skeleton-smoke-test.yml`
```yaml
# DEPRECATED ❌
- name: Set up Docker Compose
  uses: docker/setup-compose-action@v1

docker-compose up -d
docker-compose ps
docker-compose logs --tail=50 content_service
docker-compose logs --tail=50 batch_orchestrator_service
docker-compose logs --tail=50 essay_lifecycle_api
docker-compose logs --tail=50 file_service
docker-compose logs --tail=30 kafka
docker-compose down --volumes --remove-orphans

# MODERN ✅
# Remove setup step (built-in in Ubuntu runners)
docker compose up -d
docker compose ps
docker compose logs --tail=50 content_service
docker compose logs --tail=50 batch_orchestrator_service
docker compose logs --tail=50 essay_lifecycle_api
docker compose logs --tail=50 file_service
docker compose logs --tail=30 kafka
docker compose down --volumes --remove-orphans
```

### 2. Validation Scripts
**File**: `scripts/validate_batch_coordination.sh`
```bash
# DEPRECATED ❌
if ! command -v docker-compose &> /dev/null; then
    error "docker-compose is required but not installed"
fi

DOCKER_COMPOSE_FILE="docker-compose.yml"
if docker-compose config > /dev/null 2>&1; then
    success "Docker Compose configuration is valid"
else
    error "Docker Compose configuration has errors"
    docker-compose config
fi

docker-compose up -d
docker-compose logs essay_lifecycle_worker | tail -20
docker-compose logs batch_orchestrator_service | tail -20
docker-compose logs essay_lifecycle_worker | grep -i "batch.*$BATCH_ID"
docker-compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
docker-compose down

# MODERN ✅
if ! command -v docker &> /dev/null; then
    error "docker is required but not installed"
fi

DOCKER_COMPOSE_FILE="docker-compose.yml"
if docker compose config > /dev/null 2>&1; then
    success "Docker Compose configuration is valid"
else
    error "Docker Compose configuration has errors"
    docker compose config
fi

docker compose up -d
docker compose logs essay_lifecycle_worker --tail=20
docker compose logs batch_orchestrator_service --tail=20
docker compose logs essay_lifecycle_worker | grep -i "batch.*$BATCH_ID"
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
docker compose down
```

### 3. Test Scripts
**File**: `scripts/tests/quick_validation_test.sh`
```bash
# DEPRECATED ❌
log "Testing Docker Compose configuration..."
if docker-compose config > /dev/null 2>&1; then
    success "Docker Compose configuration is valid"
else
    error "Docker Compose configuration has errors"
fi

if docker-compose build > /dev/null 2>&1; then
    success "Service build successful"
else
    error "Service build failed - check docker-compose logs"
fi

docker-compose up -d > /dev/null 2>&1
echo "   2. Check logs: docker-compose logs <service-name>"
log "To stop: docker-compose down"

# MODERN ✅
log "Testing Docker Compose configuration..."
if docker compose config > /dev/null 2>&1; then
    success "Docker Compose configuration is valid"
else
    error "Docker Compose configuration has errors"
fi

if docker compose build > /dev/null 2>&1; then
    success "Service build successful"
else
    error "Service build failed - check docker compose logs"
fi

docker compose up -d > /dev/null 2>&1
echo "   2. Check logs: docker compose logs <service-name>"
log "To stop: docker compose down"
```

**File**: `scripts/tests/test_kafka_infrastructure.sh`
```bash
# DEPRECATED ❌
log_info "Ensure Docker Compose services are running: docker-compose up -d"

# MODERN ✅
log_info "Ensure Docker Compose services are running: docker compose up -d"
```

### 4. Python Test Fixtures
**File**: `tests/fixtures/docker_services.py`
```python
# DEPRECATED ❌
def __init__(self, compose_file: str = "docker-compose.yml"):
    self.compose_file = compose_file

def start_services(self):
    cmd = ["docker-compose", "-f", self.compose_file, "up", "-d"]
    
def stop_services(self):
    cmd = ["docker-compose", "-f", self.compose_file, "down"]

# MODERN ✅
def __init__(self, compose_file: str = "docker-compose.yml"):
    self.compose_file = compose_file

def start_services(self):
    cmd = ["docker", "compose", "-f", self.compose_file, "up", "-d"]
    
def stop_services(self):
    cmd = ["docker", "compose", "-f", self.compose_file, "down"]
```

### 5. Documentation Updates
**Files**: Multiple documentation files
```markdown
# DEPRECATED ❌
docker-compose up -d
docker-compose ps
docker-compose logs <service-name>
docker-compose exec service_name python -c "..."
docker-compose down
docker-compose down -v

# MODERN ✅
docker compose up -d
docker compose ps
docker compose logs <service-name>
docker compose exec service_name python -c "..."
docker compose down
docker compose down -v
```

## Third-Party Action Replacements

### GitHub Actions Health Check
```yaml
# DEPRECATED ❌
- name: Wait for Services to be Healthy
  uses: jaracogmbh/docker-compose-health-check-action@v1.0.0
  with:
    max-retries: 30
    retry-interval: 10
    compose-file: "docker-compose.yml"
    skip-exited: "true"
    skip-no-healthcheck: "false"

# MODERN ✅
- name: Wait for Services to be Healthy
  run: |
    echo "Waiting for services to be healthy..."
    max_retries=30
    retry_interval=10
    
    for ((i=1; i<=max_retries; i++)); do
      echo "Health check attempt $i/$max_retries"
      
      unhealthy_count=$(docker compose ps --format json | jq -r 'select(.Health != null and .Health != "healthy") | .Name' 2>/dev/null | wc -l)
      
      if [ "$unhealthy_count" -eq 0 ]; then
        echo "✅ All services are healthy"
        docker compose ps
        break
      else
        echo "⏳ Waiting for $unhealthy_count services to become healthy..."
        if [ $i -eq $max_retries ]; then
          echo "❌ Services failed to become healthy after $max_retries attempts"
          docker compose ps
          exit 1
        fi
        sleep $retry_interval
      fi
    done
```

## Command Availability Checks

### Dependency Validation
```bash
# DEPRECATED ❌
if ! command -v docker-compose &> /dev/null; then
    error "docker-compose is required but not installed"
fi

# MODERN ✅
if ! command -v docker &> /dev/null; then
    error "docker is required but not installed"
fi

# Verify compose plugin is available
if ! docker compose version &> /dev/null; then
    error "docker compose plugin is required but not available"
fi
```

## Configuration File References

### File Name Standards
All references to `docker-compose.yml` remain the same - this is still the standard filename for Docker Compose configuration files in v2.

```bash
# UNCHANGED ✅
DOCKER_COMPOSE_FILE="docker-compose.yml"
compose-file: "docker-compose.yml"
compose_file: str = "docker-compose.yml"
```

## Already Modernized Examples

### PDM Scripts (Already Correct ✅)
```toml
# pyproject.toml - Already using modern syntax
docker-build = "docker compose build"
docker-up = "docker compose up -d"
docker-down = "docker compose down"
docker-logs = "docker compose logs -f --tail=100"
docker-restart = {composite = ["docker compose down", "docker compose up -d --build"]}
```

## Implementation Priority

### High Priority (Critical CI/CD)
1. `.github/workflows/walking-skeleton-smoke-test.yml`
2. `scripts/validate_batch_coordination.sh`
3. `tests/fixtures/docker_services.py`

### Medium Priority (Development Tools)
1. `scripts/tests/quick_validation_test.sh`
2. `scripts/tests/test_kafka_infrastructure.sh`
3. Documentation files

### Low Priority (Documentation)
1. README.md references
2. Service-specific documentation
3. Task documentation updates

## Verification Commands

After modernization, verify with:
```bash
# Check Docker Compose v2 availability
docker compose version

# Validate configuration
docker compose config

# Test basic operations
docker compose up -d --dry-run
docker compose ps --format json
```

## Benefits Summary

- **✅ No external dependencies**: Remove setup-compose-action
- **✅ Modern syntax**: Follow Docker's official recommendations  
- **✅ Native support**: Use built-in GitHub Actions capabilities
- **✅ Future-proof**: Aligned with Docker's strategic direction
- **✅ Performance**: Faster startup without v1 installation
- **✅ Security**: Reduced attack surface 