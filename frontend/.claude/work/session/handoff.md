# HANDOFF: Frontend Session Context

## Purpose

Frontend-specific session context for design iteration and Vue 3 development.
Backend context lives in: `/.claude/work/session/handoff.md`

---

## Current Session (2025-12-08)

### Scope: API Gateway → BFF Routing + API Scaffolding

**Completed:**

1. **API Gateway BFF routing**
   - Added `BFF_TEACHER_URL` to gateway config
   - Created `bff_teacher_routes.py` (proxy following class_routes pattern)
   - Registered router in `main.py` with prefix `/bff/v1/teacher`
   - Added env var to `docker-compose.services.yml`
   - Added `bff_teacher_service` to gateway `depends_on`

2. **BFF API scaffolding**
   - Created `api/v1/teacher_routes.py` with stub `/dashboard` endpoint
   - Created `dto/teacher_v1.py` with `TeacherDashboardResponseV1` DTO
   - Created `clients/__init__.py` scaffold
   - Updated `app.py` to include router before SPA fallback
   - Updated `config.py` CORS methods for full API support

3. **Validation**
   - `pdm run typecheck-all` passes (1409 files)
   - `pdm run lint-fix --unsafe-fixes` passes

**Previous session completed:**
- BFF Teacher Service skeleton (static serving)
- Docker integration (port 4101)
- PDM scripts for BFF management
- Mypy strict config

---

## Next Session Instruction

```markdown
## Role

You are the lead developer and architect of HuleEdu. The scope of this session is
Teacher Dashboard screen implementation in the BFF service.

---

## Session Scope

Objective: Implement the Teacher Dashboard endpoint that aggregates batch data from
RAS and class names from CMS into a screen-optimized response.

Out of scope:
- Batch detail screen (separate task)
- Essay feedback screen (separate task)
- WebSocket real-time updates (Phase 2)
- Admin BFF service

---

## Before Touching Code

From monorepo root:

# 1. Read BFF architecture and patterns
cat docs/decisions/0007-bff-vs-api-gateway-pattern.md
cat .claude/rules/041.1-fastapi-integration-patterns.md
cat .claude/rules/042-async-patterns-and-di.md

# 2. Understand existing BFF structure
cat services/bff_teacher_service/app.py
cat services/bff_teacher_service/api/v1/teacher_routes.py
cat services/bff_teacher_service/dto/teacher_v1.py

# 3. Check backend service APIs to consume
cat services/result_aggregator_service/api/query_routes.py
cat services/result_aggregator_service/models_api.py
cat services/class_management_service/api/v1/class_routes.py

# 4. Implementation plan
cat frontend/TASKS/integration/bff-service-implementation-plan.md

---

## Implementation Steps

1. **Extend DTOs** (`dto/teacher_v1.py`)
   - Add `BatchSummaryV1` with fields from RAS `BatchStatusResponse`
   - Update `TeacherDashboardResponseV1` to use `list[BatchSummaryV1]`
   - Import `BatchClientStatus` from `common_core.status_enums`

2. **Create service clients** (`clients/`)
   - Create `ras_client.py` with `RASClientProtocol` and `RASClient` impl
   - Create `cms_client.py` with `CMSClientProtocol` and `CMSClient` impl
   - Use `httpx.AsyncClient` with proper timeout and error handling

3. **Setup DI** (`di.py`)
   - Create `BFFTeacherProvider` with Dishka providers
   - Provide `httpx.AsyncClient` (APP scope)
   - Provide RAS and CMS clients (APP scope)

4. **Update app.py**
   - Import and setup Dishka container
   - Use `DishkaRoute` for router

5. **Implement dashboard endpoint** (`api/v1/teacher_routes.py`)
   - Inject RAS and CMS clients via `FromDishka`
   - Extract `X-User-ID` and `X-Correlation-ID` headers
   - Parallel fetch batches (RAS) and classes (CMS) with `asyncio.gather`
   - Enrich batches with class names
   - Return `TeacherDashboardResponseV1`

6. **Validation**
   - `pdm run typecheck-all` passes
   - Add unit test with mocked clients
   - Test via gateway: `curl http://localhost:8080/bff/v1/teacher/dashboard`

---

## Key Files

| File | Purpose |
|------|---------|
| `services/bff_teacher_service/api/v1/teacher_routes.py` | Dashboard endpoint |
| `services/bff_teacher_service/dto/teacher_v1.py` | DTOs |
| `services/bff_teacher_service/clients/ras_client.py` | RAS HTTP client |
| `services/bff_teacher_service/clients/cms_client.py` | CMS HTTP client |
| `services/bff_teacher_service/di.py` | Dishka DI providers |
| `services/result_aggregator_service/models_api.py` | RAS response models |
| `frontend/TASKS/integration/bff-service-implementation-plan.md` | Full plan |

---

## When Done

Update:
- `frontend/.claude/work/session/handoff.md` - what was completed
- `frontend/TASKS/integration/bff-service-implementation-plan.md` - mark dashboard complete
- Create next session instruction for Batch Detail screen
```

---

## Key Files

| File | Purpose | Status |
|------|---------|--------|
| `services/bff_teacher_service/app.py` | BFF FastAPI app | ✅ Updated |
| `services/bff_teacher_service/config.py` | BFF settings | ✅ Updated |
| `services/bff_teacher_service/api/v1/teacher_routes.py` | API routes | ✅ Created |
| `services/bff_teacher_service/dto/teacher_v1.py` | DTOs | ✅ Created |
| `services/bff_teacher_service/clients/__init__.py` | Clients scaffold | ✅ Created |
| `services/api_gateway_service/config.py` | Gateway config | ✅ Updated |
| `services/api_gateway_service/routers/bff_teacher_routes.py` | Gateway proxy | ✅ Created |
| `services/api_gateway_service/app/main.py` | Gateway app | ✅ Updated |
| `docker-compose.services.yml` | Service definitions | ✅ Updated |

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
