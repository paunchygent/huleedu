---
type: runbook
service: bff_teacher_service
severity: low
last_reviewed: '2025-12-08'
---

# BFF and Frontend Development

Operational guide for BFF Teacher Service and Vue 3 frontend development workflows.

## Quick Reference

| Component | Port | Command |
|-----------|------|---------|
| Vite dev server | 5173 | `pdm run fe-dev` |
| BFF static serving | 4101 | `pdm run bff-start` |
| API Gateway | 8080 | `pdm run dev-start api_gateway_service` |

### API Routes

| Endpoint | Description |
|----------|-------------|
| `GET /bff/v1/teacher/dashboard` | Teacher dashboard (stub) |
| `GET /bff/v1/teacher/healthz` | BFF health check (via gateway) |
| `GET /healthz` | Direct BFF health check |

## Development Workflows

### Frontend-Only Development (Recommended for UI work)

```bash
# Terminal 1: Start Vite dev server with HMR
pdm run fe-dev

# Access at http://localhost:5173
# API calls proxy to localhost:8000 (configure in vite.config.ts)
```

### Full Stack with BFF Static Serving

```bash
# 1. Build frontend assets
pdm run fe-build

# 2. Start BFF service (serves from frontend/dist via volume mount)
pdm run bff-start

# 3. Verify health
curl http://localhost:4101/healthz

# Access at http://localhost:4101
```

### Rebuild Frontend After Changes

```bash
# Rebuild and restart (volume mount picks up changes)
pdm run fe-build && pdm run bff-restart
```

## PDM Scripts

| Script | Description |
|--------|-------------|
| `fe-install` | Install frontend dependencies (pnpm) |
| `fe-dev` | Start Vite dev server (port 5173) |
| `fe-build` | Production build to `frontend/dist/` |
| `fe-preview` | Preview production build locally |
| `fe-type-check` | Run TypeScript type checking |
| `bff-build` | Build BFF Docker image |
| `bff-start` | Start BFF container |
| `bff-logs` | Follow BFF container logs |
| `bff-restart` | Restart BFF container |

## Symptoms

### BFF returns 503 "Frontend not built"

**Cause:** `frontend/dist/` is empty or missing.

**Resolution:**
```bash
pdm run fe-build
pdm run bff-restart
```

### BFF health check shows "degraded"

**Cause:** One or more static file checks failed.

**Diagnosis:**
```bash
curl http://localhost:4101/healthz | jq .checks
```

**Resolution:** Ensure `frontend/dist/` contains:
- `index.html`
- `assets/` directory with JS/CSS bundles

### Assets return 404

**Cause:** Asset filenames include content hashes that change on rebuild.

**Resolution:** Frontend code must reference assets via Vite's module system, not hardcoded paths.

### CORS errors in browser console

**Cause:** Frontend origin not in BFF CORS config.

**Resolution:** Check `BFF_TEACHER_SERVICE_CORS_ORIGINS` in docker-compose or `.env`.

Default dev origins:
- `http://localhost:5173` (Vite)
- `http://localhost:4173` (Vite preview)
- `http://localhost:3000`

## Diagnosis

### Check BFF container logs

```bash
pdm run bff-logs
# Or directly:
docker logs -f huleedu_bff_teacher_service
```

### Verify static files in container

```bash
docker exec huleedu_bff_teacher_service ls -la /app/static/
docker exec huleedu_bff_teacher_service ls -la /app/static/assets/
```

### Test static file serving

```bash
# Health check
curl http://localhost:4101/healthz

# Index page
curl -I http://localhost:4101/

# SPA fallback (should return index.html)
curl -I http://localhost:4101/app/dashboard

# Specific asset (use actual filename from frontend/dist/assets/)
curl -I http://localhost:4101/assets/index-*.js
```

## Resolution

### Complete rebuild

```bash
# Stop BFF
docker compose stop bff_teacher_service

# Clean and rebuild frontend
rm -rf frontend/dist
pdm run fe-build

# Rebuild and start BFF
pdm run bff-build
pdm run bff-start
```

### Reset to clean state

```bash
docker compose down bff_teacher_service
docker compose up -d bff_teacher_service
```

## Prevention

### Pre-commit checks

Before committing frontend changes:
```bash
pdm run fe-type-check
pdm run fe-build
```

### CI/CD considerations

- CI builds use multi-stage Dockerfile (no volume mount)
- Frontend is built inside Docker, not externally
- Ensure `frontend/` is in Docker build context

## Architecture

```
Development:
┌─────────────┐     ┌─────────────────────┐
│  Browser    │────▶│  Vite Dev Server    │ (port 5173)
│             │     │  (HMR, hot reload)  │
│             │     │  └─ /api/* proxy ───┼──▶ API Gateway (8080)
└─────────────┘     └─────────────────────┘

Production (via API Gateway):
┌─────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Browser    │────▶│  API Gateway        │────▶│  BFF Teacher        │ (port 4101)
│             │     │  (port 8080)        │     │  ├─ /bff/v1/teacher/*│
│             │     │  ├─ JWT validation  │     │  ├─ /healthz        │
│             │     │  ├─ Rate limiting   │     │  ├─ /assets/* (static)
│             │     │  └─ /bff/v1/teacher │     │  └─ /* (index.html) │
└─────────────┘     └─────────────────────┘     └─────────────────────┘
```

## Related Documentation

- ADR-0007: BFF vs API Gateway Pattern
- ADR-0023: BFF Frontend Build Integration and Static Serving
- `.claude/rules/020.21-bff-teacher-service.md` - BFF service architecture rule
- `frontend/.claude/work/session/handoff.md` - Frontend session context
- `.claude/rules/200-frontend-core-rules.md` - Frontend coding standards
