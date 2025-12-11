---
id: fix-els-transaction-boundary-violations
title: Fix Els Transaction Boundary Violations
type: task
status: in_progress
priority: high
domain: infrastructure
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-24'
service: essay_lifecycle_service
owner: ''
program: ''
related: []
labels: []
---

# TASK: Fix Essay Lifecycle Service Transaction Boundary Violations

**Status**: Phase 1 Completed (transaction boundaries); Phase 2 In Progress (persistence & session architecture alignment)
**Priority**: High
**Created**: 2025-11-21
**Type**: Refactoring - Architectural Compliance

---

## Problem Statement

The Essay Lifecycle Service (ELS) has systematic transaction boundary violations where handlers create multiple independent transaction blocks instead of using a single Unit of Work pattern. This breaks ACID guarantees and creates inconsistency risks where database operations can commit but subsequent event publishing or state updates can fail.

### Root Cause

Handlers incorrectly structure operations into multiple sequential `async with session.begin()` blocks instead of consolidating all operations (business logic + event publishing) into a single atomic transaction.

### Architectural Standard Violated

**Rule**: `.agent/rules/042.1-transactional-outbox-pattern.md` (Lines 64-82, 137-143)

**Pattern**: Handler-Level Unit of Work with Transactional Outbox

**Requirement**: Handlers MUST create a single transaction boundary and pass the session to all collaborators (repositories, publishers, trackers) to ensure atomicity.

---

## Investigation Summary

### Scope Analysis

**Historical Violations Identified (2025-11-21)**: 17 handler files with multiple transaction blocks

**False Positives Validated** (No changes needed):
- ✅ `assignment_sql.py:assign_via_essay_states_immediate_commit()` - MVCC cross-process coordination by design (Rule 020.5)
- ✅ `batch_tracker_persistence.py` - Session-aware dual-mode pattern (accepts session OR creates own)
- ✅ `refresh_batch_metrics()` - Read-only metric collection

**Reference Implementations** (Architectural Gold Standard):
- `services/class_management_service/implementations/batch_author_matches_handler.py:126-192`
- `services/identity_service/implementations/user_repository_sqlalchemy_impl.py:23-42`
- `services/batch_conductor_service/implementations/postgres_batch_state_repository.py:171-193`

### Implementation Summary (2025-11-23)

- **Scope narrowing**
  - Re-evaluated all 17 initially flagged handlers.
  - Confirmed many were already compliant with the single-UoW pattern by late 2025 (notably the result handlers and student association handler).
  - Narrowed concrete work to:
    - Batch coordination edge path for validation failures.
    - Command handler session propagation.
    - Explicit transactional-outbox contract tests around content assignment and batch completion.

- **Batch coordination handler**
  - Kept `assign_via_essay_states_immediate_commit()` as an intentional **Option B** immediate-commit path for MVCC coordination.
  - Verified that non-Option-B paths use a shared SQLAlchemy session for state changes + outbox writes.
  - Added a dedicated unit test:
    - `services/essay_lifecycle_service/tests/unit/test_batch_coordination_handler_impl.py::TestBatchCoordinationHandler::test_handle_essay_validation_failed_guest_uses_session_for_outbox_and_completion`
    - Asserts that `handle_essay_validation_failed`:
      - Calls `publish_batch_content_provisioning_completed(..., session=session)`.
      - Calls `mark_batch_completed(batch_id, session)` for **GUEST** batches, using the *same* session.

- **Content assignment service (transactional outbox contract)**
  - Strengthened tests in:
    - `services/essay_lifecycle_service/tests/unit/test_content_assignment_service.py`
  - Now explicitly assert that `ContentAssignmentService.assign_content_to_essay`:
    - Passes the active `session` into `publish_essay_slot_assigned` and `publish_batch_content_provisioning_completed`.
    - Uses the same `session` when calling `mark_batch_completed` for GUEST batches.
  - This encodes the transactional outbox guarantee for slot assignment and batch content completion.

- **Command handlers (session propagation tightened)**
  - `SpellcheckCommandHandler.process_initiate_spellcheck_command`:
    - Now calls `repository.get_essay_state(essay_id, session)` both for the initial transition and the post-dispatch `EVT_SPELLCHECK_STARTED` update.
    - Tests updated in `test_spellcheck_command_handler.py` to assert `get_essay_state` is invoked with the active session.
  - `NlpCommandHandler.process_initiate_nlp_command`:
    - Now calls `repository.get_essay_state(essay_ref.essay_id, session)` inside the `session.begin()` block.
    - Existing unit test `test_nlp_command_handler.py` continues to validate the behavior with the new call signature.
  - `CJAssessmentCommandHandler.process_initiate_cj_assessment_command`:
    - Now calls `repository.get_essay_state(essay_id, session)` for the initial state lookup (the post-dispatch lookup already used the session).
    - Tests updated in `test_cj_assessment_command_handler.py` to assert `get_essay_state` is invoked with the session argument.

- **Routes and result handlers**
  - Validated that API routes (`essay_routes.py`, `batch_routes.py`, `health_routes.py`) are **read-only** with respect to core ELS state and do not open ad-hoc transactions for writes.
  - Verified that result handlers (`spellcheck_result_handler.py`, `nlp_result_handler.py`, `cj_result_handler.py`) already follow the single-UoW pattern (one `session.begin()` per handler method) and consistently propagate the `session` to repositories and publishers.

## Phase 1 – Implemented Changes (Historical)

> Phase 1 work for this task is complete. The bullets below are a concise
> summary of what changed in ELS and what was validated; they are **not** an
> active checklist.

### Batch coordination handler (`batch_coordination_handler_impl.py`)

- **Batch registration** – `handle_batch_essays_registered` performs batch
  registration and initial essay creation inside a single
  `session.begin()` block, then commits before any pending-content work.
- **Pending content** – pending items are processed in small, per-item
  transactions that call `assign_content_to_essay(..., session=session)` and
  then remove the corresponding pending record.
- **Validation failure (GUEST)** – `handle_essay_validation_failed` now
  publishes `BatchContentProvisioningCompletedV1` and calls
  `mark_batch_completed(..., session)` for GUEST batches within the same
  transaction so event + completion flag commit together.

Illustrative pattern for the GUEST completion path:

```python
async with self.session_factory() as session:
    async with session.begin():
        await self.batch_lifecycle_publisher.publish_batch_content_provisioning_completed(
            event_data=event,
            correlation_id=cid,
            session=session,
        )
        if is_guest:
            await self.batch_tracker.mark_batch_completed(batch_id, session)
```

### Result & command handlers

- **Single-transaction structure** – spellcheck/NLP/CJ result handlers and the
  three command handlers all follow the same pattern inside one
  `session.begin()`:
  `get_essay_state(..., session)` → `EssayStateMachine` transition →
  `update_essay_status_via_machine(..., session=session)` → optional
  `check_batch_completion(..., session=session)` or dispatcher call.
- **Session propagation** – Phase 1 tightened or validated that repository
  calls and dispatcher calls share the active transaction session so state
  updates and outbox / dispatch metadata commit atomically.
- **Clean boundaries** – thin result handlers keep CJ/NLP business data out of
  ELS; they only update status + minimal phase metadata, with rich results
  owned by downstream services.

### API routes (`essay_routes.py`, `batch_routes.py`, `health_routes.py`)

- `essay_routes` and `batch_routes` read from `EssayRepositoryProtocol`
  (`get_essay_state`, `list_essays_by_batch`) and shape HTTP responses; they
  do not introduce additional write transactions.
- `health_routes` is limited to dependency and metrics checks and does not
  participate in ELS transactional flows.

### Testing (Phase 1)

- **Unit tests** – added/updated tests for:
  - GUEST validation-failure path (shared session for outbox + completion).
  - `ContentAssignmentService.assign_content_to_essay` session usage in
    slot-assignment and batch-completion flows.
  - Spellcheck/NLP/CJ command handlers using the active `session` in
    repository and dispatcher calls.
- **Integration / E2E** – reused existing end-to-end batch flows (guest,
  student matching, sequential pipelines, CJ-after-NLP) to confirm no
  deadlocks, MVCC errors, or regressions from the tightened transaction
  boundaries.
- **Performance** – relied on existing metrics to monitor transaction
  duration/lock behaviour; any deeper optimisation is deferred to Phase 2 or
  separate tasks.

### De-scoped / validated-but-unchanged items

- **Single mega-transaction** – the idea of one transaction covering
  registration + content + completion in the coordination handler was
  intentionally **not** implemented because of MVCC and performance trade-offs;
  we kept one registration transaction plus smaller per-item/dispatch
  transactions.
- **Global collaborator audit** – a full audit of every optional-session
  collaborator (e.g. `batch_tracker_persistence`, outbox internals) was scoped
  down to the hot paths above; remaining patterns are documented as acceptable
  in shared rules.
- **Generic templates** – generic handler/route templates now live in shared
  rules (e.g. `042.1-transactional-outbox-pattern`) instead of being repeated
  in this task.

> All remaining work for ELS persistence/session alignment is tracked under
> **Phase 2** below.

**Last Updated**: 2025-11-24
**Investigator**: Claude (research-diagnostic agent)
**Approver**: User
**Implementation Status**: Phase 1 Completed; Phase 2 In Progress

---

## Phase 2  ELS Persistence & Session Architecture Alignment (Multi-PR Plan)

### 1. Background & Relationship to Phase 1 / CJ Refactor

Phase 1 of this task focused on **transaction boundary violations** in ELS handlers and collaborators, consolidating work into single Unit-of-Work transactions and enforcing the transactional outbox pattern.

Since then, the **CJ Assessment Service** has been refactored off its god-repository into:
- Per-aggregate repository protocols
- A `SessionProviderProtocol` that centralizes `AsyncSession` lifecycle

Codebase analysis for ELS revealed two remaining architectural gaps that are not bugs, but **inconsistencies with the emerging standard**:

- **[A] Pending-content persistence**:
  - `DBPendingContentOperations` uses raw SQL via `sqlalchemy.text` for CRUD on `batch_pending_content`.
  - The ORM model `BatchPendingContent` already exists but is unused.
  - `BatchCoordinationHandlerImpl` depends directly on the concrete `DBPendingContentOperations` in DI.

- **[B] Session management patterns**:
  - ELS protocols (e.g. `EssayRepositoryProtocol`, `EventPublisher`, `BatchLifecyclePublisherProtocol`) expose `session: AsyncSession | None` widely.
  - Implementations like `PostgreSQLEssayRepository` accept an injected `async_sessionmaker` and then re-express the same `AsyncSession | None` pattern.
  - BOS and ELS use similar optional-session patterns, while CJ has converged on a `SessionProviderProtocol` that hides `AsyncSession` lifecycle from most callers.

Phase 2 extends this task into a **multi-PR plan** that:
1. Aligns ELS pending-content persistence with the established repository+protocol pattern.
2. Moves ELS session management closer to the CJ/BOS patterns while preserving the legitimate outliers (Option B assignment SQL, outbox plumbing).

The already-completed work in this file (Phase 1) and the archived `fix-els-batch-registration-transaction` task now serve as **background and prior-art** for the following PRs.

### 2. PR Breakdown

#### PR 1  ORM-backed Pending Content Repository

**Goal**: Replace raw SQL in `DBPendingContentOperations` with an ORM-backed repository and introduce a protocol, without changing external behavior.

- **Scope**:
  - Define `PendingContentRepositoryProtocol` in `services/essay_lifecycle_service/protocols.py` with operations:
    - `store_pending_content(batch_id, text_storage_id, content_metadata)`
    - `get_pending_content(batch_id) -> list[dict]`
    - `remove_pending_content(batch_id, text_storage_id)`
  - Implement `PostgresPendingContentRepository` in a new module, using the existing `BatchPendingContent` ORM model instead of `sqlalchemy.text`.
  - Update DI (`provide_db_pending_content_ops`) to provide the protocol-backed repository rather than the concrete `DBPendingContentOperations`.
  - Update `BatchCoordinationHandlerImpl` to depend on the protocol rather than concrete class.
  - Keep behavior and transactional semantics identical (including how it cooperates with `ContentAssignmentService` and existing handlers).

- **Testing**:
  - Unit tests for the new repository (CRUD semantics, JSON round-trips).
  - Adjust existing handler tests that currently assert direct calls into `DBPendingContentOperations` to assert protocol usage instead (mocked via DI).

#### PR 2  ELS Session Provider Introduction (Targeted Adoption)

**Goal**: Introduce a **session provider abstraction** for ELS and adopt it in a limited, high-value subset of the codebase, using the CJ pattern as reference while avoiding a massive breaking change.

- **Scope**:
  - Add `ELSSessionProviderProtocol` (or reuse a shared `SessionProviderProtocol` from service libs if appropriate) with:
    - `@asynccontextmanager async def session(self) -> AsyncIterator[AsyncSession]`
  - Implement `ELSSessionProviderImpl` in ELS, wrapping the existing `async_sessionmaker`.
  - Wire DI so that:
    - Command handlers and result handlers receive a `session_provider` instead of, or in addition to, a bare `async_sessionmaker`.
    - New call sites that currently start sessions manually can migrate to `async with session_provider.session():`.
  - Keep **Phase 1 transactional patterns intact**; this PR only changes *how* sessions are obtained, not where transaction boundaries live.

- **Out of Scope for PR 2** (but documented for later cleanup):
  - Removing all `AsyncSession | None` parameters from protocols.
  - Refactoring ELS outbox plumbing (`BatchLifecyclePublisher`, `OutboxManagerProtocol`) which legitimately needs optional session for infra-only patterns.

- **Testing**:
  - Update or add unit tests around handlers to assert `session_provider.session()` is used.
  - Re-run ELS and cross-service integration tests to confirm behavior and performance.

#### PR 3  Protocol & Session Signature Cleanup

**Goal**: Normalize ELS protocol signatures to clearly differentiate:
- Domain-facing APIs that should not know about `AsyncSession`.
- Infra plumbing that legitimately carries `session: AsyncSession | None`.

- **Scope**:
  - For domain-oriented protocols (`EssayRepositoryProtocol`, `BatchCoordinationHandler`, `BatchPhaseCoordinator`, `SpecializedServiceRequestDispatcher`):
    - Where feasible, remove `session: AsyncSession | None` from the public interface and rely on the new session provider.
    - Keep `AsyncSession` explicit only where the method is strictly infra-level or part of the transactional outbox plumbing.
  - Update implementations such as `PostgreSQLEssayRepository` to:
    - Stop exposing `AsyncSession | None` in more than necessary places.
    - Prefer internal use of `ELSSessionProviderProtocol` for higher-level operations, delegating raw session usage to `EssayRepositoryQueries` and similar low-level helpers.
  - Document the **dual-mode patterns** that remain (e.g. `BatchTrackerPersistence.persist_slot_assignment`, `assignment_sql.py`, outbox publishers) as intentional exceptions, mirroring the explicit "False Positives (Do NOT Change)" section from Phase 1.

- **Testing**:
  - Type-checking across ELS and its consumers to validate protocol changes.
  - Focused unit tests on any changed signatures.
  - A small set of **contract tests** to ensure public APIs behave identically before and after cleanup.

#### PR 4  Documentation & Cross-Service Pattern Alignment

**Goal**: Capture the unified persistence and session pattern in documentation, aligning ELS, BOS, and CJ.

- **Scope**:
  - Update `.agent/rules/020.5-essay-lifecycle-service-architecture.md` to describe:
    - ORM-backed `BatchPendingContent` repository pattern.
    - ELS session provider usage and where optional `AsyncSession` remains acceptable.
  - Cross-reference CJ's `SessionProviderProtocol` and BOS `BatchDatabaseInfrastructure` as reference implementations.
  - Update this task file to:
    - Mark each PR as completed when merged.
    - Link to the associated PR IDs.

- **Testing / Validation**:
  - No new code tests; this PR is docs + config alignment.
  - Ensure `validate_docs_structure.py` and task frontmatter validation stay green.

### 3. Phase 2 Success Criteria (Additive to Phase 1)

- **Persistence Layer**:
  - [ ] All `batch_pending_content` access in production code goes through an ORM-backed repository (`PendingContentRepositoryProtocol` + implementation), with no `sqlalchemy.text` usages.
  - [ ] `BatchCoordinationHandlerImpl` depends on the pending-content protocol rather than the concrete operations class.

- **Session Management**:
  - [ ] `ELSSessionProviderProtocol` (or shared equivalent) is the primary way command/result handlers obtain sessions.
  - [ ] Domain-oriented protocols no longer expose `AsyncSession | None` except where strictly necessary.
  - [ ] Remaining optional-session signatures are documented as infra/transactional-outbox plumbing, not domain features.

- **Alignment with CJ/BOS**:
  - [ ] ELS patterns match CJ and BOS at the architectural level (repositories + session providers + transactional outbox), with Option B assignment SQL and other exceptions explicitly documented.
  - [ ] New documentation clearly explains how ELS fits into the cross-service persistence/session standards.
