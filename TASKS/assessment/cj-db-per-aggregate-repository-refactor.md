---
id: 'cj-db-per-aggregate-repository-refactor'
title: 'CJ DB Per-Aggregate Repository Refactor'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: 'agents'
program: ''
created: '2025-11-23'
last_updated: '2025-11-25'
related: []
labels: []
---
# CJ DB Per-Aggregate Repository Refactor

## Objective

Refactor `cj_assessment_service` database access from a monolithic `CJRepositoryProtocol` + `PostgreSQLCJRepositoryImpl` into per-aggregate repositories with clear transaction boundaries, semantic methods, and maintainable tests, while preserving current CJ behavior.

The end state is:

- **Infrastructure:** Shared `CJDatabaseInfrastructure` + `SessionProviderProtocol` managing DB engines and sessions.
- **Repositories:** One repository per aggregate (batch, essay, comparison, instruction, anchor, grade projection) with semantic methods instead of a god repository.
- **Domain:** Orchestrators and domain modules depend only on protocols and `AsyncSession`, not concrete implementations or raw SQL.
- **Tests:** Unit and integration tests use per-aggregate fixtures that mirror production DI wiring.

## Context

Currently, `db_access_impl.py` hosts a large `PostgreSQLCJRepositoryImpl` implementing `CJRepositoryProtocol` (700+ LoC) that:

- Mixes responsibilities for multiple aggregates (batches, batch state, essays, comparisons, instructions, anchors, grade projections).
- Owns both **domain-ish logic** (e.g. batch state transitions, metadata merges) and **infrastructure concerns** (sessions, queries, metrics).
- Requires standalone helper functions to avoid circular imports (e.g. used by `context_builder.py`).
- Makes it difficult to:
  - Reason about **transaction boundaries** and batch state updates.
  - Test individual aggregates or workflows in isolation.
  - Evolve the CJ design towards stricter DDD and per-aggregate repositories.

## Status (2025-11-25 post-merge)

- Per-aggregate repositories are merged and production code no longer imports `CJRepositoryProtocol` or `db_access_impl.py`.
- Remaining work to close the task: re-run the 5 workflow integration tests and 2 prompt-context unit tests that are currently blocked in this environment (Docker-backed Postgres) to confirm the new commit/metadata sequencing; once they pass, flip `status` to `done`.
- Session provider still does not auto-commit—callers must `await session.commit()` before exiting the context manager; keep this invariant in future PRs.

The service already has:

- A clear DB schema (`models_db.py`) with aggregates like `CJBatchUpload`, `CJBatchState`, `ProcessedEssay`, `ComparisonPair`, `AssessmentInstruction`, `AnchorEssayReference`, `GradeProjection`.
- Existing patterns in other services (e.g. `class_management_service`, `batch_orchestrator_service`) that use repository-per-aggregate + DI.
- Bounded-context style domain packages such as `cj_core_logic/grade_projection/` that would benefit from consuming repository protocols instead of concrete implementations.

This task aligns CJ with those patterns, improves testability, and removes circular import workarounds.

## Plan

### Phase 1: Infrastructure (½ day)

- **Goals**
  - Introduce shared DB infrastructure and a session provider used across CJ.
- **Tasks**
  - Implement `CJDatabaseInfrastructure` (wraps engine + metrics, reusable in tests).
  - Define `SessionProviderProtocol` in `protocols.py`.
  - Implement `SessionProviderImpl` using `CJDatabaseInfrastructure`.
  - Wire `SessionProviderImpl` into DI (`di.py`).
  - Create `tests/fixtures/database.py`:
    - `cj_infra` fixture from `test_db_engine`.
    - `session_provider` fixture using `CJDatabaseInfrastructure`.

### Phase 2: Protocols (½ day)

- **Goals**
  - Replace the monolithic `CJRepositoryProtocol` with per-aggregate, semantic protocols.
- **Tasks**
  - Define protocols in `protocols.py`:
    - `CJBatchRepositoryProtocol`
    - `CJEssayRepositoryProtocol`
    - `CJComparisonRepositoryProtocol`
    - `AssessmentInstructionRepositoryProtocol`
    - `AnchorRepositoryProtocol`
    - `GradeProjectionRepositoryProtocol`
  - Ensure method names are **semantic** (e.g. `mark_batch_scoring_complete`, `get_essays_for_batch`) rather than generic CRUD.
  - Mark `CJRepositoryProtocol` as deprecated in code and comments (do not remove yet).
  - Create `tests/fixtures/repositories.py` with empty-logic fixtures for each protocol (structure only at this phase).

### Phase 3: Repository Implementations (1–2 days)

- **Goals**
  - Move all DB logic from `db_access_impl.py` into per-aggregate Postgres repositories.
- **Tasks**
  - Implement `PostgreSQLCJBatchRepository`:
    - Encapsulate all `CJBatch` / `CJBatchState` operations.
    - Move `update_batch_state_in_session` logic into private helpers used only inside this repository.
    - Provide semantic methods for state transitions and metadata updates.
  - Implement:
    - `PostgreSQLCJEssayRepository`
    - `PostgreSQLCJComparisonRepository`
    - `PostgreSQLAssessmentInstructionRepository`
    - `PostgreSQLAnchorRepository`
    - `PostgreSQLGradeProjectionRepository`
    - by copying and organizing logic from `db_access_impl.py`.
  - Wire all repositories into DI (`di.py`) as implementations of the new protocols.
  - Complete `tests/fixtures/repositories.py` so integration tests can consume per-aggregate repos.

### Phase 4: Domain Module Adjustments (½ day)

- **Goals**
  - Align domain packages and naming to reflect per-aggregate repos.
- **Tasks**
  - Rename `cj_core_logic/grade_projection/projection_repository.py` → `projection_coordinator.py` to clarify that it is a domain façade, not a DB implementation.
  - Ensure `projection_coordinator.py` depends only on repository protocols (`GradeProjectionRepositoryProtocol`, `CJEssayRepositoryProtocol`, etc.), not raw SQLAlchemy.
  - (Optional) Extract `batch_metadata.py` from `batch_submission.py`:
    - Move `merge_batch_processing_metadata`, `merge_batch_upload_metadata`, and `merge_essay_processing_metadata` into a dedicated domain utility module.
  - Update imports across `cj_core_logic` accordingly.

### Phase 5: Update High-Value Call Sites (1 day)

- **Goals**
  - Remove the most problematic dependencies first (circular imports, heavy CJRepository usage).
- **Targets**
  - `cj_core_logic/context_builder.py`
  - `cj_core_logic/batch_preparation.py`
  - Admin and anchor routes:
    - `api/admin/instructions.py`
    - `api/admin/student_prompts.py`
    - `api/anchor_management.py`
- **Tasks**
  - Replace `CJRepositoryProtocol` and helper functions from `db_access_impl.py` with injections of:
    - `SessionProviderProtocol`
    - `AssessmentInstructionRepositoryProtocol`
    - `AnchorRepositoryProtocol`
    - `CJBatchRepositoryProtocol`
    - `CJEssayRepositoryProtocol` (where needed)
  - Add repository contract tests (integration-level) that exercise typical flows for each new repository.

### Phase 6: Update Orchestrators and Core Services (1–2 days)

- **Goals**
  - Push per-aggregate repositories through orchestrators and callback flows.
- **Targets**
  - `cj_core_logic/workflow_orchestrator.py`
  - `cj_core_logic/batch_processor.py`
  - `cj_core_logic/callback_state_manager.py` and related services:
    - `callback_persistence_service.py`
    - `batch_completion_checker.py`
    - `batch_pool_manager.py`
    - `batch_retry_processor.py`
  - Relevant integration tests.
- **Tasks**
  - Replace `CJRepositoryProtocol` with:
    - `SessionProviderProtocol`
    - The minimal set of repositories each module actually uses (batch, essay, comparison, instructions, anchors).
  - Centralize all `CJBatchState` changes in `CJBatchRepositoryProtocol` semantic methods (no ad-hoc state mutations elsewhere).
  - Migrate integration tests to use `session_provider` and per-aggregate repo fixtures from `tests/fixtures/repositories.py`.

### Phase 7: Specialized Components (1 day)

- **Goals**
  - Finish rewiring remaining components and align grade projection.
- **Targets**
  - `batch_monitor.py`
  - `cj_core_logic/batch_finalizer.py`
  - `cj_core_logic/grade_projector.py`
- **Tasks**
  - Update `BatchMonitor` and `BatchFinalizer` to use:
    - `SessionProviderProtocol`
    - `CJBatchRepositoryProtocol`
    - `CJEssayRepositoryProtocol`
  - Update `grade_projector.py` to use `GradeProjectionCoordinator` and `GradeProjectionRepositoryProtocol` (and any other required repos) via DI.
  - Complete test migration for these components (unit + integration).

### Phase 8: Cleanup and Validation (½ day)

- **Goals**
  - Remove legacy artifacts and validate the new architecture.
- **Tasks**
  - Delete `CJRepositoryProtocol` and all usages.
  - Delete `implementations/db_access_impl.py`.
  - Remove old CJ repository test fixtures.
  - Run full validation:
    - `pdm run format-all`
    - `pdm run lint-fix --unsafe-fixes`
    - `pdm run typecheck-all`
    - Full `pytest` / `pdm run pytest-root` for relevant paths.
  - Verify:
    - No imports of deleted modules or symbols.
    - All DI providers resolve correctly (smoke tests / startup).

## Success Criteria

- No remaining references to `CJRepositoryProtocol` or `PostgreSQLCJRepositoryImpl` in code or tests.
- All CJ DB access occurs via per-aggregate repository protocols and `SessionProviderProtocol`.
- Transaction boundaries are owned by orchestrator / service layers using `SessionProviderProtocol` (repositories do not commit/rollback).
- All existing CJ tests pass; new repository contract tests are green.
- No circular imports involving `context_builder` or `db_access_impl`.
- `db_access_impl.py` and legacy fixtures are fully removed.
- The per-aggregate repository pattern matches existing patterns in other services.

## PR 1 – Introduce `SessionProviderImpl` (Infra)

**Goal:** Centralize `AsyncSession` creation via [SessionProviderProtocol](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/protocols.py:114:0-119:31).

**Checklist**

- **Interface**
  - [x] [SessionProviderProtocol](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/protocols.py:114:0-119:31) is defined in [protocols.py](cci:7://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/protocols.py:0:0-0:0).
  - [x] [CJRepositoryProtocol](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/protocols.py:122:0-326:11) inherits from [SessionProviderProtocol](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/protocols.py:114:0-119:31) (no method changes).

- **Implementation**
  - [x] New `CJSessionProviderImpl` created in `implementations/`.
  - [x] Uses a single `AsyncEngine` and `async_sessionmaker(expire_on_commit=False, class_=AsyncSession)`.
  - [x] `session()` returns an async context manager that:
    - [x] Yields an `AsyncSession`.
    - [x] Always closes the session in `finally` (rolls back on exception).

- **DI wiring**
  - [x] `di.py` registers `CJSessionProviderImpl` as [SessionProviderProtocol](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/protocols.py:114:0-119:31).
  - [x] Engine configuration/metrics shared with existing DB infra (reuses the app engine; no duplicate engines).

- **Verification**
  - [x] Unit tests for `CJSessionProviderImpl`:
    - [x] Can open multiple sessions sequentially.
    - [x] Sessions are closed after context exit (connection closed assertion).
  - [x] `pdm run typecheck-all` passes for CJ service.
  - [x] `pdm run pytest-root services/cj_assessment_service/tests/unit` passes.

## PR 2 – Refactor Orchestrators to Use SessionProviderProtocol

**Goal:** Public orchestrator APIs no longer expose `AsyncSession`; they rely on `SessionProviderProtocol`.

**Checklist**

- **API changes**
  - [x] Orchestrator entrypoints (`batch_processor`, `workflow_orchestrator`, `batch_monitor`, etc.) drop `AsyncSession` parameters.
  - [x] Accept `SessionProviderProtocol` (or repo that implements it) instead.

- **Internal behavior**
  - [x] Wrap DB work with `async with session_provider.session() as session:`.
  - [x] Direct SQLAlchemy calls removed or explicitly marked for later migration.
  - [x] Transaction boundaries stay in orchestrator/service layers (repos do not commit/rollback).

- **Tests**
  - [x] Unit tests inject a `SessionProviderProtocol` / `CJRepositoryProtocol` mock.
  - [x] `session_provider.session()` yields `AsyncMock(spec=AsyncSession)`.
  - [x] Assertions focus on repo interactions/observable behavior (no `session.execute` assertions).

- **Verification**
  - [x] `grep` shows no public APIs taking `AsyncSession` in orchestrator modules.
  - [x] `pdm run pytest-root services/cj_assessment_service/tests/unit` passes.
  - [x] `pdm run typecheck-all` passes with no new ignores.

**Status:** In progress (PR2 orchestration refactor completed 2025-11-24; PR3 remains outstanding).

## PR 3 – Split CJRepositoryProtocol into Per‑Aggregate Repositories

**Goal:** Replace the god repo with per‑aggregate protocols and implementations.

**Checklist**

- **Protocols**
  - [x] Add semantic protocols in `protocols.py`: `CJBatchRepositoryProtocol`, `CJComparisonRepositoryProtocol`, `CJEssayRepositoryProtocol`, `AssessmentInstructionRepositoryProtocol`, `AnchorRepositoryProtocol`, `GradeProjectionRepositoryProtocol`.
  - [x] Methods are semantic (e.g., `get_batch_state`, `store_comparison_results`, `get_essays_for_batch`), not generic CRUD.

- **Implementations**
  - [x] New classes in `implementations/` (`PostgreSQLCJBatchRepository`, `PostgreSQLCJComparisonRepository`, etc.) migrate logic from `PostgreSQLCJRepositoryImpl` with no behavior change.
  - [x] Repos accept `AsyncSession` only; they do not create engines/sessionmakers or call commit/rollback.

- **DI & usage**
  - [x] `di.py` registers each implementation to its protocol.
  - [ ] Orchestrators depend only on the repos they need (e.g., callbacks use comparison + batch repos).
  - [x] `CJRepositoryProtocol` marked deprecated and used only where migration is not yet complete in this PR.

- **Tests**
  - [ ] Unit tests for each new repository class (real DB fixtures or existing patterns).
  - [ ] Orchestrator tests target new per‑aggregate protocols, not `CJRepositoryProtocol`.
  - [ ] Contract-style tests confirm behavior parity for key flows.

- **Verification**
  - [ ] `grep "CJRepositoryProtocol"` limited to definition and documented legacy shims.
  - [ ] `pdm run pytest-root services/cj_assessment_service/tests` passes.
  - [ ] `pdm run typecheck-all` passes; imports adjusted to avoid circulars.

**Status:** In progress — protocols/implementations/DI complete; call-site migration and test realignment outstanding.

## Progress (2025-11-24)

- Wave 5 fixtures/tests fixed; quality gates green (typecheck, lint, format, unit tests).
- Per-aggregate protocols and implementations added; DI provides all new repos plus deprecated shim delegating via `SessionProviderProtocol`.
- Orchestrator surfaces use `SessionProviderProtocol`; many call sites still reference `CJRepositoryProtocol` pending PR3 migration.
- Deprecated shim retained for backward compatibility; no production behavior changes since Wave 5.
- Added `PostgresDataAccess` test façade (session provider + per-aggregate repos) and converted several integration suites to per-aggregate/session-provider wiring (`test_anchor_repository_upsert.py`, `test_batch_repository.py`, `test_comparison_repository.py`, `test_real_database_integration.py`, `test_async_workflow_continuation_integration.py`, `test_batch_state_multi_round_integration.py`). Partial migration ongoing in `test_error_handling_integration.py`.
- Latest: `test_error_handling_integration.py` migrated to session-provider/per-aggregate fixtures; `test_repository_anchor_flag.py` now uses `PostgresDataAccess`.
- Targeted typecheck blockers resolved (workflow_continuation/callback_state_manager tests, integration wiring, and the identity-threading fixture now match the session_provider/batch_repository contracts); reran `pdm run typecheck-all`, which now passes with zero errors.
- Reference report: `.claude/work/reports/2025-11-24-wave5-completion-handoff.md`.

### Current verification (2025-11-25)
- `pdm run format-all`: ✅ (2025-11-24 night)
- `pdm run lint-fix --unsafe-fixes`: ✅ (2025-11-24 night)
- `pdm run typecheck-all`: ✅ (2025-11-24 late; now passes after workflow/test fixture updates)
- Targeted CJ integration/unit suites (Docker-backed) now green on a Docker-capable dev machine:
  - ✅ `pdm run pytest-root services/cj_assessment_service/tests/integration/test_metadata_persistence_integration.py::test_original_request_metadata_persists_and_rehydrates`
  - ✅ `pdm run pytest-root services/cj_assessment_service/tests/integration/test_real_database_integration.py::TestRealDatabaseIntegration::test_full_batch_lifecycle_with_real_database`
  - ✅ `pdm run pytest-root services/cj_assessment_service/tests/integration/test_student_prompt_workflow.py::test_student_prompt_workflow_end_to_end`
  - ✅ `pdm run pytest-root services/cj_assessment_service/tests/integration/test_eng5_scale_flows.py`
  - ✅ `pdm run pytest-root services/cj_assessment_service/tests/unit/test_event_processor_prompt_context.py`

### Session Update (2025-11-24 evening)

- Runtime pipeline refactored off `CJRepositoryProtocol` (now per-aggregate repos + `SessionProviderProtocol`): `event_processor`, message handlers, `batch_callback_handler`, `workflow_continuation`, `comparison_processing`, `comparison_batch_orchestrator`, `content_hydration`, `health_routes`, `kafka_consumer`, `app`.
- BatchMonitor no longer depends on deprecated repo; uses batch/essay/comparison repositories only.
- Admin surfaces (`instructions`, `student_prompts`, `judge_rubrics`, `anchor_management`) now use instruction/anchor repositories with session provider.
- Deprecated `postgres_repository` fixture removed; integration tests now need per-aggregate fixture wiring.
- Remaining public AsyncSession exposure: `batch_submission.py` helpers. CJRepositoryProtocol still defined (shim) and used by tests/DI only.

### Session Update (2025-11-24 night - Codex)

- Converted remaining `merge_*` helper callers to `session_provider` (workflow_continuation, batch_preparation, retry integration + identity/finisher unit fixtures) and adjusted anchor metadata merge helper.
- Fixed `batch_pool_manager.form_retry_batch` indentation/logic; reran format/lint (clean).
- `typecheck-all` now surfaces remaining legacy `database`/`session` kwargs across callback/comparison workflow tests and fixtures (139 errors) — pending broader migration off `CJRepositoryProtocol` and AsyncSession fixtures.
- Callback simulator now builds comparison pairs and correlation lookups via the shared `SessionProviderProtocol` instead of the deprecated `CJRepositoryProtocol`, aligning the integration helper with the new per-repo fixtures.

## Remaining Work (PR3 close-out)

- [ ] Finish public API cleanup: remove remaining `AsyncSession` exposure in `batch_submission.py`; ensure all public functions take per-aggregate repos + session provider only.
- [ ] Tests/fixtures: migrate integration/unit tests off `postgres_repository` and CJRepository mocks; use `session_provider` + per-aggregate repository fixtures/mocks.
- [ ] Remove deprecated shim: delete `CJRepositoryProtocol` definition and `implementations/db_access_impl.py`; drop shim provider from `di.py`; ensure DI still resolves.
- [ ] Grep gates: no `CJRepositoryProtocol`; no public APIs accept `AsyncSession` once shim is removed.
- [ ] Quality gates after migration: `pdm run format-all`, `pdm run lint-fix --unsafe-fixes`, `pdm run typecheck-all`, `pdm run pytest-root services/cj_assessment_service/tests`.

## Related

- Tasks:
  - `TASKS/assessment/cj-assessment-code-hardening.md`
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`
  - `TASKS/assessment/cj-batch-state-and-completion-fixes.md`
- Docs:
  - `.windsurf/rules/020.7-cj-assessment-service.md` (CJ Assessment Service architecture)
  - `.windsurf/rules/010-foundational-principles.md` (architecture principles)
  - `.windsurf/rules/042-async-patterns-and-di.md` (async patterns and DI)
