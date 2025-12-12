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

Create CMS internal **bulk** endpoint to provide student validation status for multiple batches, including deviation count and auto-confirm deadline.

## Context

The Teacher Dashboard needs to show:
- **Deviation count**: "2 uppsatser kräver manuell koppling"
- **Auto-confirm deadline**: Countdown timer for automatic student confirmation

This data lives in CMS (`essay_student_associations` table) but is not currently exposed via API.

## Acceptance Criteria

- [ ] `GET /internal/v1/batches/validation-status?batch_ids=<uuid1>,<uuid2>,...` endpoint created
- [ ] Response includes `deviation_count` and `auto_confirm_deadline`
- [ ] Auth via `X-Internal-API-Key` + `X-Service-ID` (existing pattern)
- [ ] Unit tests for endpoint

## Implementation Notes

**New endpoint (bulk, consistent with existing CMS class-info pattern):**
```
GET /internal/v1/batches/validation-status?batch_ids=<uuid1>,<uuid2>,...
```

**Response model (per batch):**
```python
class BatchValidationStatusV1(BaseModel):
    batch_id: str
    deviation_count: int  # Associations still pending teacher validation
    auto_confirm_deadline: datetime | None  # Next auto-confirm time (min(created_at) + 24h)
    total_associations: int
    confirmed_associations: int
```

**Semantics / derivation (no raw SQL):**
- Student association status uses `StudentAssociationStatus` (`common_core.status_enums.StudentAssociationStatus`).
- `deviation_count` = count where `validation_status == pending_validation`.
- `auto_confirm_deadline` is computed (CMS does not store `auto_confirm_at` today):
  - If there are pending associations: `min(created_at) + timedelta(hours=24)`
  - Else: `None`

**Bulk response shape:**
- Return a map keyed by batch_id (same pattern as the existing class-info bulk endpoint):
  - `{ "<batch_id>": BatchValidationStatusV1 | null }`

**Files to create/modify:**
- `services/class_management_service/api/internal_routes.py` - new route
- `services/class_management_service/models_api.py` - response model
- `services/class_management_service/tests/unit/test_validation_status.py`

## Blocked By

- `bff-extended-dashboard-fields` - complete Phase 2 before starting Phase 3

## Blocks

- `bff-cms-validation-integration` - BFF needs this endpoint to fetch validation data
