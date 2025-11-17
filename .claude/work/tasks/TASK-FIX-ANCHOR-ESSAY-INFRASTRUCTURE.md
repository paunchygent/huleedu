# TASK: Fix Anchor Essay Infrastructure

**Status**: READY FOR REVIEW – verification complete
**Priority**: HIGH
**Blocking**: None
**Created**: 2025-11-13
**Completed**: (pending final sign-off)

---

## Validation Results (2025-11-14)

### ENG5 Execute Flow Smoke Test – PASSED

Validated the deployed anchor infrastructure with a local ENG5 runner execute invocation:

**Batch Details:**
- Batch label: `eng5-anchor-verify`
- Canonical batch UUID: generated at runtime (see CLI log `canonical batch UUID` banner)
- Assignment ID: `00000000-0000-0000-0000-000000000001`
- Comparisons: 5 pairs (via `--max-comparisons 5`, `--no-kafka` student-only flow)
- Command: `pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode execute --assignment-id ... --course-id ... --batch-id eng5-anchor-verify --no-kafka --max-comparisons 5 --cj-service-url http://localhost:9095 --content-service-url http://localhost:8001/v1/content`

**Success Criteria Met:**
- ✅ All required services healthy (content_service, cj_assessment_service, kafka disabled via `--no-kafka`)
- ✅ CJ preflight confirmed 12 anchors present (no re-upload fallback triggered)
- ✅ Student-only flow uploaded 3 sample essays to Content Service without 404s
- ✅ No `RESOURCE_NOT_FOUND` errors surfaced during execute run
- ✅ Artefacts generated under `.claude/research/data/eng5_np_2016/` (assessment stub + CJ request envelope)
- ✅ Supporting regression tests executed: `pdm run pytest-root scripts/tests/test_eng5_np_cli_validation.py scripts/tests/test_eng5_np_runner.py scripts/tests/test_eng5_np_execute_integration.py`

**Database Validation:**
- `../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic current` → `20251114_0900 (head)`
- 12 anchor references in `anchor_essay_references` (IDs 78–89) after cleanup + re-registration
- All anchors have valid `text_storage_id` references (HTTP 200 from `http://localhost:8001/v1/content/<id>`)
- Zero orphaned references observed in ENG5 assignment query

**Artefacts Generated:**
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/.claude/research/data/eng5_np_2016/assessment_run.execute.json`
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/.claude/research/data/eng5_np_2016/requests/els_cj_assessment_request_2025-11-14T10:05:02.237118+00:00.json`

**Note:** Grade projections were not generated in this test run (may require separate aggregation step or real LLM execution mode).

### Pre-deployment State (from commits)

**Infrastructure Changes (4 commits):**
1. `87b606dd` - Content Service PostgreSQL persistence
2. `7d263334` - Anchor uniqueness constraint and idempotent registration
3. `4c67e549` - Content Service migration removing legacy filesystem fallback (500+ lines)
4. `c405775b` - Health check simplification post-legacy removal

**Anchor Infrastructure:**
- Grade scale: `eng5_np_legacy_9_step`
- Filename pattern: `anchor_essay_eng_5_17_vt_XXX_GRADE.docx` (001-012)
- Unique constraint: `(assignment_id, anchor_label, grade_scale)`
- Persistent storage: PostgreSQL-backed (`huleedu_content.stored_content`)

---

## 2025-11-14 Status Update

- Phases 1–3 from the developer checklist (Content Service persistence, CJ anchor migrations, API upsert logic) landed in commits `87b606dd`, `7d263334`, `4c67e549`, and `c405775b`.
- Manual verification performed:
  - `pdm run dev-restart cj_assessment_service` + `../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic current` (ENG5 dev DB at `20251114_0900`).
  - SQL audits via `docker exec huleedu_cj_assessment_db ... SELECT constraint_name ...` and `SELECT COUNT(*), MIN(id), MAX(id) ...` confirmed the unique constraint + 12-row cleanup.
  - Python script fetched all 12 anchor `text_storage_id`s from Content Service (HTTP 200 each).
  - `pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --assignment-id ... register-anchors ...` (idempotent re-registration) and `--mode execute --no-kafka --max-comparisons 5` smoke test.
  - Regression tests covering R1/R2 + hydrator flows: `pdm run pytest-root scripts/tests/test_eng5_np_cli_validation.py scripts/tests/test_eng5_np_runner.py scripts/tests/test_eng5_np_execute_integration.py`.
- Verification evidence attached in the developer checklist; task now awaits final sign-off.

## Problem Statement

End-to-end batch processing fails with RESOURCE_NOT_FOUND errors when retrieving anchor essays from Content Service.

### Symptoms

- Database contains 60 anchor essay references for assignment `00000000-0000-0000-0000-000000000001`
- Expected: Only 12 anchor essays (one per grade level)
- Batch processing fails when trying to retrieve content for IDs 1-48
- Only IDs 49-60 successfully retrieve content

### Root Cause

**Content Service uses ephemeral file storage that is lost on container restart.**

---

## Investigation Findings

### 1. Query Location and Logic

**File**: `services/cj_assessment_service/implementations/db_access_impl.py:563-589`

```python
async def get_anchor_essay_references(
    self,
    session: AsyncSession,
    assignment_id: str,
    grade_scale: str | None = None,
) -> list[Any]:
    stmt = select(AnchorEssayReference).where(
        AnchorEssayReference.assignment_id == assignment_id
    )

    if grade_scale:
        stmt = stmt.where(AnchorEssayReference.grade_scale == grade_scale)

    result = await session.execute(stmt)
    return list(result.scalars().all())
```

**Issues Identified**:

- No `ORDER BY` clause - returns records in arbitrary order
- No `LIMIT` clause - fetches ALL matching records
- No deduplication logic
- Simple filter by `assignment_id` and optionally `grade_scale`

**Called From**: `services/cj_assessment_service/cj_core_logic/batch_preparation.py:329`

---

### 2. Upload Mechanism

**File**: `services/cj_assessment_service/api/anchor_management.py:108-115`

```python
anchor_ref = AnchorEssayReference(
    assignment_id=register_request.assignment_id,
    grade=register_request.grade,
    grade_scale=grade_scale,
    text_storage_id=storage_id,
)
session.add(anchor_ref)  # ← ALWAYS CREATES NEW RECORD
await session.flush()
```

**Issues Identified**:

- Always uses INSERT - never updates existing records
- No unique constraint on database table
- No deduplication check before insertion

**Database Schema**:

```sql
Table: anchor_essay_references
Indexes:
    "anchor_essay_references_pkey" PRIMARY KEY, btree (id)
    "ix_anchor_essay_references_assignment_id" btree (assignment_id)
    "ix_anchor_essay_references_grade" btree (grade)
    "ix_anchor_essay_references_grade_scale" btree (grade_scale)

MISSING: UNIQUE constraint on (assignment_id, grade, grade_scale)
```

---

### 3. Upload Timeline (2025-11-13)

Five separate upload operations created 60 records:

| Batch | Time (UTC) | IDs Created | Status |
|-------|------------|-------------|--------|
| 1 | 14:24 | 1-12 | ❌ Content lost |
| 2 | 14:53 | 13-24 | ❌ Content lost |
| 3 | 14:55 | 25-36 | ❌ Content lost |
| 4 | 16:19 | 37-48 | ❌ Content lost |
| 5 | 18:36 | 49-60 | ✅ Content exists |

**Critical Event**: Content Service restarted at **18:35:47 UTC**

---

### 4. Content Service Storage Details

#### Current Implementation (MVP)

- **Type**: File-based ephemeral storage
- **Path**: `/app/.local_content_store_mvp/` (inside container)
- **Persistence**: NONE - data lost on container restart
- **Impact**: All content uploaded before 18:35:47 UTC was wiped

#### Evidence from Logs

**Valid Uploads (IDs 49-60, after restart)**:

```
2025-11-13 18:36:10 [info] Stored content with ID: 54c995dc26de42568d75b4e3a89c2295
2025-11-13 18:36:10 [info] Stored content with ID: 51e3cddb66f5434385ca055ec738eb46
2025-11-13 18:36:10 [info] Stored content with ID: 445767ddf050483e8aed7112f4d912c4
```

**Failed Retrievals (IDs 1-48, before restart)**:

```
2025-11-13 18:37:45 [warning] Content download failed: content with ID 'f54e560cb23c4e69985f3d90c621f8f4' not found
2025-11-13 18:37:45 [warning] Content download failed: content with ID '67fbdbc9adae449ead3708b72717998c' not found
```

#### Storage ID Validity

| ID Range | Upload Time | Storage ID Example | Valid? | Reason |
|----------|-------------|-------------------|--------|--------|
| 1-12 | 14:24 (4h before restart) | f54e560cb23c4e69985f3d90c621f8f4 | ❌ | Pre-restart |
| 13-24 | 14:53 (3.7h before restart) | 3b5a9c3c53964e8a837271bd0eb7bfb7 | ❌ | Pre-restart |
| 25-36 | 14:55 (3.6h before restart) | e2a07e22ec504cf8886552256966daaf | ❌ | Pre-restart |
| 37-48 | 16:19 (2.3h before restart) | 5391cc20da3e4ca0aca41e3c478e1144 | ❌ | Pre-restart |
| 49-60 | 18:36 (23s after restart) | 54c995dc26de42568d75b4e3a89c2295 | ✅ | Post-restart |

---

## Implementation Plan

This task is implemented in three phases. The parent document stays **architectural and intent-focused**; detailed steps, code sketches, and commands live in the child checklist:

- `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE-CHECKLIST.md` – developer playbook.

### Phase 1: Content Service persistence

**Goal**: Replace Content Service’s ephemeral filesystem storage with a PostgreSQL-backed store that matches existing service patterns.

**Key outcomes**:

- Stored content survives container restarts.
- Content is addressable by a stable `content_id` used across File Service, CJ, ENG5 runners, etc.
- Content Service exposes a **single protocol** for persistence (repository or store abstraction), with:
  - A `StoredContent` model that includes bytes, size, timestamps, correlation_id, and `content_type` for HTTP semantics.
  - A repository implementation that owns its own `AsyncSession` lifecycle and raises `RESOURCE_NOT_FOUND` on missing content.
- DI and config follow the `file_service` pattern:
  - `DATABASE_URL` computed via `SecureServiceSettings`.
  - A dedicated `content_service_db` in `docker-compose.infrastructure.yml`.

**Implementation guidance**:

- Use `services/file_service/` as the reference for:
  - Database model layout and metadata.
  - Repository + protocol patterns.
  - DI wiring and `DATABASE_URL` conventions.
- Keep routes thin:
  - Inject only the protocol (not sessions/engines).
  - Delegate all DB work and error semantics to the repository.
- For concrete steps (models, protocols, DI, migrations, Docker, manual curl checks), follow **Phase 1** in the child checklist.

### Phase 2: Anchor uniqueness and cleanup

**Goal**: Ensure CJ uses a clean, non-duplicated set of anchors for each assignment and prevent future duplicates at the database level.

**Key outcomes**:

- `anchor_essay_references` enforces uniqueness per `(assignment_id, anchor_label, grade_scale)`
  combination, allowing multiple anchors at the same grade as long as their labels differ.
- ENG5 dev data is cleaned so only the post-restart anchor set (IDs 49–60) remains for the test assignment.
- A unique constraint enforces the invariant for all future writes.

**Design points**:

- Anchors are **assignment-scoped** today and use `assignment_id` as the join key to `AssessmentInstruction`.
- The database uniqueness invariant is ultimately defined on `(assignment_id, anchor_label, grade_scale)`
  so that identity is filename/label-based, not grade-based. This permits multiple anchors per grade
  while still giving a stable key for idempotent registration.
- Cleanup for ENG5 is explicitly scoped to the known test assignment and grade scale to avoid touching any future/production data.

**Implementation guidance**:

- Add CJ Alembic migrations that:
  - Delete stale ENG5 duplicates created before the Content Service persistence fix (dev-only cleanup).
  - Introduce a transitional unique constraint `uq_anchor_assignment_grade_scale` on
    `(assignment_id, grade, grade_scale)` for the cleaned ENG5 data set.
  - Add an `anchor_label` column, backfill existing rows with deterministic synthetic labels, and
    replace the grade-based constraint with `uq_anchor_assignment_label_scale` on
    `(assignment_id, anchor_label, grade_scale)`.
- Add migration tests to exercise:
  - Upgrade from a clean database.
  - Duplicate-prevention behaviour.
  - Basic NULL semantics (for documentation only, not relied on in current flows).
- For exact SQL snippets, test structure, and verification commands, follow **Phase 2** and **Phase 2.5** in the child checklist.

### Phase 3: Anchor upsert and ENG5 runner verification

**Goal**: Make anchor registration idempotent at the `(assignment_id, anchor_label, grade_scale)` key
and prove that ENG5 execute flows run cleanly end-to-end while supporting multiple anchors per grade.

**Key outcomes**:

- Registering anchors for the same `(assignment_id, anchor_label, grade_scale)` updates the existing
  row instead of creating duplicates.
- The CJ anchor registration API remains stable (still returns `anchor_id`, `storage_id`, and `grade_scale`).
- ENG5 runner execute-mode uses the corrected anchor set without `RESOURCE_NOT_FOUND` errors from Content Service.

**Design points**:

- Upsert logic should live in the **CJ repository implementation**, not directly in the API handler:
  - The repository can implement a Postgres `INSERT ... ON CONFLICT ... DO UPDATE` or an explicit select-then-update pattern.
  - It should return the `anchor_id` so the handler can preserve the response contract.
- `register_anchor_essay` should:
  - Resolve `grade_scale` via `AssessmentInstruction` using `assignment_id`.
  - Store essay text via Content Service (storage-by-reference, no inline text).
  - Delegate anchor persistence to the repository’s upsert method.

**ENG5 filename convention (for anchors)**:

- ENG5 anchor essays are named like `anchor_essay_0001_F+.txt`.
- `anchor_label` is the filename stem (e.g. `anchor_essay_0001_F+`).
- `grade` is inferred from the last underscore-separated token in the stem (e.g. `F+`).

**Implementation guidance**:

- Follow **Phase 3** in the child checklist for:
  - Repository method signature and upsert pattern.
  - API changes in `anchor_management.py`.
  - Unit/integration tests that verify row-count stability and updated `text_storage_id`.
- Use the ENG5 CLI flows described in the checklist to validate that:
  - Re-registering anchors does not create extra rows.
  - The ENG5 execute flow completes successfully with anchors and grade projections in place.

---

## Understanding Nullable assignment_id

**Current reality**

- `AnchorEssayReference` is **assignment-scoped** today.
- All anchors used by ENG5 / CJ flows are created with a **non-NULL `assignment_id`**.
- There is **no `course_id` column** on `anchor_essay_references`, and no logic that loads anchors by course.

**Relationship to AssessmentInstruction**

- `AssessmentInstruction` supports two scopes via an XOR constraint:
  - Assignment-level (`assignment_id` NOT NULL, `course_id` NULL)
  - Course-level (`assignment_id` NULL, `course_id` NOT NULL)
- For ENG5 and current CJ batches, anchors are **only** attached to the assignment-level scope:
  - `assignment_id` is the join key between AssessmentInstruction and AnchorEssayReference.
  - Grade scale and prompt/rubric references come from AssessmentInstruction.

**Why is `assignment_id` nullable on AnchorEssayReference?**

- The column is declared nullable to leave room for a future design where anchors might also exist at course scope.
- That future has **not** been modeled yet:
  - There is no `course_id` on the anchor table.
  - There is no code path that queries anchors by course.

**Implications for this migration**

- The unique constraint `UNIQUE (assignment_id, grade, grade_scale)` is intentionally defined for **assignment-level anchors only**.
- We do **not** rely on PostgreSQL's `NULL` semantics here; real anchors always have `assignment_id` set.
- When/if we add course-level anchors, we will do so via a dedicated schema change (e.g. adding `course_id` to the anchor table and defining explicit uniqueness rules), not by overloading NULL `assignment_id` rows.

---

### Phase 2.5: Create Migration Test (Rule 085.4)

**File**: `services/cj_assessment_service/tests/integration/test_anchor_unique_migration.py`

**Pattern**: Based on `test_judge_rubric_migration.py` and `test_error_code_migration.py`

**Required Tests**:

1. `test_migration_upgrade_from_clean_database` - MANDATORY smoke test
2. `test_constraint_prevents_duplicate_assignment_anchors` - Verify uniqueness
3. `test_constraint_allows_null_assignment_id_duplicates` - Verify NULL behavior
4. `test_migration_idempotency` - Guard against DDL conflicts

**Run**: `pdm run pytest-root services/cj_assessment_service/tests/integration/test_anchor_unique_migration.py -v`

---

### Phase 3: Implement Upsert Logic in API

**Objective**: Update existing anchors instead of creating duplicates

**File**: `services/cj_assessment_service/api/anchor_management.py:108-115`

**New repository method** (using SQLAlchemy upsert; the API handler should call this,
not embed raw SQL directly):

```python
from sqlalchemy.dialects.postgresql import insert

stmt = insert(AnchorEssayReference).values(
    assignment_id=register_request.assignment_id,
    grade=register_request.grade,
    grade_scale=grade_scale,
    text_storage_id=storage_id,
)

stmt = stmt.on_conflict_do_update(
    constraint='uq_anchor_assignment_grade_scale',
    set_={'text_storage_id': storage_id}
)

await session.execute(stmt)
await session.flush()
```

**Testing**:

1. Upload 12 anchor essays
2. Upload same 12 anchor essays again
3. Verify database still contains exactly 12 records (not 24)
4. Verify `text_storage_id` values updated to latest uploads

---

## Files to Modify

### Phase 1: Content Service Database Migration

1. `services/content_service/models_db.py` - NEW: Database model
2. `services/content_service/protocols.py` - Add ContentRepositoryProtocol
3. `services/content_service/implementations/content_repository_impl.py` - NEW: DB repository
4. `services/content_service/implementations/mock_content_repository.py` - NEW: Mock for tests
5. `services/content_service/di.py` - Wire up repository and session
6. `services/content_service/api/content_routes.py` - Use repository instead of file store
7. `services/content_service/config.py` - Add DATABASE_URL
8. `services/content_service/alembic/` - Initialize and create migration
9. `docker-compose.infrastructure.yml` - Add content_db service and volume

### Phase 2: CJ Assessment Constraint Migration

10. `services/cj_assessment_service/alembic/versions/[NEW]` - Unique constraint + cleanup

### Phase 2.5: Migration Test

11. `services/cj_assessment_service/tests/integration/test_anchor_unique_migration.py` - NEW

### Phase 3: CJ Assessment Upsert

12. `services/cj_assessment_service/api/anchor_management.py:108-115` - Upsert logic

---

## Testing Plan

### After Phase 1 (Content Persistence)

```bash
# Upload, restart service, verify content persists
curl -X POST http://localhost:8001/v1/content -H "Content-Type: application/json" -d '{"content": "test", "metadata": {}}'
pdm run dev-restart content_service
curl http://localhost:8001/v1/content/{storage_id}  # Should succeed
```

### After Phase 2 (Constraint Migration)

```bash
# Run batch processing - should succeed with clean anchor data
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode execute \
  --assignment-id 00000000-0000-0000-0000-000000000001 --course-id 00000000-0000-0000-0000-000000000002 \
  --batch-id test-$(date +%Y%m%d-%H%M) --max-comparisons 5 --kafka-bootstrap localhost:9093 \
  --await-completion --completion-timeout 30 --verbose
```

Expected: No RESOURCE_NOT_FOUND errors

### After Phase 2.5 (Migration Test)

```bash
pdm run pytest-root services/cj_assessment_service/tests/integration/test_anchor_unique_migration.py -v
```

Expected: All 4 tests pass

### After Phase 3 (Upsert Implementation)

```bash
# Upload anchors twice - second upload should update, not duplicate
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode register-anchors \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --anchors scripts/cj_experiments_runners/eng5_np/data/eng5_np_anchor_essays.json

# Verify only 12 records exist (not 24)
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment \
  -c "SELECT COUNT(*) FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001';"
```

Expected: COUNT=12

---

## Success Criteria

- ✅ Content Service storage persists across container restarts
- ✅ Database contains exactly 12 anchor references for test assignment
- ✅ All anchor storage IDs valid in Content Service
- ✅ Migration test passes (rule 085.4 compliance)
- ✅ Batch processing completes without RESOURCE_NOT_FOUND errors
- ✅ Database constraint prevents duplicate anchors
- ✅ Re-uploading anchors updates existing records (no duplicates)
- ✅ End-to-end metadata passthrough test passes

---

## Related Tasks

- `TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` - Metadata passthrough implementation (COMPLETE)
- `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE-CHECKLIST.md` - Developer checklist and step-by-step implementation guide for this task
- This task unblocks end-to-end testing of metadata passthrough feature

---

## Notes

- CJ Assessment DB was reset on 2025-11-13, so all 60 records were created same day
- The duplicate upload issue is a workflow problem (manual re-uploads), not a code bug
- Content Service restart was the triggering event that exposed the storage issue
- Root cause: Content Service used ephemeral file storage instead of persistent database
- Solution: Migrate to PostgreSQL-backed storage following established File Service pattern
- **Pattern Compliance**: Phase 2 migration combines cleanup + constraint following `20250719_0003_add_content_idempotency_constraints.py`
- **Migration Testing**: Phase 2.5 follows rule 085.4 mandatory smoke test pattern
- **Nullable assignment_id**: Intentional design supporting both assignment-level and future course-level anchors
