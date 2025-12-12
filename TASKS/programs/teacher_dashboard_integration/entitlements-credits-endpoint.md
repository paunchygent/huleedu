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

Expose user credit balance for dashboard display, determining whether this belongs in BFF or a dedicated entitlements service.

## Context

The Teacher Dashboard header shows credit balance (e.g., "847 credits"). This requires:
1. Determining where credit data lives (entitlements_service? org_service?)
2. Creating an endpoint to fetch current balance
3. Including in BFF or separate API call

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
- `GET /api/v1/user/credits` (via API Gateway)
- Frontend makes parallel call
- Better separation of concerns

**Option C: API Gateway responsibility**
- Gateway injects credits into response
- Transparent to BFF

**Response model (if BFF):**
```python
class TeacherDashboardResponseV1(BaseModel):
    batches: list[TeacherBatchItemV1]
    total_count: int
    limit: int
    offset: int
    credits: int | None = None  # NEW
```

**Research needed:**
- Where is credit data currently stored?
- Is there an existing entitlements service?
- What's the credit deduction model?

## Blocked By

- `websocket-batch-updates` - complete Phase 4 before Phase 5
- Research: entitlements service existence

## Blocks

- `frontend-live-data-integration` - credits display needed for complete UX
