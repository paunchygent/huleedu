# Task: Migrate Remaining Services to Explicit Topic Column Pattern

## Priority: CRITICAL 🔴
**These services are currently incompatible with the shared library and will fail at runtime**

## Background

The shared library has been updated to use an explicit `topic` column in the outbox pattern for better performance and cleaner architecture. Support for the old embedded topic pattern (storing topic in JSON) has been completely removed. Services using the old pattern will fail when the relay worker attempts to access `event.topic`.

## Services Requiring Migration

### 1. class_management_service ❌
- **Current State**: Embeds topic in JSON at `implementations/outbox_manager.py:95`
- **Model**: Missing explicit topic column in `models_db.py`
- **Database**: Needs migration to add topic column

### 2. essay_lifecycle_service ❌
- **Current State**: Embeds topic in JSON in OutboxManager
- **Model**: Missing explicit topic column in `models_db.py`
- **Database**: Needs migration to add topic column

### 3. nlp_service ❌
- **Current State**: Embeds topic in JSON in OutboxManager
- **Model**: Missing explicit topic column in `models_db.py`
- **Database**: Needs migration to add topic column

## Migration Steps for Each Service

### Step 1: Create Database Migration

Create a new Alembic migration following the pattern from BOS (`20250808_0400_b602bb2e74f4`):

```bash
cd services/{service_name}
pdm run alembic revision -m "Add explicit topic column to event outbox"
```

Migration template:
```python
"""Add explicit topic column to event outbox.

Revision ID: {auto-generated}
Revises: {previous-revision}
Create Date: {timestamp}

Migration to add explicit topic column to event_outbox table for better
performance and consistency with shared library expectations.
"""

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    """Add explicit topic column and migrate data from JSON."""
    
    # Step 1: Add nullable topic column
    op.add_column(
        "event_outbox",
        sa.Column(
            "topic",
            sa.String(255),
            nullable=True,
            comment="Kafka topic to publish to",
        ),
    )
    
    # Step 2: Extract topic from existing JSON event_data
    op.execute("""
        UPDATE event_outbox 
        SET topic = event_data->>'topic'
        WHERE event_data->>'topic' IS NOT NULL
    """)
    
    # Step 3: Set default for any remaining nulls
    op.execute("""
        UPDATE event_outbox 
        SET topic = 'huleedu.{service}.unknown.v1'
        WHERE topic IS NULL
    """)
    
    # Step 4: Make column NOT NULL
    op.alter_column(
        "event_outbox",
        "topic",
        nullable=False,
    )
    
    # Step 5: Add index for topic queries
    op.create_index(
        "ix_event_outbox_topic",
        "event_outbox",
        ["topic"],
        unique=False,
    )
    
    # Step 6: Update composite index for relay worker
    op.drop_index("ix_event_outbox_unpublished", table_name="event_outbox")
    op.create_index(
        "ix_event_outbox_unpublished_topic",
        "event_outbox",
        ["published_at", "topic", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )

def downgrade() -> None:
    """Remove explicit topic column and restore original indexes."""
    
    # Restore original index
    op.drop_index("ix_event_outbox_unpublished_topic", table_name="event_outbox")
    op.create_index(
        "ix_event_outbox_unpublished",
        "event_outbox",
        ["published_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    
    # Drop topic index and column
    op.drop_index("ix_event_outbox_topic", table_name="event_outbox")
    op.drop_column("event_outbox", "topic")
```

### Step 2: Update EventOutbox Model

In `services/{service_name}/models_db.py`, update the EventOutbox class:

**Find:**
```python
class EventOutbox(Base):
    # ... existing fields ...
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON payload containing the full event envelope including topic",
    )
    event_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional key for Kafka partitioning",
    )
    
    # Publishing state
    created_at: Mapped[datetime] = mapped_column(
```

**Replace with:**
```python
class EventOutbox(Base):
    # ... existing fields ...
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON payload containing the event envelope data",
    )
    event_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional key for Kafka partitioning",
    )
    
    # Kafka targeting
    topic: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Kafka topic to publish to",
    )
    
    # Publishing state
    created_at: Mapped[datetime] = mapped_column(
```

**Also update the table indexes:**
```python
    __table_args__ = (
        # Index for polling unpublished events efficiently with topic filtering
        Index(
            "ix_event_outbox_unpublished_topic",
            "published_at",
            "topic",
            "created_at",
            postgresql_where="published_at IS NULL",
        ),
        # Index for filtering by topic
        Index(
            "ix_event_outbox_topic",
            "topic",
        ),
        # ... other existing indexes ...
    )
```

### Step 3: Update OutboxManager Implementation

In `services/{service_name}/implementations/outbox_manager.py`:

**Find the line that embeds topic in JSON:**
```python
# Serialize the envelope to JSON for storage
serialized_data = event_data.model_dump(mode="json")

# Add topic to the event data for relay worker
serialized_data["topic"] = topic  # ← REMOVE THIS LINE

# Determine Kafka key from envelope metadata or aggregate ID
```

**Remove the topic embedding line**, leaving:
```python
# Serialize the envelope to JSON for storage
serialized_data = event_data.model_dump(mode="json")

# Determine Kafka key from envelope metadata or aggregate ID
```

The repository call should already pass topic as a parameter:
```python
outbox_id = await self.outbox_repository.add_event(
    aggregate_id=aggregate_id,
    aggregate_type=aggregate_type,
    event_type=event_type,
    event_data=serialized_data,  # No longer contains topic
    topic=topic,  # Passed as explicit parameter
    event_key=event_key,
)
```

### Step 4: Update Tests

Update any test files with `FakeOutboxEvent` classes to include the topic property:

1. Add `topic: str` parameter to `__init__`
2. Store as `self._topic = topic`
3. Add property getter:
```python
@property
def topic(self) -> str:
    return self._topic
```

4. Update all test instantiations to include topic parameter
5. Remove `"topic": "..."` from event_data dictionaries in tests

### Step 5: Apply Migration and Test

For each service:

```bash
# Apply the migration
cd services/{service_name}
pdm run alembic upgrade head

# Run type checking
cd ../..
pdm run typecheck-all

# Run integration tests
pdm run pytest services/{service_name}/tests/integration/test_outbox*.py -xvs

# Run all tests for the service
pdm run pytest services/{service_name}/tests/ -x
```

## Verification Checklist

For each service, verify:

- [ ] Database migration created and applied
- [ ] EventOutbox model has explicit `topic` field
- [ ] OutboxManager does NOT embed topic in JSON
- [ ] Table indexes updated for topic column
- [ ] All tests updated and passing
- [ ] Type checking passes
- [ ] Integration tests confirm events are published correctly

## Services Already Migrated (Reference)

These services already use the correct pattern and can be used as references:

- ✅ **batch_orchestrator_service** - Just migrated, good reference for migration
- ✅ **file_service** - Clean implementation
- ✅ **result_aggregator_service** - Clean implementation  
- ✅ **cj_assessment_service** - Clean implementation

## Expected Outcome

After migration, all services will:
1. Store topic in an explicit, indexed database column
2. Have better query performance for topic-based filtering
3. Be compatible with the updated shared library
4. Maintain clean separation between event data and Kafka metadata

## Time Estimate

Per service: ~30-45 minutes
- Database migration: 10 minutes
- Code updates: 10 minutes
- Test updates: 10 minutes
- Testing and verification: 10 minutes

Total for all 3 services: ~2 hours

## Risk Assessment

**HIGH RISK**: Services are currently broken with the updated shared library. The relay worker will fail with AttributeError when trying to access `event.topic`. This migration is mandatory and urgent.