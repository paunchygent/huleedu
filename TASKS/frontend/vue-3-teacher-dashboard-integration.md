---
id: 'vue-3-teacher-dashboard-integration'
title: 'Vue 3 Teacher Dashboard Integration'
type: 'story'
status: 'research'
priority: 'high'
domain: 'frontend'
service: 'bff_teacher_service'
owner_team: 'frontend'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-10'
last_updated: '2025-12-10'
related: ["teacher-dashboard-integration-hub", "bff-teacher-api-contract-validation", "bff-teacher-dashboard-endpoint", "bff-service-implementation-plan", "ADR-0007"]
labels: ['vue3', 'frontend-integration', 'teacher-dashboard', 'bff']
---
# Vue 3 Teacher Dashboard Integration

## Objective

Integrate the Vue 3 frontend with the BFF Teacher Dashboard endpoint to display batch listings with pagination and status filtering.

## Context

The BFF Teacher Service backend is complete:
- **Endpoint:** `GET /v1/teacher/dashboard` with pagination (`limit`, `offset`) and status filtering
- **OpenAPI schema:** `docs/reference/apis/bff-teacher-openapi.json`
- **TypeScript types:** `docs/reference/apis/bff-teacher-types.ts`
- **Tests:** 58 tests (35 unit + 23 contract) all passing
- **Functional validation:** 4/4 functional tests passing against real services

This story delivers the first end-to-end user-facing feature consuming the BFF pattern.

## Prerequisites

- BFF Teacher Service running: `pdm run dev-start bff_teacher_service`
- API Gateway routing configured (already done)
- User authentication flow working (JWT via API Gateway)

## Plan

### Phase 1: API Client Setup
1. Copy/import TypeScript types from `docs/reference/apis/bff-teacher-types.ts`
2. Create `src/api/teacherApi.ts` with typed fetch wrapper
3. Handle authentication headers (`Authorization: Bearer <token>`)
4. Handle error responses (401, 502, validation errors)

### Phase 2: Dashboard Component
1. Create `src/views/TeacherDashboard.vue`
2. Fetch batches on mount using API client
3. Display batch list with key fields:
   - Batch ID, class name, status, progress
   - Created/updated timestamps
   - Essay counts (total, completed, failed)

### Phase 3: Pagination
1. Add pagination controls (prev/next or page numbers)
2. Wire `limit` and `offset` query params
3. Display total count from response

### Phase 4: Status Filtering
1. Add status filter dropdown
2. Valid statuses: `pending_content`, `ready`, `processing`, `scoring`, `completed`, `failed`, `cancelled`
3. Wire `status` query param

### Phase 5: Polish
1. Loading states
2. Empty states (no batches)
3. Error handling UI
4. Responsive layout

## API Reference

**Endpoint:** `GET /v1/teacher/dashboard`

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 20 | Items per page (1-100) |
| `offset` | int | 0 | Pagination offset |
| `status` | string | - | Filter by status |

**Response:**

```typescript
interface TeacherDashboardResponseV1 {
  batches: BatchSummaryV1[];
  total_count: number;
  limit: number;
  offset: number;
}

interface BatchSummaryV1 {
  batch_id: string;
  class_name: string | null;
  status: string;
  progress_percentage: number;
  total_essays: number;
  completed_essays: number;
  failed_essays: number;
  created_at: string;
  updated_at: string;
}
```

**Error responses:**
- `400` - Invalid status value
- `401` - Missing/invalid authentication
- `502` - Backend service unavailable

## Success Criteria

- [ ] Dashboard displays batch list from BFF endpoint
- [ ] Pagination works (limit/offset)
- [ ] Status filter works
- [ ] Loading and error states handled
- [ ] TypeScript types used (no `any`)
- [ ] Works against running BFF service

## Testing

```bash
# Start BFF service
pdm run dev-start bff_teacher_service

# Start frontend dev server
cd frontend && pnpm dev

# Navigate to dashboard and verify
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `frontend/src/api/teacherApi.ts` | Create - API client |
| `frontend/src/types/teacher.ts` | Create - Copy types |
| `frontend/src/views/TeacherDashboard.vue` | Create - Dashboard view |
| `frontend/src/router/index.ts` | Modify - Add route |

## Related Documentation

- Programme Hub: `TASKS/programs/teacher_dashboard_integration/HUB.md`
- BFF Implementation Plan: `frontend/TASKS/integration/bff-service-implementation-plan.md`
- API Contract Task: `TASKS/programs/teacher_dashboard_integration/bff-teacher-api-contract-validation.md`
- Epic: `docs/product/epics/teacher-dashboard-epic.md`
- ADR: `docs/decisions/0007-bff-vs-api-gateway-pattern.md`
