---
id: 'bff-teacher-dashboard-endpoint'
title: 'BFF Teacher Dashboard Endpoint'
type: 'task'
status: 'blocked'
priority: 'high'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-09'
last_updated: '2025-12-09'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-teacher-service-internal-clients"]
labels: ["bff", "dashboard", "aggregation"]
---
# BFF Teacher Dashboard Endpoint

## Objective

Implement `GET /v1/teacher/dashboard` endpoint that aggregates batch data from RAS with class info from CMS.

**Blocked by**: `bff-teacher-service-internal-clients`

## Context

The Teacher Dashboard displays a list of batches with status and class names. This requires:
1. Fetching batch list from RAS
2. Looking up class info from CMS via batch_id
3. Merging into screen-optimized DTO

## Plan

### 1. Update DTOs
**File**: `services/bff_teacher_service/dto/teacher_v1.py` (UPDATE)

- `BatchSummaryV1`: batch_id, class_id, class_name, status, essay counts, timestamps
- `TeacherDashboardResponseV1`: list of BatchSummaryV1, total_count

### 2. Implement Dashboard Endpoint
**File**: `services/bff_teacher_service/api/v1/teacher_routes.py` (UPDATE)

Flow:
1. Get batches from RAS (`get_batches_for_user`)
2. Get batch→class mapping from CMS (`get_batch_class_info`)
3. Transform to DTOs with class info merged

### 3. Register DI in App
**File**: `services/bff_teacher_service/app.py` (UPDATE)

Setup Dishka container with BFFTeacherProvider.

### 4. Unit Tests
**File**: `services/bff_teacher_service/tests/unit/test_dashboard_endpoint.py` (CREATE)

Test cases:
- Returns batches with class names
- Handles empty batch list
- Handles batches without class associations (null values)
- Error handling for service failures

## Success Criteria

- [ ] Dashboard returns batches with class names
- [ ] Handles batches without class associations (null, not error)
- [ ] Proper error responses for service failures
- [ ] Unit tests pass
- [ ] `pdm run typecheck-all` passes

## Related

- Programme Hub: `TASKS/programs/teacher-dashboard-integration/HUB.md`
- Blocked by: `bff-teacher-service-internal-clients`
- Blocks: `bff-teacher-api-contract-validation`
