# HANDOFF: Frontend Session Context

## Purpose

Frontend-specific session context for design iteration and Vue 3 development.
Backend context lives in: `/.claude/work/session/handoff.md`

---

## Current Session (2025-12-08)

### Scope: BFF Static Serving Integration

**Completed:**

1. **BFF Teacher Service skeleton created** (`services/bff_teacher_service/`)
   - FastAPI app serving Vue 3 frontend static assets
   - Health endpoint at `/healthz` following Rule 072 format
   - Static files mount at `/assets/*`
   - SPA fallback serving `index.html` for client-side routing
   - Correlation ID middleware
   - CORS configured for dev origins

2. **Docker integration**
   - Multi-stage Dockerfile (Node.js frontend builder + Python base)
   - Added to `docker-compose.services.yml` on port 4101
   - Volume mount for dev: `frontend/dist:/app/static:ro`
   - Health check: `curl -f http://localhost:4101/healthz`

3. **PDM scripts added**
   - `pdm run bff-build` - Build BFF Docker image
   - `pdm run bff-start` - Start BFF service
   - `pdm run bff-logs` - Follow BFF logs
   - `pdm run bff-restart` - Restart BFF service

4. **Mypy strict config**
   - Added `services.bff_teacher_service.*` to strict mypy overrides

**Validated:**
- Health check returns healthy with all static file checks passing
- index.html served at root
- Assets served at /assets/*
- SPA fallback works for client-side routes (/app/dashboard → index.html)

---

## Next Session – Recommended Focus

1. **API Gateway routing to BFF:**
   - Configure API Gateway to proxy `/bff/v1/teacher/*` to BFF service
   - Add BFF_TEACHER_URL to gateway config

2. **Full BFF implementation (separate task):**
   - API composition endpoints (DTOs, service clients)
   - Teacher dashboard, batch detail, essay feedback screens
   - See: `frontend/TASKS/integration/bff-service-implementation-plan.md`

3. **Development workflow:**
   - Frontend dev: `pdm run fe-dev` (Vite on port 5173)
   - BFF static serving: `pdm run bff-start` (port 4101)
   - Full stack: API Gateway (8080) → BFF (4101) or direct services

---

## Key Files

| File | Purpose | Status |
|------|---------|--------|
| `services/bff_teacher_service/app.py` | BFF FastAPI static serving | ✅ Created |
| `services/bff_teacher_service/config.py` | BFF settings | ✅ Created |
| `services/bff_teacher_service/Dockerfile` | Multi-stage build | ✅ Created |
| `docker-compose.services.yml` | BFF service definition | ✅ Updated |
| `frontend/dist/` | Vue 3 production build | ✅ Verified |
| `styles/src/huleedu-landing-final.html` | Landing page | ✅ Updated |
| `styles/src/anmal-intresse.html` | Waitlist signup | ✅ Updated |
| `docs/design/customer-flows.md` | Personas & journeys | Reference |

---

## Task System

Frontend has its own task system separate from backend:

- **Frontend tasks:** `frontend/TASKS/` (frontend-specific location)
- **Frontend ADRs:** `frontend/docs/decisions/` (frontend-only decisions)
- **Cross-cutting ADRs:** `docs/decisions/` (affects both frontend AND backend)
- **Backend tasks:** `TASKS/` in monorepo root (assessment/, infrastructure/, etc.)

> **Note:** Session context is team-specific. Frontend session lives here; backend session lives in `/.claude/work/session/handoff.md`. Do not merge them.

This structure enables frontend-specific hooks, agents, and tooling when starting Claude from the `frontend/` directory.

---

## Cross-Reference

- **Backend context:** `/.claude/work/session/handoff.md`
- **Design specs:** `frontend/docs/design/`
- **Frontend rules:** `/.claude/rules/200-frontend-core-rules.md`
- **Prototype docs:** `frontend/styles/src/README.md` (Swedish)
- **Frontend tasks:** `frontend/TASKS/`
