---
description: Core SQLAlchemy patterns - enums, timestamps, JSON serialization, outbox integration
globs: 
alwaysApply: false
---

# 053: SQLAlchemy Core Standards

## Database Enums
- **MUST** use `str, enum.Enum` inheritance for database enums
- **FORBIDDEN**: Plain `enum.Enum` inheritance (causes SQLAlchemy KeyError)

```python
# ✅ CORRECT
class StatusEnum(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"

# ❌ FORBIDDEN
class StatusEnum(enum.Enum):
    PENDING = "pending"
```

## PostgreSQL Timestamps
- **MUST** use naive UTC timestamps for `TIMESTAMP WITHOUT TIME ZONE`
- **PATTERN**: Use `.replace(tzinfo=None)` to convert timezone-aware datetimes

```python
# ✅ CORRECT
updated_at=datetime.now(timezone.utc).replace(tzinfo=None)

# ❌ FORBIDDEN 
updated_at=datetime.now(timezone.utc)  # Causes timezone errors
```

## Enum Field Configuration
- **REQUIRED**: Use `values_callable=lambda obj: [e.value for e in obj]` for PostgreSQL enums

```python
status: Mapped[StatusEnum] = mapped_column(
    SQLAlchemyEnum(
        StatusEnum,
        name="status_enum",
        values_callable=lambda obj: [e.value for e in obj]
    ),
    nullable=False,
)
```

## JSON Field Datetime Serialization
- **MUST** convert datetime objects to ISO strings before storing in JSON fields
- **PATTERN**: Use `.isoformat()` for datetime serialization in update operations

```python
# ✅ CORRECT - Convert datetime to string for JSON storage
timeline_for_db = {k: v.isoformat() for k, v in timeline.items()}
stmt = update(Table).values(timeline=timeline_for_db)

# ❌ FORBIDDEN - Direct datetime storage causes JSON serialization error
stmt = update(Table).values(timeline=timeline)  # TypeError: datetime not JSON serializable
```

## Transactional Outbox Pattern

### EventOutbox Table Requirements
**MUST** include `event_outbox` table for reliable event publishing:

```python
from huleedu_service_libs.outbox import EventOutbox

# Import in models_db.py for Alembic detection
class EventOutbox(Base):
    __tablename__ = "event_outbox"
    
    id: Mapped[UUID] = mapped_column(PostgreSQL_UUID(as_uuid=True), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

### Required Performance Indexes
**MUST** include these indexes for optimal relay worker performance:

```python
# In Alembic migration
def upgrade() -> None:
    # ... table creation ...
    
    # Critical index for relay worker polling
    op.create_index(
        'ix_event_outbox_unpublished', 
        'event_outbox', 
        ['published_at', 'created_at'],
        postgresql_where=sa.text('published_at IS NULL')
    )
    
    # Index for aggregate-based queries
    op.create_index(
        'ix_event_outbox_aggregate', 
        'event_outbox', 
        ['aggregate_type', 'aggregate_id']
    )
```

### Session Sharing Pattern
**MUST** share database session between business logic and outbox:

```python
async def business_operation_with_event(self, data, correlation_id):
    async with self.repository.get_session() as session:
        # Business logic
        result = await self.repository.update_entity(
            entity_id=data.entity_id,
            updates=data.updates,
            session=session,  # Share session
        )
        
        # Store event in same transaction
        await self.outbox_repository.add_event(
            aggregate_id=str(data.entity_id),
            event_data={"result": result.model_dump()},
            session=session,  # Same session for atomicity
        )
        
        await session.commit()  # Atomic commit
```