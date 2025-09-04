— BEGIN START-OF-CONVERSATION PROMPT —

Context: HuleEdu Monorepo

- Root: /Users/olofs_mba/Documents/Repos/huledu-reboot
- Python 3.11, PDM, SQLAlchemy async + asyncpg, Aiokafka, Quart
- Services are in /services; this work focuses on services/essay_lifecycle_servi
ce (ELS)

Read This First (Required)

- Rules index: .cursor/rules/000-rule-index.mdc
- Project structure: .cursor/rules/015-project-structure-standards.mdc
- Repository workflow/tools: .cursor/rules/080-repository-workflow-and-tooling.m
dc
- Foundational architecture: .cursor/rules/010-foundational-principles.mdc
- Architectural mandates: .cursor/rules/020-architectural-mandates.mdc
- Async + DI patterns: .cursor/rules/042-async-patterns-and-di.mdc
- SQLAlchemy standards: .cursor/rules/053-sqlalchemy-standards.mdc
- Testing QA: .cursor/rules/070-testing-and-quality-assurance.mdc
- Database migrations: .cursor/rules/085-database-migration-standards.mdc
- Structured error handling: .cursor/rules/048-structured-error-handling-standar
ds.mdc
- Modes: .cursor/rules/110-ai-agent-interaction-modes.mdc, 110.1-planning-mode.m
dc, 110.2-coding-mode.mdc, 110.3-testing-mode.mdc

Service-Specific Architecture (Recommended)

- Essay Lifecycle Service: .cursor/rules/020.5-essay-lifecycle-service-architect
ure.mdc

Executive Summary (What We Did, Why, Where We Are)

- Problem: Redis was used for atomic slot assignment, batch state, and coordinat
ion. This created split-brain (Redis vs DB), brittle tests, infra coupling, and
difficult cleanup. Tests hung due to cleanup/deadlock behaviors; testcontainers
missed migrations.
- Approach adopted:
  - DB-first coordination: Replace Redis slot atomics with PostgreSQL CTE + FOR
UPDATE SKIP LOCKED and enforce idempotency with partial unique indexes.
  - Single source of truth: All critical batch state (slots, pending content, va
lidation failures) is in PostgreSQL.
  - No-immediate-cleanup policy: Do not delete batches inline (especially for GU
EST). Mark completion in DB, use a retention script to purge later.
  - Test infra compatibility: Add ORM models for new tables so Base.metadata.cre
ate_all works with testcontainers (no migrations needed in tests).
  - Observability: Introduce Prometheus Gauges to reflect active and completed b
atch counts per class type (GUEST/REGULAR).
 - Current status:
  - Slot assignment logic is DB-only and idempotent. Primary production path uses essay_states as the single inventory via a single-statement UPDATE with immediate commit (Option B).
  - Legacy DatabaseSlotOperations remains available for tests/metrics-only, not used in the service hot path.
  - ELS handlers/services refactored to remove Redis from the critical path.
  - New ORM models for batch_validation_failures and batch_pending_content, evol
ved SlotAssignmentDB to “inventory” with statuses available/assigned/failed.
  - Migrations added and applied in development. Tests (unit/integration) update
d to DB-first semantics and no-immediate-cleanup.
  - Added a retention CLI script to purge completed GUEST batches after a retent
ion period.
  - Type-checks fixed (zero mypy errors) without type-ignores.

Key Files To Review (ELS)

- Domain models/tables:
  - services/essay_lifecycle_service/models_db.py
    - BatchEssayTracker: now includes completed_at
    - SlotAssignmentDB: inventory row per slot with status ∈ {available, assigne
d, failed}
    - BatchValidationFailure (new)
    - BatchPendingContent (new)
- Core implementations:
  - Assignment (Option B hot path): services/essay_lifecycle_service/implementations/assignment_sql.py
  - Slot ops (legacy metrics/testing): services/essay_lifecycle_service/implementations/database_slot_operations.py
  - Batch tracker: services/essay_lifecycle_service/implementations/batch_essay_
tracker_impl.py
  - Persistence: services/essay_lifecycle_service/implementations/batch_tracker_
persistence.py
  - Domain service: services/essay_lifecycle_service/domain_services/content_ass
ignment_service.py
  - Handlers: services/essay_lifecycle_service/implementations/batch_coordinatio
n_handler_impl.py; services/essay_lifecycle_service/implementations/student_asso
ciation_handler.py
  - Failure/pending (DB): services/essay_lifecycle_service/implementations/db_fa
ilure_tracker.py; services/essay_lifecycle_service/implementations/db_pending_co
ntent_ops.py
  - DI wiring: services/essay_lifecycle_service/di.py
- Migrations (ELS):
  - services/essay_lifecycle_service/alembic/versions/20250902_2100_slot_invento
ry_via_slot_assignments.py
  - services/essay_lifecycle_service/alembic/versions/20250902_2210_db_failures_
and_pending_content.py
  - services/essay_lifecycle_service/alembic/versions/20250903_0100_add_complete
d_at_to_batch_tracker.py
- Metrics and purge:
  - services/essay_lifecycle_service/metrics.py (adds huleedu_batches_active and
 huleedu_batches_completed)
  - services/essay_lifecycle_service/scripts/db_purge_guest.py (CLI tool)
  - services/essay_lifecycle_service/pyproject.toml (pdm script: db-purge-guest)

Test Updates (Representative)

- services/essay_lifecycle_service/tests/integration/test_database_slot_operatio
ns.py (idempotency/assignment/exhaustion)
- services/essay_lifecycle_service/tests/integration/test_batch_metrics_refresh.
py (gauges)
- services/essay_lifecycle_service/tests/integration/test_pending_content_race_c
ondition.py (race fix, DB-first)
- services/essay_lifecycle_service/tests/distributed/test_concurrent_slot_assign
ment.py (multi-instance slot concurrency)
- services/essay_lifecycle_service/tests/integration/test_content_provisioned_fl
ow.py (DB-only flow)
- services/essay_lifecycle_service/tests/unit/test_content_assignment_service.py
 (no cleanup, mark completion)
- services/essay_lifecycle_service/tests/unit/test_student_association_handler.p
y (REGULAR marks completion; no cleanup)

Known Issues Previously Uncovered (Now Addressed)

- Deadlock: Occurred when attempting to delete a batch within the same transacti
on that created it (nested session), especially for GUEST immediate cleanup. Res
olved by no-immediate-cleanup policy and marking completion instead.
- Testcontainers missing tables: Tests relied on Base.metadata.create_all; there
fore, we added ORM models so tests create all tables without migrations.
- Split-brain: Redis state vs DB persisted state created reconciliation complexi
ty. We eliminated Redis from the critical path and consolidated state in DB.

What We Are Doing Right Now (and Why)

- We have already:
  - Implemented DB-first slot assignment, DB-backed failure and pending content
handling.
  - Removed Redis dependency from critical ELS flows.
  - Adopted a no-immediate-cleanup policy; mark completion in DB, purge later vi
a CLI/cron.
  - Added Gauges for active/completed batch counts and a retention CLI.
- Current focus:
  - Solidify and validate DB-first architecture end-to-end; ensure tests and met
rics are robust.
  - Ensure purge script is operationally ready and documented.
  - Optionally remove legacy Redis coordination helpers (redis_batch_* etc.) if
no longer referenced by code/tests.
  - Ensure docs reflect the new architecture and policy.
  - Keep mypy at 0 errors (no ignores), ensure full tests pass.

Acceptance Criteria For This Iteration

- All ELS tests pass (unit/integration).
- Type checks pass (pdm run typecheck-all) with zero ignores.
- The retention CLI (db-purge-guest) works and logs clear output; dry-run works.
- Metrics (huleedu_batches_active, huleedu_batches_completed) are exposed and sh
ow correct counts in the scenarios covered by tests.
- No immediate DB cleanup remains in business flow paths; completion is marked i
n DB (completed_at).
- Optional: Legacy Redis helpers can be removed (if unreachable), or quarantined
 behind a flag.

How To Run Locally (from ELS directory)

- Apply migrations (dev): pdm run migrate-upgrade
- Type checks: pdm run typecheck
- Unit tests: pdm run test -m "not integration"
- Integration tests: pdm run test -m integration
- Purge (dry-run): pdm run db-purge-guest --older-than-days 14 --dry-run
- Purge (execute): pdm run db-purge-guest --older-than-days 14

Guardrails

- Read the referenced rules before coding (must).
- Follow .cursor/rules/053 for SQLAlchemy; don’t bypass session management patte
rns or create engines ad-hoc except in tests.
- Follow .cursor/rules/070 for tests; keep them deterministic; use testcontainer
s when appropriate; ensure ORM models cover test schemas.
- Follow .cursor/rules/085 for migrations; never modify existing versions; only
add new ones.
- Follow .cursor/rules/048 for structured error handling; no ad-hoc exceptions e
scaping outer boundaries.
- No type-ignores; keep mypy clean. Avoid casts; prefer precise types.
- Keep changes minimal and focused; do not introduce unrelated refactors.

Open Follow-ups (if time allows)

- Prune legacy slot assignment artifacts (slot_assignments inventory, DatabaseSlotOperations, repository idempotency helpers) after test migration:
  - Replace DatabaseSlotOperations usages in tests with assignment_sql.assign_via_essay_states_immediate_commit
  - Remove EssayRepositoryProtocol legacy methods and update tests verifying protocol compliance
  - Drop implementations/essay_repository_idempotency.py and related imports
  - Remove DI provider provide_db_slot_operations and DefaultBatchEssayTracker dependency
  - Delete tests dedicated to DatabaseSlotOperations once Option B equivalents exist
- Documentation updates:
  - ELS README: update architecture and DB-first rationale, no-immediate-cleanup
 policy, retention script usage.
- Add a Prometheus Counter (optional) for “batches_purged_total{class_type}”.

- Planning mode: Outline steps; identify any risky refactors and add guards.
- Review the exact files listed above; confirm no lingering references to Redis
in critical flow.
- Implement changes; keep to style and patterns used in this repo.
- Testing mode: Run and fix tests; ensure metrics show meaningful values in the
added test.
- Deliver concise summary of changes and verification steps.

— END START-OF-CONVERSATION PROMPT —
