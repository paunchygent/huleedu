---
id: 'vue-3-teacher-dashboard-integration'
title: 'Vue 3 Teacher Dashboard Integration'
type: 'story'
status: 'in_progress'
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

## Implementation Status

### Completed (2025-12-10)

**Approach:** Extended existing schema/service patterns instead of creating new `src/api/` and `src/types/` directories.

| Step | Status | Details |
|------|--------|---------|
| Schema extension | Done | Added `limit`, `offset` to `TeacherDashboardResponseSchema` |
| Service extension | Done | Added `TeacherDashboardParams` interface with query string building |
| Service tests | Done | 5 tests covering no params, pagination, status filter, combined params |
| View component | Done | Created `TeacherDashboardView.vue` with brutalist styling |
| Router | Done | Added `/app/inlamningar` route |
| Navigation | Done | Added "Inlamningar" nav link to `AppLayout.vue` |
| Type check | Pass | `pnpm type-check` passes |
| Unit tests | Pass | 5/5 tests pass |

### Remaining

- [x] Manual testing against running BFF service
- [x] End-to-end verification (dev login → dashboard → data fetch working)
- [ ] **Design polish (next session)** - current Vue component is a functional stub only

### Design Debt Note

**IMPORTANT:** The current `TeacherDashboardView.vue` is NOT a design reference. It is a functional stub proving e2e connectivity only. The design has:
- Correct colors and fonts
- Incorrect layout, information hierarchy, and UX patterns

**Do NOT use current `.vue` files as design patterns.**

**Design references for next session:**
1. **`frontend/styles/src/dashboard_brutalist_final.html`** - **CANONICAL DASHBOARD PROTOTYPE** (use this!)
2. `frontend/styles/src/huleedu-landing-final.html` - landing page prototype
3. `frontend/docs/product/epics/design-spec-teacher-dashboard.md` - UX specification
4. `frontend/docs/product/epics/design-system-epic.md` - general design principles
5. `frontend/docs/FRONTEND.md` - "Purist, fast, semantic" philosophy

**Key design principles (from user):**
- Dashboard is a **hub**, not a detailed report - minimal, actionable items only
- Show most recent batches not yet processed or just processed
- **No clutter**: avoid bombarding users with success/failure/warning/error symbols everywhere
- No emoji-heavy "AI slop" aesthetic - pure brutalist, professional tool
- Information hierarchy: what does the teacher need to act on RIGHT NOW?

## API Reference

**Endpoint:** `GET /v1/teacher/dashboard`

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 20 | Items per page (1-100) |
| `offset` | int | 0 | Pagination offset |
| `status` | string | - | Filter by status |

**Response (actual API):**

```typescript
interface TeacherDashboardResponseV1 {
  batches: TeacherBatchItemV1[];
  total_count: number;
  limit: number;
  offset: number;
}

interface TeacherBatchItemV1 {
  batch_id: string;
  title: string;
  class_name: string | null;
  status: BatchClientStatus;
  total_essays: number;
  completed_essays: number;
  created_at: string;
}

type BatchClientStatus =
  | 'pending_content'
  | 'ready'
  | 'processing'
  | 'completed_successfully'
  | 'completed_with_failures'
  | 'failed'
  | 'cancelled';
```

**Note:** `progress_percentage` is calculated client-side from `completed_essays / total_essays`.

**Error responses:**
- `400` - Invalid status value
- `401` - Missing/invalid authentication
- `502` - Backend service unavailable

## Success Criteria

- [x] Dashboard displays batch list from BFF endpoint
- [x] Pagination works (limit/offset)
- [x] Status filter works
- [x] Loading and error states handled
- [x] TypeScript types used (no `any`)
- [ ] Works against running BFF service (pending manual test)

## Testing

```bash
# Start BFF service
pdm run dev-start bff_teacher_service

# Start frontend dev server
cd frontend && pnpm dev

# Navigate to dashboard and verify
```

## Files Modified

| File | Action |
|------|--------|
| `frontend/src/schemas/teacher-dashboard.ts` | Extended - Added `limit`, `offset` to response schema |
| `frontend/src/services/teacher-dashboard.ts` | Extended - Added params interface and query string building |
| `frontend/src/services/teacher-dashboard.spec.ts` | Extended - Added 4 new test cases for params |
| `frontend/src/views/TeacherDashboardView.vue` | Created - Dashboard view with brutalist styling |
| `frontend/src/router/index.ts` | Modified - Added `/app/inlamningar` route |
| `frontend/src/layouts/AppLayout.vue` | Modified - Added "Inlamningar" nav link |

## Related Documentation

- Programme Hub: `TASKS/programs/teacher_dashboard_integration/HUB.md`
- BFF Implementation Plan: `frontend/TASKS/integration/bff-service-implementation-plan.md`
- API Contract Task: `TASKS/programs/teacher_dashboard_integration/bff-teacher-api-contract-validation.md`
- Epic: `docs/product/epics/teacher-dashboard-epic.md`
- ADR: `docs/decisions/0007-bff-vs-api-gateway-pattern.md`
