# Prompt: Implement Transactional Outbox Pattern for CJ Assessment Service

## Context

I need to implement the transactional outbox pattern for the CJ Assessment Service to ensure atomic event publishing with database transactions. The service currently publishes events directly to Kafka, which risks inconsistency if events fail after database commits.

## Required Implementation

Implement the outbox pattern following our established standards and patterns from other services.

## Key Resources & Rules

### 1. Transactional Outbox Pattern Standard
Read `.cursor/rules/042.1-transactional-outbox-pattern.mdc` which defines:
- The TRUE outbox pattern (store in DB, relay to Kafka)
- When to use outbox vs direct publishing
- Implementation requirements for atomicity

### 2. Shared Outbox Library
Use the existing library at `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/`:
- `outbox_manager.py` - Core outbox management logic
- `outbox_relay.py` - Worker that publishes from outbox to Kafka
- `models.py` - Base outbox table models
- Review how these components work together

### 3. Database Migration Standards
Follow `.cursor/rules/085-database-migration-standards.mdc`:
- Create migration in `services/cj_assessment_service/alembic/versions/`
- Use format: `YYYYMMDD_HHMM_description.py`
- Include both `upgrade()` and `downgrade()` functions
- Use timezone-aware timestamps: `sa.DateTime(timezone=True)`
- Create proper indexes for unpublished events query

### 4. Database Infrastructure
From `docker-compose.infrastructure.yml`:
- CJ Assessment database name: `huleedu_cj_assessment`
- Connection via service's `DATABASE_URL` environment variable
- PostgreSQL with UUID support: `gen_random_uuid()`

### 5. Async Patterns & DI
Follow `.cursor/rules/042-async-patterns-and-di.mdc`:
- Implement `OutboxRepositoryProtocol` in `protocols.py`
- Create `OutboxRepositoryImpl` in `implementations/`
- Wire via Dishka DI in `di.py` with proper scoping
- Use `Scope.REQUEST` for database sessions

### 6. Event-Driven Architecture
Follow `.cursor/rules/030-event-driven-architecture-eda-standards.mdc`:
- Use `EventEnvelope` wrapper for all events
- Implement transactional outbox pattern (section 3.1)
- Ensure idempotent event handling
- Store events within same transaction as business data

### 7. Python Coding Standards
Follow `.cursor/rules/050-python-coding-standards.mdc`:
- Type hints for all functions
- Async/await patterns throughout
- Proper error handling with `huleedu_service_libs.error_handling`
- Structured logging with correlation IDs

### 8. Reference Implementations

Study how the outbox pattern is implemented in other services:

#### File Service (`services/file_service/`)
- Check `implementations/outbox_manager.py` for outbox manager
- Review `implementations/event_publisher_impl.py` for integration
- See `alembic/versions/` for outbox table migration
- Note the relay worker setup in `outbox_relay_worker.py`

#### Batch Orchestrator Service (`services/batch_orchestrator_service/`)
- Check `implementations/batch_event_publisher.py` for outbox usage
- Review `implementations/outbox_manager.py` for transaction handling
- See migration: `20250726_0001_add_event_outbox_table.py`
- Note Redis notification pattern for relay worker

#### Class Management Service (`services/class_management_service/`)
- Check how outbox integrates with domain events
- Review `implementations/event_publisher_impl.py`
- Note the pattern for storing then notifying relay

## Implementation Steps

### Step 1: Create Database Migration

Create `services/cj_assessment_service/alembic/versions/YYYYMMDD_HHMM_add_event_outbox_table.py`:

```python
"""Add event outbox table for transactional event publishing

Revision ID: [generate with alembic]
Revises: [current revision]
Create Date: [current date]
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    op.create_table(
        'event_outbox',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('aggregate_id', sa.String(255), nullable=False),
        sa.Column('aggregate_type', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(255), nullable=False),
        sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()),
                  nullable=False),
        sa.Column('event_key', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default=sa.text('0'),
                  nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Critical indexes for outbox processing
    op.create_index('ix_event_outbox_unpublished', 'event_outbox',
                    ['published_at', 'created_at'],
                    postgresql_where=sa.text('published_at IS NULL'))
    op.create_index('ix_event_outbox_aggregate', 'event_outbox',
                    ['aggregate_type', 'aggregate_id'])

def downgrade() -> None:
    op.drop_index('ix_event_outbox_aggregate', table_name='event_outbox')
    op.drop_index('ix_event_outbox_unpublished', table_name='event_outbox')
    op.drop_table('event_outbox')
```

### Step 2: Add Outbox Model

Add to `services/cj_assessment_service/models_db.py`:

```python
from sqlalchemy.dialects.postgresql import UUID
import uuid

class EventOutbox(Base):
    """Transactional outbox for reliable event publishing."""
    __tablename__ = "event_outbox"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    event_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### Step 3: Create Outbox Protocol

Add to `services/cj_assessment_service/protocols.py`:

```python
from typing import Protocol, Any
from datetime import datetime
from uuid import UUID

class OutboxRepositoryProtocol(Protocol):
    """Protocol for outbox repository operations."""
    
    async def add_event(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: dict[str, Any],
        event_key: str | None = None,
    ) -> None:
        """Add event to outbox within current transaction."""
        ...
    
    async def get_unpublished_events(
        self,
        limit: int = 100
    ) -> list[Any]:
        """Get unpublished events for relay."""
        ...
    
    async def mark_as_published(
        self,
        event_id: UUID,
        published_at: datetime
    ) -> None:
        """Mark event as successfully published."""
        ...
```

### Step 4: Implement Outbox Manager

Create `services/cj_assessment_service/implementations/outbox_manager.py`:

```python
"""Outbox manager implementation following BOS/File Service pattern."""

from typing import Any
from uuid import UUID

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.protocols import (
    OutboxRepositoryProtocol,
    AtomicRedisClientProtocol,
)
from services.cj_assessment_service.config import Settings

logger = create_service_logger("cj_assessment_service.outbox_manager")

class OutboxManager:
    """Manages transactional event publishing via outbox pattern."""
    
    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> None:
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings
    
    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,  # EventEnvelope[Any]
        topic: str,
        correlation_id: UUID | str,
    ) -> None:
        """Store event in outbox for transactional publishing."""
        
        # Validate event data is serializable
        if not hasattr(event_data, 'model_dump'):
            raise_external_service_error(
                service="cj_assessment_service",
                operation="publish_to_outbox",
                external_service="event_serialization",
                message="Event data must be a Pydantic model",
                correlation_id=str(correlation_id),
            )
        
        # Serialize event with topic
        serialized_data = event_data.model_dump(mode="json")
        serialized_data["topic"] = topic
        
        # Store in outbox (within current transaction)
        await self.outbox_repository.add_event(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_data=serialized_data,
            event_key=aggregate_id,  # Use aggregate_id for Kafka partitioning
        )
        
        # Notify relay worker via Redis
        await self.notify_relay_worker()
        
        logger.info(
            "Event stored in outbox",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "topic": topic,
            }
        )
    
    async def notify_relay_worker(self) -> None:
        """Wake up the relay worker to process outbox."""
        try:
            await self.redis_client.lpush(
                "outbox:wake:cj_assessment_service", "1"
            )
        except Exception as e:
            # Log but don't fail - relay has polling fallback
            logger.warning(f"Failed to notify relay worker: {e}")
```

### Step 5: Wire Dependency Injection

Update `services/cj_assessment_service/di.py`:

```python
from dishka import Provider, Scope, provide

from services.cj_assessment_service.implementations.outbox_manager import OutboxManager
from services.cj_assessment_service.implementations.outbox_repository import OutboxRepositoryImpl

class OutboxProvider(Provider):
    """Provider for outbox pattern components."""
    
    @provide(scope=Scope.REQUEST)
    async def provide_outbox_repository(
        self,
        db_session: AsyncSession,
    ) -> OutboxRepositoryProtocol:
        """Provide outbox repository with current transaction."""
        return OutboxRepositoryImpl(db_session)
    
    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager."""
        # Note: repository injected per-request
        return lambda repo: OutboxManager(
            outbox_repository=repo,
            redis_client=redis_client,
            settings=settings,
        )

# Add to container creation:
# container = make_container(
#     ...,
#     OutboxProvider(),
# )
```

### Step 6: Apply Migration

```bash
# From repository root
cd services/cj_assessment_service

# Check current revision
pdm run alembic current

# Generate migration (if using autogenerate)
pdm run alembic revision --autogenerate -m "Add event outbox table"

# Or use the manually created migration
pdm run alembic upgrade head

# Verify in database
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "\dt event_outbox"
```

## Testing the Implementation

### Unit Test

```python
# tests/unit/test_outbox_manager.py

@pytest.mark.asyncio
async def test_outbox_stores_event():
    """Test that outbox manager stores events correctly."""
    
    # Arrange
    mock_repo = Mock(spec=OutboxRepositoryProtocol)
    mock_redis = Mock(spec=AtomicRedisClientProtocol)
    manager = OutboxManager(mock_repo, mock_redis, Settings())
    
    event = CJAssessmentCompletedV1(...)
    envelope = EventEnvelope(event_data=event, ...)
    
    # Act
    await manager.publish_to_outbox(
        aggregate_type="cj_batch",
        aggregate_id="batch123",
        event_type="CJAssessmentCompletedV1",
        event_data=envelope,
        topic="huleedu.cj.assessment.completed.v1",
        correlation_id="corr123"
    )
    
    # Assert
    mock_repo.add_event.assert_called_once()
    mock_redis.lpush.assert_called_once_with(
        "outbox:wake:cj_assessment_service", "1"
    )
```

### Integration Test

```python
# tests/integration/test_outbox_integration.py

@pytest.mark.integration
async def test_outbox_transaction_atomicity():
    """Test that outbox ensures atomic transaction."""
    
    async with create_test_database() as db:
        async with db.begin() as session:
            # Store business data
            grade_projection = GradeProjection(...)
            session.add(grade_projection)
            
            # Store event in outbox
            outbox_entry = EventOutbox(
                aggregate_type="cj_batch",
                aggregate_id="batch123",
                event_type="CJAssessmentCompletedV1",
                event_data={...}
            )
            session.add(outbox_entry)
            
            # Commit atomically
            await session.commit()
        
        # Verify both were saved
        assert await db.get_projection("essay123") is not None
        assert await db.get_unpublished_events() == 1
```

## Validation Checklist

- [ ] Migration creates outbox table with correct schema
- [ ] Indexes created for efficient unpublished event queries
- [ ] Outbox model added to models_db.py
- [ ] Protocol defined for outbox operations
- [ ] OutboxManager implemented following File Service pattern
- [ ] DI wiring completed with proper scoping
- [ ] Integration with existing event publishing updated
- [ ] Unit tests pass
- [ ] Integration tests verify atomicity
- [ ] Relay worker can read and publish events

## Common Issues & Solutions

1. **Migration fails**: Check current revision with `alembic current`
2. **UUID generation fails**: Ensure PostgreSQL extension enabled
3. **Redis connection fails**: Check Redis is running in docker-compose
4. **Transaction not atomic**: Ensure using same session for business + outbox
5. **Events not publishing**: Check relay worker is running

## Success Criteria

- Events and database changes are atomic
- No events lost if Kafka is down
- Relay worker processes outbox queue
- Pattern matches File Service and BOS implementations
- All tests pass

---

**Note**: This implementation ensures reliable event publishing even during Kafka outages, maintaining data consistency across the distributed system.