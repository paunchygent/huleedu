---
id: 'propagate-assignment-id-from-cj-to-ras-storage-phase-b'
title: 'Propagate assignment_id from CJ to RAS storage (Phase B)'
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
related: ['TASKS/assessment/propagate-assignment-id-from-bos-to-cj-request-phase-a.md', '.claude/plans/cuddly-churning-sloth.md']
labels: ['cross-service', 'event-contract', 'migration-required']
---
# Propagate assignment_id from CJ to RAS storage (Phase B)

## Objective

Propagate `assignment_id` from CJ Assessment Service results to RAS storage, enabling teachers to see which assignment was processed.

## Context

After Phase A completes, CJ Assessment Service will receive `assignment_id` in the request. This phase ensures the value flows through to results and is persisted in RAS.

**Current flow gap:**

| Boundary | Contract | Status |
|----------|----------|--------|
| CJ → RAS | `AssessmentResultV1` | ⚠️ In `assessment_metadata` dict only |
| RAS Storage | `BatchResult` model | ❌ No column |

## Plan

### Step 1: Add first-class `assignment_id` to CJ → RAS event
**File**: `libs/common_core/src/common_core/events/cj_assessment_events.py`
- Add `assignment_id: str | None = Field(default=None)` to `AssessmentResultV1`

### Step 2: CJ Assessment populates `assignment_id` in result
**File**: `services/cj_assessment_service/event_processor.py`
- Pass `assignment_id` from request event to `AssessmentResultV1`

### Step 3: Add `assignment_id` column to RAS BatchResult
**File**: `services/result_aggregator_service/models_db.py`
- Add `assignment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)`

### Step 4: RAS migration for new column
**File**: `services/result_aggregator_service/alembic/versions/<timestamp>_add_assignment_id_to_batch_results.py`
- Add column migration with index

### Step 4b: Migration integration test (per rule 085)
**File**: `services/result_aggregator_service/tests/integration/test_assignment_id_batch_migration.py`

Per migration standards, create TestContainers-based integration test:
1. Provision ephemeral PostgreSQL via TestContainers
2. Run `alembic upgrade head` against clean database
3. Verify `assignment_id` column exists with correct type (VARCHAR 255, nullable)
4. Verify index `ix_batch_results_assignment_id` exists
5. Test insert roundtrip with `assignment_id` populated
6. Test idempotency (run migrations twice)

**Pattern**: Follow `services/file_service/tests/integration/test_assignment_id_migration.py`

### Step 5: RAS handler stores `assignment_id`
**File**: `services/result_aggregator_service/implementations/assessment_event_handler.py`
- Extract `assignment_id` from `AssessmentResultV1`
- Store in `BatchResult.assignment_id`

### Step 6: Update tests
- `services/cj_assessment_service/tests/` - result publishing tests
- `services/result_aggregator_service/tests/` - handler and storage tests
- `tests/functional/test_e2e_cj_assessment_workflows.py` - verify end-to-end

## Success Criteria

1. `AssessmentResultV1` has first-class `assignment_id` field
2. CJ Assessment populates `assignment_id` in result events
3. RAS `batch_results` table has `assignment_id` column with index
4. RAS persists `assignment_id` from assessment results
5. Migration integration test passes (TestContainers-based per rule 085):
   - Column creation verified
   - Index creation verified
   - Insert roundtrip works
   - Idempotency confirmed
6. End-to-end test confirms `assignment_id` flows from request to RAS
7. All existing tests pass

## Related

- Phase A: `TASKS/assessment/propagate-assignment_id-from-bos-to-cj-request-phase-a.md`
- Plan file: `.claude/plans/cuddly-churning-sloth.md`

## Completion Notes (2025-11-27)

- Added `assignment_id: str | None` to `AssessmentResultV1` and wired CJ dual event publisher to populate it from `ELS_CJAssessmentRequestV1.assignment_id`.
- Extended RAS `BatchResult` with nullable `assignment_id` column plus Alembic migration `0a6c563e4523_add_assignment_id_to_batch_results` (column + `ix_batch_results_assignment_id` index).
- Added `set_batch_assignment_id` to `BatchRepositoryProtocol` and implementations; `AssessmentEventHandler.process_assessment_result` now persists `data.assignment_id` when present.
- Updated RAS API model `BatchStatusResponse` to expose `assignment_id` in read models.
- Tests: updated CJ dual event publishing unit test; added RAS unit test for handler wiring and integration tests for repository persistence and Alembic migration (including idempotency).
