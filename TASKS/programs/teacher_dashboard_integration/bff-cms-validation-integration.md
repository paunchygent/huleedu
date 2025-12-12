---
id: 'bff-cms-validation-integration'
title: 'BFF CMS Validation Integration'
type: 'task'
status: 'blocked'
priority: 'medium'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "cms-student-validation-endpoint", "frontend-live-data-integration"]
labels: ["bff", "cms", "validation"]
---
# BFF CMS Validation Integration

## Objective

Extend BFF to consume CMS validation endpoint and expose `deviation_count` and `auto_confirm_deadline` in dashboard response.

## Context

After CMS exposes validation status via internal API, BFF needs to:
1. Fetch validation data for all batches in the page (bulk, avoid N+1)
2. Include validation fields in `TeacherBatchItemV1` response
3. Enable frontend to show action cards with deviation counts and countdowns

## Acceptance Criteria

- [ ] CMS client extended with `get_validation_status_for_batches(batch_ids)` method
- [ ] Dashboard endpoint fetches validation data in parallel with existing RAS + class-info calls
- [ ] `TeacherBatchItemV1` includes `deviation_count`, `auto_confirm_deadline`
- [ ] Contract tests updated
- [ ] Performance: validation fetch doesn't significantly increase latency

## Implementation Notes

**Extended CMS client (bulk, consistent with CMS class-info pattern):**
```python
# services/bff_teacher_service/clients/cms_client.py
async def get_validation_status_for_batches(
    self,
    batch_ids: list[UUID],
    correlation_id: UUID,
) -> dict[str, BatchValidationStatus | None]:
    """Fetch validation status for multiple batches (single request)."""
    # GET /internal/v1/batches/validation-status?batch_ids=<uuid1>,<uuid2>,...
    ...
```

**Extended DTO:**
```python
class TeacherBatchItemV1(BaseModel):
    # ... existing fields ...
    deviation_count: int | None = None
    auto_confirm_deadline: datetime | None = None
```

**Parallel fetch pattern (single-call bulk fanout):**
```python
# In dashboard endpoint
class_info_map, validation_map = await asyncio.gather(
    cms_client.get_class_info_for_batches(batch_ids=batch_ids, correlation_id=correlation_id),
    cms_client.get_validation_status_for_batches(batch_ids=batch_ids, correlation_id=correlation_id),
)
```

## Blocked By

- `cms-student-validation-endpoint` - CMS must expose validation data first

## Blocks

- `frontend-live-data-integration` - Frontend needs deviation data for action cards
