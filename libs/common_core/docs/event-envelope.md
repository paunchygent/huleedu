# Event Envelope

EventEnvelope is the mandatory wrapper for ALL Kafka events in HuleEdu architecture.

## Structure

```python
from common_core.events.envelope import EventEnvelope

class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str  # Kafka topic from topic_name()
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_service: str
    schema_version: int = 1
    correlation_id: UUID = Field(default_factory=uuid4)
    data_schema_uri: str | None = None
    data: Any  # T_EventData when typed, dict when deserialized
    metadata: Optional[Dict[str, Any]] = Field(default=None)
```

## Critical Field: data - Pydantic v2 Workaround

**Problem**: Pydantic v2 creates malformed BaseModel instances during JSON deserialization when generic type information is unavailable (GitHub issues #6895, #7815).

**Solution**: Field typed as `Any` instead of `T_EventData`. Type safety maintained through two-phase deserialization:

```python
# Phase 1: Deserialize envelope with generic data
envelope = EventEnvelope[Any].model_validate_json(kafka_bytes)
# envelope.data is dict

# Phase 2: Validate data against specific model
typed_data = MyEventDataV1.model_validate(envelope.data)
# Now typed and validated
```

When creating typed envelopes: `EventEnvelope[SpecificType]` provides type safety at creation time.

## Creating Events

### Basic Pattern

```python
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name
from uuid import UUID

envelope = EventEnvelope[MyEventDataV1](
    event_type=topic_name(ProcessingEvent.MY_EVENT),
    source_service="my_service_name",
    correlation_id=existing_correlation_id,  # Propagate from request
    data=MyEventDataV1(
        field1="value",
        field2=123
    )
)
```

### With Metadata

```python
envelope = EventEnvelope[MyEventDataV1](
    event_type=topic_name(ProcessingEvent.MY_EVENT),
    source_service="my_service",
    correlation_id=correlation_id,
    metadata={
        "retry_count": 2,
        "original_timestamp": original_ts.isoformat(),
        "batch_context": {"batch_id": "batch_123"}
    },
    data=my_data
)
```

## Serialization for Kafka

Kafka requires bytes. Use `model_dump_json().encode('utf-8')`:

```python
# Correct
event_bytes: bytes = envelope.model_dump_json().encode('utf-8')
await kafka_bus.publish(topic=topic, value=event_bytes)

# WRONG - Kafka rejects Python objects
await kafka_bus.publish(topic=topic, value=envelope)  # ❌
```

## Deserialization Patterns

### Two-Phase Deserialization (Standard)

```python
from typing import Any

# Phase 1: Deserialize envelope
envelope_generic = EventEnvelope[Any].model_validate_json(kafka_message_bytes)

# Phase 2: Validate specific event data model
if envelope_generic.event_type == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
    data = CJAssessmentCompletedV1.model_validate(envelope_generic.data)
    # Process typed data
elif envelope_generic.event_type == topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED):
    data = EssaySpellcheckCompletedV1.model_validate(envelope_generic.data)
    # Process typed data
```

### With Error Handling

```python
from pydantic import ValidationError
from common_core.error_enums import ErrorCode

try:
    envelope = EventEnvelope[Any].model_validate_json(message_bytes)

    # Route to specific handler
    if envelope.event_type == expected_topic:
        event_data = MyEventDataV1.model_validate(envelope.data)
        await process_event(event_data, envelope.correlation_id)
    else:
        logger.warning(
            "Unexpected event type",
            event_type=envelope.event_type,
            expected=expected_topic,
            correlation_id=str(envelope.correlation_id)
        )

except ValidationError as e:
    logger.error(
        "Event deserialization failed",
        error=str(e),
        raw_message=message_bytes[:200]  # Truncate for logging
    )
    # Handle poison message
```

## Correlation ID Propagation

correlation_id must flow through entire request chain for distributed tracing:

```python
# 1. API Gateway: Generate or extract from headers
correlation_id = UUID(request.headers.get("X-Correlation-ID", str(uuid4())))

# 2. Service A: Use in envelope when publishing event
envelope_to_b = EventEnvelope[RequestToB](
    correlation_id=correlation_id,  # Propagate
    # ...
)

# 3. Service B: Extract from received envelope, use for downstream
received_envelope = EventEnvelope[Any].model_validate_json(kafka_bytes)
correlation_id = received_envelope.correlation_id

envelope_to_c = EventEnvelope[RequestToC](
    correlation_id=correlation_id,  # Continue propagation
    # ...
)
```

All log statements should include correlation_id for trace aggregation.

## Event ID Generation

`event_id` auto-generated via `uuid4()` by default. For idempotency, generate deterministically from business data:

```python
from uuid import uuid5, NAMESPACE_DNS

# Deterministic event_id from business data
idempotency_key = f"{batch_id}:{essay_id}:{phase}"
event_id = uuid5(NAMESPACE_DNS, idempotency_key)

envelope = EventEnvelope[MyEventV1](
    event_id=event_id,  # Override default
    # ...
)
```

Services check Redis for event_id before processing to ensure idempotency.

## Schema Version Field

`schema_version` always `1` in current architecture. Reserved for future envelope structure evolution:

```python
# Current: All events use schema_version=1
envelope = EventEnvelope[...](
    schema_version=1,  # Default
    # ...
)

# Future: If envelope structure changes
# schema_version=2 would indicate new envelope fields/structure
# Consumers check schema_version to handle old vs new envelopes
```

Do not confuse with event data versioning (e.g., `MyEventV1` vs `MyEventV2`). schema_version is for envelope structure only.

## data_schema_uri Field

Optional JSON Schema URI for event data model. Currently unused:

```python
envelope = EventEnvelope[MyEventV1](
    data_schema_uri="https://schemas.huleedu.com/events/my_event/v1.json",  # Optional
    # ...
)
```

Reserved for future schema registry integration. Not required for current event processing.

## Canonical Examples

### CJ Assessment Service - Event Consumption

File: `services/cj_assessment_service/kafka_handlers.py`

```python
async def handle_cj_request(self, message: bytes) -> None:
    envelope = EventEnvelope[Any].model_validate_json(message)
    request_data = ELS_CJAssessmentRequestV1.model_validate(envelope.data)

    # Use correlation_id for all logging/tracing
    correlation_id = envelope.correlation_id

    # Process request...
```

### CJ Assessment Service - Event Production

File: `services/cj_assessment_service/event_publisher.py`

```python
# Thin event to ELS
completion_envelope = EventEnvelope[CJAssessmentCompletedV1](
    event_type=topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
    source_service="cj_assessment_service",
    correlation_id=request_envelope.correlation_id,  # Propagate
    data=CJAssessmentCompletedV1(
        entity_ref=batch_id,
        status=ProcessingStage.COMPLETED,
        # ...
    )
)

# Rich event to RAS
result_envelope = EventEnvelope[AssessmentResultV1](
    event_type=topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
    source_service="cj_assessment_service",
    correlation_id=request_envelope.correlation_id,  # Same correlation_id
    data=AssessmentResultV1(
        batch_id=batch_id,
        essay_results=[...],
        # ...
    )
)

# Publish both
await kafka_bus.publish(topic1, completion_envelope.model_dump_json().encode('utf-8'))
await kafka_bus.publish(topic2, result_envelope.model_dump_json().encode('utf-8'))
```

## Common Errors

### Error: Publishing Python Object Instead of Bytes

```python
# WRONG
await kafka_bus.publish(topic, envelope)  # ❌ Kafka expects bytes

# CORRECT
await kafka_bus.publish(topic, envelope.model_dump_json().encode('utf-8'))  # ✓
```

### Error: Accessing envelope.data Without Type Validation

```python
# WRONG - envelope.data is dict after deserialization
envelope = EventEnvelope[Any].model_validate_json(bytes)
value = envelope.data.field_name  # ❌ AttributeError

# CORRECT - Validate against specific model first
envelope = EventEnvelope[Any].model_validate_json(bytes)
typed_data = MyEventV1.model_validate(envelope.data)
value = typed_data.field_name  # ✓ Type-safe access
```

### Error: Creating Envelope Without topic_name()

```python
# WRONG - Hardcoded topic strings
envelope = EventEnvelope[MyEventV1](
    event_type="huleedu.my.event.v1",  # ❌ Hardcoded, typo-prone
    # ...
)

# CORRECT - Use topic_name() for consistency
from common_core.event_enums import ProcessingEvent, topic_name

envelope = EventEnvelope[MyEventV1](
    event_type=topic_name(ProcessingEvent.MY_EVENT),  # ✓ Type-safe
    # ...
)
```

## Related Documentation

- [Event Registry](event-registry.md) - ProcessingEvent enum and topic_name()
- [Dual-Event Pattern](dual-event-pattern.md) - Thin vs rich events
- `.claude/rules/052-event-contract-standards.md` - Event structure requirements
- `libs/huleedu_service_libs/docs/kafka-redis.md` - KafkaBus.publish() implementation
