---
type: research
id: RES-bff-vue-3-frontend-integration-design
title: "Designing a BFF Layer for Vue 3 Frontend Integration (Research)"
status: active
created: 2025-11-24
source: TASKS/frontend/bff-vue-3-frontend-integration-design.md
last_updated: 2025-11-24
---

# Designing a BFF Layer for Vue 3 Frontend Integration (Research)

This document is the research/architecture companion to `TASKS/frontend/bff-vue-3-frontend-integration-design.md`. It summarizes the key design decisions for introducing per-role Backend-for-Frontend (BFF) services to support a Vue 3 teacher/admin dashboard, and is the reference point for implementation tasks such as `TASKS/frontend/bff-service-implementation-plan.md`.

## 1. Goals and Scope

- **Primary goal**
  - Provide a thin, role-specific BFF layer between the Vue 3 SPA and the existing event-driven backend (API Gateway, RAS, CMS, Content, File, WebSocket service).
- **Scope**
  - Teacher and Admin BFFs as separate services.
  - Screen-specific DTOs tailored to Vue components.
  - Composition over multiple backend services with minimal round-trips.
  - Integration with existing OpenAPI → TypeScript pipeline.
  - Real-time updates via Redis + WebSocket service.

## 2. BFF Topology and Service Ownership

- **Per-role BFFs (recommended)**
  - `bff-teacher`: teacher UI surfaces (initially 4 screens).
  - `bff-admin`: admin UI surfaces (initially 2 screens).
  - Future: `bff-student` or others can follow the same pattern.
- **Why not a single BFF**
  - Avoids mixing teacher and admin concerns in one codebase.
  - Cleaner security and ownership boundaries.
  - Independent scaling and deployment for teacher vs admin traffic.
- **Service structure (per BFF)**
  - `app.py`: FastAPI app, CORS, tracing, error handling.
  - `api/v1/...`: versioned HTTP routes (e.g. `/v1/teacher/...`).
  - `dto/`: Pydantic DTOs for screen-specific responses.
  - `clients/`: HTTP clients for CMS, RAS, File, Content, Identity.
  - `streaming/`: optional Kafka/Redis modules for view-model events.

## 3. Screen-Specific DTO Contracts (Teacher BFF)

Each teacher screen has a dedicated DTO and endpoint:

- **Class Dashboard DTO – `TeacherClassDashboardV1`**
  - Endpoint: `GET /bff/v1/teacher/dashboard`.
  - Contents: list of batch summaries (batch id, class id/name, status, progress, counts, timestamps, pipeline).
  - Data sources: RAS (batches per teacher), CMS (class metadata).

- **Batch Detail DTO – `TeacherBatchDetailV1`**
  - Endpoint: `GET /bff/v1/teacher/batches/{batch_id}`.
  - Contents: batch-level metadata plus an array of essay statuses (id, filename, processing status, scores, timing, etc.).
  - Data source: primarily RAS batch status (possibly enriched with CMS for class names).

- **Essay Feedback DTO – `TeacherEssayFeedbackV1`**
  - Endpoint: `GET /bff/v1/teacher/batches/{batch_id}/essays/{essay_id}`.
  - Contents: single essay’s content, scores, spellcheck results, AI feedback, status, timestamps.
  - Data sources: RAS (analysis / grades / AI feedback), Content Service (essay text). Optionally backed by a dedicated RAS essay endpoint.

- **Student Associations DTO – `StudentAssociationListV1`**
  - Endpoint: `GET /bff/v1/teacher/batches/{batch_id}/associations`.
  - Contents: list of student–batch associations (student id/name, essay/file linkage, confirmed flag, class id).
  - Data source: CMS association endpoints.

- **Admin DTOs (sketched)**
  - Pending Users DTO: list of users awaiting approval.
  - System Settings DTO: configuration surface for platform-level settings.

### DTO Definition & Ownership

- DTOs are **owned by the BFF services** and defined in their `dto/` modules (e.g. `services/bff_teacher_service/dto/teacher_v1.py`).
- BFFs are the single source of truth for their own HTTP contracts.
- Backend services (RAS, CMS, etc.) remain owner of their internal/domain models.

### Versioning Strategy

- URL path versioning: `/bff/v1/teacher/...`, `/bff/v1/admin/...`.
- DTO class naming: suffix with `V1`, `V2`, etc.
- Non-breaking additions stay within `v1`; breaking changes require a new version path and DTOs.

## 4. Backend-to-BFF Communication Patterns

- **Request flow**
  - Production: Vue → API Gateway (JWT validation, rate limiting, CORS) → BFF.
  - BFF responds with DTO JSON; Gateway forwards transparently.
- **Dev mode**
  - Optionally allow direct Vue → BFF calls (bypassing Gateway) with BFF handling CORS and JWT.
- **Internal HTTP calls (BFF → backend services)**
  - Use async HTTP client (e.g. `httpx.AsyncClient`) with base URLs from env.
  - Prefer internal-only endpoints and service-level auth where available (e.g. `X-Internal-API-Key` for RAS `/internal/v1/...`).
  - Pass user context (user id, possibly role) explicitly when backend needs it.

### RAS vs direct composition

- Prefer **RAS** as a read-optimized aggregator:
  - Example: `GET /internal/v1/batches/user/{user_id}` for dashboard.
  - Example: `GET /internal/v1/batches/{batch_id}/status` for batch detail.
- When RAS doesn’t yet provide a suitable endpoint:
  - Either extend RAS (preferred medium-term), or
  - Temporarily over-fetch and filter within BFF.
- BFF remains a **thin composition layer**, not a second RAS.

### Error handling and mapping

- Use `huleedu_service_libs` error handlers and `ErrorCode` enums from `common_core`.
- Map downstream failures to structured error responses, e.g.:
  - RAS 404 → `RESOURCE_NOT_FOUND`.
  - Downstream 5xx or timeouts → `EXTERNAL_SERVICE_ERROR`.
- Correlation IDs from the Gateway are propagated and logged for tracing.

## 5. Real-Time Updates and Vue Integration

- **WebSocket service**
  - Existing FastAPI WebSocket service using Redis Pub/Sub.
  - Clients connect with JWT as query param; service subscribes to `user:{user_id}:events` channels.

- **BFF’s role**
  - Publish **view-model events** (e.g. `BATCH_UPDATED`, `ESSAY_UPDATED`) to Redis when relevant state changes.
  - Alternatively, subscribe to domain events (Kafka) and re-publish to Redis with frontend-focused payloads.

- **Payload strategy**
  - Prefer **deltas** (minimal updates) over full snapshots.
  - Events can:
    - Directly update Vue Query caches (e.g. dashboard/batch detail data), or
    - Trigger refetches when changes are complex.

- **Vue integration patterns**
  - Use a composable or Pinia store (e.g. `useWebSocket`) to:
    - Maintain a WebSocket connection (with reconnect/backoff).
    - Dispatch incoming events into Vue Query cache updates or Pinia state.
    - Optionally expose connection state for UX feedback ("Live updates disconnected").

## 6. Caching and Performance Strategy

- **Client-side (Vue Query)**
  - Cache DTO responses per query key (e.g. `['teacherDashboard']`, `['batchDetail', batchId]`).
  - Use modest cache TTLs (tens of seconds–minutes) tuned per screen.
  - Combine with WebSocket events for near real-time UX.

- **Server-side (BFF)**
  - Optional short-lived caches per user/batch for expensive aggregations.
  - Start with in-memory caching; move to Redis if multiple replicas or higher scale.
  - Use timeouts and circuit-breaker patterns for downstream calls to avoid cascading failures.

## 7. Relationship to Implementation Tasks

- **Primary driving tasks**
  - `TASKS/frontend/bff-vue-3-frontend-integration-design.md` – full narrative design (this doc’s source).
  - `TASKS/frontend/bff-service-implementation-plan.md` – concrete implementation plan for `bff_teacher_service` following this design.

- **Intended usage**
  - Architecture/design reviews should reference this document and the underlying TASKS spec.
  - Implementation work should be tracked via TASKS files and mapped back here via `related` fields.

Future work may promote parts of this research into a more formal architecture document under `docs/architecture/` once the design is validated in production.
