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
last_updated: "2025-12-09"
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
| BFF Service Clients | `bff-teacher-service-internal-clients.md` | 🔓 Ready | - |
| BFF Dashboard Endpoint | `bff-teacher-dashboard-endpoint.md` | 🔒 Blocked | Service clients |
| API Contract Validation | `bff-teacher-api-contract-validation.md` | 🔒 Blocked | Dashboard endpoint |

_Last refresh: 2025-12-09_

## 2. Active Workstreams

### Phase 0 (Prerequisite): CMS Internal Endpoint ✅
**Task**: `cms-batch-class-info-internal-endpoint.md` (COMPLETED 2025-12-09)

Endpoint: `GET /internal/v1/batches/class-info?batch_ids=<uuid1>,<uuid2>,...`

**Implementation**:
- Query: `SELECT DISTINCT batch_id, class_id, class_name FROM essay_student_associations JOIN user_classes...`
- Response: `{batch_id: {class_id: uuid, class_name: str} | null}`
- Auth: `X-Internal-API-Key` + `X-Service-ID` via `before_request` hook
- Tests: 9 unit tests in `test_batch_class_info.py`

### Phase 1: BFF Service Clients
**Task**: `bff-teacher-service-internal-clients.md`

Implement RAS and CMS HTTP clients with Dishka DI:
- `RASClient`: `get_batches_for_user()`, `get_batch_status()`
- `CMSClient`: `get_batch_class_info()`

### Phase 2: BFF Dashboard Endpoint
**Task**: `bff-teacher-dashboard-endpoint.md`

Implement `GET /v1/teacher/dashboard`:
1. Get batches from RAS
2. Get batch→class mapping from CMS
3. Merge into `TeacherDashboardResponseV1`

### Phase 3: API Contract Validation
**Task**: `bff-teacher-api-contract-validation.md`

Validate and export API contracts:
- OpenAPI schema generation
- TypeScript types for frontend
- Contract tests for DTOs

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
pdm run pytest-root services/bff_teacher_service/tests/ -v
pdm run pytest-root services/class_management_service/tests/unit/test_batch_class_info.py -v
pdm run typecheck-all
```

## 4. Decisions & Risks

| Date | Decision | Source |
| --- | --- | --- |
| 2025-12-09 | Batch→Class lookup via CMS internal endpoint (not RAS `assignment_id`) | Research report |
| 2025-12-09 | `assignment_id` links to assessment instructions, NOT classes | Domain model correction |
| 2025-12-08 | BFF pattern adopted over Gateway aggregation | ADR-0007 |

**Current Risks**:
- ~~CMS internal endpoint blocks all downstream work~~ (RESOLVED 2025-12-09)
- RAS endpoint response structure needs integration test validation

## 5. Upcoming Milestones

| Target Date | Milestone | Blocking Items |
| --- | --- | --- |
| ~~2025-12-10~~ | ✅ CMS endpoint implemented + tested | - |
| 2025-12-12 | BFF clients + DI setup complete | - |
| 2025-12-13 | Dashboard endpoint working | Service clients |
| 2025-12-16 | API contracts validated + exported | Dashboard endpoint |

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

- **2025-12-09** – CMS internal endpoint completed: `GET /internal/v1/batches/class-info` with auth hook, 9 unit tests.
- **2025-12-09** – Hub created from research report; initial tasks defined.
