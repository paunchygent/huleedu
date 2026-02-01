---
id: bff-dashboard-service-implementation
title: BFF Dashboard Service Implementation
type: task
status: done
priority: medium
domain: integration
service: frontend
owner_team: frontend
owner: ''
program: teacher_dashboard_integration
created: 2025-12-09
last_updated: '2026-02-01'
related:
- frontend/TASKS/integration/bff-vue-3-frontend-integration-design.md
- frontend/src/schemas/teacher-dashboard.ts
- frontend/src/lib/api-client.ts
labels:
- frontend
- bff
- integration
---

# BFF Dashboard Service Implementation

## Objective
Implement the frontend service layer for the Teacher Dashboard, bridging the Vue application with the BFF `GET /v1/teacher/dashboard` endpoint. This service will enforce runtime type safety using Zod schemas.

## Context
- **Design**: `bff-vue-3-frontend-integration-design.md` specifies a BFF pattern with screen-specific DTOs.
- **Backend**: The BFF endpoint is currently a stub returning mock data.
- **Validation**: Zod schemas have been created in `frontend/src/schemas/teacher-dashboard.ts`.
- **Client**: `frontend/src/lib/api-client.ts` has been updated to support `requestWithValidation`.

## Implementation Plan

1. **Create Service Module**: `frontend/src/services/teacher-dashboard.ts`
    - Import `apiClient` and Zod schemas.
    - Export `fetchTeacherDashboard` async function.
    - Use `apiClient.getWithValidation` to fetch and validate data.

2. **Define Types**:
    - Ensure types exported from `src/schemas/teacher-dashboard.ts` are correctly used.

3. **Error Handling**:
    - Service lets API/Zod errors bubble up (to be handled by Vue Query/Component).

## Verification
- **Unit Test**: Created `frontend/src/services/teacher-dashboard.spec.ts`.
- **Result**: `pnpm test` passed, confirming `apiClient.getWithValidation` is called with the correct schema and endpoint.
