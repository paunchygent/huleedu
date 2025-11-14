# TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE – Developer Checklist

This checklist is a child document for `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md`.

It is intended for the engineer implementing the fix and verifying that ENG5 / CJ flows work end-to-end with persistent anchors.

---

## Phase 1 – Content Service: Database-backed storage

### 1. Implement models and protocols

- [x] **Add `StoredContent` model**
  - File: `services/content_service/models_db.py`
  - Implement table `stored_content` with:
    - `content_id: String(32)` – primary key (UUID hex)
    - `content_data: LargeBinary` – raw bytes
    - `content_size: Integer` – byte length
    - `created_at: DateTime(timezone=True)` – indexed, `server_default=func.current_timestamp()`
    - `correlation_id: PostgresUUID(as_uuid=True) | None`
    - `content_type: String(100)` – NOT NULL, MIME type (e.g. `text/plain`)

- [x] **Add `ContentRepositoryProtocol`**
  - File: `services/content_service/protocols.py`
  - Methods:
    - `save_content(content_id: str, content_data: bytes, content_type: str, correlation_id: UUID | None = None) -> None`
    - `get_content(content_id: str, correlation_id: UUID | None = None) -> bytes`
    - `content_exists(content_id: str) -> bool`

- [x] **Implement `ContentRepository`**
  - File: `services/content_service/implementations/content_repository_impl.py`
  - Responsibilities:
    - Own `AsyncEngine` and `async_sessionmaker`.
    - `_get_session()` context manager commits / rolls back and closes sessions.
    - `save_content()` inserts `StoredContent` with `content_type` and logs via `create_service_logger`.
    - `get_content()` selects by `content_id`, raises `raise_resource_not_found` if missing.
    - `content_exists()` returns boolean.

- [x] **Implement `MockContentRepository` for tests**
  - File: `services/content_service/implementations/mock_content_repository.py`
  - Simple in-memory `dict[str, bytes]` store implementing `ContentRepositoryProtocol`.

### 2. Wire DI and config

- [x] **Add `DATABASE_URL` to Content Service `Settings`**
  - File: `services/content_service/config.py`
  - Follow `file_service.config.Settings.DATABASE_URL` pattern.
  - Use env prefix `CONTENT_SERVICE_`, external dev port `5445`, docker host `content_service_db`.

- [x] **Add DI provider for engine + repository**
  - File: `services/content_service/di.py`
  - Create provider (or extend existing) to:
    - Provide `Settings` (existing).
    - Provide `AsyncEngine` via `create_async_engine(settings.DATABASE_URL, ...)`.
    - Provide `ContentRepositoryProtocol` using `ContentRepository(engine)`.

### 3. Update HTTP routes (Content Service)

- [x] **Inject repository instead of filesystem store**
  - File: `services/content_service/api/content_routes.py`
  - For `POST /v1/content`:
    - Inject `FromDishka[ContentRepositoryProtocol]` instead of `ContentStoreProtocol` (or adjust store to delegate to repo).
    - Generate `content_id = uuid.uuid4().hex`.
    - Pass `content_type` (from `Content-Type` header, fallback to `text/plain`) to `save_content()`.
  - For `GET /v1/content/<content_id>`:
    - Validate `content_id` format as today.
    - Call `get_content(content_id, correlation_id)` to get bytes.
    - Return a `Response` with:
      - Body = bytes
      - `Content-Type` = `content_type` from DB (if exposed) or `application/octet-stream` as a safe default.

- [x] **Update or add unit tests for metrics and error handling**
  - File: `services/content_service/tests/unit/test_content_routes_metrics.py`
  - Ensure metrics behavior is unchanged (success, not_found, error paths).

### 4. Database and docker-compose

- [x] **Create Alembic migration for `stored_content`**
  - Directory: `services/content_service/alembic/`
  - Commands:
    - `cd services/content_service`
    - `pdm run alembic init alembic` (first time only)
    - Configure `alembic.ini` and `env.py` to use `StoredContent` metadata.
    - `pdm run alembic revision --autogenerate -m "Create stored_content table"`
    - Review migration; ensure all columns and indexes are correct.

- [x] **Add Postgres container for Content Service**
  - File: `docker-compose.infrastructure.yml`
  - Add `content_service_db` service following `file_service_db` pattern.
  - Expose port `5445` for local dev.

- [x] **Run and verify migration**
  - Commands:
    - `pdm run dev-build-start content_service`
    - `cd services/content_service`
    - `pdm run alembic upgrade head`
    - `pdm run alembic current`

### 5. Manual verification (persistence)

- [x] **Upload content and capture `storage_id`**
  - `curl -X POST http://localhost:8001/v1/content -H "Content-Type: text/plain" -d 'test content for persistence'`

- [x] **Verify row in `stored_content`**
  - `docker exec huleedu_content_service_db psql -U "$HULEEDU_DB_USER" -d huleedu_content -c "SELECT content_id, content_size, content_type FROM stored_content;"`

- [x] **Restart Content Service and re-fetch**
  - `pdm run dev-restart content_service`
  - `curl http://localhost:8001/v1/content/{content_id}`
  - Expect: same bytes, no 404, Content Service logs show DB access.

---

## Phase 2 – Anchor uniqueness and cleanup

### 1. Add Alembic migration in CJ Assessment Service

- [x] **Create migration skeleton**
  - `cd services/cj_assessment_service`
  - `pdm run alembic revision -m "Add unique constraint to anchor_essay_references"`

- [x] **Implement upgrade() cleanup + constraint**
  - File: `services/cj_assessment_service/alembic/versions/<revision>_add_anchor_unique_constraint.py`
  - In `upgrade()`:
    - Step 1: Development-only cleanup for ENG5 test data:
      - `DELETE FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001' AND grade_scale = 'swedish_8_anchor' AND id < 49;`
      - Comment explicitly that this is scoped to ENG5 dev assignment and safe because no production anchors exist yet.
    - Step 2: Add unique constraints in two steps:
      - First migration: introduce transitional `uq_anchor_assignment_grade_scale` on
        `(assignment_id, grade, grade_scale)` for cleaned ENG5 data (migration `20251114_0230`).
      - Second migration: add `anchor_label`, backfill existing rows, and replace the grade-based
        constraint with `uq_anchor_assignment_label_scale` on
        `(assignment_id, anchor_label, grade_scale)` (migration `20251114_0900`).

- [x] **Implement downgrade()**
  - Drop `uq_anchor_assignment_label_scale` and `anchor_label` in the latest migration; earlier
    migration drops `uq_anchor_assignment_grade_scale` when downgrading past the transitional
    step. No attempt is made to restore deleted rows.
  - No attempt to restore deleted rows.

### 2. Add migration tests (Rule 085.4)

- [x] **Create integration test file**
  - File: `services/cj_assessment_service/tests/integration/test_anchor_unique_migration.py`

- [x] **Test: upgrade from clean database**
  - `test_migration_upgrade_from_clean_database`
  - Start from empty DB, apply migration, assert constraint exists (via `information_schema.table_constraints`).

- [x] **Test: constraint prevents duplicates**
  - `test_constraint_prevents_duplicate_assignment_anchors`
  - Insert one row for a given `(assignment_id, grade, grade_scale)`.
  - Attempt to insert a second row with the same triple and assert `IntegrityError`.

- [x] **Test: constraint behavior with NULL assignment_id (current design)**
  - `test_constraint_allows_null_assignment_id_duplicates` (optional but informative).
  - Insert multiple rows with `assignment_id = NULL` and same `(grade, grade_scale)` and assert success.
  - Document in test docstring that we do **not** rely on this in production today; it is only checking PG semantics.

- [x] **Test: migration idempotency**
  - `test_migration_idempotency`
  - Apply migration, then re-run `upgrade()` logic in a controlled way or verify that running migrations from a pre-migration DB twice (reset DB) does not fail.

### 3. Manual verification

- [ ] **Run migration against ENG5 dev DB**
  - `pdm run dev-restart cj_assessment_service`
  - `cd services/cj_assessment_service`
  - `pdm run alembic upgrade head`

- [ ] **Check constraint and cleanup**
  - Constraint:
    - `docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c "SELECT constraint_name FROM information_schema.table_constraints WHERE table_name = 'anchor_essay_references' AND constraint_type = 'UNIQUE';"`
    - Expect to see `uq_anchor_assignment_label_scale` as the effective uniqueness constraint for
      assignment-scoped anchors.
  - ENG5 assignment row count:
    - `docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c "SELECT COUNT(*), MIN(id), MAX(id) FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001';"`
    - Expect: `COUNT = 12`, `MIN >= 49`.

---

## Phase 3 – Anchor upsert logic

### 1. Add repository-level upsert

- [x] **Extend CJ repository implementation**
  - File: `services/cj_assessment_service/implementations/db_access_impl.py`
  - Add method (example signature):
    - `async def upsert_anchor_reference(self, session: AsyncSession, *, assignment_id: str, anchor_label: str, grade: str, grade_scale: str, text_storage_id: str) -> int:`
  - Implementation options:
    - Option A: `insert(...).on_conflict_do_update(constraint="uq_anchor_assignment_label_scale", set_={"text_storage_id": text_storage_id, "grade": grade}).returning(AnchorEssayReference.id)`.
    - Option B: `SELECT` then explicit update/insert (constraint remains a safety net).
  - Return the `anchor_id` so the API can preserve its response contract.

### 2. Update anchor registration API to use repository

- [x] **Update `register_anchor_essay` handler**
  - File: `services/cj_assessment_service/api/anchor_management.py`
  - Keep responsibilities:
    - Parse and validate JSON.
    - Use `CJRepositoryProtocol.get_assignment_context()` to resolve `grade_scale` for the provided `assignment_id`.
    - Validate `grade` against `grade_scale` with `validate_grade_for_scale`.
    - Store essay text in Content Service via `ContentClientProtocol.store_content()`.
  - Replace direct `AnchorEssayReference` construction and `session.add()` with a call to `repository.upsert_anchor_reference(...)`.
  - Response should still include:
    - `anchor_id` (from repository return value).
    - `storage_id` (Content Service storage ID).
    - `grade_scale`.
    - `status: "registered"`.

### 3. Tests for upsert behavior

- [x] **Add/extend unit tests for `register_anchor_essay`**
  - File: `services/cj_assessment_service/tests/unit/test_anchor_management.py` (or create if missing).
  - Cases:
    - First registration for `(assignment_id, anchor_label, grade_scale)` creates anchor.
    - Second registration with same triple updates `text_storage_id` and does **not** increase row count.

- [x] **Add repository-level tests**
  - File: `services/cj_assessment_service/tests/integration/test_anchor_repository_upsert.py` (optional but recommended).
  - Verify that upsert uses the unique constraint correctly and returns the expected `anchor_id`.

### 4. End-to-end ENG5 flow verification

- [ ] **Re-register ENG5 anchors**
  - Use CJ admin CLI or HTTP API to register the 12 anchors for ENG5 assignment.
  - Re-run registration once more to confirm no duplicates and updated `text_storage_id`.

- [ ] **Run ENG5 execute flow**
  - Command (example):
    - `pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode execute --assignment-id 00000000-0000-0000-0000-000000000001 --course-id 00000000-0000-0000-0000-000000000002 --batch-id test-$(date +%Y%m%d-%H%M) --max-comparisons 5 --kafka-bootstrap localhost:9093 --await-completion --completion-timeout 30 --verbose`
  - Expectations:
    - No `RESOURCE_NOT_FOUND` errors from Content Service.
    - CJ completes successfully and grade projections are generated.

---

## Final success checklist (matches parent task)

- [x] Content Service storage persists across container restarts.
- [ ] Database contains exactly 12 anchor references for ENG5 test assignment after cleanup.
- [ ] All anchor `text_storage_id` values are valid in Content Service (no 404 on fetch).
- [x] Migration test suite passes (Rule 085.4 compliance).
- [ ] Batch processing completes without `RESOURCE_NOT_FOUND` errors.
- [x] Database constraint prevents duplicate anchors.
- [x] Re-uploading anchors updates existing records (no duplicate rows).
- [ ] End-to-end ENG5 metadata passthrough test passes.
