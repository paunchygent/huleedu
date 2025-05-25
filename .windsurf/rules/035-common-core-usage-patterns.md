---
trigger: model_decision
description: "Mandatory patterns for Common Core event handling, Kafka integration, and type-safe data validation using Pydantic v2"
---

# Common Core Usage Patterns

## 1. Service Integration

### 1.1 Core Dependencies
```python
# pyproject.toml
[project.dependencies]
common-core = { path = "../common_core" }  # Local development
# OR
common-core = "^1.0.0"  # Published package
```

### 1.2 Key Components
- **Event Schemas**: Type-safe event definitions
- **Enums**: Shared business enumerations
- **Models**: Reusable Pydantic models
- **Utilities**: Common helpers and validators

## 2. Event Publishing (Producer)

### 2.1 Basic Event Creation
```python
from datetime import datetime
from uuid import uuid4
from common_core.events import EventEnvelope, EventMetadata
from common_core.events.spellcheck_models import SpellcheckRequestedDataV1

# Create typed event data
event_data = SpellcheckRequestedDataV1(
    text="Sample essay content",
    language="en-US",
    metadata={"priority": "high"}
)

# Create envelope with metadata
envelope = EventEnvelope[SpellcheckRequestedDataV1](
    event_id=str(uuid4()),
    event_type="huleedu.essay.spellcheck.requested.v1",
    source_service="batch-service",
    timestamp=datetime.utcnow(),
    correlation_id=str(uuid4()),
    data=event_data,
    metadata=EventMetadata(
        published_at=datetime.utcnow(),
        schema_version="1.0.0"
    )
)
```

### 2.2 Publishing to Kafka
```python
from kafka import KafkaProducer
import orjson

async def publish_event(
    producer: KafkaProducer,
    topic: str,
    envelope: EventEnvelope
) -> None:
    """Publish event to Kafka with error handling.
    
    Args:
        producer: Initialized Kafka producer
        topic: Target Kafka topic
        envelope: Event envelope to publish
        
    Note:
        Uses envelope.model_dump(mode='json') to ensure all values are JSON-serializable
        before final serialization with orjson.
    """
    try:
        # Serialize using model_dump(mode='json') for JSON-serializable dict
        # This ensures all values are JSON-compatible before final serialization
        serialized = orjson.dumps(
            envelope.model_dump(mode='json'),
            option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_SERIALIZE_UUID
        )
        
        # Async produce with error handling
        future = await producer.send(
            topic=topic,
            value=serialized,
            headers=[
                ("event_type", envelope.event_type.encode()),
                ("correlation_id", envelope.correlation_id.encode())
            ]
        )
        await future  # Wait for ack
        
    except Exception as exc:
        logger.error(
            "Failed to publish event",
            event_type=envelope.event_type,
            error=str(exc),
            exc_info=True
        )
        raise
```

## 3. Event Consumption (Consumer)

### 3.1 Basic Consumption
```python
from typing import TypeVar, Type, Any
from pydantic import TypeAdapter
from common_core.events import EventEnvelope

T = TypeVar('T')

def parse_event(
    message: bytes,
    event_type: Type[T]
) -> tuple[EventEnvelope[T], dict[str, Any]]:
    """Parse and validate Kafka message."""
    try:
        # Deserialize message
        raw = orjson.loads(message)
        
        # Validate against schema
        adapter = TypeAdapter(EventEnvelope[event_type])
        envelope = adapter.validate_python(raw)
        
        return envelope, raw.get("metadata", {})
        
    except Exception as exc:
        logger.error(
            "Failed to parse event",
            raw_message=message,
            error=str(exc),
            exc_info=True
        )
        raise
```

### 3.2 Consumer Implementation
```python
from kafka import AIOKafkaConsumer

async def consume_events(bootstrap_servers: list[str], topic: str, group_id: str):
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        value_deserializer=orjson.loads,
        enable_auto_commit=False
    )
    
    try:
        await consumer.start()
        
        async for msg in consumer:
            try:
                envelope, _ = parse_event(msg.value, SpellcheckRequestedDataV1)
                await process_event(envelope.data, envelope.metadata)
                await consumer.commit()
                
            except Exception as exc:
                logger.error("Error processing message", exc_info=exc)
                # Implement retry or dead-letter queue logic
                
    finally:
        await consumer.stop()
```

## 4. Best Practices

### 4.1 Schema Evolution
- Use semantic versioning for event types
- Add new fields as optional with sensible defaults
- Never remove or change required fields in existing schemas
- Document breaking changes in release notes

### 4.2 Error Handling
- Implement dead-letter queues for failed messages
- Add circuit breakers for external service calls
- Log sufficient context for debugging
- Use structured logging with correlation IDs

### 4.3 Performance
- Batch events when possible
- Use connection pooling for Kafka producers/consumers
- Monitor consumer lag and processing time
- Consider compression for large messages

### 4.4 Monitoring
- Track event publication/consumption metrics
- Monitor schema validation errors
- Set up alerts for consumer lag
- Log event processing duration
