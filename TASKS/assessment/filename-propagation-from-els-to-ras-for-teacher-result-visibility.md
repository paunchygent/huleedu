---
id: 'filename-propagation-from-els-to-ras-for-teacher-result-visibility'
title: 'Filename propagation from ELS to RAS for teacher result visibility'
type: 'task'
status: 'completed'
priority: 'high'
domain: 'assessment'
service: 'result_aggregator_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-27'
last_updated: '2025-11-27'
related: ['docs/operations/cj-assessment-runbook.md', '.claude/work/reports/2025-11-27-filename-propagation-flow-mapping.md']
labels: ['cross-service', 'event-contract', 'teacher-ux']
---

# Filename Propagation from ELS to RAS for Teacher Result Visibility

## Summary

Add `original_file_name` to `EssaySlotAssignedV1` event contract and propagate through RAS to populate `essay_results.filename`, enabling teachers to identify which student wrote which essay in CJ results.

## User Stories

See [CJ Assessment Runbook](../../docs/operations/cj-assessment-runbook.md#user-stories) for complete user story context.

**Primary**: As a teacher viewing CJ assessment results, I want to see the student name (derived from filename) alongside the CJ rank and score, so I can identify whose work I'm evaluating.

**GUEST Batch (Critical)**: As a teacher running an experiment with old essays not associated with a class, filename is my ONLY way to identify students since there's no student_id linkage.

## Problem Statement

### Current State
```
File Service ──✅──► ELS ──❌──► RAS ──► Teacher UI
              filename      filename MISSING
              in event      in EssaySlotAssignedV1
```

- File Service publishes `EssayContentProvisionedV1` with `original_file_name` ✅
- ELS stores filename in `slot_assignments.original_file_name` ✅
- ELS publishes `EssaySlotAssignedV1` **WITHOUT** `original_file_name` ❌
- RAS receives event but has no filename to store ❌
- `essay_results.filename` remains NULL ❌

### Evidence

```sql
-- RAS essay_results: filename is NULL
SELECT essay_id, filename, file_upload_id FROM essay_results LIMIT 5;
-- filename | NULL for all rows

-- But file_uploads has filename
SELECT file_upload_id, filename FROM file_uploads LIMIT 5;
-- filename | 'Student%20Name%20(Class).docx' for all rows
```

### Impact

| Flow | Impact |
|------|--------|
| **GUEST Batch** | **Critical** - filename is ONLY identifier (no class, no student_id) |
| **REGULAR Batch** | High - filename needed until student matching completes |
| **Future (optional spellcheck)** | No additional impact - filename tracking independent |

## Solution

### Event Contract Change

**File**: `libs/common_core/src/common_core/events/essay_lifecycle_events.py`

```python
class EssaySlotAssignedV1(BaseModel):
    """Critical mapping between file_upload_id and essay_id."""

    event: str = "essay.slot.assigned"
    batch_id: str
    essay_id: str
    file_upload_id: str
    text_storage_id: str
    original_file_name: str  # ⬅️ ADD: Propagate filename for result display
    correlation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### Implementation Tasks

| # | Service | File | Change |
|---|---------|------|--------|
| 1 | common_core | `events/essay_lifecycle_events.py` | Add `original_file_name: str` field |
| 2 | ELS | Event publisher (find location) | Include filename from `slot_assignments` table |
| 3 | RAS | `implementations/assessment_event_handler.py:58` | Pass `data.original_file_name` to updater |
| 4 | RAS | `protocols.py:122` | Add `filename: str \| None` param to `update_essay_file_mapping` |
| 5 | RAS | `implementations/batch_repository_postgres_impl.py:291` | Pass filename through |
| 6 | RAS | `implementations/essay_result_updater.py:290` | Set `essay.filename = filename` |

### Code Changes

#### 1. Event Contract
```python
# libs/common_core/src/common_core/events/essay_lifecycle_events.py
class EssaySlotAssignedV1(BaseModel):
    # ... existing fields ...
    original_file_name: str  # ADD
```

#### 2. RAS Protocol
```python
# services/result_aggregator_service/protocols.py
async def update_essay_file_mapping(
    self,
    essay_id: str,
    file_upload_id: str,
    text_storage_id: Optional[str] = None,
    filename: Optional[str] = None,  # ADD
) -> None: ...
```

#### 3. RAS Event Handler
```python
# services/result_aggregator_service/implementations/assessment_event_handler.py
async def process_essay_slot_assigned(self, envelope, data):
    await self.batch_repository.update_essay_file_mapping(
        essay_id=data.essay_id,
        file_upload_id=data.file_upload_id,
        text_storage_id=data.text_storage_id,
        filename=data.original_file_name,  # ADD
    )
```

#### 4. RAS Essay Updater
```python
# services/result_aggregator_service/implementations/essay_result_updater.py
async def update_essay_file_mapping(
    self, essay_id: str, file_upload_id: str,
    text_storage_id: Optional[str] = None,
    filename: Optional[str] = None,  # ADD
):
    if essay:
        essay.file_upload_id = file_upload_id
        if text_storage_id:
            essay.original_text_storage_id = text_storage_id
        if filename:  # ADD
            essay.filename = filename
```

## Database Impact

**No migrations required** - `essay_results.filename` column already exists:

```python
# services/result_aggregator_service/models_db.py:111
filename: Mapped[Optional[str]] = mapped_column(String(255))
```

## Testing Requirements

### Unit Tests
- [ ] `EssaySlotAssignedV1` includes `original_file_name` field
- [ ] RAS `update_essay_file_mapping` accepts and stores filename
- [ ] RAS event handler extracts filename from event

### Integration Tests
- [ ] ELS publishes filename in `EssaySlotAssignedV1`
- [ ] RAS populates `essay_results.filename` from event

### E2E Tests
- [ ] GUEST batch: filename visible in RAS results
- [ ] REGULAR batch: filename visible before student matching

```python
@pytest.mark.e2e
async def test_guest_batch_filename_in_results():
    """GUEST batch filename propagates to RAS results."""
    # Upload essays with known filenames
    # Process through pipeline
    # Query RAS: assert essay_results.filename is populated
```

## Success Criteria

1. [x] `EssaySlotAssignedV1` event includes `original_file_name`
2. [x] ELS populates filename from `content_metadata.original_file_name`
3. [x] RAS `essay_results.filename` populated for new batches
4. [x] Functional test `test_complete_cj_assessment_processing_pipeline` verifies filename
5. [x] No breaking changes to existing consumers (field is additive)

## Completion Notes (2025-11-27)

**Implementation completed:**
- Event contract: `libs/common_core/src/common_core/events/essay_lifecycle_events.py`
- ELS publisher: `services/essay_lifecycle_service/domain_services/content_assignment_service.py`
- RAS protocol: `services/result_aggregator_service/protocols.py`
- RAS handler: `services/result_aggregator_service/implementations/assessment_event_handler.py`
- RAS repository: `services/result_aggregator_service/implementations/batch_repository_postgres_impl.py`
- RAS updater: `services/result_aggregator_service/implementations/essay_result_updater.py`

**Additional fix:** `tests/utils/auth_manager.py` - Added `dotenv_values()` to load JWT secret from `.env` file (was falling back to hardcoded value causing 401 errors)

**Verification:** Functional test `test_complete_cj_assessment_processing_pipeline` passes, filename field populated in RAS results.

## Backfill Strategy (Optional, Post-MVP)

For historical batches with NULL filename:

**Option A**: File Service lookup endpoint
```
GET /v1/files/batch/{batch_id}/essay-mappings
→ [{essay_id, file_upload_id, filename}, ...]
```

**Option B**: Direct DB join (one-time script)
```sql
UPDATE essay_results er
SET filename = fu.filename
FROM file_uploads fu
WHERE er.file_upload_id = fu.file_upload_id
  AND er.filename IS NULL;
```

## Related Documents

- **Investigation Report**: `.claude/work/reports/2025-11-27-filename-propagation-flow-mapping.md`
- **CJ Runbook**: `docs/operations/cj-assessment-runbook.md`
- **Event Contracts Rule**: `.agent/rules/052-event-contract-standards.md`
- **RAS Architecture**: `.agent/rules/020.12-result-aggregator-service-architecture.md`

## Estimation

- **Complexity**: Low (additive event field + handler updates)
- **Risk**: Low (no breaking changes, DB column exists)
- **Effort**: 2-3 hours (implementation + tests)
- **Services**: 3 (common_core, ELS, RAS)
