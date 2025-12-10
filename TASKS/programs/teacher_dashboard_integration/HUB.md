---
id: "teacher-dashboard-integration-hub"
title: "Teacher Dashboard Integration Programme Hub"
type: "programme"
status: "in_progress"
priority: "high"
domain: "programs"
service: "bff_teacher_service"
owner_team: "frontend"
owner: ""
program: "teacher_dashboard_integration"
created: "2025-12-09"
last_updated: "2025-12-10"
related:
  - "frontend/TASKS/integration/bff-service-implementation-plan.md"
  - "docs/decisions/0007-bff-vs-api-gateway-pattern.md"
  - "docs/product/epics/teacher-dashboard-epic.md"
labels: ["bff", "frontend-integration", "teacher-dashboard"]
---
**Purpose**: Coordinate Teacher BFF integration work across CMS, RAS, and BFF services. Serves as template for future service integrations (AI Feedback, NLP).

## 1. Programme Snapshot

| Workstream | Task File | Status | Blocking Items |
| --- | --- | --- | --- |
| CMS Internal Endpoint | `cms-batch-class-info-internal-endpoint.md` | ✅ Completed | - |
| BFF Service Clients | `bff-teacher-service-internal-clients.md` | ✅ Completed (func tests validated) | - |
| BFF Dashboard Endpoint | `bff-teacher-dashboard-endpoint.md` | ✅ Completed (pagination, status filter) | - |
| API Contract Validation | `bff-teacher-api-contract-validation.md` | ✅ Completed (23 contract tests) | - |

_Last refresh: 2025-12-10 (session 8)_

## 2. Active Workstreams

### Phase 0 (Prerequisite): CMS Internal Endpoint ✅
**Task**: `cms-batch-class-info-internal-endpoint.md` (COMPLETED 2025-12-09)

Endpoint: `GET /internal/v1/batches/class-info?batch_ids=<uuid1>,<uuid2>,...`

**Implementation**:
- Query: `SELECT DISTINCT batch_id, class_id, class_name FROM essay_student_associations JOIN user_classes...`
- Response: `{batch_id: {class_id: uuid, class_name: str} | null}`
- Auth: `X-Internal-API-Key` + `X-Service-ID` via `before_request` hook
- Tests: 9 unit tests in `test_batch_class_info.py`

### Phase 1: BFF Service Clients ✅
**Task**: `bff-teacher-service-internal-clients.md` (COMPLETED 2025-12-10)

Implemented RAS and CMS HTTP clients with Dishka DI:

**Files created**:
- `protocols.py`: RASClientProtocol, CMSClientProtocol
- `clients/ras_client.py`: RASClientImpl with `get_batches_for_user()`
- `clients/cms_client.py`: CMSClientImpl with `get_class_info_for_batches()`
- `clients/_utils.py`: Shared auth header builder
- `di.py`: BFFTeacherProvider, RequestContextProvider
- `middleware.py`: CorrelationIDMiddleware (extracted)

**Tests**: 19 unit tests + 4 functional tests passing

**Functional tests validated (2025-12-10)**:
```bash
ALLOW_REAL_LLM_FUNCTIONAL=1 pdm run pytest-root tests/functional/test_bff_teacher_dashboard_functional.py -v
# 4/4 passed
```

### Phase 2: BFF Dashboard Endpoint ✅
**Task**: `bff-teacher-dashboard-endpoint.md` (COMPLETED 2025-12-10)

Full implementation with pagination and status filtering:
- `limit` (1-100, default 20), `offset` (default 0) query params
- `status` filter with client-friendly values (7 valid statuses)
- Invalid status returns 400 validation error
- Response includes `total_count`, `limit`, `offset` metadata
- 35 unit tests (17 edge cases + 8 core + 10 client tests)

### Phase 3: API Contract Validation ✅
**Task**: `bff-teacher-api-contract-validation.md` (COMPLETED 2025-12-10)

Validated and exported API contracts:
- OpenAPI schema: `docs/reference/apis/bff-teacher-openapi.json`
- TypeScript types: `docs/reference/apis/bff-teacher-types.ts`
- Contract tests: 23 tests in `services/bff_teacher_service/tests/contract/`
- PDM script: `bff-openapi` for schema regeneration

## 3. Key Artifacts & Commands

**Research Report** (archived):
- `.claude/archive/reports/teacher-dashboard-endpoint-implementation-plan-2025-12-09.md`

**Services**:
- BFF: `services/bff_teacher_service/`
- CMS: `services/class_management_service/`
- RAS: `services/result_aggregator_service/`

**Implementation Plan**:
- `frontend/TASKS/integration/bff-service-implementation-plan.md`

**Tests**:
```bash
pdm run pytest-root services/bff_teacher_service/tests/ -v  # 18 tests
pdm run pytest-root services/class_management_service/tests/unit/test_batch_class_info.py -v
pdm run typecheck-all
```

## 4. Decisions & Risks

| Date | Decision | Source |
| --- | --- | --- |
| 2025-12-10 | External service errors return 502 Bad Gateway | Error handling pattern |
| 2025-12-09 | Batch→Class lookup via CMS internal endpoint (not RAS `assignment_id`) | Research report |
| 2025-12-09 | `assignment_id` links to assessment instructions, NOT classes | Domain model correction |
| 2025-12-08 | BFF pattern adopted over Gateway aggregation | ADR-0007 |

**Current Risks**:
- ~~CMS internal endpoint blocks all downstream work~~ (RESOLVED 2025-12-09)
- ~~Service clients block dashboard endpoint~~ (RESOLVED 2025-12-10)
- ~~RAS endpoint response structure needs integration test validation~~ (RESOLVED 2025-12-10 - functional tests pass)

## 5. Upcoming Milestones

| Target Date | Milestone | Blocking Items |
| --- | --- | --- |
| ~~2025-12-10~~ | ✅ CMS endpoint implemented + tested | - |
| ~~2025-12-12~~ | ✅ BFF clients + DI setup complete | - |
| ~~2025-12-13~~ | ✅ Dashboard endpoint polished (pagination, status filter) | - |
| ~~2025-12-16~~ | ✅ API contracts validated + exported | - |

## 6. Future Service Integration Template

This programme establishes patterns for future BFF integrations:

1. **Research Phase**: Analyze target service APIs, identify missing endpoints
2. **Prerequisite Phase**: Implement missing internal endpoints
3. **Client Phase**: Create service clients with protocols + DI
4. **Aggregation Phase**: Build BFF endpoints with DTOs
5. **Validation Phase**: Contract tests, OpenAPI export, TypeScript types

**Applicable to**:
- AI Feedback Service integration
- NLP Service AES integration
- Admin BFF integration

## 7. Change Log

- **2025-12-10 (session 8)** – Phase 3 completed: API contract validation. OpenAPI schema exported, TypeScript types created, 23 contract tests added. Programme COMPLETE.
- **2025-12-10 (session 2)** – Functional tests validated (4/4 pass). Fixed BFF startup issue (`response_model=None` for union return types). Fixed RAS `ALLOWED_SERVICE_IDS` env var (prefix mismatch).
- **2025-12-10** – Phase 1 completed: RAS/CMS clients with Dishka DI, 19 unit tests, middleware extraction.
- **2025-12-09** – CMS internal endpoint completed: `GET /internal/v1/batches/class-info` with auth hook, 9 unit tests.
- **2025-12-09** – Hub created from research report; initial tasks defined.
