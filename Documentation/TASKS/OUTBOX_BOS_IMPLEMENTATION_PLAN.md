# Batch Orchestrator Service: Outbox Pattern Implementation Plan

## Executive Summary
This document provides a step-by-step implementation plan for adding the Transactional Outbox Pattern to Batch Orchestrator Service (BOS), following the established patterns from File Service and Essay Lifecycle Service.

## Current Architecture Analysis

### Event Publishing Flow
1. **Phase Initiators** (Spellcheck, NLP, CJ Assessment, AI Feedback) → 
2. **BatchEventPublisherProtocol** → 
3. **DefaultBatchEventPublisherImpl** → 
4. **KafkaPublisherProtocol**

### Key Files to Modify
- `implementations/event_publisher_impl.py` - Main publisher implementation
- `config.py` - Add outbox configuration
- `di.py` - Update dependency injection
- `worker_main.py` - Start EventRelayWorker
- New migration file in `alembic/versions/`

## Implementation Steps

### Step 1: Create Database Migration
**File**: `services/batch_orchestrator_service/alembic/versions/20250726_0001_add_event_outbox_table.py`

```python
"""Add event outbox table for Transactional Outbox Pattern

Revision ID: 20250726_0001
Revises: [latest_revision]
Create Date: 2025-07-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250726_0001"
down_revision: Union[str, None] = "[latest_revision]"  # TODO: Update with actual latest
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the event_outbox table and indexes."""
    # Create event_outbox table
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
            comment="Unique identifier for the outbox entry",
        ),
        sa.Column(
            "aggregate_id",
            sa.String(255),
            nullable=False,
            comment="ID of the aggregate this event relates to",
        ),
        sa.Column(
            "aggregate_type",
            sa.String(100),
            nullable=False,
            comment="Type of aggregate (e.g., 'batch', 'pipeline')",
        ),
        sa.Column(
            "event_type",
            sa.String(255),
            nullable=False,
            comment="Type of the event (e.g., 'huleedu.batch.spellcheck.initiate.command.v1')",
        ),
        sa.Column(
            "event_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            comment="JSON payload containing the full event envelope including topic",
        ),
        sa.Column(
            "event_key",
            sa.String(255),
            nullable=True,
            comment="Optional key for Kafka partitioning",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Timestamp when the event was created",
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the event was successfully published",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Number of publication attempts",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last error message if publication failed",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Event outbox table for reliable event publishing to Kafka",
    )

    # Create indexes for efficient querying
    
    # Index for polling unpublished events (partial index)
    op.create_index(
        "ix_event_outbox_unpublished",
        "event_outbox",
        ["published_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    
    # Index for looking up events by aggregate
    op.create_index(
        "ix_event_outbox_aggregate",
        "event_outbox",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )
    
    # Index for monitoring/debugging by event type
    op.create_index(
        "ix_event_outbox_event_type",
        "event_outbox",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the event_outbox table and indexes."""
    # Drop indexes first
    op.drop_index("ix_event_outbox_event_type", table_name="event_outbox")
    op.drop_index("ix_event_outbox_aggregate", table_name="event_outbox")
    op.drop_index("ix_event_outbox_unpublished", table_name="event_outbox")
    
    # Drop table
    op.drop_table("event_outbox")
```

### Step 2: Update Configuration
**File**: `services/batch_orchestrator_service/config.py`

Add the following settings:
```python
# Outbox Pattern Settings
OUTBOX_POLL_INTERVAL_SECONDS: float = 5.0
OUTBOX_BATCH_SIZE: int = 100
OUTBOX_MAX_RETRIES: int = 5
OUTBOX_ERROR_RETRY_INTERVAL_SECONDS: float = 30.0
```

### Step 3: Modify Event Publisher Implementation
**File**: `services/batch_orchestrator_service/implementations/event_publisher_impl.py`

```python
"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import raise_kafka_publish_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol

logger = create_service_logger("bos.event_publisher")


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol with outbox pattern."""

    def __init__(
        self, 
        kafka_bus: KafkaPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        settings: Settings,
    ) -> None:
        """Initialize with Kafka bus and outbox repository dependencies."""
        self.kafka_bus = kafka_bus
        self.outbox_repository = outbox_repository
        self.settings = settings

    async def publish_batch_event(
        self, event_envelope: EventEnvelope[Any], key: str | None = None
    ) -> None:
        """Publish batch event via transactional outbox pattern."""
        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if event_envelope.metadata is None:
                event_envelope.metadata = {}
            inject_trace_context(event_envelope.metadata)

        # Determine aggregate information from event
        aggregate_id = key or str(event_envelope.correlation_id)
        aggregate_type = self._determine_aggregate_type(event_envelope.event_type)
        
        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_envelope.event_type,
                event_data=event_envelope,
                topic=event_envelope.event_type,  # BOS uses event_type as topic
                event_key=key,
            )
            
            logger.info(
                f"Event stored in outbox for reliable delivery",
                extra={
                    "event_type": event_envelope.event_type,
                    "aggregate_id": aggregate_id,
                    "correlation_id": str(event_envelope.correlation_id),
                },
            )
            
        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="batch_orchestrator_service",
                    operation="publish_batch_event",
                    message=f"Failed to store event in outbox: {e.__class__.__name__}",
                    correlation_id=event_envelope.correlation_id,
                    topic=event_envelope.event_type,
                    event_type=event_envelope.event_type,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def _publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: EventEnvelope[Any],
        topic: str,
        event_key: str | None = None,
    ) -> None:
        """
        Store event in outbox for reliable delivery.

        This implements the Transactional Outbox Pattern, decoupling business
        operations from Kafka availability.
        """
        # Serialize the envelope to JSON for storage
        serialized_data = event_data.model_dump(mode="json")
        
        # Store topic in the data for relay worker
        serialized_data["topic"] = topic
        
        # Store in outbox
        outbox_id = await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=serialized_data,
            topic=topic,
            event_key=event_key,
        )
        
        logger.debug(
            f"Event stored in outbox",
            extra={
                "outbox_id": str(outbox_id),
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "aggregate_type": aggregate_type,
            },
        )

    def _determine_aggregate_type(self, event_type: str) -> str:
        """Determine aggregate type from event type."""
        if "batch" in event_type.lower():
            return "batch"
        elif "pipeline" in event_type.lower():
            return "pipeline"
        else:
            return "unknown"
```

### Step 4: Update DI Configuration
**File**: `services/batch_orchestrator_service/di.py`

Add the following imports:
```python
from huleedu_service_libs.outbox import OutboxProvider, OutboxRepositoryProtocol
from huleedu_service_libs.outbox.relay import OutboxSettings
```

Add OutboxSettings provider:
```python
@provide(scope=Scope.APP)
def provide_outbox_settings(self, settings: Settings) -> OutboxSettings:
    """Provide custom outbox settings from service configuration."""
    return OutboxSettings(
        poll_interval_seconds=settings.OUTBOX_POLL_INTERVAL_SECONDS,
        batch_size=settings.OUTBOX_BATCH_SIZE,
        max_retries=settings.OUTBOX_MAX_RETRIES,
        error_retry_interval_seconds=settings.OUTBOX_ERROR_RETRY_INTERVAL_SECONDS,
        enable_metrics=True,
    )
```

Update event publisher provider:
```python
@provide(scope=Scope.APP)
def provide_batch_event_publisher(
    self,
    kafka_bus: KafkaPublisherProtocol,
    outbox_repository: OutboxRepositoryProtocol,
    settings: Settings,
) -> BatchEventPublisherProtocol:
    """Provide the batch event publisher with outbox support."""
    return DefaultBatchEventPublisherImpl(kafka_bus, outbox_repository, settings)
```

Update container creation to include OutboxProvider:
```python
container = make_async_container(
    CoreInfrastructureProvider(),
    ServiceClientsProvider(),
    ServiceImplementationsProvider(),
    PipelinePhaseProvider(),
    EventHandlerProvider(),
    OutboxProvider(),  # Add this
)
```

### Step 5: Start EventRelayWorker in Worker
**File**: `services/batch_orchestrator_service/worker_main.py`

Add import:
```python
from huleedu_service_libs.outbox import EventRelayWorker
```

In the `start_worker` function, after getting dependencies:
```python
# Get EventRelayWorker from container
event_relay_worker = await request_container.get(EventRelayWorker)

# Start the relay worker
await event_relay_worker.start()
logger.info("EventRelayWorker started for outbox pattern")
```

In the shutdown handler, add:
```python
# Stop relay worker
if event_relay_worker:
    await event_relay_worker.stop()
    logger.info("EventRelayWorker stopped")
```

### Step 6: Create Integration Tests
Create test files following the File Service pattern:
- `tests/integration/test_outbox_pattern_integration.py`
- `tests/unit/test_event_publisher_outbox.py`

## Testing Plan

### 1. Unit Tests
- Test event publisher with mocked outbox repository
- Verify correct data serialization
- Test error handling

### 2. Integration Tests
- Test full outbox flow with real database
- Test relay worker functionality
- Test failure and recovery scenarios

### 3. End-to-End Tests
- Verify events flow through outbox to Kafka
- Test with Kafka unavailable
- Test service restart scenarios

## Rollback Plan
1. Deploy with feature flag to disable outbox if needed
2. Keep direct Kafka publishing as fallback
3. Migration can be safely rolled back

## Monitoring & Alerts
- Monitor outbox queue depth
- Alert on events stuck in outbox > 30 minutes
- Monitor relay worker health
- Track publish success/failure rates

## Timeline
1. Day 1: Create migration and update configuration
2. Day 2: Modify event publisher and DI
3. Day 3: Update worker and create tests
4. Day 4: Integration testing
5. Day 5: Deploy to staging and monitor

## Success Metrics
- Zero event loss during Kafka outages
- < 5ms latency added per event
- 99.99% eventual delivery rate
- Successful recovery from all failure scenarios