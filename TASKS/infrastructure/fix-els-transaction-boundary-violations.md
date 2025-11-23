---
id: fix-els-transaction-boundary-violations
title: Fix Els Transaction Boundary Violations
type: task
status: completed
priority: high
domain: infrastructure
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-23'
service: essay_lifecycle_service
owner: ''
program: ''
related: []
labels: []
---

# TASK: Fix Essay Lifecycle Service Transaction Boundary Violations

**Status**: Completed – Remaining real transaction boundary violations fixed and tested
**Priority**: High
**Created**: 2025-11-21
**Type**: Refactoring - Architectural Compliance

---

## Problem Statement

The Essay Lifecycle Service (ELS) has systematic transaction boundary violations where handlers create multiple independent transaction blocks instead of using a single Unit of Work pattern. This breaks ACID guarantees and creates inconsistency risks where database operations can commit but subsequent event publishing or state updates can fail.

### Root Cause

Handlers incorrectly structure operations into multiple sequential `async with session.begin()` blocks instead of consolidating all operations (business logic + event publishing) into a single atomic transaction.

### Architectural Standard Violated

**Rule**: `.claude/rules/042.1-transactional-outbox-pattern.md` (Lines 64-82, 137-143)

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

---

## Affected Files

### High Priority - Core Handlers (initial analysis)

#### 1. Batch Coordination Handler
**File**: `services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py`
**Violations**: 7 independent transaction blocks

**Critical Methods**:
- `handle_batch_essays_registered()` - Lines 79-191 (3 separate transactions)
  - Transaction 1 (Lines 79-113): Batch registration + essay creation
  - Transaction 2 (Lines 124-141): Content assignment loop
  - Transaction 3 (Lines 185-191): Batch completion event publishing

- `handle_essay_content_provisioned()` - Lines 245-334 (2 separate transactions)
  - Transaction 1 (Lines 265): Content assignment
  - Transaction 2 (Lines 312-334): Post-assignment side effects + events

- `handle_essay_validation_failed()` - Lines 385-450 (2 separate transactions)
  - Transaction 1: Failure tracking
  - Transaction 2 (Lines 404-450): Batch completion event publishing

**Impact**: If any later transaction fails, earlier operations remain committed, causing database/event inconsistency.

#### 2. Result Handlers (now conformant)

**Spellcheck Result Handler**
- **File**: `services/essay_lifecycle_service/implementations/spellcheck_result_handler.py`
- **Violations**: 2 transaction blocks
  - Line 69: `handle_spellcheck_rich_result()` - Persist metrics
  - Line 157: `handle_spellcheck_phase_completed()` - State transition + batch coordination

**NLP Result Handler**
- **File**: `services/essay_lifecycle_service/implementations/nlp_result_handler.py`
- **Violations**: 1 transaction block
  - Line 96: `handle_nlp_analysis_completed()` - State transitions for batch

**CJ Result Handler**
- **File**: `services/essay_lifecycle_service/implementations/cj_result_handler.py`
- **Violations**: 2 transaction blocks
  - Line 102: `handle_cj_assessment_completed()` - State transitions
  - Line 349: `handle_cj_assessment_failed()` - Batch-wide failure handling

**Student Association Handler**
- **File**: `services/essay_lifecycle_service/implementations/student_association_handler.py`
- **Violations**: 1 transaction block
  - Line 85: `handle_student_associations_confirmed()` - Event publishing + batch completion

#### 3. Command Handlers (session propagation tightened)

**Spellcheck Command Handler**
- **File**: `services/essay_lifecycle_service/implementations/spellchecker_command_handler.py`
- **Violations**: 1 transaction block
  - Line 68: `process_initiate_spellcheck_command()` - State machine transitions

**NLP Command Handler**
- **File**: `services/essay_lifecycle_service/implementations/nlp_command_handler.py`
- **Violations**: 1 transaction block
  - Line 75: `process_initiate_nlp_command()` - State machine transitions

**CJ Assessment Command Handler**
- **File**: `services/essay_lifecycle_service/implementations/cj_assessment_command_handler.py`
- **Violations**: 1 transaction block
  - Line 71: `process_initiate_cj_assessment_command()` - State machine transitions

#### 4. API Routes (read-only, no transactional writes)

**Essay Routes**
- **File**: `services/essay_lifecycle_service/api/essay_routes.py`
- **Violations**: Multiple transaction blocks in endpoint handlers
- **Methods**: Essay submission, status updates

**Batch Routes**
- **File**: `services/essay_lifecycle_service/api/batch_routes.py`
- **Violations**: Transaction blocks in batch management endpoints
- **Methods**: Batch creation, status queries

**Health Routes**
- **File**: `services/essay_lifecycle_service/api/health_routes.py`
- **Status**: May have transaction blocks in health check operations

### Medium Priority - Collaborator Validation (5 files)

#### 5. Session Propagation Verification

**Files requiring validation** (should already be correct, but need verification):
- `services/essay_lifecycle_service/implementations/batch_tracker_persistence.py`
- `services/essay_lifecycle_service/implementations/essay_repository_postgres_impl.py`
- `services/essay_lifecycle_service/implementations/db_failure_tracker.py`
- `services/essay_lifecycle_service/domain_services/content_assignment_service.py`
- `services/essay_lifecycle_service/implementations/batch_lifecycle_publisher.py`

**Verification Checklist**:
- [ ] All methods accept `session: AsyncSession | None` parameter
- [ ] When session provided, methods use it (no `self.session_factory()`)
- [ ] When session provided, methods NEVER commit (let caller handle)
- [ ] When session is None, methods create own session and commit (standalone usage)

---

## Implementation Plan

### Phase 1: Batch Coordination Handler (Highest Impact)

**Target**: `batch_coordination_handler_impl.py`

#### Method 1: `handle_batch_essays_registered()`

**Current Pattern** (Lines 79-191):
```python
# Transaction 1: Register batch
async with self.session_factory() as session:
    async with session.begin():
        await self.batch_tracker.register_batch(...)
        await self.repository.create_essay_records_batch(...)

# Transaction 2: Process pending content
for content_metadata in pending_content_list:
    async with self.session_factory() as session:
        async with session.begin():
            await self.content_assignment_service.assign_content_to_essay(...)

# Transaction 3: Publish completion event
async with self.session_factory() as session:
    async with session.begin():
        await self.batch_lifecycle_publisher.publish_batch_content_provisioning_completed(...)
```

**Refactored Pattern**:
```python
# SINGLE TRANSACTION for all operations
async with self.session_factory() as session:
    async with session.begin():
        # Phase 1: Register batch
        await self.batch_tracker.register_batch(..., session=session)
        await self.repository.create_essay_records_batch(..., session=session)

        # Phase 2: Process pending content
        for content_metadata in pending_content_list:
            await self.content_assignment_service.assign_content_to_essay(
                ...,
                session=session  # Share session for atomicity
            )

        # Phase 3: Publish completion event (outbox)
        await self.batch_lifecycle_publisher.publish_batch_content_provisioning_completed(
            ...,
            session=session  # Outbox in same transaction
        )

        # All commits atomically at end
```

**Key Changes**:
1. Single outer `async with session.begin()` block
2. Pass `session=session` to ALL collaborators
3. Remove intermediate transaction blocks
4. Event publishing uses same session (transactional outbox)

#### Method 2: `handle_essay_content_provisioned()`

**Current Pattern** (Lines 245-334):
```python
# Direct assignment call (creates own transaction)
await assign_via_essay_states_immediate_commit(...)

# Transaction 2: Post-assignment effects
async with self.session_factory() as session:
    async with session.begin():
        await self.content_assignment_service.assign_content_to_essay(...)
        await self.batch_lifecycle_publisher.publish_event(...)
```

**Refactored Pattern**:
```python
# SINGLE TRANSACTION for all operations
async with self.session_factory() as session:
    async with session.begin():
        # Assignment with session (if applicable)
        await self.content_assignment_service.assign_content_to_essay(
            ...,
            session=session
        )

        # Post-assignment effects
        await self.batch_lifecycle_publisher.publish_event(
            ...,
            session=session
        )

        # Commits atomically
```

**Note**: `assign_via_essay_states_immediate_commit()` is FALSE POSITIVE - keep its immediate commit for MVCC coordination, but structure handler to minimize impact.

#### Method 3: `handle_essay_validation_failed()`

**Pattern**: Consolidate failure tracking + batch completion check into single transaction

### Phase 2: Result Handlers

**Approach**: Each handler method should have exactly ONE `async with session.begin()` block that encompasses:
1. State machine transitions
2. Batch coordination checks
3. Event publishing (via outbox)

**Standard Template**:
```python
async def handle_phase_completed(self, envelope, correlation_id, http_session, span):
    event_data = PhaseCompletedV1.model_validate(envelope.data)

    # SINGLE TRANSACTION
    async with self.session_factory() as session:
        async with session.begin():
            # 1. Get current state
            essay_state = await self.repository.get_essay_state(
                event_data.essay_id,
                session
            )

            # 2. Update state via state machine
            updated_state = await self.repository.update_essay_status_via_machine(
                essay_id=event_data.essay_id,
                event=StateEvent.PHASE_COMPLETED,
                session=session,
                correlation_id=correlation_id,
            )

            # 3. Check batch completion
            await self.batch_coordinator.check_batch_completion(
                essay_state=updated_state,
                phase_name=PhaseName.CURRENT_PHASE,
                correlation_id=correlation_id,
                session=session,  # Share session
            )

            # Commits atomically

    return True
```

### Phase 3: Command Handlers

**Pattern**: Similar to result handlers - single transaction for state machine + command emission

### Phase 4: API Routes

**Pattern**: Single transaction per endpoint operation:
```python
@router.post("/essays/{essay_id}/submit")
async def submit_essay(essay_id: str, data: SubmitRequest):
    async with session_factory() as session:
        async with session.begin():
            # 1. Validate essay
            essay = await repository.get_essay(essay_id, session)

            # 2. Update state
            await repository.update_essay_status(essay_id, Status.SUBMITTED, session)

            # 3. Publish event (outbox)
            await publisher.publish_essay_submitted(essay_id, session)

            # Commits atomically

    return {"status": "submitted"}
```

---

## Testing Strategy

### Unit Tests

**New Tests Required**:
1. Transaction rollback tests - verify all operations rollback on failure
2. Atomicity tests - ensure database + outbox either both succeed or both fail
3. Concurrent worker tests - verify MVCC coordination still works

**Example Test**:
```python
@pytest.mark.asyncio
async def test_batch_registration_atomic_rollback():
    """Verify batch registration rolls back entirely if event publishing fails."""

    # Setup: Mock event publisher to fail
    mock_publisher.publish_event.side_effect = Exception("Publishing failed")

    # Execute: Register batch
    with pytest.raises(Exception):
        await handler.handle_batch_essays_registered(event, correlation_id)

    # Verify: NO batch in database (transaction rolled back)
    async with session_factory() as session:
        batch = await batch_tracker.get_batch(batch_id, session)
        assert batch is None  # Should not exist due to rollback
```

### Integration Tests

**Existing Tests to Validate**:
- `tests/functional/test_e2e_comprehensive_real_batch_guest_flow.py`
- `tests/functional/test_e2e_comprehensive_real_batch_with_student_matching.py`
- `tests/functional/test_e2e_cj_after_nlp_with_pruning.py`
- `tests/functional/test_e2e_sequential_pipelines.py`

**Validation Criteria**:
- All tests pass without modification
- No new deadlocks or MVCC errors
- No performance degradation

### Performance Testing

**Concerns**:
- Single large transaction vs. multiple small transactions
- Lock contention with concurrent workers
- MVCC snapshot visibility

**Mitigation**:
- Keep `assign_via_essay_states_immediate_commit()` for MVCC coordination
- Use `FOR UPDATE SKIP LOCKED` to prevent deadlocks
- Monitor transaction duration metrics

---

## Success Criteria

### Code Quality

> Note: The original checklist assumed refactoring **all 17** initially flagged handlers.
> By 2025-11-23, many of these were already compliant. The implementation for this
> task focused on the **remaining real violations and weak points**, summarized above.

- [ ] Remaining high-risk paths in batch coordination use a shared session for state changes and outbox writes (validated by new tests).
- [ ] Command handlers consistently pass the active `session` into repository reads/writes when operating inside a transaction.
- [ ] Option B (`assign_via_essay_states_immediate_commit`) is explicitly documented as an intentional immediate-commit exception for MVCC coordination.
- [ ] Transactional outbox publisher calls in assignment/batch-completion flows are covered by unit tests asserting the `session` parameter.

### Architectural Compliance
- [ ] Follows Rule 042.1 (Transactional Outbox Pattern)
- [ ] Matches reference implementations (Class Management Service pattern)
- [ ] Session propagation follows session-aware dual-mode pattern
- [ ] No regression in MVCC coordination behavior

### Testing
- [ ] All existing integration tests pass
- [ ] New atomicity tests added and passing
- [ ] Transaction rollback tests verify proper cleanup
- [ ] No new deadlocks or MVCC errors in concurrent scenarios

### Performance
- [ ] No significant performance degradation
- [ ] Transaction duration within acceptable limits
- [ ] Lock contention remains manageable with concurrent workers

---

## Rollback Plan

If refactoring causes issues:

1. **Git Revert**: All changes in single PR, easy to revert
2. **Feature Flag**: Consider adding `ENABLE_ATOMIC_TRANSACTIONS` flag if phased rollout needed
3. **Monitoring**: Watch for:
   - Increased transaction duration
   - Deadlock errors (PostgreSQL error code 40P01)
   - MVCC snapshot isolation errors
   - Event publishing failures

---

## Related Documentation

### Rules
- `.claude/rules/042.1-transactional-outbox-pattern.md` - Primary pattern definition
- `.claude/rules/042-async-patterns-and-di.md` - Async session management
- `.claude/rules/020.5-essay-lifecycle-service-architecture.md` - ELS-specific patterns
- `.claude/rules/085-database-migration-standards.md` - Database transaction standards

### Reference Implementations
- `services/class_management_service/implementations/batch_author_matches_handler.py:126-192` - Gold standard
- `services/identity_service/implementations/user_repository_sqlalchemy_impl.py` - Simple CRUD pattern
- `services/batch_conductor_service/implementations/postgres_batch_state_repository.py` - Repository pattern

### Investigation Reports
- `.claude/work/session/handoff.md` - Investigation context
- This document - Full investigation findings

---

## Notes

### False Positives (Do NOT Change)

1. **`assignment_sql.py:assign_via_essay_states_immediate_commit()`**
   - **Keep as-is**: Immediate commit required for MVCC cross-process coordination
   - **Justification**: Uses `FOR UPDATE SKIP LOCKED` to prevent worker deadlocks
   - **Rule**: Endorsed in Rule 020.5:37-40

2. **`batch_tracker_persistence.py` session-aware methods**
   - **Keep dual-mode pattern**: Accept session OR create own
   - **Correct behavior**: Never commits when session provided
   - **Pattern**: `persist_slot_assignment()`, `mark_batch_completed()`

3. **`refresh_batch_metrics()`**
   - **Keep as-is**: Read-only metric collection, no atomicity requirements

### Open Questions

1. **Transaction Size**: Are consolidated transactions too large?
   - **Mitigation**: Monitor transaction duration, consider breaking into sub-operations if needed

2. **Lock Contention**: Will longer transactions increase lock contention?
   - **Mitigation**: `FOR UPDATE SKIP LOCKED` should prevent most issues

3. **Outbox Relay**: Is relay worker handling increased outbox volume?
   - **Monitoring**: Watch outbox table size and relay processing rate

---

## Implementation Checklist

### Pre-Implementation
- [ ] Read Rule 042.1 (Transactional Outbox Pattern)
- [ ] Review reference implementation (Class Management Service)
- [ ] Understand MVCC coordination pattern in `assignment_sql.py`
- [ ] Review existing integration tests

### Implementation
- [ ] Phase 1: Refactor `batch_coordination_handler_impl.py`
- [ ] Phase 2: Refactor result handlers (4 files)
- [ ] Phase 3: Refactor command handlers (3 files)
- [ ] Phase 4: Refactor API routes (3 files)
- [ ] Phase 5: Validate session propagation (5 collaborator files)

### Testing
- [ ] Run existing integration tests
- [ ] Add transaction rollback tests
- [ ] Add atomicity verification tests
- [ ] Run concurrent worker tests
- [ ] Performance regression testing

### Validation
- [ ] Code review against architectural standards
- [ ] Verify no collaborator commits when session provided
- [ ] Confirm outbox pattern consistently used
- [ ] Monitor metrics after deployment

### Documentation
- [ ] Update this task document with findings
- [ ] Document any deviations in Rule 020.5
- [ ] Update handoff.md with refactoring context

---

**Last Updated**: 2025-11-21
**Investigator**: Claude (research-diagnostic agent)
**Approver**: User
**Implementation Status**: Ready to Begin
