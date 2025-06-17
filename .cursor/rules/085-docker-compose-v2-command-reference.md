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

### PDM Script Shortcuts (Monorepo)
```bash
# Docker environment management
pdm run docker-rebuild    # Clean rebuild: down --remove-orphans + build + up -d
pdm run docker-reset      # Full reset: down --remove-orphans --volumes + build + up -d
pdm run docker-restart    # Quick restart: down + up -d --build
pdm run docker-down-clean # down --remove-orphans (cleanup without rebuild)

# Standard operations
pdm run docker-build      # docker compose build
pdm run docker-up         # docker compose up -d
pdm run docker-down       # docker compose down
pdm run docker-logs       # docker compose logs -f --tail=100
```

### Standalone Script
```bash
# For non-PDM usage
./scripts/docker-rebuild.sh        # Standard rebuild
./scripts/docker-rebuild.sh --reset # Full reset with volume removal
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