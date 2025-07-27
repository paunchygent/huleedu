# Transactional Outbox Pattern Implementation for Essay Lifecycle Service

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Background and Problem Statement](#background-and-problem-statement)
3. [The Solution: Unit of Work Pattern](#the-solution-unit-of-work-pattern)
4. [Implementation Plan Overview](#implementation-plan-overview)
5. [Detailed Implementation Steps](#detailed-implementation-steps)
6. [Code Examples: Before and After](#code-examples-before-and-after)
7. [Testing Strategy](#testing-strategy)
8. [Common Pitfalls to Avoid](#common-pitfalls-to-avoid)

---

## Executive Summary

**Goal**: Transform the Essay Lifecycle Service (ELS) from using a "resilient publishing pattern" (Kafka with outbox fallback) to a **true transactional outbox pattern** where all database changes and event publishing happen atomically within the same database transaction.

**Key Change**: Every operation that modifies the database AND publishes events must now manage a single database transaction that encompasses both actions.

**Impact**: This is a breaking change that affects all handlers, repositories, and the event publisher. No backwards compatibility is maintained.

---

## Background and Problem Statement

### Current Implementation (INCORRECT)
The current ELS implementation has a critical flaw:

```python
# PROBLEM: Two separate transactions!
async def handle_essay_content_provisioned(self, event_data, correlation_id):
    # Transaction 1: Database write
    await self.repository.update_essay_state(...)  # Has its own transaction
    
    # Transaction 2: Event publish (or fallback to outbox)
    await self.event_publisher.publish_essay_slot_assigned(...)  # Separate transaction
```

**The Problem**: If the database write succeeds but event publishing fails (even with outbox fallback), we have data inconsistency. The essay state is updated but no event is published.

### Desired Implementation (CORRECT)
```python
# SOLUTION: One transaction for both operations!
async def handle_essay_content_provisioned(self, event_data, correlation_id):
    async with self.session_factory() as session:
        async with session.begin():  # Start transaction
            # Both operations use the SAME session/transaction
            await self.repository.update_essay_state(..., session=session)
            await self.event_publisher.publish_essay_slot_assigned(..., session=session)
            # Transaction commits here - BOTH succeed or BOTH fail
```

---

## The Solution: Unit of Work Pattern

The **Unit of Work** pattern ensures that all operations within a business transaction share the same database session and transaction boundary.

### Key Concepts:
1. **Session Factory**: Creates database sessions for transaction management
2. **Shared Session**: Passed to all operations within a transaction
3. **Transaction Boundary**: Managed by the handler, not individual repositories
4. **Atomic Commit**: All changes commit together or roll back together

### Architectural Flow:
```
Handler (owns transaction)
    ├── Creates Session
    ├── Begins Transaction
    ├── Calls Repository (passes session)
    │   └── Uses provided session for DB operations
    ├── Calls EventPublisher (passes session)
    │   └── Uses provided session to write to outbox table
    └── Commits/Rollbacks Transaction
```

---

## Implementation Plan Overview

### Phase 1: Update Protocols and Interfaces
1. Add `session: AsyncSession` parameter to all write methods in `EssayRepositoryProtocol`
2. Update `EventPublisher` protocol (already done in the provided refactor)

### Phase 2: Update Repository Implementation
1. Modify `PostgreSQLEssayRepository` to accept external sessions
2. Add session factory exposure method
3. Remove internal transaction management from write methods

### Phase 3: Update All Handlers
1. Inject session factory into handlers via DI
2. Implement transaction management in every handler method that writes data
3. Pass session to both repository and event publisher calls

### Phase 4: Update Dependency Injection
1. Create session factory provider
2. Update handler providers to inject session factory

### Phase 5: Update Tests
1. Mock session and transaction behavior
2. Test rollback scenarios
3. Verify atomicity guarantees

---

## Detailed Implementation Steps

### Step 1: Update EssayRepositoryProtocol

**File**: `services/essay_lifecycle_service/protocols.py`

**Changes Required**: Add `session: AsyncSession` parameter to ALL methods that modify data.

```python
from sqlalchemy.ext.asyncio import AsyncSession

class EssayRepositoryProtocol(Protocol):
    """Protocol for essay state persistence operations."""
    
    # READ methods - No change needed
    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        ...
    
    # WRITE methods - Add session parameter
    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
        session: AsyncSession,  # NEW REQUIRED PARAMETER
    ) -> None:
        """Update essay state with new status and metadata."""
        ...
    
    async def create_essay_record(
        self, 
        essay_ref: EntityReference, 
        correlation_id: UUID | None = None,
        session: AsyncSession,  # NEW REQUIRED PARAMETER
    ) -> EssayState:
        """Create new essay record from entity reference."""
        ...
    
    async def create_essay_records_batch(
        self, 
        essay_refs: list[EntityReference], 
        correlation_id: UUID | None = None,
        session: AsyncSession,  # NEW REQUIRED PARAMETER
    ) -> list[EssayState]:
        """Create multiple essay records in single atomic transaction."""
        ...
    
    async def create_or_update_essay_state_for_slot_assignment(
        self,
        internal_essay_id: str,
        batch_id: str,
        text_storage_id: str,
        original_file_name: str,
        file_size: int,
        content_hash: str | None,
        initial_status: EssayStatus,
        correlation_id: UUID | None = None,
        session: AsyncSession,  # NEW REQUIRED PARAMETER
    ) -> EssayState:
        """Create or update essay state for slot assignment."""
        ...
    
    async def create_essay_state_with_content_idempotency(
        self,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession,  # NEW REQUIRED PARAMETER
    ) -> tuple[bool, str | None]:
        """Create essay state with atomic idempotency check."""
        ...
    
    # NEW METHOD - Expose session factory
    def get_session_factory(self) -> Any:  # Returns async_sessionmaker
        """Get the session factory for transaction management."""
        ...
```

### Step 2: Update PostgreSQLEssayRepository

**File**: `services/essay_lifecycle_service/implementations/essay_repository_postgres_impl.py`

**Key Changes**:
1. Expose session factory
2. Remove internal session creation from write methods
3. Use provided session parameter

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

class PostgreSQLEssayRepository(EssayRepositoryProtocol):
    def __init__(self, settings: Settings, database_metrics: DatabaseMetrics):
        # ... existing initialization ...
        
        # Create session factory
        self._session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    
    def get_session_factory(self) -> async_sessionmaker:
        """Get the session factory for transaction management."""
        return self._session_factory
    
    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
        session: AsyncSession,  # NOW REQUIRED
    ) -> None:
        """Update essay state using provided session."""
        # BEFORE (WRONG):
        # async with self._session_factory() as session:
        #     stmt = update(EssayStateOrm)...
        #     await session.execute(stmt)
        #     await session.commit()  # DON'T commit here!
        
        # AFTER (CORRECT):
        stmt = update(EssayStateOrm).where(
            EssayStateOrm.essay_id == essay_id
        ).values(
            current_status=new_status,
            processing_metadata=func.jsonb_merge(
                EssayStateOrm.processing_metadata,
                metadata
            ),
            updated_at=datetime.now(UTC)
        )
        
        if storage_reference:
            content_type, storage_id = storage_reference
            stmt = stmt.values(
                storage_references=func.jsonb_set(
                    EssayStateOrm.storage_references,
                    [content_type.value],
                    f'"{storage_id}"'
                )
            )
        
        result = await session.execute(stmt)
        
        if result.rowcount == 0:
            raise_resource_not_found(
                service="essay_lifecycle_service",
                operation="update_essay_state",
                resource_type="Essay",
                resource_id=essay_id,
                correlation_id=correlation_id or UUID("00000000-0000-0000-0000-000000000000"),
            )
        
        # NO session.commit() - Let the handler manage the transaction!
```

### Step 3: Update Event Publisher (Already Provided)

**File**: `services/essay_lifecycle_service/implementations/event_publisher.py`

The provided refactor is correct. Key points:
- Removed Kafka direct publishing
- All methods require `session: AsyncSession`
- Uses outbox repository with provided session

### Step 4: Update Batch Coordination Handler

**File**: `services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py`

**Pattern to Apply to EVERY Handler Method**:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

class DefaultBatchCoordinationHandler(BatchCoordinationHandler):
    def __init__(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        event_publisher: EventPublisher,
        session_factory: async_sessionmaker,  # NEW DEPENDENCY
    ) -> None:
        self.batch_tracker = batch_tracker
        self.repository = repository
        self.event_publisher = event_publisher
        self.session_factory = session_factory  # Store session factory
    
    async def handle_batch_essays_registered(
        self,
        event_data: BatchEssaysRegistered,
        correlation_id: UUID,
    ) -> bool:
        """Handle batch registration with proper transaction management."""
        try:
            logger.info(
                "Processing BatchEssaysRegistered event",
                extra={
                    "batch_id": event_data.batch_id,
                    "expected_count": event_data.expected_essay_count,
                    "correlation_id": str(correlation_id),
                },
            )
            
            # START UNIT OF WORK
            async with self.session_factory() as session:
                async with session.begin():  # Auto commit/rollback
                    # Register batch with tracker (if it needs DB access)
                    await self.batch_tracker.register_batch(event_data, correlation_id)
                    
                    # Create essay records in database
                    essay_refs = [
                        EntityReference(
                            entity_id=essay_id, 
                            entity_type="essay", 
                            parent_id=event_data.batch_id
                        )
                        for essay_id in event_data.essay_ids
                    ]
                    
                    await self.repository.create_essay_records_batch(
                        essay_refs, 
                        correlation_id=correlation_id,
                        session=session  # PASS SESSION
                    )
                    
                    # Check if batch is immediately complete
                    batch_completion_result = await self.batch_tracker.check_batch_completion(
                        event_data.batch_id
                    )
                    
                    if batch_completion_result is not None:
                        batch_ready_event, original_correlation_id = batch_completion_result
                        
                        # Publish event IN SAME TRANSACTION
                        await self.event_publisher.publish_batch_essays_ready(
                            event_data=batch_ready_event,
                            correlation_id=original_correlation_id or correlation_id,
                            session=session  # PASS SESSION
                        )
                    
                    # Transaction commits here automatically
                    
            logger.info(
                "Successfully processed batch registration",
                extra={"batch_id": event_data.batch_id}
            )
            return True
            
        except Exception as e:
            # Log error and re-raise
            logger.error(
                f"Failed to process batch registration: {e}",
                extra={"batch_id": event_data.batch_id},
                exc_info=True
            )
            raise
    
    async def handle_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: UUID,
    ) -> bool:
        """Handle content provisioning with atomic slot assignment and event publishing."""
        try:
            # START UNIT OF WORK
            async with self.session_factory() as session:
                async with session.begin():
                    # Try slot assignment (Redis operation, outside transaction)
                    assigned_essay_id = await self.batch_tracker.assign_slot_to_content(
                        event_data.batch_id, 
                        event_data.text_storage_id, 
                        event_data.original_file_name
                    )
                    
                    if assigned_essay_id is None:
                        # No slots - publish excess content event
                        excess_event = ExcessContentProvisionedV1(
                            batch_id=event_data.batch_id,
                            original_file_name=event_data.original_file_name,
                            text_storage_id=event_data.text_storage_id,
                            reason="NO_AVAILABLE_SLOT",
                            correlation_id=correlation_id,
                            timestamp=datetime.now(UTC),
                        )
                        
                        await self.event_publisher.publish_excess_content_provisioned(
                            event_data=excess_event,
                            correlation_id=correlation_id,
                            session=session  # PASS SESSION
                        )
                        return False
                    
                    # Create/update essay state in database
                    essay_data = {
                        "internal_essay_id": assigned_essay_id,
                        "initial_status": EssayStatus.READY_FOR_PROCESSING,
                        "original_file_name": event_data.original_file_name,
                        "file_size": event_data.file_size_bytes,
                        "file_upload_id": event_data.file_upload_id,
                        "content_hash": event_data.content_md5_hash,
                    }
                    
                    was_created, final_essay_id = await self.repository.create_essay_state_with_content_idempotency(
                        batch_id=event_data.batch_id,
                        text_storage_id=event_data.text_storage_id,
                        essay_data=essay_data,
                        correlation_id=correlation_id,
                        session=session  # PASS SESSION
                    )
                    
                    if was_created:
                        # Persist slot assignment
                        await self.batch_tracker.persist_slot_assignment(
                            event_data.batch_id,
                            assigned_essay_id,
                            event_data.text_storage_id,
                            event_data.original_file_name,
                        )
                    
                    # Always publish slot assigned event
                    slot_assigned_event = EssaySlotAssignedV1(
                        batch_id=event_data.batch_id,
                        essay_id=final_essay_id,
                        file_upload_id=event_data.file_upload_id,
                        text_storage_id=event_data.text_storage_id,
                        correlation_id=correlation_id,
                    )
                    
                    await self.event_publisher.publish_essay_slot_assigned(
                        event_data=slot_assigned_event,
                        correlation_id=correlation_id,
                        session=session  # PASS SESSION
                    )
                    
                    # Check batch completion
                    batch_completion_result = await self.batch_tracker.mark_slot_fulfilled(
                        event_data.batch_id, 
                        final_essay_id, 
                        event_data.text_storage_id
                    )
                    
                    if batch_completion_result is not None:
                        batch_ready_event, original_correlation_id = batch_completion_result
                        
                        await self.event_publisher.publish_batch_essays_ready(
                            event_data=batch_ready_event,
                            correlation_id=original_correlation_id or correlation_id,
                            session=session  # PASS SESSION
                        )
                    
                    # Transaction commits here
                    
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to process content provisioning: {e}",
                extra={
                    "batch_id": event_data.batch_id,
                    "text_storage_id": event_data.text_storage_id
                },
                exc_info=True
            )
            raise
```

### Step 5: Update Command Handlers

**Files to Update**:
- `spellcheck_command_handler.py`
- `cj_assessment_command_handler.py`
- `future_services_command_handlers.py`
- `batch_command_handler_impl.py`

**Pattern for Command Handlers**:

```python
class SpellcheckCommandHandler:
    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
        session_factory: async_sessionmaker,  # NEW
    ) -> None:
        self.repository = repository
        self.request_dispatcher = request_dispatcher
        self.event_publisher = event_publisher
        self.session_factory = session_factory
    
    async def initiate_spellcheck_for_batch(
        self,
        batch_id: str,
        language: Language,
        correlation_id: UUID,
    ) -> None:
        """Initiate spellcheck with proper transaction management."""
        # START UNIT OF WORK
        async with self.session_factory() as session:
            async with session.begin():
                # Get essays (read operation, can use session)
                essays = await self.repository.list_essays_by_batch(batch_id)
                
                essays_to_process = []
                for essay in essays:
                    if essay.current_status == EssayStatus.READY_FOR_PROCESSING:
                        # Update status to IN_PROGRESS
                        await self.repository.update_essay_state(
                            essay_id=essay.essay_id,
                            new_status=EssayStatus.SPELLCHECK_IN_PROGRESS,
                            metadata={"spellcheck_started_at": datetime.now(UTC).isoformat()},
                            correlation_id=correlation_id,
                            session=session  # PASS SESSION
                        )
                        
                        # Publish status update event
                        await self.event_publisher.publish_status_update(
                            essay_ref=EntityReference(
                                entity_id=essay.essay_id,
                                entity_type="essay"
                            ),
                            status=EssayStatus.SPELLCHECK_IN_PROGRESS,
                            correlation_id=correlation_id,
                            session=session  # PASS SESSION
                        )
                        
                        essays_to_process.append(
                            EssayProcessingInputRefV1(
                                essay_id=essay.essay_id,
                                text_storage_id=essay.storage_references.get(ContentType.ORIGINAL_TEXT)
                            )
                        )
                
                # Dispatch requests (if dispatcher needs session)
                if essays_to_process:
                    await self.request_dispatcher.dispatch_spellcheck_requests(
                        essays_to_process=essays_to_process,
                        language=language,
                        batch_id=batch_id,
                        correlation_id=correlation_id,
                        session=session  # PASS SESSION if dispatcher writes to DB
                    )
                
                # Transaction commits here
```

### Step 6: Update Service Result Handler

**File**: `services/essay_lifecycle_service/implementations/service_result_handler_impl.py`

```python
class DefaultServiceResultHandler(ServiceResultHandler):
    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,  # NEW
    ) -> None:
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory
    
    async def handle_spellcheck_result(
        self,
        result_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> bool:
        """Handle spellcheck result with transaction management."""
        # START UNIT OF WORK
        async with self.session_factory() as session:
            async with session.begin():
                # Update essay state
                new_status = (
                    EssayStatus.SPELLCHECK_COMPLETED 
                    if result_data.success 
                    else EssayStatus.SPELLCHECK_FAILED
                )
                
                await self.repository.update_essay_state(
                    essay_id=result_data.essay_id,
                    new_status=new_status,
                    metadata={
                        "spellcheck_completed_at": datetime.now(UTC).isoformat(),
                        "spellcheck_result": result_data.model_dump(),
                    },
                    storage_reference=(
                        ContentType.SPELLCHECKED_TEXT, 
                        result_data.corrected_text_storage_id
                    ) if result_data.success else None,
                    correlation_id=correlation_id,
                    session=session  # PASS SESSION
                )
                
                # Publish status update
                await self.event_publisher.publish_status_update(
                    essay_ref=EntityReference(
                        entity_id=result_data.essay_id,
                        entity_type="essay"
                    ),
                    status=new_status,
                    correlation_id=correlation_id,
                    session=session  # PASS SESSION
                )
                
                # Check batch phase completion
                essay_state = await self.repository.get_essay_state(result_data.essay_id)
                if essay_state:
                    await self.batch_coordinator.check_batch_completion(
                        essay_state=essay_state,
                        phase_name=PhaseName.SPELLCHECK,
                        correlation_id=correlation_id,
                        session=session  # PASS SESSION if coordinator publishes events
                    )
                
                # Transaction commits here
                
        return True
```

### Step 7: Update Dependency Injection

**File**: `services/essay_lifecycle_service/di.py`

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

class CoreInfrastructureProvider(Provider):
    # ... existing providers ...
    
    @provide(scope=Scope.APP)
    def provide_session_factory(
        self, repository: EssayRepositoryProtocol
    ) -> async_sessionmaker:
        """Provide session factory from repository."""
        return repository.get_session_factory()

class CommandHandlerProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_spellcheck_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
        session_factory: async_sessionmaker,  # INJECT
    ) -> SpellcheckCommandHandler:
        """Provide spellcheck command handler with session factory."""
        return SpellcheckCommandHandler(
            repository, request_dispatcher, event_publisher, session_factory
        )
    
    # Update ALL handler providers similarly...

class BatchCoordinationProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_batch_coordination_handler(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        event_publisher: EventPublisher,
        session_factory: async_sessionmaker,  # INJECT
    ) -> BatchCoordinationHandler:
        """Provide batch coordination handler with session factory."""
        return DefaultBatchCoordinationHandler(
            batch_tracker, repository, event_publisher, session_factory
        )
```

### Step 8: Update Service Request Dispatcher (If Needed)

**File**: `services/essay_lifecycle_service/implementations/service_request_dispatcher.py`

Only needs updating if it performs database writes. If it only publishes events:

```python
class DefaultSpecializedServiceRequestDispatcher:
    async def dispatch_cj_assessment_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        course_code: CourseCode,
        essay_instructions: str,
        batch_id: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,  # ADD if needed
    ) -> None:
        """Dispatch requests, using session if database writes are needed."""
        # If no DB writes, just publish to outbox
        for essay in essays_to_process:
            request_data = {
                "essay_id": essay.essay_id,
                "text_storage_id": essay.text_storage_id,
                # ... other fields ...
            }
            
            if session:
                # If called within a transaction, use provided session
                await self.outbox_repository.add_event(
                    aggregate_id=essay.essay_id,
                    aggregate_type="essay",
                    event_type="cj_assessment.request.v1",
                    event_data=request_data,
                    topic="essay.cj_assessment.requests",
                    session=session
                )
            else:
                # If called standalone, create own transaction
                await self.outbox_repository.add_event(
                    aggregate_id=essay.essay_id,
                    aggregate_type="essay",
                    event_type="cj_assessment.request.v1",
                    event_data=request_data,
                    topic="essay.cj_assessment.requests"
                )
```

---

## Code Examples: Before and After

### BEFORE: Incorrect Pattern (Separate Transactions)

```python
# WRONG: Each operation has its own transaction
class SomeHandler:
    async def handle_something(self, data, correlation_id):
        # Transaction 1: Update database
        await self.repository.update_essay_state(
            essay_id=data.essay_id,
            new_status=EssayStatus.PROCESSING,
            metadata={"started_at": datetime.now().isoformat()}
        )
        # Transaction 1 commits here
        
        # Transaction 2: Publish event
        await self.event_publisher.publish_status_update(
            essay_ref=EntityReference(entity_id=data.essay_id, entity_type="essay"),
            status=EssayStatus.PROCESSING,
            correlation_id=correlation_id
        )
        # Transaction 2 commits here
        
        # PROBLEM: If event publishing fails, database is already updated!
```

### AFTER: Correct Pattern (Unit of Work)

```python
# CORRECT: One transaction for all operations
class SomeHandler:
    def __init__(self, repository, event_publisher, session_factory):
        self.repository = repository
        self.event_publisher = event_publisher
        self.session_factory = session_factory
    
    async def handle_something(self, data, correlation_id):
        # Create single transaction boundary
        async with self.session_factory() as session:
            async with session.begin():  # Start transaction
                # All operations use the same session
                await self.repository.update_essay_state(
                    essay_id=data.essay_id,
                    new_status=EssayStatus.PROCESSING,
                    metadata={"started_at": datetime.now().isoformat()},
                    session=session  # SAME SESSION
                )
                
                await self.event_publisher.publish_status_update(
                    essay_ref=EntityReference(entity_id=data.essay_id, entity_type="essay"),
                    status=EssayStatus.PROCESSING,
                    correlation_id=correlation_id,
                    session=session  # SAME SESSION
                )
                
                # Transaction commits here - BOTH succeed or BOTH rollback
```

---

## Testing Strategy

### 1. Test Transaction Rollback

```python
async def test_handler_rollback_on_event_publish_failure():
    """Test that database changes rollback when event publishing fails."""
    # Arrange
    mock_repository = Mock(spec=EssayRepositoryProtocol)
    mock_event_publisher = Mock(spec=EventPublisher)
    mock_event_publisher.publish_status_update.side_effect = Exception("Publish failed")
    
    session_factory = ... # Test session factory
    handler = SomeHandler(mock_repository, mock_event_publisher, session_factory)
    
    # Act & Assert
    with pytest.raises(Exception):
        await handler.handle_something(data, correlation_id)
    
    # Verify repository.update_essay_state was called but rolled back
    # In a real test, check database state to ensure no changes persisted
```

### 2. Test Atomicity

```python
async def test_handler_atomic_commit():
    """Test that all operations commit together."""
    # Test that after successful handler execution:
    # 1. Database changes are committed
    # 2. Events are in outbox table
    # 3. Both have the same transaction timestamp
```

### 3. Mock Session in Unit Tests

```python
@pytest.fixture
def mock_session():
    """Provide a mock session for unit tests."""
    session = AsyncMock(spec=AsyncSession)
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session

@pytest.fixture
def mock_session_factory(mock_session):
    """Provide a mock session factory."""
    factory = AsyncMock()
    factory.__aenter__ = AsyncMock(return_value=mock_session)
    factory.__aexit__ = AsyncMock()
    return factory
```

---

## Common Pitfalls to Avoid

### 1. ❌ DON'T: Create Multiple Sessions

```python
# WRONG: Creating separate sessions breaks atomicity
async def handle_something(self, data, correlation_id):
    async with self.session_factory() as session1:
        await self.repository.update_essay_state(..., session=session1)
    
    async with self.session_factory() as session2:  # DIFFERENT SESSION!
        await self.event_publisher.publish_event(..., session=session2)
```

### 2. ❌ DON'T: Commit Inside Repository

```python
# WRONG: Repository shouldn't manage transactions
class PostgreSQLEssayRepository:
    async def update_essay_state(self, ..., session: AsyncSession):
        # ... do update ...
        await session.commit()  # NO! Let the handler manage this
```

### 3. ❌ DON'T: Mix Redis Operations Inside Transactions

```python
# WRONG: Redis operations can't be rolled back
async with session.begin():
    await self.repository.update_essay_state(..., session=session)
    await self.redis_client.set("some_key", "value")  # NOT TRANSACTIONAL!
    await self.event_publisher.publish_event(..., session=session)
    # If event publish fails, database rolls back but Redis doesn't!
```

### 4. ✅ DO: Keep Redis Operations Outside Transactions

```python
# CORRECT: Redis operations before or after transaction
# Before transaction (for reads/checks)
redis_data = await self.redis_client.get("some_key")

async with session.begin():
    # Only database operations inside transaction
    await self.repository.update_essay_state(..., session=session)
    await self.event_publisher.publish_event(..., session=session)

# After transaction (for notifications)
await self.redis_client.publish("notification", "Transaction completed")
```

### 5. ✅ DO: Handle Session Scope Properly

```python
# CORRECT: Session factory creates session with proper scope
async with self.session_factory() as session:
    async with session.begin():
        # All operations here
        pass
    # Session is automatically closed after this block
```

---

## Summary Checklist

- [ ] Update `EssayRepositoryProtocol` with session parameters
- [ ] Update `PostgreSQLEssayRepository` to use provided sessions
- [ ] Update all handlers to manage transactions
- [ ] Update DI configuration to inject session factories
- [ ] Update tests for new transaction patterns
- [ ] Remove all internal transaction management from repositories
- [ ] Ensure NO backwards compatibility - clean break
- [ ] Test rollback scenarios thoroughly
- [ ] Document the pattern for future developers

---

## Questions to Ask During Implementation

1. **Does this method modify the database?** → Needs session parameter
2. **Does this method publish events?** → Needs session parameter
3. **Does this handler do both?** → Needs transaction management
4. **Is this a read-only operation?** → No session needed (can use its own)
5. **Am I inside a transaction?** → Don't create another session!

---

## End Goal

Every business operation that modifies state and publishes events is **atomic**. Either everything succeeds together, or everything fails together. No partial states, no inconsistencies, no event loss.