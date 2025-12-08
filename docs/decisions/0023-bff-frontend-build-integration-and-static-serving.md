---
type: decision
id: ADR-0023
status: accepted
created: '2025-12-08'
last_updated: '2025-12-08'
---

# ADR-0023: BFF Frontend Build Integration and Static Serving

## Status

Accepted

## Context

The HuleEdu platform requires serving Vue 3 frontend assets in production while maintaining
fast iteration during development. The BFF Teacher Service (ADR-0007) needs to serve
static assets alongside its API composition responsibilities.

### Key Requirements

1. **Production builds must be self-contained** - Docker images include all frontend assets
2. **Development must support hot-reload** - Vite dev server on port 5173 with HMR
3. **Build pattern must align with existing Docker stack** - Use `huledu-deps:dev` base image
4. **SPA routing must work** - All frontend routes serve index.html for client-side routing
5. **Fast dev iteration** - Avoid full Docker rebuilds when only frontend changes

### Options Considered

1. **Multi-stage Dockerfile only** - Node.js builds frontend, Python serves
2. **Volume mount only** - Build frontend externally, mount into container
3. **Hybrid approach** - Multi-stage for CI/production, volume mount for dev
4. **Separate nginx container** - Dedicated static server

## Decision

Implement **hybrid approach** with the following pattern:

### 1. Multi-Stage Dockerfile

```dockerfile
# Stage 1: Frontend Builder
FROM node:20-slim AS frontend-builder
RUN corepack enable pnpm
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# Stage 2: Python Base (huledu-deps pattern)
ARG DEPS_IMAGE=huledu-deps:dev
FROM ${DEPS_IMAGE} AS base
# ... standard Python setup ...

# Stage 3: Production
FROM base AS production
COPY services/bff_teacher_service/ /app/services/bff_teacher_service/
COPY --from=frontend-builder /frontend/dist /app/static
```

### 2. Docker Compose Volume Override

```yaml
bff_teacher_service:
  volumes:
    # Dev override: mount local frontend/dist for hot iteration
    - ./frontend/dist:/app/static:ro
```

### 3. Development Workflow

- **Frontend dev**: `pdm run fe-dev` (Vite on port 5173, proxies /api to backend)
- **BFF static serving**: `pdm run bff-start` (port 4101, serves built assets)
- **No proxy in BFF** - Developers access Vite directly for HMR

### 4. FastAPI Static Serving

```python
# Mount assets directory
app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")))

# SPA fallback for client-side routing
@app.get("/{full_path:path}")
async def serve_spa(full_path: str) -> FileResponse | JSONResponse:
    if (static_dir / "index.html").exists():
        return FileResponse(static_dir / "index.html")
    return JSONResponse(status_code=503, content={"detail": "Frontend not built"})
```

### 5. Request Routing

**Development**:

```
Browser → Vite (5173) → HMR + /api proxy → API Gateway (8080)
```

**Production**:

```
Browser → BFF (4101) → Static files from /app/static
         ↘ /api/* → API Gateway → Backend services
```

## Consequences

### Positive

- **Fast dev iteration** - Change frontend, rebuild with `pdm run fe-build`, container picks up changes via volume mount
- **Self-contained production builds** - CI builds include frontend, no external dependencies
- **Vite HMR preserved** - No proxy overhead in BFF for development
- **Pattern alignment** - Follows `huledu-deps:dev` base image pattern
- **SPA routing works** - All unmatched routes serve index.html

### Negative

- **Two-step dev build** - Must run `pdm run fe-build` before `pdm run bff-start`
- **Volume mount platform issues** - Some Docker Desktop configurations may have file sync delays
- **Larger Docker context** - Build context includes `frontend/` directory

### Mitigations

- Add `pdm run bff-refresh` script combining `fe-build` + `bff-restart`
- Document workflow clearly in handoff.md
- CI/CD always uses multi-stage (ignores volume mount)

## Related ADRs

- ADR-0007: BFF vs API Gateway Pattern (BFF service architecture)

## Implementation

- Service: `services/bff_teacher_service/`
- Dockerfile: `services/bff_teacher_service/Dockerfile`
- Docker Compose: `docker-compose.services.yml` (bff_teacher_service)
- PDM scripts: `bff-build`, `bff-start`, `bff-logs`, `bff-restart`
