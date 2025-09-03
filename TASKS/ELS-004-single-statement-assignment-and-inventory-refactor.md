Title: ELS-004 — Use essay_states As Inventory (Option B First), Option A As Fallback

Summary
- PRIORITY: Implement Option B to treat `essay_states` as the slot inventory (single-table, single-UPDATE hot path). This simplifies the model and materially reduces latency and contention.
- OPTIONAL/FALLBACK: Keep Option A (single-statement CTE+upsert against current two-table model) available behind a separate flag if needed later.
- Prototype/dev scope only: no deployment. Focus on correctness, concurrency, and performance measured by distributed tests.

Context
- Current DB-first coordination works, but performance tails are high due to multiple DB round-trips and contention backoffs:
  - Batch tracker lookup
  - Slot assignment (UPDATE with FOR UPDATE SKIP LOCKED) + idempotency retries
  - Essay state creation/update
  - Event publishing (mock/outbox in tests)
- Recent regressions highlighted that slot assignment must run in its own transaction for cross-process visibility (MVCC). We’ve restored that. Now we target fewer round-trips and simpler model.

Goals
- Option B FIRST: Migrate hot path to treat `essay_states` as the slot inventory, reducing writes to a single UPDATE per assignment.
  - Preserve idempotency (duplicate text_storage_id within the batch returns True for all callers and consumes only one slot).
  - Keep `slot_assignments` for metrics/observability only (no hot-path writes).
  - Meet/exceed targets:
    - test_cross_instance_slot_assignment: avg < 0.2s
    - test_high_concurrency_slot_assignment_performance: P95 < 0.5s (target stretch < 0.3s)
- Option A (fallback): Provide a single-statement CTE+upsert path behind a flag if Option B hits unforeseen issues.

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
- Option B behind a feature flag (default off) passes distributed tests when enabled:
  - Idempotent duplicates: 20/20 True; only 1 essay row updated.
  - Cross-instance assignment: 6/6 succeed; avg < 0.2s.
  - High-concurrency performance: exactly N successes for N essays; P95 < 0.5s (goal < 0.3s).
- Option A remains documented as fallback and can be enabled separately if needed; not required to implement first.

Option B — Use essay_states as Inventory (Deprecate slot_assignments from Hot Path) — PRIORITY

Design Overview
- Treat `essay_states` as the single source of truth for inventory and status.
- At batch registration, essay rows already exist (current code creates them). Slot assignment becomes a single UPDATE, executed in its own transaction for MVCC visibility:
  - UPDATE essay_states
    SET current_status=:ready_status,
        text_storage_id=:tsid,
        processing_metadata=:proc_meta_json,
        storage_references=:storage_json,
        timeline=:timeline_json,
        updated_at=now()
    WHERE batch_id=:batch_id AND current_status=:available_status
      AND NOT EXISTS (
        SELECT 1 FROM essay_states e2
        WHERE e2.batch_id=:batch_id AND e2.text_storage_id=:tsid
      )
    ORDER BY essay_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
    RETURNING essay_id
- Idempotency: enforce partial unique index on `(batch_id, text_storage_id)` where text_storage_id IS NOT NULL. On duplicate storms, losers catch IntegrityError at commit and then read the winner → return True.
- Batch completion: counts and ready_essays derive from `essay_states` only (most repository methods already support this).

Feature Flag
- Add Settings flag: `ELS_USE_ESSAY_STATES_AS_INVENTORY` (default False)
- When True, ContentAssignmentService bypasses slot_assignments entirely and uses the UPDATE-on-essay_states approach.

Implementation Steps (B)
- Model/index in `services/essay_lifecycle_service/models_db.py`:
  - Add partial unique index on `essay_states (batch_id, text_storage_id)` with `postgresql_where=text("text_storage_id IS NOT NULL")`.
  - Confirm statuses include clear available/registered and ready/assigned values used by the UPDATE.
- Assignment DAO path (new):
  - `services/essay_lifecycle_service/implementations/assignment_sql.py`: add `assign_via_essay_states_immediate_commit(batch_id, text_storage_id, original_file_name, file_size, content_hash, initial_status, correlation_id)`.
  - This function opens its own session/transaction, executes the UPDATE above, commits immediately, catches IntegrityError for duplicates, and returns `(was_created: bool, essay_id: str | None)`; on duplicate, read winner and return `(False, essay_id)`.
- ContentAssignmentService:
  - If flag enabled, call the new DAO function for assignment; then proceed with event publishing and completion checks using the outer session.
- BatchTrackerPersistence / batch registration:
  - Keep pre-creating essay rows as is (already done). You may keep `slot_assignments` rows as metrics-only. No hot-path writes to `slot_assignments` when the flag is enabled.
- Queries relying on inventory state:
  - Ensure batch completion checks and status summaries use `essay_states` (existing repository methods already do for most cases).

Affected Files (B)
- `services/essay_lifecycle_service/config.py` (new flag)
- `services/essay_lifecycle_service/models_db.py` (partial unique index on essay_states)
- `services/essay_lifecycle_service/implementations/assignment_sql.py` (new)
- `services/essay_lifecycle_service/domain_services/content_assignment_service.py` (conditional path)
- `services/essay_lifecycle_service/implementations/batch_tracker_persistence.py` (optional: guard slot_assignments hot-path writes; keep for metrics)
- Tests: no changes expected; existing suites validate correctness/perf; add a focused unit/integration test for the DAO if useful

Validation & Testing
- From repo root:
  - `pdm run pytest services/essay_lifecycle_service/tests/distributed/test_concurrent_slot_assignment.py -xvs`
  - `pdm run test-all`
- Toggle flags independently to compare:
  - `ESSAY_LIFECYCLE_SERVICE_ELS_USE_ESSAY_STATES_AS_INVENTORY=true`
  - `ESSAY_LIFECYCLE_SERVICE_USE_ADVISORY_LOCKS_FOR_ASSIGNMENT=true` (optional, stabilizes duplicate storms)
  - Keep `ELS_USE_CTE_UPSERT_ASSIGNMENT` off (fallback not in scope first)
- Targets:
  - Idempotent duplicates: 20/20 True
  - Cross-instance avg < 0.2s
  - High-concurrency P95 < 0.5s (goal < 0.3s)

Rollout/Toggle Strategy (Prototype)
- Default flags off; run baseline tests
- Enable Option B only; measure and compare
- Keep Option A documented as fallback; implement only if needed

Backout Plan
- Flags off returns to the current, known-good path
- No migrations required for tests; models-driven create_all ensures tables and indexes are present for the prototype

Implementation Tips
- Follow `.cursor/rules/048-structured-error-handling-standards.mdc` for surfacing DB errors through HuleEduError wrappers
- Keep SQL parameterized and prefer `text()` with named binds
- Reuse existing JSON shaping for processing_metadata, storage_references, and timeline via existing mappers
- Keep logs concise at INFO on success paths; add DEBUG for detailed timings when needed

Timebox & Ownership
- Option B implementation + tests: 2–3 days (model/index + wiring)
- Option A (fallback) + tests: 1–2 days (only if required)

Appendix — Why B First
- Architectural Elegance: essays ARE the inventory (DDD alignment)
- Simplicity: removes dual-table hot path and backoff storms
- Performance: single UPDATE; expected P95 < 0.3s and avg < 0.1s under test load
