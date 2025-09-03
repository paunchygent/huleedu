Title: ELS-004 — Single-Statement DB Assignment (Option A) then Inventory Refactor (Option B)

Summary
- Replace multi-round-trip content→slot assignment with a single SQL statement (Option A), then simplify the data model by using essay_states as the slot inventory (Option B).
- Scope is prototype/dev only: no deployment work. Focus on correctness, concurrency, and measured performance improvements in the distributed tests.

Context
- Current DB-first coordination works, but performance tails are high due to multiple DB round-trips and contention backoffs:
  - Batch tracker lookup
  - Slot assignment (UPDATE with FOR UPDATE SKIP LOCKED) + idempotency retries
  - Essay state creation/update
  - Event publishing (mock/outbox in tests)
- Recent regressions highlighted that slot assignment must run in its own transaction for cross-process visibility (MVCC). We’ve restored that. Now we target fewer round-trips and simpler model.

Goals
- Option A: Implement a single-statement content assignment that:
  - Handles idempotency (duplicate text_storage_id) and slot selection atomically
  - Updates slot_assignments and upserts essay_states in one server round-trip
  - Returns the final essay_id and whether it was created vs reused
- Option B: Migrate hot path to treat essay_states as the slot inventory (deprecate slot_assignments in hot path), reducing writes to 1 UPDATE per assignment
- Keep tests green and improve metrics:
  - test_cross_instance_slot_assignment: avg < 0.2s
  - test_high_concurrency_slot_assignment_performance: P95 < 0.5s

Non-Goals
- No production rollout or infra changes
- No broad redesign of unrelated components

Relevant Rules for Onboarding
- .cursor/rules/015-project-structure-standards.mdc
- .cursor/rules/080-repository-workflow-and-tooling.mdc
- .cursor/rules/042-async-patterns-and-di.mdc
- .cursor/rules/050-python-coding-standards.mdc
- .cursor/rules/048-structured-error-handling-standards.mdc
- .cursor/rules/070-testing-standards.mdc
- .cursor/rules/110-ai-agent-interaction-modes.mdc (110.1 Planning, 110.2 Coding)

Acceptance Criteria
- Option A behind a feature flag (default off) passes the distributed tests when enabled:
  - 20/20 idempotent duplicate provisions return True (no IntegrityErrors surfaced)
  - Cross-instance assignment: 6/6 succeed; avg < 0.2s
  - High-concurrency performance: exactly N successes for N essays; P95 < 0.5s
- Option B behind a separate flag (default off) passes the same tests and meets or beats Option A metrics.

Option A — Single-Statement Assignment + Upsert

Design Overview
- Introduce a consolidated SQL executed once per content provision. Pseudocode outline:
  1) existing AS (select sa.internal_essay_id from slot_assignments sa join batch_essay_trackers t on t.id = sa.batch_tracker_id where t.batch_id = :batch_id and sa.text_storage_id = :tsid limit 1)
  2) grab AS (select sa.id, sa.internal_essay_id from slot_assignments sa join batch_essay_trackers t on t.id = sa.batch_tracker_id where t.batch_id = :batch_id and sa.status = 'available' and not exists (select 1 from existing) order by sa.internal_essay_id limit 1 for update skip locked)
  3) upd AS (update slot_assignments s set status='assigned', text_storage_id=:tsid, original_file_name=:fname, assigned_at=now() from grab g where s.id=g.id returning g.internal_essay_id)
  4) chosen AS (select internal_essay_id from existing union all select internal_essay_id from upd limit 1)
  5) upsert AS (insert into essay_states(essay_id,batch_id,current_status,processing_metadata,storage_references,timeline,text_storage_id,updated_at)
                values ((select internal_essay_id from chosen), :batch_id, :status, :proc_meta_json, :storage_json, :timeline_json, :tsid, now())
                on conflict (essay_id) do update
                set current_status=:status, processing_metadata=:proc_meta_json, storage_references=:storage_json, timeline=:timeline_json, text_storage_id=:tsid, updated_at=now()
                returning essay_id)
  6) Final select returns (select essay_id from upsert)
- Idempotency safeguards: rely on the existing partial unique index on (batch_tracker_id, text_storage_id) in slot_assignments, and a partial unique index on (batch_id, text_storage_id) in essay_states (NULLs allowed) when Option B lands.

Feature Flag
- Add Settings flag: ELS_USE_CTE_UPSERT_ASSIGNMENT (default False)
- When True, ContentAssignmentService uses the consolidated SQL path; otherwise use current two-step path.

Implementation Steps (A)
- Add configuration flag in services/essay_lifecycle_service/config.py
- Create DAO helper for consolidated SQL (new module or extend essay_repository_idempotency.py):
  - services/essay_lifecycle_service/implementations/assignment_sql.py (new)
  - Provide one async function: assign_and_upsert_single_statement(session, batch_id, text_storage_id, original_file_name, file_size, content_hash, initial_status, correlation_id) -> tuple[bool, str]
- Wire into ContentAssignmentService:
  - If flag enabled: open a session.begin() and call DAO once; publish event; check completion.
  - Keep slot assignment transaction boundaries as-is when the flag is off (no behavior change).
- Tests:
  - Reuse existing distributed tests; add one unit test invoking DAO directly with a real engine via testcontainers for schema created by Base.metadata.create_all.

Affected Files (A)
- services/essay_lifecycle_service/config.py (new flag)
- services/essay_lifecycle_service/implementations/assignment_sql.py (new)
- services/essay_lifecycle_service/domain_services/content_assignment_service.py (conditional path)
- services/essay_lifecycle_service/implementations/essay_repository_idempotency.py (optional helper re-use)
- services/essay_lifecycle_service/tests (no behavior change required; add focused unit test for DAO)

Notes & Risks (A)
- Advisory locks: Keep optional USE_ADVISORY_LOCKS_FOR_ASSIGNMENT True/False to reduce duplicate storm tails. With the single-statement approach, duplicates primarily short-circuit at step (1), but advisory locks still help by preventing work duplication under collision.
- Logging: On the hot path, keep logs at INFO minimal to avoid measurable overhead under capture.

Option B — Use essay_states as Inventory (Deprecate slot_assignments from Hot Path)

Design Overview
- Treat essay_states as the single source of truth for inventory and status. At batch registration, essay rows already exist (current code creates them). Slot assignment becomes a single UPDATE:
  - UPDATE essay_states
    SET current_status=:ready_status,
        text_storage_id=:tsid,
        processing_metadata=:proc_meta_json,
        storage_references=:storage_json,
        timeline=:timeline_json,
        updated_at=now()
    WHERE batch_id=:batch_id AND current_status=:available_status
    ORDER BY essay_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
    RETURNING essay_id
- Idempotency: partial unique index on (batch_id, text_storage_id) where text_storage_id is not null.
- Batch completion: counts and ready_essays now derive from essay_states only.

Feature Flag
- Add Settings flag: ELS_USE_ESSAY_STATES_AS_INVENTORY (default False)
- When True, ContentAssignmentService bypasses slot_assignments entirely and uses the UPDATE-on-essay_states approach.

Implementation Steps (B)
- Model/index changes in services/essay_lifecycle_service/models_db.py:
  - Add partial unique index on essay_states(batch_id, text_storage_id) where text_storage_id IS NOT NULL
  - Ensure statuses include a clear available/registered value used at registration and a ready/assigned value used at content assignment
- DAO path for assignment:
  - services/essay_lifecycle_service/implementations/assignment_sql.py: add assign_via_essay_states(session, ...)
- Update ContentAssignmentService to honor the new flag and select the essay_states path.
- Update batch completion and status queries to rely on essay_states only where needed (many are already essay_states-based).
- Keep slot_assignments in DB for now (metrics/back-compat), but remove it from the hot path; you may choose to backfill or soft-deprecate it later.

Affected Files (B)
- services/essay_lifecycle_service/config.py (new flag)
- services/essay_lifecycle_service/models_db.py (partial unique index on essay_states)
- services/essay_lifecycle_service/implementations/assignment_sql.py (add function)
- services/essay_lifecycle_service/domain_services/content_assignment_service.py (conditional path)
- services/essay_lifecycle_service/implementations/batch_tracker_persistence.py (if any slot_assignments pre-seeding can be reduced or guarded by flag)
- tests: no changes expected; existing suites validate concurrency and performance

Validation & Testing
- From repo root:
  - pdm run pytest services/essay_lifecycle_service/tests/distributed/test_concurrent_slot_assignment.py -xvs
  - pdm run test-all
- Toggle flags independently to compare:
  - ELS_USE_CTE_UPSERT_ASSIGNMENT=true (Option A on)
  - ELS_USE_ESSAY_STATES_AS_INVENTORY=true (Option B on)
  - USE_ADVISORY_LOCKS_FOR_ASSIGNMENT=true to stabilize duplicate storms (optional)
- Targets:
  - Idempotent duplicates: 20/20 True
  - Cross-instance avg < 0.2s
  - High-concurrency P95 < 0.5s

Rollout/Toggle Strategy (Prototype Only)
- Default flags off; run baseline tests
- Enable Option A only; measure and compare
- If satisfied, enable Option B only; measure and compare
- Do not enable both until each is validated individually

Backout Plan
- Flags off returns to the current, known-good path
- No migrations required for tests; models-driven create_all ensures tables and indexes are present for the prototype

Implementation Tips
- Follow .cursor/rules/048-structured-error-handling-standards.mdc for surfacing DB errors through HuleEduError wrappers
- Keep SQL parameterized and prefer text() with named binds
- Reuse existing JSON shaping for processing_metadata, storage_references, and timeline; avoid duplicating mapping logic where EssayRepositoryMappers can help
- Keep logs concise at INFO on success paths; add DEBUG for detailed timings when needed

Timebox & Ownership
- Option A implementation + tests: 1–2 days
- Option B implementation + tests: 2–3 days (model/index touch + wiring)

