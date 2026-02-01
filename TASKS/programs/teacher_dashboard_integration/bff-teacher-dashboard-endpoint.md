---
id: bff-teacher-dashboard-endpoint
title: BFF Teacher Dashboard Endpoint
type: task
status: done
priority: high
domain: programs
service: bff_teacher_service
owner_team: agents
owner: ''
program: teacher_dashboard_integration
created: '2025-12-09'
last_updated: '2026-02-01'
related:
- TASKS/programs/teacher_dashboard_integration/HUB.md
- bff-teacher-service-internal-clients
labels:
- bff
- dashboard
- aggregation
---
# BFF Teacher Dashboard Endpoint

## Objective

Polish and validate `GET /bff/v1/teacher/dashboard` endpoint that aggregates batch data from RAS with class info from CMS.

**Blocked by**: `bff-teacher-service-internal-clients` ✅ (completed)

## Context

The Teacher Dashboard displays a list of batches with status and class names. This requires:
1. Fetching batch list from RAS
2. Looking up class info from CMS via batch_id
3. Merging into screen-optimized DTO

## Completion Summary (2025-12-10)

### Phase 1 (Completed)
- Basic dashboard endpoint with RAS/CMS integration
- Dishka DI for internal HTTP clients
- Error handling with 502 for backend failures
- 4/4 functional tests passing

### Phase 2 (Completed)
**Pagination Support**:
- Added `limit` (1-100, default 20), `offset` (default 0) query params
- Response includes `total_count`, `limit`, `offset` metadata
- Fixed RAS `count_user_batches()` method for accurate pagination totals

**Status Filtering**:
- Added `status` query param with client-friendly values
- Validation returns 400 for invalid status values
- Client→internal status mapping for RAS filtering:
  - `pending_content` → `awaiting_content_validation`, `awaiting_pipeline_configuration`
  - `ready` → `ready_for_pipeline_execution`
  - `processing` → `processing_pipelines`, `awaiting_student_validation`, etc.
  - `completed_successfully` → `completed_successfully`
  - `completed_with_failures` → `completed_with_failures`
  - `failed` → `content_ingestion_failed`, `failed_critically`
  - `cancelled` → `cancelled`

**Test Coverage**:
- `test_dashboard_edge_cases.py` (17 tests) - pagination boundaries, status filtering, edge cases
- `test_teacher_routes.py` (8 tests) - core functionality, error handling
- `test_cms_client.py`, `test_ras_client.py` - client tests
- Total: 35 unit tests passing

### Files Modified
- `services/bff_teacher_service/api/v1/teacher_routes.py` - Query params, status mapping, validation
- `services/bff_teacher_service/dto/teacher_v1.py` - Pagination metadata in response
- `services/result_aggregator_service/protocols.py` - Added `count_user_batches()`
- `services/result_aggregator_service/implementations/*` - Count implementation
- `services/result_aggregator_service/api/query_routes.py` - Use count for total

## Success Criteria

- [x] Dashboard returns batches with class names
- [x] Handles batches without class associations (null, not error)
- [x] Proper error responses for service failures
- [x] Functional tests pass (4/4)
- [x] `pdm run typecheck-all` passes
- [x] Edge case unit tests added (17 tests)
- [x] Pagination with limit/offset query params
- [x] Status filtering with validation

## Related

- Programme Hub: `TASKS/programs/teacher-dashboard-integration/HUB.md`
- Blocked by: `bff-teacher-service-internal-clients`
- Blocks: `bff-teacher-api-contract-validation`
