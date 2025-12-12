---
id: 'cms-student-validation-endpoint'
title: 'CMS Student Validation Endpoint'
type: 'task'
status: 'blocked'
priority: 'medium'
domain: 'programs'
service: 'class_management_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-cms-validation-integration"]
labels: ["cms", "student-validation", "internal-api"]
---
# CMS Student Validation Endpoint

## Objective

Create CMS internal endpoint to provide student validation status for batches, including deviation count and auto-confirm deadline.

## Context

The Teacher Dashboard needs to show:
- **Deviation count**: "2 uppsatser kräver manuell koppling"
- **Auto-confirm deadline**: Countdown timer for automatic student confirmation

This data lives in CMS (`essay_student_associations` table) but is not currently exposed via API.

## Acceptance Criteria

- [ ] `GET /internal/v1/batches/{batch_id}/validation-status` endpoint created
- [ ] Response includes `deviation_count` and `auto_confirm_deadline`
- [ ] Auth via `X-Internal-API-Key` + `X-Service-ID` (existing pattern)
- [ ] Unit tests for endpoint

## Implementation Notes

**New endpoint:**
```
GET /internal/v1/batches/{batch_id}/validation-status
```

**Response model:**
```python
class BatchValidationStatusV1(BaseModel):
    batch_id: str
    deviation_count: int  # Essays needing manual student match
    auto_confirm_deadline: datetime | None  # When auto-confirm triggers
    total_associations: int
    confirmed_associations: int
```

**Query logic:**
```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'pending_review') AS deviation_count,
    MIN(auto_confirm_at) AS auto_confirm_deadline
FROM essay_student_associations
WHERE batch_id = :batch_id
```

**Files to create/modify:**
- `services/class_management_service/api/internal_routes.py` - new route
- `services/class_management_service/models_api.py` - response model
- `services/class_management_service/tests/unit/test_validation_status.py`

## Blocked By

- `bff-extended-dashboard-fields` - complete Phase 2 before starting Phase 3

## Blocks

- `bff-cms-validation-integration` - BFF needs this endpoint to fetch validation data
