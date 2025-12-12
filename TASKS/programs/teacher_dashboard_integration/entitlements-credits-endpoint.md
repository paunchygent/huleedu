---
id: 'entitlements-credits-endpoint'
title: 'Entitlements Credits Endpoint'
type: 'task'
status: 'blocked'
priority: 'low'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "frontend-live-data-integration"]
labels: ["entitlements", "credits", "bff"]
---
# Entitlements Credits Endpoint

## Objective

Expose credit balance for dashboard display, deciding how the frontend should fetch it (BFF aggregation vs separate call).

## Context

The Teacher Dashboard header shows credit balance (e.g., "847 credits"). This requires:
1. Using the existing Entitlements Service as source of truth
2. Exposing the balance to the frontend via either:
   - BFF aggregation (single dashboard response), or
   - a separate endpoint/call (parallel fetch)

**Current state:**
- `entitlements_service` exists and already exposes a balance endpoint:
  - `GET /v1/entitlements/balance/<user_id>` (returns `user_balance`, `org_balance`, `org_id`).
- Org-aware balance is not fully wired yet (Entitlements has an explicit TODO to derive org context).

## Acceptance Criteria

- [ ] Architecture decision: BFF aggregation vs dedicated endpoint
- [ ] Endpoint returns current user credit balance
- [ ] Response model defined
- [ ] Frontend can display credits in header

## Implementation Notes

**Architecture options:**

**Option A: BFF aggregation**
- Add to dashboard response: `credits: int | None`
- BFF fetches from entitlements service
- Single API call for dashboard

**Option B: Separate endpoint**
- BFF exposes `GET /bff/v1/teacher/credits` (or similar) and proxies to Entitlements
- Frontend makes parallel call
- Better separation of concerns

**Response model (if BFF):**
```python
class TeacherDashboardResponseV1(BaseModel):
    batches: list[TeacherBatchItemV1]
    total_count: int
    limit: int
    offset: int
    credits: int | None = None  # NEW
```

**Known constraints / follow-ups:**
- Decide whether to display `user_balance` only for this sprint, or to extend Entitlements to accept org context.

## Blocked By

- `websocket-batch-updates` - complete Phase 4 before Phase 5

## Blocks

- `frontend-live-data-integration` - credits display needed for complete UX
