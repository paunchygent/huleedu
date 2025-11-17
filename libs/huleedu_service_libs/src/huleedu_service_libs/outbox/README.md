# Transactional Outbox Pattern Library

This library provides a generic, reusable implementation of the Transactional Outbox Pattern for reliable event publishing across HuleEdu microservices.

## Overview

The Transactional Outbox Pattern ensures that database updates and event publications are atomic, preventing data inconsistency when Kafka is temporarily unavailable. Events are stored in a database table within the same transaction as business logic, then reliably delivered to Kafka by a background worker.

## Key Components

- **OutboxRepositoryProtocol**: Interface for outbox storage operations
- **EventOutbox**: SQLAlchemy model for the event_outbox table
- **PostgreSQLOutboxRepository**: Default PostgreSQL implementation
- **EventRelayWorker**: Background worker that polls and publishes events
- **OutboxProvider**: Dishka provider for dependency injection
- **OutboxMetrics**: Prometheus metrics for monitoring

## Quick Start

### 1. Add Database Migration

Copy the migration template to your service and customize it:

```bash
cp libs/huleedu_service_libs/src/huleedu_service_libs/outbox/templates/create_outbox_table.py.template \
   services/your_service/alembic/versions/$(date +%Y%m%d_%H%M%S)_add_event_outbox_table.py
```

Edit the file to set proper revision IDs, then run:

```bash
pdm run -p services/your_service migrate-upgrade
```

### 2. Update DI Configuration

Add the OutboxProvider to your service's DI container:

```python
# services/your_service/di.py
from huleedu_service_libs.outbox import OutboxProvider

container = make_async_container(
    CoreInfrastructureProvider(),
    ServiceImplementationsProvider(),
    OutboxProvider(),  # Add this
)
```

### 3. Refactor Event Publishers

Replace direct Kafka calls with outbox writes:

```python
# Before
await self.kafka_bus.publish(topic=topic, envelope=envelope)

# After
await self.outbox_repository.add_event(
    aggregate_id=event.aggregate_id,
    aggregate_type="your_aggregate",
    event_type=envelope.event_type,
    event_data=envelope.model_dump(mode="json"),
    topic=topic,
    event_key=event.key,  # Optional
)
```

### 4. Start the Relay Worker

In your service's startup:

```python
# services/your_service/startup_setup.py
from huleedu_service_libs.outbox import EventRelayWorker

async def initialize_services(app: Quart, settings: Settings) -> None:
    # ... existing setup ...
    
    async with container() as request_container:
        relay_worker = await request_container.get(EventRelayWorker)
        await relay_worker.start()
```

## Configuration

Customize outbox behavior by providing custom settings:

```python
from huleedu_service_libs.outbox import OutboxSettings, OutboxSettingsProvider

custom_settings = OutboxSettings(
    poll_interval_seconds=2.0,  # Poll more frequently
    batch_size=50,             # Smaller batches
    max_retries=10,            # More retries
    error_retry_interval_seconds=60.0,
    enable_metrics=True,
)

container = make_async_container(
    CoreInfrastructureProvider(),
    OutboxSettingsProvider(custom_settings),
    OutboxProvider(),
)
```

## Monitoring

The library provides Prometheus metrics:

- `outbox_queue_depth`: Current number of unpublished events
- `outbox_events_added_total`: Total events added to outbox
- `outbox_events_published_total`: Successfully published events
- `outbox_events_failed_total`: Permanently failed events
- `outbox_relay_errors_total`: Temporary relay errors
- `outbox_event_age_seconds`: Age of events when published
- `outbox_relay_processing_seconds`: Processing time per event

## Best Practices

1. **Atomic Transactions**: Always add events to outbox within the same transaction as your business logic
2. **Idempotency**: Ensure event consumers are idempotent (use @idempotent_consumer)
3. **Event Ordering**: Events are processed in creation order per service instance
4. **Error Handling**: Monitor failed events and investigate max retry failures
5. **Performance**: Keep event payloads reasonably sized for database storage

## Testing

For unit tests, mock the OutboxRepositoryProtocol:

```python
from unittest.mock import AsyncMock

mock_outbox = AsyncMock(spec=OutboxRepositoryProtocol)
mock_outbox.add_event.return_value = uuid4()
```

For integration tests, use the real implementation with TestContainers.
