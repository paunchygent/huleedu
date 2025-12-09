---
id: 'bff-teacher-api-contract-validation'
title: 'BFF Teacher API Contract Validation'
type: 'task'
status: 'blocked'
priority: 'medium'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-09'
last_updated: '2025-12-09'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-teacher-dashboard-endpoint"]
labels: ["openapi", "contract-testing", "typescript"]
---
# BFF Teacher API Contract Validation

## Objective

Validate and export API contracts for the BFF Teacher Service to ensure frontend integration readiness.

**Blocked by**: `bff-teacher-dashboard-endpoint`

## Context

Before frontend development begins, we need:
- Validated OpenAPI schema
- TypeScript types for frontend
- Contract tests to prevent breaking changes
- Documentation for API consumers

## Plan

### 1. OpenAPI Schema Export
**Deliverable**: `docs/reference/apis/bff-teacher-openapi.json`

Export and validate schema from running service.

### 2. TypeScript Types Generation
**Deliverable**: `docs/reference/apis/bff-teacher-types.ts`

Generate types using `openapi-typescript` or similar tool.

### 3. Contract Tests
**File**: `services/bff_teacher_service/tests/contract/test_dto_contracts.py` (CREATE)

Validate DTO schemas, required fields, enum values.

### 4. Service README Update
**File**: `services/bff_teacher_service/README.md` (UPDATE)

Document endpoints, env vars, testing commands.

### 5. Correlation ID Validation

Verify correlation ID propagates through BFF to backend services.

## Success Criteria

- [ ] OpenAPI schema exported and valid
- [ ] TypeScript types generated without errors
- [ ] Contract tests validate all DTOs
- [ ] README documents all endpoints
- [ ] Correlation ID propagates correctly
- [ ] Frontend team can consume types

## Related

- Programme Hub: `TASKS/programs/teacher-dashboard-integration/HUB.md`
- Blocked by: `bff-teacher-dashboard-endpoint`
- Frontend plan: `frontend/TASKS/integration/bff-service-implementation-plan.md`
