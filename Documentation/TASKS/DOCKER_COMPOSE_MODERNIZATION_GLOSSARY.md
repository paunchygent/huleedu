# Docker Compose v1→v2 Command Reference

## Commands

```bash
# v1 → v2
docker-compose up -d                           → docker compose up -d
docker-compose down --volumes --remove-orphans → docker compose down --volumes --remove-orphans
docker-compose ps                              → docker compose ps
docker-compose logs <service>                  → docker compose logs <service>
docker-compose build --no-cache                → docker compose build --no-cache
```

## GitHub Actions

```yaml
# v1 (REMOVED)
- uses: docker/setup-compose-action@v1
- uses: jaracogmbh/docker-compose-health-check-action@v1.0.0

# v2 (IMPLEMENTED)  
# Built-in Docker Compose v2, native health checks with jq
```

## Python

```python
# v1 → v2
["docker-compose", "up", "-d"]    → ["docker", "compose", "up", "-d"]
["docker-compose", "ps"]          → ["docker", "compose", "ps"]
```

## Health Checks

```bash
# v1 (BROKEN - counted empty strings as unhealthy)
select(.Health != null and .Health != "healthy")

# v2 (FIXED - positive logic)
select(.Health == "healthy") | count == 5
```

---
**Status**: Complete modernization achieved.
