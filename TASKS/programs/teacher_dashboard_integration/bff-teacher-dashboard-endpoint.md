---
id: 'bff-teacher-dashboard-endpoint'
title: 'BFF Teacher Dashboard Endpoint'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-09'
last_updated: '2025-12-10'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-teacher-service-internal-clients"]
labels: ["bff", "dashboard", "aggregation"]
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

## Current State (2025-12-10)

**Basic implementation complete** in Phase 1:
- `services/bff_teacher_service/api/v1/teacher_routes.py` - Dashboard endpoint
- `services/bff_teacher_service/dto/teacher_v1.py` - DTOs
- Functional tests passing (4/4)

**This phase focuses on**: Edge case handling, pagination, additional unit tests.

## Remaining Work

### 1. Edge Case Unit Tests
**File**: `services/bff_teacher_service/tests/unit/test_dashboard_edge_cases.py` (CREATE)

Test cases:
- Large batch lists (pagination boundary)
- Batches without class associations (CMS returns null)
- Partial CMS failures (some batches have class info, others don't)
- RAS returns empty list for new user

### 2. Pagination Support
- Review if current implementation handles pagination correctly
- Add offset/limit query params to dashboard endpoint if needed

### 3. Status Filtering
- Add optional `status` query param for filtering batches

## Success Criteria

- [x] Dashboard returns batches with class names
- [x] Handles batches without class associations (null, not error)
- [x] Proper error responses for service failures
- [x] Functional tests pass (4/4)
- [x] `pdm run typecheck-all` passes
- [ ] Edge case unit tests added
- [ ] Pagination documented/tested

## Related

- Programme Hub: `TASKS/programs/teacher-dashboard-integration/HUB.md`
- Blocked by: `bff-teacher-service-internal-clients`
- Blocks: `bff-teacher-api-contract-validation`
