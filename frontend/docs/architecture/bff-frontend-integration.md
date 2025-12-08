# BFF Frontend Integration Architecture

## Overview

This document defines the architecture for Backend-for-Frontend (BFF) services that bridge the HuleEdu event-driven backend with the Vue 3 teacher/admin dashboards.

It is the normative architecture reference for:

- `bff_teacher_service` (teacher-facing BFF)
- `bff_admin_service` (admin-facing BFF, future)

and is derived from:

- `TASKS/frontend/bff-vue-3-frontend-integration-design.md`
- `docs/research/bff-vue-3-frontend-integration-design.md`

Implementation tasks MUST align with this document.

---

## 1. Goals and Scope

- **Goals**
  - Provide thin, role-specific BFFs between Vue 3 SPA and backend.
  - Expose screen-specific DTOs that match UI needs.
  - Minimize cross-service round-trips by delegating aggregation to RAS where possible.
  - Integrate with existing OpenAPI → TypeScript generation.
  - Support real-time updates via Redis + WebSocket service.

- **In Scope**
  - Teacher BFF (`bff_teacher_service`) for:
    - Class dashboard
    - Batch detail
    - Essay feedback
    - Student associations
  - Admin BFF (`bff_admin_service`, later) for:
    - Pending user approvals
    - System settings

- **Out of Scope**
  - Core domain logic in RAS, CMS, Content, File services.
  - Authentication implementation details in API Gateway.

---

## 2. Service Topology and Ownership

### 2.1 Per-Role BFFs (Required)

- **Teacher BFF (`bff_teacher_service`)**
  - Owns teacher-facing read models (DTOs) and endpoints.
  - Depends on RAS, CMS, Content, File, WebSocket service.

- **Admin BFF (`bff_admin_service`)**
  - Owns admin-facing DTOs and endpoints.
  - Depends on Identity, Config service (future), and others as needed.

**Rationale:**

- Keeps security and domain boundaries clear per role.
- Allows independent scaling and deployment strategies.
- Avoids a monolithic multi-role BFF with complex internal authorization rules.

### 2.2 Service Structure (Per BFF)

Each BFF service MUST follow the standard HuleEdu service layout:

- `app.py` – FastAPI app setup (CORS, tracing, error handling, DI wiring).
- `config.py` – Pydantic settings (ports, downstream URLs, Redis, etc.).
- `di.py` – Dishka providers for settings, HTTP clients, Redis/RedisPubSub, and service-specific clients.
- `api/v1/` – Versioned routes (e.g. `/v1/teacher/...`).
- `dto/` – Pydantic models for screen-specific DTOs.
- `clients/` – HTTP clients for RAS, CMS, Content, File, Identity.
- `streaming/` – Kafka/Redis integration for real-time events (optional in MVP).
- `tests/` – Unit, integration, and contract tests.

---

## 3. Teacher BFF DTO Contracts

Teacher BFF is the reference implementation. It exposes four primary DTOs and endpoints.

### 3.1 Class Dashboard

- **Endpoint**: `GET /bff/v1/teacher/dashboard`
- **DTO**: `TeacherClassDashboardV1`
- **Shape (high-level)**:
  - `batches: list[BatchSummaryV1]`
  - `total_count: int`
- **Data sources**:
  - RAS: `GET /internal/v1/batches/user/{user_id}` – all batches for teacher.
  - CMS: `GET /v1/classes?owner_id={teacher_id}` – enrich with class names.

### 3.2 Batch Detail

- **Endpoint**: `GET /bff/v1/teacher/batches/{batch_id}`
- **DTO**: `TeacherBatchDetailV1`
- **Shape (high-level)**:
  - Batch metadata (status, timestamps, pipeline, class info).
  - `essays: list[EssayStatusV1]` with status, score, spellcheck info, timing.
- **Data source**:
  - Primarily RAS: `GET /internal/v1/batches/{batch_id}/status`.
  - CMS for class name enrichment when `class_id` is present.

### 3.3 Essay Feedback

- **Endpoint**: `GET /bff/v1/teacher/batches/{batch_id}/essays/{essay_id}`
- **DTO**: `TeacherEssayFeedbackV1`
- **Data sources**:
  - RAS: essay-level scores, AI feedback, processing status.
  - Content Service: essay text (via storage reference).
- **Implementation note**:
  - Preferred: dedicated RAS endpoint to fetch single-essay details.
  - Acceptable MVP: fetch batch details and filter in BFF.

### 3.4 Student Associations

- **Endpoint**: `GET /bff/v1/teacher/batches/{batch_id}/associations`
- **DTO**: `StudentAssociationListV1`
- **Data source**:
  - CMS: association endpoints (batch ↔ student ↔ essay/file).

### 3.5 Versioning

- URL paths MUST be versioned: `/bff/v1/teacher/...`.
- DTO class names MUST carry version suffixes (`...V1`, `...V2`, ...).
- Breaking changes require new URL + DTO versions; non-breaking additions stay within `v1`.

---

## 4. Backend-to-BFF Communication Patterns

### 4.1 Request Flow

- **Production**:
  - Vue SPA → API Gateway (JWT, rate limiting, CORS) → BFF.
  - Gateway forwards request and response transparently for `/bff/v1/...` routes.

- **Development (optional)**:
  - Vue SPA → BFF directly for faster iteration.
  - In this mode, BFF MUST:
    - Configure CORS for dev origins.
    - Validate JWT using shared libs where necessary.

### 4.2 Internal HTTP Calls (BFF → Services)

- Use `httpx.AsyncClient` with DI-managed lifetime.
- Downstream URLs configured via BFF settings (`*_BASE_URL`).
- Prefer internal, service-authenticated endpoints where available, e.g.:
  - RAS internal endpoints require `X-Internal-API-Key` + `X-Service-ID`.
- Pass user identity explicitly (user id, role) when needed for authorization or filtering.

### 4.3 RAS vs Direct Composition

- Prefer RAS as the primary read-optimized aggregator for assessment results.
- BFF SHOULD:
  - Call RAS for batches and essay results.
  - Only fall back to multi-service composition where RAS does not expose a suitable endpoint.
- If BFF must call multiple services per screen (e.g. RAS + CMS), it SHOULD:
  - Perform calls in parallel with `asyncio.gather`.
  - Consider backend improvements (new RAS endpoints) where composition becomes complex.

### 4.4 Error Handling

- BFF MUST use `huleedu_service_libs` structured error handling:
  - Raise `HuleEduError` with `ErrorCode` from `common_core`.
  - Map downstream 404 to `RESOURCE_NOT_FOUND`.
  - Map downstream 5xx/timeouts to `EXTERNAL_SERVICE_ERROR` (or similar).
- Correlation IDs from Gateway MUST be propagated and logged for tracing.

---

## 5. Authentication and Authorization Responsibilities

- **Gateway**
  - Primary JWT validator for external clients.
  - Enforces auth, rate limiting, and CORS for `/bff/v1/...`.

- **BFF**
  - Trusts authenticated requests from Gateway in production.
  - MAY perform additional validation when called directly in dev.
  - MUST enforce authorization semantics such as:
    - Teacher can only access their own batches/classes.

JWT verification logic should be implemented once in Gateway and shared libraries, with BFF reusing those helpers only when necessary for direct dev access.

---

## 6. Real-Time Updates

### 6.1 WebSocket Backplane

- WebSocket service uses Redis Pub/Sub for real-time notifications.
- Authenticated clients connect with JWT and subscribe to user-specific channels.

### 6.2 BFF Role in Notifications

- BFF MAY publish **view-model events** when relevant state changes:
  - e.g. `BATCH_UPDATED`, `ESSAY_UPDATED` events containing enough data for UI patching.
- Implementation MUST use the shared `RedisPubSub` helper from `huleedu_service_libs`:
  - Async client: `redis.asyncio.Redis`.
  - Channel naming via `RedisPubSub.get_user_channel(user_id)` to stay consistent with WebSocket service.
  - High-level publishing via `publish_user_notification`.

### 6.3 Frontend Consumption

- Vue app maintains a WebSocket connection (via composable/Pinia store).
- Incoming events SHOULD:
  - Update Vue Query caches for dashboard/batch detail.
  - Or trigger query invalidation for complex changes.
- On reconnect, client SHOULD refetch critical queries to recover from missed events.

---

## 7. Caching and Performance

### 7.1 Client-Side (Vue Query)

- Use query keys per view (e.g. `['teacherDashboard']`, `['batchDetail', batchId]`).
- Tune cache times per screen; combine with real-time events.

### 7.2 Server-Side (BFF)

- Optional short-lived caches per user/batch for expensive aggregations.
- Start with in-memory cache; move to Redis if horizontal scaling demands shared state.
- Use timeouts and circuit breakers on downstream calls to avoid cascading failures.

---

## 8. Relationships to Tasks and Implementations

- **Design & Architecture Sources**
  - `TASKS/frontend/bff-vue-3-frontend-integration-design.md` (full design doc).
  - `docs/research/bff-vue-3-frontend-integration-design.md` (research summary).

- **Primary Implementation Plan**
  - `TASKS/frontend/bff-service-implementation-plan.md` – implementation of `bff_teacher_service` aligned with this architecture.

Any new BFF-related tasks MUST reference this file in their `related` frontmatter or inline links.
