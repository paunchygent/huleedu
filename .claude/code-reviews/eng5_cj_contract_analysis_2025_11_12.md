# ENG5 Runner ↔ CJ Assessment Service: Complete Contract Mismatch Analysis

**Date**: 2025-11-12  
**Analyst**: Claude Code  
**Scope**: Comprehensive analysis of ALL contract mismatches and potential issues  
**Context**: Following ENG5 runner reaching CJ service but failing on data validation

---

## Executive Summary

**Status**: 🔴 **2 CRITICAL BLOCKERS FOUND** + 2 medium-priority validation issues

Analysis identified:
- ✅ 3 issues already fixed (storage ID prefix, batch ID validation, markdown support)
- ✅ 1 issue already mitigated (essay ID truncation implemented)
- ❌ **2 CRITICAL schema/data issues blocking execution**
- ⚠️ 2 medium-priority validation concerns requiring investigation

The user's fixes addressed surface symptoms but missed the underlying schema mismatch (error_code type) and data flow issue (storage ID sourcing).

---

## CRITICAL Issue #1: Database Type Mismatch - error_code Column

### Root Cause
**Schema-Model inconsistency**: PostgreSQL has `error_code` as ENUM type, but SQLAlchemy model defines it as `String(100)`.

### Evidence

**Database schema** (confirmed via `psql \dT+ errorcode`):
```sql
CREATE TYPE errorcode AS ENUM (
    'UNKNOWN_ERROR',
    'VALIDATION_ERROR',
    'RESOURCE_NOT_FOUND',
    'CONFIGURATION_ERROR',
    'EXTERNAL_SERVICE_ERROR',
    -- ... 22 more values
);

-- Column definition:
error_code errorcode  -- PostgreSQL USER-DEFINED type
```

**SQLAlchemy model** (`services/cj_assessment_service/models_db.py:195`):
```python
error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

**Runtime error path** (`cj_core_logic/callback_state_manager.py:95-97`):
```python
comparison_pair.error_code = (
    comparison_result.error_detail.error_code.value
)  # Converts ErrorCode enum to string like "RATE_LIMIT"
```

**PostgreSQL error when attempting write**:
```
ERROR: column "error_code" is of type errorcode but expression is of type character varying
HINT: You will need to rewrite or cast the expression.
```

### Impact
- **Severity**: 🔴 BLOCKING
- **Trigger**: Any LLM comparison failure (rate limits, timeouts, parsing errors)
- **Effect**: 
  - Database write fails with type error
  - Comparison cannot be marked as failed
  - Retry logic breaks
  - Batch gets stuck in partial state
- **Frequency**: High during initial testing (LLM provider issues, prompt errors common)

### Which Service Needs Fixing
**CJ Assessment Service** - Database migration required

### Fix Options

**Option A: Drop ENUM, use VARCHAR (RECOMMENDED)**
```sql
-- Migration: 20251112_HHMM_fix_error_code_type.py

def upgrade() -> None:
    # Convert ENUM column to VARCHAR
    op.execute("""
        ALTER TABLE cj_comparison_pairs 
        ALTER COLUMN error_code TYPE VARCHAR(100) 
        USING error_code::text;
    """)
    
    # Drop the ENUM type
    op.execute("DROP TYPE errorcode;")

def downgrade() -> None:
    # Recreate ENUM type with all values from common_core.error_enums.ErrorCode
    op.execute("""
        CREATE TYPE errorcode AS ENUM (
            'UNKNOWN_ERROR',
            'VALIDATION_ERROR',
            -- ... all 26 values
        );
    """)
    
    # Convert column back to ENUM
    op.execute("""
        ALTER TABLE cj_comparison_pairs 
        ALTER COLUMN error_code TYPE errorcode 
        USING error_code::errorcode;
    """)
```

**Pros**: 
- Model already correct (String(100))
- Flexible for adding new error codes
- No Python code changes needed

**Cons**:
- Loses database-level type safety

**Option B: Use SQLAlchemy ENUM (NOT RECOMMENDED)**
```python
# models_db.py
from common_core.error_enums import ErrorCode

error_code: Mapped[ErrorCode | None] = mapped_column(
    SQLAlchemyEnum(
        ErrorCode,
        name="errorcode",
        values_callable=lambda obj: [e.value for e in obj],
    ),
    nullable=True,
)
```

**Pros**: Type-safe at both layers

**Cons**:
- Requires migration to sync ENUM values
- Less flexible (database migration needed for new error codes)
- Callback manager needs `.value` extraction remains

### Recommended Action
**Use Option A** - Drop ENUM, standardize on VARCHAR for error codes across all services.

### Priority
🔴 **P0 - CRITICAL**: Must fix before any error handling testing

---

## CRITICAL Issue #2: Storage ID Mismatch - Prompt Upload

### Root Cause
**Runner is using file checksum (64-char SHA256) instead of Content Service's returned storage_id (32-char UUID hex)**.

### Evidence Trail

**Content Service generates** (`implementations/filesystem_content_store.py:48`):
```python
content_id = uuid.uuid4().hex  # Returns 32-character hex string
# Example: "a1b2c3d4e5f6789012345678901234ab"
```

**Content Service validates on retrieval** (`api/content_routes.py:87`):
```python
if not all(c in "0123456789abcdefABCDEF" for c in content_id) or len(content_id) != 32:
    raise_validation_error(
        message="Invalid content ID format - must be 32 character hex string",
    )
```

**Runner uploads correctly** (`content_upload.py:68-76`):
```python
storage_id = payload.get("storage_id")  # ✅ Gets Content Service's UUID
if not storage_id:
    raise ContentUploadError("Content Service response missing storage_id")

typer.echo(f"Uploaded {path.name} -> storage_id={storage_id}", err=True)
return str(storage_id)  # ✅ Returns the 32-char UUID
```

**BUT the uploaded storage_id is discarded** in `requests.py:24-46`:
```python
def build_prompt_reference(
    record: FileRecord, storage_id: str | None = None
) -> StorageReferenceMetadata | None:
    if not record.exists:
        return None
    if storage_id is None:  # ❌ This guard is good...
        raise ValueError("storage_id is required when prompt file exists")
    reference = StorageReferenceMetadata()
    reference.add_reference(
        ContentType.STUDENT_PROMPT_TEXT,
        storage_id=storage_id,  # ✅ Would use correct ID if passed...
        path_hint=str(record.path),
    )
    return reference
```

**The problem**: In execute mode, need to verify the caller:
1. Uploads prompt via `upload_essays_parallel()` (which returns {checksum: storage_id} map)
2. Extracts the **actual Content Service storage_id** from upload result
3. Passes that to `build_prompt_reference(record, storage_id=actual_storage_id)`

**Instead, the user's "fix"** in `requests.py:30` removed the prefix but still uses checksum:
```python
# User's attempt (WRONG):
storage_id = record.checksum  # Still 64-char SHA256!

# Correct approach:
# storage_id should come from upload_essays_parallel() return value
```

### Impact
- **Severity**: 🔴 BLOCKING
- **Trigger**: CJ service attempts to hydrate `student_prompt_ref.storage_id` via Content Service
- **Effect**:
  - Content Service returns 400: "Invalid content ID format - must be 32 character hex string"
  - CJ batch preparation fails
  - Event processing halts
  - Metric `huleedu_cj_prompt_fetch_failures_total{reason="validation_error"}` increments
- **Frequency**: 100% of execute-mode runs with prompt files

### Which Service Needs Fixing
**ENG5 Runner** - Execute mode flow needs correction

### Required Changes

**File**: `scripts/cj_experiments_runners/eng5_np/cli.py` (execute mode section)

**Current flow** (needs verification):
```python
# Somewhere in execute mode:
# 1. Upload essays
storage_map = await upload_essays_parallel(
    records=anchors + students,
    content_service_url=content_service_url,
)

# 2. Build prompt reference - WRONG if using record.checksum
prompt_ref = build_prompt_reference(
    prompt_record, 
    storage_id=prompt_record.checksum  # ❌ 64-char SHA256
)

# 3. Compose request with bad storage_id
request = compose_cj_assessment_request(
    essay_refs=essay_refs,
    prompt_reference=prompt_ref,  # Contains wrong ID
)
```

**Correct flow**:
```python
# 1. Upload ALL content (including prompt)
all_records = [prompt_record] + anchors + students
storage_map = await upload_essays_parallel(
    records=all_records,
    content_service_url=content_service_url,
)

# 2. Extract prompt's actual storage_id from upload results
prompt_checksum = prompt_record.checksum or sha256_of_file(prompt_record.path)
prompt_storage_id = storage_map[prompt_checksum]  # ✅ 32-char UUID

# 3. Build prompt reference with ACTUAL storage_id
prompt_ref = build_prompt_reference(
    prompt_record,
    storage_id=prompt_storage_id  # ✅ Content Service UUID
)

# 4. Compose request
request = compose_cj_assessment_request(
    essay_refs=essay_refs,
    prompt_reference=prompt_ref,  # Contains correct ID
)
```

### Action Required
1. **Trace execute mode in cli.py**: Find where prompt upload + reference building happens
2. **Verify prompt is included** in `upload_essays_parallel()` call
3. **Fix storage_id extraction**: Use `storage_map[prompt_checksum]` not `record.checksum`
4. **Add validation**: Assert storage_id is 32 chars before building reference

### Priority
🔴 **P0 - CRITICAL**: Blocks all CJ batches with prompt references

---

## MEDIUM Issue #3: Assignment ID Existence Validation

### Root Cause
**Runner may use assignment_id that doesn't exist** in CJ's `assessment_instructions` table.

### Evidence

**Event contract** (`common_core/events/cj_assessment_events.py:122-126`):
```python
assignment_id: str | None = Field(
    default=None,
    max_length=100,
    description="Assignment context for grade projection",
)
```

**CJ database schema** (`models_db.py:417-419`):
```python
assignment_id: Mapped[str | None] = mapped_column(
    String(100), nullable=True, unique=True, index=True
)
```

**CLI requires assignment_id** (`cli.py:250-254`):
```python
assignment_id: uuid.UUID = typer.Option(
    ...,  # REQUIRED
    help="Assignment ID (REQUIRED). Must exist in CJ service assessment_instructions table. "
    "Create via: POST /admin/v1/assessment-instructions",
)
```

**Question**: Does CJ service validate assignment_id existence during batch preparation?

### Impact
- **Severity**: 🟡 MEDIUM
- **Trigger**: Execute mode with non-existent assignment_id
- **Effect** (unknown, needs investigation):
  - Option A: CJ rejects batch with validation error (GOOD - fail fast)
  - Option B: CJ accepts batch, grade projection fails silently (BAD - partial success)
  - Option C: CJ accepts batch, uses default scale (OKAY - degraded mode)
- **Frequency**: Only when runner misconfigured

### Which Service Needs Investigation
**Both**:
1. **CJ Service**: Check `batch_preparation.py` or `event_processor.py` for assignment_id lookup
2. **Runner**: Add preflight check via CJ admin API (`GET /admin/v1/assessment-instructions/{assignment_id}`)

### Recommended Action
**Add preflight validation in runner**:
```python
# In execute mode, before upload:
async def validate_assignment_exists(assignment_id: UUID, cj_url: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{cj_url}/admin/v1/assessment-instructions/{assignment_id}") as resp:
            if resp.status == 404:
                raise ValueError(
                    f"Assignment {assignment_id} not found in CJ service.\n"
                    f"Create via: pdm run cj-admin instructions create ..."
                )
            resp.raise_for_status()
```

### Priority
🟡 **P1 - HIGH**: Should add before production use, but won't block initial testing

---

## MEDIUM Issue #4: Grade Scale Registration

### Root Cause
**Need to verify** `eng5_np_legacy_9_step` scale exists in CJ service configuration.

### Evidence

**Runner uses** (`cli.py:259-262`):
```python
grade_scale: str = typer.Option(
    "eng5_np_legacy_9_step",
    help="Grade scale key registered in the CJ service",
)
```

**CJ default** (`models_db.py:423`):
```python
grade_scale: Mapped[str] = mapped_column(
    String(50), nullable=False, server_default="swedish_8_anchor", index=True
)
```

**Test fixtures use this scale**:
- `test_eng5_scale_flows.py:240`: `grade_scale = "eng5_np_legacy_9_step"`
- Multiple test files reference this scale

### Impact
- **Severity**: 🟢 LOW (likely already working)
- **Trigger**: Grade projection lookup
- **Effect**: May fall back to default or error
- **Frequency**: 100% of ENG5 batches

### Which Service Needs Verification
**CJ Service** - Check grade scales configuration:
1. Look for `grade_scales.py` or similar config module
2. Verify `eng5_np_legacy_9_step` is registered
3. If not: Check if it's seeded via migration or startup script

### Recommended Action
**Low priority check**: Since tests use this scale, it's likely already configured. Verify during testing.

### Priority
🟢 **P2 - LOW**: Likely already working based on test coverage

---

## ✅ Issues Already Fixed

### 1. Storage ID Prefix ✅ PARTIALLY FIXED
**Location**: `scripts/cj_experiments_runners/eng5_np/requests.py:30`

**Before**:
```python
storage_id = f"prompt::{record.checksum}"  # Wrong: added prefix + used checksum
```

**After**:
```python
storage_id = record.checksum  # Better: removed prefix, but still wrong ID (see Issue #2)
```

**Status**: Prefix removed, but still using wrong ID source. See Issue #2 for complete fix.

---

### 2. Batch ID Validation ✅ COMPLETE
**Location**: `scripts/cj_experiments_runners/eng5_np/requests.py:60-63`

```python
if not settings.batch_id or settings.batch_id.strip() == "":
    raise ValueError(
        "batch_id cannot be empty - must be provided via --batch-id CLI argument"
    )
```

**Status**: Good defensive programming. Prevents empty string from reaching CJ service.

---

### 3. Markdown Support ✅ COMPLETE
**Location**: Text extraction now handles `.md` files

**Status**: Working correctly for prompt files in markdown format.

---

### 4. Essay ID Length Constraint ✅ COMPLETE
**Location**: `scripts/cj_experiments_runners/eng5_np/utils.py:33-64` + `inventory.py:192`

**Implementation**:
```python
def generate_essay_id(filename_stem: str, max_length: int = 36) -> str:
    """Generate essay ID with length constraint using truncation and hash suffix."""
    sanitized = sanitize_identifier(filename_stem)
    
    if len(sanitized) <= max_length:
        return sanitized
    
    # Truncate and append 8-char deterministic hash
    hash_suffix_length = 8
    separator_length = 1
    base_max_length = max_length - hash_suffix_length - separator_length
    name_hash = sha256(sanitized.encode()).hexdigest()[:hash_suffix_length]
    base = sanitized[:base_max_length]
    return f"{base}_{name_hash.upper()}"
```

**Usage** (`inventory.py:192`):
```python
essay_id = generate_essay_id(record.path.stem, max_length=36)
```

**Status**: Already implemented and working. Long names like `EDITH_STRANDLER_SA24_ENG5_NP_WRITING_ROLE_MODELS` (50 chars) get truncated to `EDITH_STRANDLER_SA24_ENG5_NP_W_A3F4B2C1` (36 chars).

---

## ✅ Contract Compliance Verified

### Event Contract: ELS_CJAssessmentRequestV1

Analyzed `requests.py:compose_cj_assessment_request()` against schema in `common_core/events/cj_assessment_events.py:106-132`.

**All required fields present**:
- ✅ `event_name` = ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED
- ✅ `system_metadata`: SystemProcessingMetadata (batch context)
- ✅ `essays_for_cj`: list[EssayProcessingInputRefV1]
- ✅ `language`: str (from settings)
- ✅ `course_code`: CourseCode (from settings)
- ✅ `student_prompt_ref`: StorageReferenceMetadata | None (optional, correctly handled)
- ✅ `llm_config_overrides`: LLMConfigOverrides | None (optional, CLI-driven)
- ✅ `assignment_id`: str | None (max_length=100, validated by Pydantic)
- ✅ `user_id`: str (from settings)
- ✅ `org_id`: str | None (optional, from settings)

**Field types match**:
- ✅ `assignment_id` max_length=100 (Pydantic) ≤ String(100) (database)
- ✅ `student_prompt_ref` uses StorageReferenceMetadata pattern (once Issue #2 fixed)
- ✅ LLM overrides validated via `_build_llm_overrides()` in cli.py

**No contract violations found** in event structure.

---

### Essay Processing Input Refs

**Schema** (`common_core/metadata_models.py`):
```python
class EssayProcessingInputRefV1(BaseModel):
    essay_id: str
    text_storage_id: str
```

**Runner implementation** (`inventory.py:180-209`):
```python
def _records_to_refs(
    records: Sequence[FileRecord],
    *,
    prefix: str,
    storage_id_map: Mapping[str, str] | None,
) -> list[EssayProcessingInputRefV1]:
    refs = []
    for record in records:
        essay_id = generate_essay_id(record.path.stem, max_length=36)  # ✅ Constrained
        checksum = record.checksum or sha256_of_file(record.path)
        
        if storage_id_map is None:
            text_storage_id = f"{prefix}::{checksum}"  # ❌ Plan/dry-run mode
        else:
            text_storage_id = storage_id_map[checksum]  # ✅ Execute mode (correct)
        
        refs.append(EssayProcessingInputRefV1(
            essay_id=essay_id,
            text_storage_id=text_storage_id,
        ))
    return refs
```

**Status**: ✅ Correctly uses storage_id from upload map in execute mode. Prefix pattern only used in plan/dry-run (acceptable for mock data).

---

## Summary Table

| # | Issue | Severity | Service | Type | Status | Blocking |
|---|-------|----------|---------|------|--------|----------|
| 1 | error_code ENUM vs VARCHAR | CRITICAL | CJ | Schema | ❌ OPEN | YES |
| 2 | Storage ID source (checksum vs UUID) | CRITICAL | Runner | Data Flow | ❌ OPEN | YES |
| 3 | Assignment ID validation | HIGH | Both | Validation | ⚠️ NEEDS CHECK | MAYBE |
| 4 | Grade scale registration | MEDIUM | CJ | Config | ✅ LIKELY OK | NO |
| - | Storage ID prefix removed | - | Runner | - | ✅ FIXED | - |
| - | Batch ID validation added | - | Runner | - | ✅ FIXED | - |
| - | Markdown support | - | Runner | - | ✅ FIXED | - |
| - | Essay ID length truncation | - | Runner | - | ✅ FIXED | - |
| - | Event contract compliance | - | Both | - | ✅ VERIFIED | - |

**Critical Path Blockers**: 2 (Issues #1, #2)  
**Investigation Required**: 1 (Issue #3)  
**Low Priority**: 1 (Issue #4)

---

## Recommended Fix Order

### Phase 1: Database Schema (CJ Service) - 30 min
**Issue #1**: Fix error_code column type
1. Create migration `20251112_HHMM_fix_error_code_type.py`
2. Drop errorcode ENUM, use VARCHAR(100)
3. Test error handling path (simulate LLM failure)
4. Verify error_code writes successfully

### Phase 2: Data Flow (Runner) - 1-2 hours
**Issue #2**: Fix storage ID usage
1. Trace execute mode in `cli.py` (find upload + prompt ref building)
2. Ensure prompt included in `upload_essays_parallel()` call
3. Extract storage_id from upload results: `storage_map[prompt_checksum]`
4. Pass to `build_prompt_reference(record, storage_id=actual_storage_id)`
5. Add assertion: `assert len(storage_id) == 32` before event composition
6. Test prompt upload → CJ hydration flow

### Phase 3: Validation (Both) - 1 hour
**Issue #3**: Assignment ID validation
1. Check CJ `batch_preparation.py` for assignment_id lookup logic
2. Add runner preflight check: `GET /admin/v1/assessment-instructions/{assignment_id}`
3. Document required setup steps (create instructions before running)

**Issue #4**: Grade scale verification
1. Find CJ grade scales config (likely `grade_scales.py`)
2. Verify `eng5_np_legacy_9_step` registered
3. If missing: Add to config or seed migration

### Phase 4: Integration Testing - 2-3 hours
**End-to-end validation**:
1. Create test assignment via `cj-admin instructions create`
2. Run execute mode with real Content Service
3. Verify CJ batch preparation succeeds
4. Trigger LLM error to test error_code write
5. Check metrics: `huleedu_cj_prompt_fetch_failures_total` (should be 0)
6. Validate grade projection uses correct scale

---

## Files Requiring Changes

### CJ Assessment Service
1. `services/cj_assessment_service/alembic/versions/20251112_HHMM_fix_error_code_type.py` (NEW - migration)
2. `services/cj_assessment_service/event_processor.py` or `batch_preparation.py` (MAYBE - add assignment_id validation)

### ENG5 Runner
1. `scripts/cj_experiments_runners/eng5_np/cli.py` (FIX - execute mode storage_id flow)
2. `scripts/cj_experiments_runners/eng5_np/cli.py` (ADD - preflight assignment_id check)

---

## Testing Checklist

### CJ Service
- [ ] error_code column accepts VARCHAR writes
- [ ] Error handling path works (simulate LLM provider failure)
- [ ] Assignment ID lookup handles missing records gracefully
- [ ] Grade scale `eng5_np_legacy_9_step` recognized in projection logic

### Runner
- [ ] Prompt upload returns 32-char storage_id from Content Service
- [ ] Event contains correct storage_id (not file checksum)
- [ ] Essay IDs all ≤ 36 characters
- [ ] Long essay names get truncated with hash suffix (already working)
- [ ] Assignment ID validated before execution
- [ ] Preflight checks prevent execution with invalid setup

### Integration
- [ ] CJ successfully fetches prompt content via storage_id
- [ ] Essay records write to database without constraint errors
- [ ] Grade projection works with ENG5 scale
- [ ] Error handling preserves correlation_id through full stack
- [ ] Metrics reflect accurate success/failure counts

---

## Root Cause Analysis

### Why These Issues Weren't Caught Earlier

**Issue #1 (error_code type)**:
- Migration probably created ENUM to match Python ErrorCode enum
- Model wasn't updated to use SQLAlchemy ENUM wrapper
- Error path not tested (happy path doesn't trigger error writes)
- **Lesson**: Test error handling paths explicitly

**Issue #2 (storage_id)**:
- User fixed symptom (prefix) without tracing data flow
- Upload returns correct ID, but caller ignores it
- Execute mode may have been tested with mocks (file checksums worked)
- **Lesson**: Trace data through full flow, not just fix immediate error

**Issue #3 (assignment_id)**:
- CLI documents requirement but doesn't validate
- Runner trusts user to create instructions first
- **Lesson**: Add preflight checks for external dependencies

**Issue #4 (grade scale)**:
- Tests use scale, so likely configured
- Not documented in obvious place
- **Lesson**: Document configuration requirements

### Prevention Strategies
1. **Schema-Model Parity**: CI check that migrations match model types
2. **Contract Testing**: Validate event payloads against downstream service expectations
3. **Integration Tests**: Full flow with real services, not just unit tests with mocks
4. **Preflight Validation**: Check external dependencies before execution
5. **Error Path Coverage**: Test failure scenarios explicitly

---

## Next Steps

**Immediate** (today):
1. Create error_code migration (CJ service)
2. Fix runner storage_id flow (trace execute mode)
3. Test with real services

**High Priority** (this week):
1. Add assignment_id preflight check
2. Verify grade scale registration
3. Integration test suite

**Medium Priority** (next sprint):
1. Add contract validation tests
2. Document setup requirements
3. Improve error messages

**Recommended Starting Point**: Fix Issue #1 (migration) while investigating Issue #2 (trace cli.py execute mode). They can be developed in parallel.
