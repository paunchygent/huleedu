# Backend-For-Frontend (BFF) Pattern — Adoption & Rollout Plan

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
  - `pdm run lint` (Ruff)

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

