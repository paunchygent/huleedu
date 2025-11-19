# Migration Integration Test Corrections - 2025-11-19

## File Fixed
`services/cj_assessment_service/tests/integration/test_total_budget_migration.py`

## Test Results
**All 6 tests now PASS** ✓

```
test_migration_upgrade_from_clean_database - PASSED
test_total_budget_accepts_integer_values - PASSED
test_total_budget_backfill_for_existing_rows - PASSED
test_total_budget_nullable_for_backwards_compatibility - PASSED
test_current_iteration_defaults_to_zero - PASSED
test_migration_idempotency - PASSED
```

## Model Validation Results

### CJBatchUpload Model
**Required fields:**
- `bos_batch_id` (str)
- `event_correlation_id` (str)
- `language` (str)
- `course_code` (str)
- `expected_essay_count` (int)
- `status` (CJBatchStatusEnum) - default: PENDING

**Timestamp fields (server-managed, NOT settable):**
- `created_at` - server_default=NOW()
- `updated_at` - server_default=NOW(), onupdate=NOW()
- `completed_at` - nullable

**Optional fields:**
- `processing_metadata` (dict | None)
- `assignment_id` (str | None)
- `user_id` (str | None)
- `org_id` (str | None)

### CJBatchState Model
**Required fields:**
- `batch_id` (int) - primary key, FK to CJBatchUpload.id
- `state` (CJBatchStateEnum) - default: INITIALIZING
- `total_comparisons` (int) - default: 0
- `submitted_comparisons` (int) - default: 0
- `completed_comparisons` (int) - default: 0
- `failed_comparisons` (int) - default: 0
- `current_iteration` (int) - default: 0
- `completion_threshold_pct` (int) - default: 95
- `partial_scoring_triggered` (bool) - default: False

**Timestamp fields (server-managed):**
- `last_activity_at` (datetime, timezone-aware) - server_default=NOW(), onupdate=NOW()

**Optional fields:**
- `total_budget` (int | None) - nullable (for backwards compatibility)
- `processing_metadata` (dict | None)

### Enum Values

**CJBatchStatusEnum** (services/cj_assessment_service/enums_db.py):
- PENDING
- FETCHING_CONTENT
- PERFORMING_COMPARISONS
- COMPLETE_STABLE
- COMPLETE_MAX_COMPARISONS
- COMPLETE_INSUFFICIENT_ESSAYS
- ERROR_PROCESSING
- ERROR_ESSAY_PROCESSING

**CJBatchStateEnum** (common_core.status_enums):
- INITIALIZING
- GENERATING_PAIRS
- WAITING_CALLBACKS
- SCORING
- COMPLETED
- FAILED
- CANCELLED

## Corrections Made

### 1. Missing Import
**Problem:** `CJBatchStateEnum` was used but not imported.

**Fix:** Added import at line 32:
```python
from common_core.status_enums import CJBatchStateEnum
```

### 2. Invalid String Values for Enum Fields
**Problem:** Tests used string values like "processing" and "pending" instead of enum members.

**Locations:**
- Line 248: `state="processing"` → `state=CJBatchStateEnum.GENERATING_PAIRS`
- Line 323: `state="processing"` → `state=CJBatchStateEnum.GENERATING_PAIRS.value`
- Line 392: `state="pending"` → `state=CJBatchStateEnum.INITIALIZING`
- Line 438: `state="pending"` → `state=CJBatchStateEnum.INITIALIZING`

**Rationale:**
- When using ORM models, use enum members (e.g., `CJBatchStateEnum.GENERATING_PAIRS`)
- When using raw SQL with text(), use `.value` (e.g., `CJBatchStateEnum.GENERATING_PAIRS.value`)
- Never use string literals that don't match enum values

### 3. Attempting to Set Server-Managed Timestamp Fields
**Problem:** Tests tried to manually set `created_at` and `updated_at` on CJBatchUpload, which have server defaults and should not be set manually.

**Location:** Lines 285-300 in `test_total_budget_backfill_for_existing_rows`

**Original code:**
```python
INSERT INTO cj_batch_uploads
(bos_batch_id, event_correlation_id, language, course_code,
 expected_essay_count, status, created_at, updated_at)
VALUES
(:bos_batch_id, :event_correlation_id, :language, :course_code,
 :expected_essay_count, :status, :created_at, :updated_at)
```

**Fixed code:**
```python
INSERT INTO cj_batch_uploads
(bos_batch_id, event_correlation_id, language, course_code,
 expected_essay_count, status)
VALUES
(:bos_batch_id, :event_correlation_id, :language, :course_code,
 :expected_essay_count, :status)
```

**Rationale:** Server defaults (NOW()) handle these automatically. CJBatchUpload model has no `created_at` or `updated_at` in the mapped columns that can be set manually.

### 4. Attempting to Set CJBatchState Timestamp Fields
**Problem:** Similar to #3, test tried to set `created_at` and `updated_at` on CJBatchState raw SQL insert.

**Location:** Lines 307-327 in `test_total_budget_backfill_for_existing_rows`

**Original code:**
```python
INSERT INTO cj_batch_states
(batch_id, total_comparisons, submitted_comparisons, completed_comparisons,
 failed_comparisons, state, created_at, updated_at)
VALUES
(:batch_id, :total, :submitted, :completed, :failed, :state,
 :created_at, :updated_at)
```

**Fixed code:**
```python
INSERT INTO cj_batch_states
(batch_id, total_comparisons, submitted_comparisons, completed_comparisons,
 failed_comparisons, state)
VALUES
(:batch_id, :total, :submitted, :completed, :failed, :state)
```

**Rationale:** CJBatchState has `last_activity_at` (not `created_at`/`updated_at`) with server_default=NOW() and onupdate=NOW(). It's timezone-aware and should not be manually set.

## Key Learnings

### 1. Always Validate Model Structure First
Before writing tests:
1. Read the actual model definitions
2. Document ALL required fields
3. Document ALL optional fields and defaults
4. Identify server-managed fields (server_default, onupdate)
5. Check enum definitions for exact valid values

### 2. Enum Usage Patterns
- **ORM models**: Use enum members directly (`state=CJBatchStateEnum.INITIALIZING`)
- **Raw SQL with SQLAlchemy text()**: Use `.value` (`"state": CJBatchStateEnum.INITIALIZING.value`)
- **Never**: Use string literals that guess at enum values

### 3. Server-Managed Timestamp Fields
- Fields with `server_default=text("NOW()")` should NOT be manually set
- Let PostgreSQL handle timestamp population
- This applies to both ORM and raw SQL inserts

### 4. Timezone Awareness
- `CJBatchState.last_activity_at` is `DateTime(timezone=True)` - timezone-aware
- `CJBatchUpload.created_at/updated_at` are `DateTime` without timezone - naive
- When using `datetime.now(UTC)`, strip timezone if target field is naive: `.replace(tzinfo=None)`

## Test Execution
All tests run successfully with testcontainers PostgreSQL:

```bash
pdm run pytest-root services/cj_assessment_service/tests/integration/test_total_budget_migration.py -v
```

**Result:** 6 passed in 32.45s

## Validation
The tests now properly validate:
1. Migration runs cleanly on fresh PostgreSQL instance
2. `total_budget` column created with correct type (integer, nullable)
3. `current_iteration` has correct default (0)
4. Integer values can be stored in `total_budget`
5. Backfill logic works (NULL total_budget → total_comparisons value)
6. Backwards compatibility maintained (total_budget can be NULL)
7. Migration is idempotent (can run twice without errors)
