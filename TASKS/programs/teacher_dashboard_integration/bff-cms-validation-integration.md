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
1. Fetch validation data for each batch (parallel with RAS/class-info calls)
2. Include validation fields in `TeacherBatchItemV1` response
3. Enable frontend to show action cards with deviation counts and countdowns

## Acceptance Criteria

- [ ] CMS client extended with `get_validation_status(batch_id)` method
- [ ] Dashboard endpoint fetches validation data in parallel with existing calls
- [ ] `TeacherBatchItemV1` includes `deviation_count`, `auto_confirm_deadline`
- [ ] Contract tests updated
- [ ] Performance: validation fetch doesn't significantly increase latency

## Implementation Notes

**Extended CMS client:**
```python
# services/bff_teacher_service/clients/cms_client.py
async def get_validation_status(self, batch_id: str) -> BatchValidationStatus | None:
    """Fetch validation status for a batch."""
    response = await self._client.get(
        f"{self._base_url}/internal/v1/batches/{batch_id}/validation-status",
        headers=self._build_headers(),
    )
    # Handle 404 as None (batch may not have student associations)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return BatchValidationStatus.model_validate(response.json())
```

**Extended DTO:**
```python
class TeacherBatchItemV1(BaseModel):
    # ... existing fields ...
    deviation_count: int | None = None
    auto_confirm_deadline: datetime | None = None
```

**Parallel fetch pattern:**
```python
# In dashboard endpoint
validation_tasks = [
    cms_client.get_validation_status(batch.batch_id)
    for batch in batches
]
validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
```

## Blocked By

- `cms-student-validation-endpoint` - CMS must expose validation data first

## Blocks

- `frontend-live-data-integration` - Frontend needs deviation data for action cards
