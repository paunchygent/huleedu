---
description: ALWAYS activate when using Docker or using Docker commands. This is the correct v2 syntax
globs: 
alwaysApply: false
---
# 085: Docker Compose v2 Command Reference

## Command Syntax Transformation

### Basic Commands
```bash
# v1 → v2
docker-compose up -d            → docker compose up -d
docker-compose down             → docker compose down
docker-compose ps               → docker compose ps
docker-compose build            → docker compose build
docker-compose logs <service>   → docker compose logs <service>
docker-compose exec <service>   → docker compose exec <service>
```

### Advanced Operations
```bash
# v1 → v2
docker-compose down --volumes --remove-orphans → docker compose down --volumes --remove-orphans
docker-compose build --no-cache                → docker compose build --no-cache
docker-compose logs --tail=50 <service>        → docker compose logs --tail=50 <service>
docker-compose up -d <service>                 → docker compose up -d <service>
```

### GitHub Actions
```yaml
# v1 (DEPRECATED)
- uses: docker/setup-compose-action@v1

# v2 (MODERN)
# No setup required - built into Ubuntu runners
```

### Python Subprocess
```python
# v1 → v2
["docker-compose", "up", "-d"]     → ["docker", "compose", "up", "-d"]
["docker-compose", "ps"]           → ["docker", "compose", "ps"]
["docker-compose", "down"]         → ["docker", "compose", "down"]
```

### Health Check Availability
```bash
# v1 → v2
command -v docker-compose         → docker compose version
```

---
**Key Change**: `docker-compose` (hyphen) → `docker compose` (space)
