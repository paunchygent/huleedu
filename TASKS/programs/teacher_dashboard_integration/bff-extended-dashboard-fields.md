---
id: 'bff-extended-dashboard-fields'
title: 'BFF Extended Dashboard Fields'
type: 'task'
status: 'blocked'
priority: 'high'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-12'
last_updated: '2025-12-12'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "ras-processing-phase-derivation", "frontend-live-data-integration"]
labels: ["bff", "dashboard", "dto-extension"]
---
# BFF Extended Dashboard Fields

## Objective

Extend `TeacherBatchItemV1` DTO to expose additional fields from RAS that the frontend needs for complete dashboard UX.

## Context

Current BFF dashboard endpoint returns minimal fields. RAS already has these fields but BFF doesn't expose them:
- `failed_essay_count` - for "Klar med avvikelser" display
- `processing_completed_at` - for accurate time display
- `current_phase` - for progress labels ("CJ-bedömning pågår")

## Acceptance Criteria

- [ ] `TeacherBatchItemV1` includes: `failed_essays`, `completed_at`, `processing_phase`
- [ ] `BatchSummaryV1` (RAS client model) updated to parse new fields
- [ ] Route handler maps new fields correctly
- [ ] Contract tests updated for new response shape
- [ ] OpenAPI schema regenerated (`pdm run bff-openapi`)

## Implementation Notes

**Files to modify:**
- `services/bff_teacher_service/dto/teacher_v1.py`
- `services/bff_teacher_service/clients/ras_client.py` (BatchSummaryV1)
- `services/bff_teacher_service/api/v1/teacher_routes.py`
- `services/bff_teacher_service/tests/contract/*.py`

**Extended DTO:**
```python
class TeacherBatchItemV1(BaseModel):
    batch_id: str
    title: str = "Untitled Batch"
    class_name: str | None = None
    status: BatchClientStatus
    total_essays: int = 0
    completed_essays: int = 0
    failed_essays: int = 0              # NEW
    created_at: datetime
    completed_at: datetime | None = None # NEW
    processing_phase: str | None = None  # NEW
```

**Field mapping in route:**
```python
TeacherBatchItemV1(
    # ... existing ...
    failed_essays=batch.failed_essay_count,
    completed_at=batch.processing_completed_at,
    processing_phase=batch.current_phase,
)
```

## Blocked By

- `ras-processing-phase-derivation` - RAS must return accurate `current_phase`

## Blocks

- `frontend-live-data-integration` - Frontend needs these fields for complete UX
