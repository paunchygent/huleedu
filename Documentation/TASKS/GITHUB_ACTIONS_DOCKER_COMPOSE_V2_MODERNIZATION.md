# GitHub Actions Docker Compose v2 Modernization Plan

## Overview

This document outlines Phase 2 modernization of the GitHub Actions workflow to use modern Docker Compose v2 syntax (`docker compose`) instead of the deprecated Docker Compose v1 (`docker-compose`).

**Status**: Planning Phase  
**Prerequisites**: Phase 1 (docker-compose v1 compatibility fix) must be completed and validated  
**Target**: Modernize to Docker Compose v2 for cleaner, maintainable CI/CD

## Current State Analysis

### Docker Compose v1 Usage in Workflow

Based on analysis of `.github/workflows/walking-skeleton-smoke-test.yml`:

1. **Setup Step** (Line 20-21):

   ```yaml
   - name: Set up Docker Compose
     uses: docker/setup-compose-action@v1
   ```

2. **Direct Commands** (8 instances):
   - Line 26: `docker-compose up -d`
   - Line 148: `docker-compose ps`
   - Line 151: `docker-compose logs --tail=50 content_service`
   - Line 154: `docker-compose logs --tail=50 batch_orchestrator_service`
   - Line 157: `docker-compose logs --tail=50 essay_lifecycle_api`
   - Line 160: `docker-compose logs --tail=50 file_service`
   - Line 163: `docker-compose logs --tail=30 kafka`
   - Line 188: `docker-compose down --volumes --remove-orphans`

3. **Third-Party Action** (Line 29):

   ```yaml
   - name: Wait for Services to be Healthy
     uses: jaracogmbh/docker-compose-health-check-action@v1.0.0
   ```

## Modernization Strategy

### Phase 2.1: Command Syntax Migration

Replace all `docker-compose` commands with `docker compose` equivalents:

| Current Command | Modern Equivalent |
|----------------|------------------|
| `docker-compose up -d` | `docker compose up -d` |
| `docker-compose ps` | `docker compose ps` |
| `docker-compose logs --tail=50 service` | `docker compose logs --tail=50 service` |
| `docker-compose down --volumes --remove-orphans` | `docker compose down --volumes --remove-orphans` |

### Phase 2.2: Remove Docker Compose v1 Setup

**Remove these lines:**

```yaml
- name: Set up Docker Compose
  uses: docker/setup-compose-action@v1
```

**Rationale**: Ubuntu latest runners include Docker Compose v2 by default since 2023.

### Phase 2.3: Replace Third-Party Health Check Action

**Current Implementation:**

```yaml
- name: Wait for Services to be Healthy
  uses: jaracogmbh/docker-compose-health-check-action@v1.0.0
  with:
    max-retries: 30
    retry-interval: 10
    compose-file: "docker-compose.yml"
    skip-exited: "true"
    skip-no-healthcheck: "false"
```

**Modern Replacement:**

```yaml
- name: Wait for Services to be Healthy
  run: |
    echo "Waiting for services to be healthy..."
    max_retries=30
    retry_interval=10
    
    for ((i=1; i<=max_retries; i++)); do
      echo "Health check attempt $i/$max_retries"
      
      # Get service health status
      unhealthy_services=$(docker compose ps --format json | jq -r 'select(.Health != null and .Health != "healthy") | .Name' 2>/dev/null || true)
      
      if [ -z "$unhealthy_services" ]; then
        echo "✅ All services are healthy"
        break
      else
        echo "⏳ Unhealthy services: $unhealthy_services"
        if [ $i -eq $max_retries ]; then
          echo "❌ Services failed to become healthy after $max_retries attempts"
          docker compose ps
          exit 1
        fi
        sleep $retry_interval
      fi
    done
```

## Implementation Plan

### Step 1: Environment Validation

Verify Docker Compose v2 availability in GitHub Actions Ubuntu runners:

```yaml
- name: Verify Docker Compose v2
  run: |
    docker compose version
    docker compose --help | head -5
```

### Step 2: Incremental Migration

Apply changes in this order to minimize risk:

1. **Remove setup-compose-action step**
2. **Replace simple commands first** (`up`, `down`, `ps`)
3. **Replace logging commands** (multiple instances)
4. **Replace health check action** (most complex)
5. **Full workflow validation**

### Step 3: Testing Strategy

#### Pre-Migration Testing

- Ensure current workflow passes with Phase 1 fix
- Document expected behavior and outputs
- Capture baseline metrics (startup time, etc.)

#### Post-Migration Testing  

- Verify identical service startup behavior
- Validate health checking logic equivalency
- Confirm log output format compatibility
- Test failure scenarios (unhealthy services)

### Step 4: Rollback Strategy

If issues occur during migration:

1. **Immediate Rollback**: Revert to Phase 1 implementation
2. **Partial Rollback**: Keep modern commands but restore third-party health action
3. **Hybrid Approach**: Use `docker compose` commands but keep setup-compose-action

## Detailed Implementation

### Complete Modernized Workflow Steps

```yaml
jobs:
  smoke-test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        
      # REMOVED: Set up Docker Compose step
        
      - name: Start HuleEdu Services
        run: |
          echo "Starting HuleEdu walking skeleton services..."
          docker compose up -d
          echo "Services starting, waiting for health checks..."
        
      - name: Wait for Services to be Healthy
        run: |
          echo "Waiting for services to be healthy..."
          max_retries=30
          retry_interval=10
          
          for ((i=1; i<=max_retries; i++)); do
            echo "Health check attempt $i/$max_retries"
            
            # Check if all services with health checks are healthy
            unhealthy_count=$(docker compose ps --format json | jq -r 'select(.Health != null and .Health != "healthy") | .Name' 2>/dev/null | wc -l)
            
            if [ "$unhealthy_count" -eq 0 ]; then
              echo "✅ All services are healthy"
              docker compose ps
              break
            else
              echo "⏳ Waiting for $unhealthy_count services to become healthy..."
              if [ $i -eq $max_retries ]; then
                echo "❌ Services failed to become healthy after $max_retries attempts"
                echo "Service status:"
                docker compose ps
                exit 1
              fi
              sleep $retry_interval
            fi
          done
```

### Modified Display Service Logs Section

```yaml
- name: Display Service Logs on Failure
  if: failure()
  run: |
    echo "=== Service Logs for Debugging ==="
    echo "--- Docker Compose Services Status ---"
    docker compose ps
    
    echo "--- Content Service Logs ---"
    docker compose logs --tail=50 content_service
    
    echo "--- Batch Orchestrator Service Logs ---"
    docker compose logs --tail=50 batch_orchestrator_service
    
    echo "--- Essay Lifecycle Service Logs ---"
    docker compose logs --tail=50 essay_lifecycle_api
    
    echo "--- File Service Logs ---"
    docker compose logs --tail=50 file_service
    
    echo "--- Kafka Logs ---"
    docker compose logs --tail=30 kafka
```

### Modified Cleanup Section

```yaml
- name: Cleanup
  if: always()
  run: |
    echo "Cleaning up Docker resources..."
    docker compose down --volumes --remove-orphans
    docker system prune -f 
```

## Benefits of Modernization

### Performance Improvements

- **Faster startup**: No need to install docker-compose v1
- **Reduced dependencies**: Native Docker Compose v2 support
- **Smaller workflow**: Fewer steps and external actions

### Maintainability

- **Modern syntax**: Following Docker's official recommendations
- **Native tooling**: Using built-in GitHub Actions capabilities
- **Reduced external dependencies**: Fewer third-party actions to maintain

### Future-Proofing

- **Long-term support**: Docker Compose v2 is actively maintained
- **Security**: Reduced attack surface with fewer external dependencies
- **Compatibility**: Aligned with Docker's strategic direction

## Risk Assessment

### Low Risk

- Command syntax changes (direct mapping)
- Removal of setup step (v2 included by default)

### Medium Risk  

- Health check logic replacement
- JSON parsing dependencies (jq availability)

### Mitigation Strategies

- Incremental implementation
- Comprehensive testing
- Rollback procedures
- Baseline documentation

## Success Criteria

1. **Functional Equivalency**: All services start and health checks pass
2. **Performance**: No significant increase in workflow execution time
3. **Reliability**: No increase in flaky test failures
4. **Maintainability**: Cleaner, more readable workflow
5. **Documentation**: Updated workflow reflects modern practices

## Implementation Timeline

- **Week 1**: Environment validation and simple command replacement
- **Week 2**: Health check action replacement and testing
- **Week 3**: Full integration testing and refinement
- **Week 4**: Documentation updates and team training

## Conclusion

Phase 2 modernization will bring the GitHub Actions workflow in line with Docker's current best practices while maintaining full functional compatibility. The migration strategy prioritizes safety through incremental changes and comprehensive testing.
