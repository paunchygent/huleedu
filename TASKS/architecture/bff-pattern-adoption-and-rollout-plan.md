---
id: bff-pattern-adoption-and-rollout-plan
title: Backend-For-Frontend (BFF) Pattern — Adoption & Rollout Plan
type: task
status: proposed
priority: medium
domain: architecture
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-08-24'
last_updated: '2026-02-01'
related: []
labels: []
---
Status: Draft
Owner: Architecture
Last updated: 2025-08-23

## Purpose

- Define a concrete, repo-aligned plan to introduce per-role BFFs without assumptions.
- Capture explicit decision points and unknowns before implementation (“no vibe-coding”).
- Sequence work to deliver Teacher BFF first, then Admin BFF.

## Scope

- Phase 1: `bff-teacher` for Teacher screens (1–4) with gateway routing and initial DTOs.
- Phase 2: `bff-admin` for Admin screens (6–7) with gateway routing; introduce Config service if approved.
- Future: Student BFF when Student role goes live.

## Current State (Evidence Only)

- API Gateway (FastAPI): `services/api_gateway_service`
  - App and routers registered in `services/api_gateway_service/app/__init__.py`
  - Routers present: `routers/class_routes.py`, `routers/status_routes.py`, `routers/file_routes.py`, `routers/batch_routes.py` (proxy + composition patterns)
  - Config: `services/api_gateway_service/config.py` exposes downstream URLs and CORS
- Result Aggregator Service (RAS, Quart): `services/result_aggregator_service`
  - Query endpoints (internal):
    - `GET /internal/v1/batches/{batch_id}/status` in `api/query_routes.py`
    - `GET /internal/v1/batches/user/{user_id}` in `api/query_routes.py`
- Class Management Service (CMS, Quart): `services/class_management_service`
  - Classes CRUD and roster: `api/class_routes.py` registered under `/v1/classes` in `app.py`
  - Batch association endpoints:
    - `GET /v1/batches/{batch_id}/student-associations` in `api/batch_routes.py`
    - `POST /v1/batches/{batch_id}/student-associations/confirm` in `api/batch_routes.py`
- File Service (Quart): `services/file_service`
  - File ingestion and batch file ops under `/v1/files/...` in `api/file_routes.py`
- Identity Service (Quart): `services/identity_service`
  - Authentication/registration/profile/verification under `/v1/auth/*`, `/v1/users/*`
  - No explicit admin user approval endpoints found
- WebSocket Service (FastAPI): `services/websocket_service`
  - WebSocket endpoint `/` (query param token) in `routers/websocket_routes.py`
  - Uses Redis pub/sub via `implementations/message_listener.py`
- Shared libs: `libs/common_core`, `libs/huleedu_service_libs` (HTTP clients, error handling, redis, metrics, DI utilities)
- Docker Compose: `docker-compose.services.yml` — no BFF services defined yet

## Desired End State

- Introduce per-role BFFs:
  - `bff-teacher`: Composes CMS, RAS, Files, Content, Identity for Teacher UI screens
  - `bff-admin`: Composes Identity (admin), Config service (new), and operational sources for Admin UI
- Gateway routes:
  - `/bff/v1/teacher/*` → `bff-teacher`
  - `/bff/v1/admin/*` → `bff-admin`
- DTOs: Versioned, role/screen-specific Pydantic models under each BFF (e.g., `dto/teacher_v1.py`)
- Streaming: BFF emits minimal diffs to Redis channels `user:{user_id}:events`; `websocket_service` broadcasts to clients

## Decision Points (To Resolve Before/While Implementing)

1. BFF topology: single multi-role BFF vs separate per-role services
   - Default recommendation: separate `bff-teacher` and `bff-admin` for ownership and scaling
2. Contract ownership: where DTOs live and how to version
   - Proposal: DTOs colocated in each BFF under `dto/*_v1.py` with semantic versioning; contract tests required
3. Streaming scope initial cut
   - Which screens stream (e.g., Teacher dashboard, batch details) and payload shapes for diffs
4. CMS class listing contract
   - Need `GET /v1/classes` with owner filter or equivalent (not present today)
5. RAS essay-level query
   - Do we add `GET /internal/v1/batches/{batch_id}/essays/{essay_id}` (not present today) to avoid over-fetching?
6. Identity admin workflows
   - Approve/deny/list pending endpoints required (not present today). Where to implement and with what schema?
7. Config service
   - Introduce a new `config_service` vs. storing settings elsewhere; define its minimal API surface and storage
8. Error mapping standard in BFFs
   - Adopt `huleedu_service_libs.error_handling.fastapi` mapping and a common BFF error envelope
9. Caching strategy in BFFs
   - Short TTL in-memory vs Redis cache for stable metadata; per dependency timeouts and circuit breakers

## Screen Inventory → BFF Endpoints (No Assumptions Beyond Evidence)

- Teacher 1. Class dashboard (summary across batches)
  - Proposed: `GET /v1/teacher/dashboard`
  - Sources available today: RAS user batches (exists). CMS class listing (missing).
  - DTO: `TeacherClassDashboardV1` (fields for batch-centric summary available; class-centric summary blocked on CMS list)
- Teacher 2. Batch detail (progress + actions)
  - `GET /v1/teacher/batches/{batch_id}` → compose RAS batch status (exists) and file/batch state if needed (exists)
  - DTO: `TeacherBatchDetailV1`
- Teacher 3. Essay feedback view/editor
  - `GET /v1/teacher/batches/{batch_id}/essays/{essay_id}` → can filter essay from RAS batch status (exists), but essay-only endpoint would be cleaner (missing)
  - DTO: `TeacherEssayFeedbackV1`
- Teacher 4. Student-matching review
  - `GET /v1/teacher/batches/{batch_id}/associations`, `POST /v1/teacher/batches/{batch_id}/associations/confirm` → CMS endpoints exist
  - DTOs: `StudentAssociationListV1`, `AssociationConfirmRequestV1`
- Admin 6. Account validation
  - Endpoints in Identity for listing/approve/deny users are missing
- Admin 7. Service settings
  - Requires a new Config service API (missing)

## Proposed BFF Service Structures (Concrete)

- `services/bff_teacher_service/`
  - `app.py`: FastAPI app setup (CORS, tracing, metrics, DI), ≤150 LoC
  - `api/teacher_routes.py`: `/v1/teacher/*` handlers
  - `dto/teacher_v1.py`: Pydantic DTOs for screens 1–4
  - `di.py`: Providers (httpx clients, redis, metrics, authZ helper)
  - `clients/`: thin wrappers for CMS, RAS, Identity, Content, File
  - `streaming/`: optional Kafka consumer and Redis publisher
  - `tests/`: unit and contract tests with HTTP client mocks
- `services/bff_admin_service/` (mirror structure)

## Domain Gaps to Close (Blocking/Enhancing)

- CMS: Add `GET /v1/classes` with support for filtering by owner (owner from `X-User-ID`)
- RAS: Add essay-level query to avoid full-batch fetch for single essay view
- Identity: Add admin endpoints for listing pending users and approve/deny actions
- Config: Stand up minimal `config_service` with `GET/PUT /v1/settings/{namespace}` and audit logging

## Implementation Plan (Incremental)

Phase 1 — `bff-teacher` MVP

1) Create service skeleton `services/bff_teacher_service/` (app, di, dto, clients, tests)
2) Implement endpoints:
   - `GET /v1/teacher/batches/{batch_id}` (compose from RAS)
   - `GET /v1/teacher/batches/{batch_id}/essays/{essay_id}` (filter from RAS batch payload)
   - `GET /v1/teacher/batches/{batch_id}/associations` (proxy → CMS + normalize)
   - `POST /v1/teacher/batches/{batch_id}/associations/confirm` (proxy → CMS + normalize)
   - `GET /v1/teacher/dashboard` (batch-centric summary from RAS only; upgrade later when CMS list ready)
3) Add API Gateway proxy routes:
   - `/bff/v1/teacher/{path:path}` → `BFF_TEACHER_URL`
4) Wire Docker Compose service for `bff-teacher` with envs:
   - URLs for RAS/CMS/Identity/File/Content, Redis, INTERNAL_API_KEY for RAS
5) Tests: unit + contract tests for DTOs; simulate downstream HTTP
6) Optional: Redis streaming for batch status diffs (publish to `user:{user_id}:events`)

Phase 2 — Domain Enhancements + `bff-admin`
7) Implement CMS class list endpoint and update Teacher dashboard DTO to include class-centric summary
8) Add RAS essay-level query and update essay endpoint to use it
9) Add Identity admin endpoints for pending approvals (list/approve/deny)
10) Stand up `bff_admin_service` with:
    - `GET /v1/admin/users/pending`, `POST /v1/admin/users/{id}/approve|deny`
    - `GET/PUT /v1/admin/settings/{namespace}` (after Config service exists)
11) Add API Gateway proxy routes: `/bff/v1/admin/{path:path}` → `BFF_ADMIN_URL`

## Example DTO Placeholders (Fields Grounded in Existing Models)

Note: Finalize all DTOs via a contract workshop before coding. Placeholders below list only fields backed by current evidence.

- `TeacherBatchDetailV1`
  - `batch_id` (from RAS `BatchStatusResponse.batch_id`)
  - `overall_status` (from RAS `BatchStatusResponse.overall_status`)
  - `essays[]`:
    - `essay_id`, `filename`, `file_upload_id`,
    - `spellcheck_status`, `spellcheck_correction_count`, `spellcheck_corrected_text_storage_id`,
    - `cj_assessment_status`, `cj_rank`, `cj_score`,
    - `last_updated`
  - `requested_pipeline`, `current_phase`, `created_at`, `last_updated`

- `StudentAssociationListV1`
  - Backed by CMS response `get_batch_student_associations` structure (exact field names to confirm in CMS handler output)

- `TeacherClassDashboardV1`
  - MVP fields sourced only from `GET /internal/v1/batches/user/{user_id}`: aggregated counts and latest update times
  - Class-centric fields are “TBD” pending CMS `GET /v1/classes` implementation

## Testing & Validation

- Unit tests for BFF route handlers and composition (mock `httpx.AsyncClient`)
- Contract tests for DTO models using sample payloads from:
  - `services/result_aggregator_service/models_api.py::BatchStatusResponse`
  - CMS association responses (validate shape we actually return)
- Runbook from repo root:
  - `pdm run test-unit` (unit tests)
  - `pdm run test-integration` (when available)
  - `pdm run typecheck-all` after models/tests added
  - `pdm run format-all` (Ruff formatting)
  - `pdm run lint-fix --unsafe-fixes` (Ruff linting)

## Observability & Security (Reused Patterns)

- Metrics: Reuse `huleedu_service_libs.metrics_middleware` for HTTP; per-downstream histograms
- Tracing: Propagate `X-Correlation-ID`; OTEL setup mirrors existing services
- AuthZ: Gateway provides JWT; BFF trusts `X-User-ID` and enforces teacher↔class scope via CMS checks where needed
- RAS internal calls authenticated via `X-Internal-API-Key` + `X-Service-ID`

## Risks & Mitigations

- Missing downstream endpoints (CMS list, RAS essay, Identity admin):
  - Track as dependencies; stage dashboard as batch-centric; iterate post-availability
- Duplication across BFFs:
  - Extract shared client and policy helpers into a small internal library (or reuse `huleedu_service_libs` patterns)
- Streaming complexity:
  - Start with Redis pub/sub diffs for batch status only; expand deliberately

## Open Questions

1. Confirm BFF topology (single vs per-role) and service names/ports
2. Finalize DTO fields for each screen (contract-first review required)
3. Decide caching policy per dependency (in-memory vs Redis; TTL values)
4. Confirm Config service MVP scope (namespaces, audit requirements)
5. Confirm Identity admin approval workflow (states, events, side effects)

## Non-Goals (For Now)

- Full document assembly service (use Content/File as-is)
- Cross-service direct DB access (forbidden by architecture rules)
- Gateway taking on UI-specific composition (BFF owns it)

## Acceptance Criteria (Phase 1)

- `bff-teacher` service composes real data for screens 2–4
- `/bff/v1/teacher/*` routes available via API Gateway
- DTO models exist with contract tests; no unverified fields
- Unit tests cover composition, error mapping, and partial failure cases
- Optional: batch status diffs published to Redis and visible through `websocket_service`

---

# Junior Developer Guide: BFF in HuleEdu (Textbook Walkthrough)

This section explains, step by step, what a Backend‑For‑Frontend (BFF) is, why we use it, and exactly how it looks in this repository—using only structures that exist here today. Code snippets are illustrative and follow the same libraries and patterns you can see under `services/api_gateway_service/` and other services.

## BFF 101 (What and Why)

- A BFF is a small backend tailored to a specific frontend (or role) that:
  - Calls multiple domain services in parallel (composition).
  - Returns a screen‑specific shape (DTO) that fits the UI perfectly.
  - Enforces fine‑grained access policy for that UI.
- What a BFF is NOT:
  - It’s not the API Gateway. The gateway handles edge concerns (authN, coarse rate limits, CORS) and forwards to the right backend.
  - It’s not a domain service (e.g., Class Management, Result Aggregator). Those own business logic and data. The BFF only composes their results.

In HuleEdu terms:

- Gateway: `services/api_gateway_service` (FastAPI) — entrypoint for the web app.
- BFFs (to add): one per role, e.g. `bff-teacher`, later `bff-admin`. Gateway routes `/bff/v1/*` to them.
- Services that the BFF composes:
  - Class Management Service (CMS): `services/class_management_service` (Quart)
  - Result Aggregator Service (RAS): `services/result_aggregator_service` (Quart)
  - File & Content services (Quart)
  - Identity service (Quart)
  - WebSocket service (FastAPI) for push updates (existing pub/sub pipeline)

## How BFF Shows Up in This Repo

- New services under `services/` (e.g., `services/bff_teacher_service/`).
- New gateway routers that forward `/bff/v1/teacher/*` to the teacher BFF (thin proxy only).
- DTOs (Pydantic) defined inside the BFF for each screen, with versioned modules like `dto/teacher_v1.py`.
- Clients that call existing services (using `httpx.AsyncClient`) and reuse shared libs from `libs/huleedu_service_libs` (metrics, error mapping, redis, etc.).

## Step‑by‑Step: Build `bff-teacher` MVP

We’ll implement four endpoints aligned with Teacher screens that already have upstream support:

1) Dashboard summary (batch‑centric for MVP)
2) Batch detail view
3) Essay feedback view (subset from RAS batch payload)
4) Student association review/confirm (CMS)

### 1) Create the service skeleton

Target structure:

```
services/bff_teacher_service/
  app.py               # FastAPI app, middleware, DI hookup
  di.py                # Provide httpx clients, redis, settings, metrics
  dto/teacher_v1.py    # Screen‑specific Pydantic models (v1)
  api/teacher_routes.py# Role endpoints under /v1/teacher/*
  clients/
    ras_client.py
    cms_client.py
    file_client.py
    content_client.py
    identity_client.py
  tests/
    test_teacher_routes.py
```

Why FastAPI? Evidence: the gateway and websocket services already use FastAPI + Dishka (`dishka.integrations.fastapi`) and HuleEdu libs have FastAPI error integration (`huleedu_service_libs.error_handling.fastapi`). Using the same stack reduces friction.

Minimal `app.py` (follows gateway patterns):

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from huleedu_service_libs.error_handling.fastapi import register_error_handlers

from .di import setup_dependency_injection
from .api.teacher_routes import router as teacher_router

app = FastAPI(title="bff-teacher", version="1.0.0")
register_error_handlers(app)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

setup_dependency_injection(app)
app.include_router(teacher_router, prefix="/v1/teacher", tags=["Teacher BFF"])
```

### 2) Define DTOs (screen contracts)

Only include fields we can fetch from current services. Example DTOs referencing RAS structures in `services/result_aggregator_service/models_api.py`:

```python
# services/bff_teacher_service/dto/teacher_v1.py
from datetime import datetime
from pydantic import BaseModel
from common_core.status_enums import BatchClientStatus
from common_core.pipeline_models import PhaseName

class EssayV1(BaseModel):
    essay_id: str
    filename: str | None = None
    file_upload_id: str | None = None
    spellcheck_status: str | None = None
    spellcheck_correction_count: int | None = None
    spellcheck_corrected_text_storage_id: str | None = None
    cj_assessment_status: str | None = None
    cj_rank: int | None = None
    cj_score: float | None = None
    last_updated: datetime

class BatchDetailV1(BaseModel):
    batch_id: str
    overall_status: BatchClientStatus
    requested_pipeline: str | None = None
    current_phase: PhaseName | None = None
    essays: list[EssayV1]
    created_at: datetime
    last_updated: datetime
```

### 3) Write thin service clients

Clients call existing endpoints. Example RAS client using internal auth headers (compose file provides `${HULEEDU_INTERNAL_API_KEY}` to RAS):

```python
# services/bff_teacher_service/clients/ras_client.py
from httpx import AsyncClient

class RASClient:
    def __init__(self, base_url: str, api_key: str, service_id: str = "bff-teacher"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.service_id = service_id

    async def get_batch_status(self, batch_id: str) -> dict:
        url = f"{self.base_url}/internal/v1/batches/{batch_id}/status"
        async with AsyncClient(timeout=30) as client:
            r = await client.get(url, headers={
                "X-Internal-API-Key": self.api_key,
                "X-Service-ID": self.service_id,
            })
            r.raise_for_status()
            return r.json()

    async def get_user_batches(self, user_id: str, limit: int = 20, offset: int = 0) -> dict:
        url = f"{self.base_url}/internal/v1/batches/user/{user_id}?limit={limit}&offset={offset}"
        async with AsyncClient(timeout=30) as client:
            r = await client.get(url, headers={
                "X-Internal-API-Key": self.api_key,
                "X-Service-ID": self.service_id,
            })
            r.raise_for_status()
            return r.json()
```

Example CMS client for owner class list (you can see the new `GET /v1/classes/` route in `services/class_management_service/api/class_routes.py`):

```python
# services/bff_teacher_service/clients/cms_client.py
from httpx import AsyncClient

class CMSClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def list_classes(self, user_id: str, limit: int = 20, offset: int = 0) -> dict:
        url = f"{self.base_url}/v1/classes?limit={limit}&offset={offset}"
        async with AsyncClient(timeout=30) as client:
            r = await client.get(url, headers={"X-User-ID": user_id})
            r.raise_for_status()
            return r.json()
```

### 4) Implement the BFF routes

Example: Batch detail screen composition (maps RAS response to `BatchDetailV1`).

```python
# services/bff_teacher_service/api/teacher_routes.py
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from ..clients.ras_client import RASClient
from ..dto.teacher_v1 import BatchDetailV1, EssayV1

router = APIRouter()

@router.get("/batches/{batch_id}", response_model=BatchDetailV1)
@inject
async def get_batch_detail(batch_id: str, ras: FromDishka[RASClient], user_id: FromDishka[str]):
    # 1) Fetch from RAS (internal)
    data = await ras.get_batch_status(batch_id)
    # 2) Enforce ownership: data["user_id"] must equal user_id
    if data.get("user_id") != user_id:
        # Return 403 in real implementation
        raise PermissionError("User not authorized for batch")
    # 3) Map to DTO
    essays = [EssayV1(**e) for e in data.get("essays", [])]
    return BatchDetailV1(
        batch_id=data["batch_id"],
        overall_status=data["overall_status"],
        requested_pipeline=data.get("requested_pipeline"),
        current_phase=data.get("current_phase"),
        essays=essays,
        created_at=data["created_at"],
        last_updated=data["last_updated"],
    )
```

Note: In the real implementation, you will normalize errors via `huleedu_service_libs.error_handling.fastapi` and return proper 4xx/5xx responses, just like the gateway does.

### 5) Dependency Injection (DI)

Follow the gateway pattern: provide dependencies (settings, user_id, clients) with Dishka.

```python
# services/bff_teacher_service/di.py
import os
from dishka import make_container, Provider
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from .clients.ras_client import RASClient
from .clients.cms_client import CMSClient

class BFFProvider(Provider):
    def __init__(self):
        self.ras = lambda: RASClient(os.environ["RESULT_AGGREGATOR_URL"], os.environ["HULEEDU_INTERNAL_API_KEY"])  # noqa: E501
        self.cms = lambda: CMSClient(os.environ["CMS_API_URL"])  # provided by docker env

    async def provide_user_id(self) -> str:
        # In practice, read from request scope set by gateway middleware
        return "mock-user-id"

def setup_dependency_injection(app: FastAPI) -> None:
    container = make_container(BFFProvider())
    setup_dishka(container, app)
```

### 6) Expose BFF via the Gateway (minimal proxy)

Add thin proxy routes in the gateway to forward `/bff/v1/teacher/*` to `bff-teacher`:

```python
# services/api_gateway_service/routers/bff_teacher_routes.py (pattern mirrors class_routes.py)
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from httpx import AsyncClient
from services.api_gateway_service.config import settings

router = APIRouter(route_class=DishkaRoute)

@router.api_route("/bff/v1/teacher/{path:path}", methods=["GET","POST","PUT","DELETE"])
async def proxy_teacher_bff(path: str, request: Request) -> tuple[str, int, dict]:
    url = f"{settings.BFF_TEACHER_URL}/v1/teacher/{path}"
    async with AsyncClient(timeout=30) as client:
        r = await client.request(
            method=request.method,
            url=url,
            headers={
                # Forward auth context and correlation ID
                "Authorization": request.headers.get("Authorization", ""),
                "X-User-ID": request.headers.get("X-User-ID", ""),
                "X-Correlation-ID": request.headers.get("X-Correlation-ID", ""),
            },
            params=request.query_params,
            content=await request.body(),
        )
    return r.text, r.status_code, dict(r.headers)
```

Register this router in `services/api_gateway_service/app/__init__.py` the same way other routers are included.

### 7) Wire Docker Compose (service + envs)

Add a service like (example, adjust ports/names as needed):

```yaml
# docker-compose.services.yml (illustrative snippet)
  bff_teacher_service:
    build:
      context: .
      dockerfile: services/bff_teacher_service/Dockerfile
    container_name: huleedu_bff_teacher
    networks: [huleedu_internal_network]
    environment:
      - RESULT_AGGREGATOR_URL=http://result_aggregator_service:4003
      - CMS_API_URL=http://class_management_service:5002
      - FILE_SERVICE_URL=http://file_service:7001
      - CONTENT_SERVICE_URL=http://content_service:8000
      - HULEEDU_INTERNAL_API_KEY=${HULEEDU_INTERNAL_API_KEY}
      - ENVIRONMENT=${ENVIRONMENT:-production}
```

Then add to gateway config:

```python
# services/api_gateway_service/config.py (add fields)
BFF_TEACHER_URL: str = Field(default="http://bff_teacher_service:4101")
```

### 8) Test the BFF

Unit test example using FastAPI’s test client and mocking the RAS client:

```python
import pytest
from fastapi.testclient import TestClient
from services.bff_teacher_service.app import app

def test_get_batch_detail_happy_path(monkeypatch):
    class FakeRAS:
        async def get_batch_status(self, batch_id: str) -> dict:
            return {
                "batch_id": batch_id,
                "user_id": "u1",
                "overall_status": "processing",
                "essays": [],
                "created_at": "2024-01-01T00:00:00Z",
                "last_updated": "2024-01-01T00:01:00Z",
            }

    # Monkeypatch DI to return FakeRAS and user_id "u1"
    # (Implementation depends on DI setup; pattern mirrors gateway tests.)

    client = TestClient(app)
    r = client.get("/v1/teacher/batches/b123", headers={"X-User-ID":"u1"})
    assert r.status_code == 200
    assert r.json()["batch_id"] == "b123"
```

## End‑to‑End Example Calls

1) CMS class list (now available):

```
GET /v1/classes?limit=10&offset=0
Headers: X-User-ID: teacher_123

Response 200
{
  "classes": [
    {"id":"...","name":"Writing 101","course_code":"...","student_count":25,"created_at":"..."}
  ],
  "pagination": {"limit":10,"offset":0,"returned":1}
}
```

2) Teacher BFF batch detail via gateway:

```
GET /bff/v1/teacher/batches/abcd-1234
Headers: Authorization: Bearer <jwt>, X-User-ID: teacher_123

Response 200 (BatchDetailV1)
{
  "batch_id":"abcd-1234",
  "overall_status":"processing",
  "essays": [ {"essay_id":"...","filename":"...","last_updated":"..."} ],
  "created_at":"...",
  "last_updated":"..."
}
```

## Streaming Notes (Where BFF fits)

- The WebSocket service already consumes teacher notification events from Kafka and publishes to Redis channels. See `services/websocket_service/implementations/notification_event_consumer.py`.
- A BFF can optionally publish small diffs to Redis (e.g., batch status changes) using the same Redis client interfaces in `huleedu_service_libs.protocols` (evidence exists). This is an enhancement, not required for MVP because WS push is already implemented for notifications.

## Responsibilities Recap

- BFF (per role): composition, role‑specific DTOs, fine‑grained authZ, minimal policy, optional Redis diffs.
- API Gateway: authN, CORS, coarse rate limit, correlation IDs, thin proxy to BFFs/services.
- Domain Services (CMS, RAS, etc.): business logic, persistence, events; no UI‑specific response shaping.

## Common Pitfalls (and Repo‑specific Tips)

- Don’t put composition logic in the gateway; keep it in the BFF.
- Only include DTO fields backed by actual upstream data (verify endpoints and model fields).
- Propagate `X-User-ID` and `X-Correlation-ID` in all inter‑service calls (patterns exist across services).
- Use `httpx.AsyncClient` with timeouts and per‑service circuit breakers (see resilience rules under `.cursor/rules/`).
- Reuse error mapping utilities from `huleedu_service_libs.error_handling` for consistency.
