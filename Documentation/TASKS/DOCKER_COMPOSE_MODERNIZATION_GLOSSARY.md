# Docker Compose Modernization Glossary

## GitHub Actions Workflows

### Commands

```yaml
# DEPRECATED v1
docker-compose up -d
docker-compose down --volumes --remove-orphans  
docker-compose ps
docker-compose logs --tail=50 <service>
```

```yaml
# MODERN v2
docker compose up -d
docker compose down --volumes --remove-orphans
docker compose ps
docker compose logs --tail=50 <service>
```

### Actions

```yaml
# DEPRECATED v1
- name: Set up Docker Compose
  uses: docker/setup-compose-action@v1

- name: Wait for Services to be Healthy  
  uses: jaracogmbh/docker-compose-health-check-action@v1.0.0
```

```yaml
# MODERN v2
# Remove setup step (built-in in Ubuntu runners)

- name: Wait for Services to be Healthy
  run: |
    unhealthy_count=$(docker compose ps --format json | jq -r 'select(.Health != null and .Health != "healthy") | .Name' 2>/dev/null | wc -l)
```

## Health Check Implementation

### Docker Compose Service Health Checks

```yaml
# MISSING (Previous state)
services:
  content_service:
    # ... other config
    # No healthcheck defined
```

```yaml
# MODERN v2 (Added during modernization)
services:
  content_service:
    # ... other config
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/healthz || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 20s
```

### Dockerfile Health Check Prerequisites

```dockerfile
# MISSING (Previous state)
FROM python:3.11-slim
# ... other instructions
RUN pip install --no-cache-dir pdm
```

```dockerfile
# MODERN v2 (Fixed during modernization)
FROM python:3.11-slim
# ... other instructions
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm
```

### Service Dependency Conditions

```yaml
# PREVIOUS (Less reliable)
depends_on:
  content_service:
    condition: service_started
```

```yaml
# MODERN v2 (Health-aware)
depends_on:
  content_service:
    condition: service_healthy
```

## Shell Scripts (.sh files)

### Command Availability Checks

```bash
# DEPRECATED v1
if ! command -v docker-compose &> /dev/null; then
    error "docker-compose is required but not installed"
fi
```

```bash
# MODERN v2
if ! command -v docker &> /dev/null; then
    error "docker is required but not installed"
fi

if ! docker compose version &> /dev/null; then
    error "docker compose plugin is required but not available"
fi
```

### Basic Commands

```bash
# DEPRECATED v1
docker-compose config
docker-compose up -d
docker-compose ps
docker-compose build
docker-compose down
```

```bash
# MODERN v2
docker compose config
docker compose up -d
docker compose ps
docker compose build
docker compose down
```

### Log Commands

```bash
# DEPRECATED v1
docker-compose logs service_name | tail -20
docker-compose logs --tail=50 service_name
```

```bash
# MODERN v2
docker compose logs service_name --tail=20
docker compose logs --tail=50 service_name
```

### Exec Commands

```bash
# DEPRECATED v1
docker-compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
```

```bash
# MODERN v2
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
```

## Python Code (.py files)

### Subprocess Commands

```python
# DEPRECATED v1
cmd = ["docker-compose", "-f", self.compose_file, "up", "-d"]
cmd = ["docker-compose", "-f", self.compose_file, "down"]
```

```python
# MODERN v2
cmd = ["docker", "compose", "-f", self.compose_file, "up", "-d"]
cmd = ["docker", "compose", "-f", self.compose_file, "down"]
```

## Documentation Files (.md files)

### Command Examples

```markdown
# DEPRECATED v1
docker-compose up -d
docker-compose ps
docker-compose logs <service-name>
docker-compose exec service_name python -c "..."
docker-compose down
docker-compose down -v
```

```markdown
# MODERN v2
docker compose up -d
docker compose ps
docker compose logs <service-name>
docker compose exec service_name python -c "..."
docker compose down
docker compose down -v
```

### Instructions

```markdown
# DEPRECATED v1
Ensure Docker Compose services are running: docker-compose up -d
Check logs: docker-compose logs <service-name>
To stop: docker-compose down
```

```markdown
# MODERN v2
Ensure Docker Compose services are running: docker compose up -d
Check logs: docker compose logs <service-name>
To stop: docker compose down
```

## TOML Configuration Files

### PDM Scripts (Already Correct)

```toml
# MODERN v2 (Already using correct syntax)
docker-build = "docker compose build"
docker-up = "docker compose up -d"
docker-down = "docker compose down"
docker-logs = "docker compose logs -f --tail=100"
docker-restart = {composite = ["docker compose down", "docker compose up -d --build"]}
```

## File References (Unchanged)

### Configuration File Names

```bash
# UNCHANGED - These remain the same in v2
DOCKER_COMPOSE_FILE="docker-compose.yml"
compose-file: "docker-compose.yml"
compose_file: str = "docker-compose.yml"
```

## Count Summary

| Context | Deprecated Instances | Status |
|---------|---------------------|---------|
| GitHub Actions | 10 commands + 2 actions | ✅ Modernized |
| Shell Scripts | 15+ commands | ✅ Modernized |
| Python Code | 2 subprocess calls | ✅ Modernized |
| Documentation | 20+ references | ✅ Modernized |
| TOML Scripts | 0 (already modern) | ✅ N/A |
