---
trigger: model_decision
description: "Pydantic v2 standards. Follow when defining data models, schemas, or validation logic to ensure type safety and data consistency."
---

# 051: Pydantic v2 Standards

## 1. Purpose
Mandatory Pydantic v2 usage patterns for HuleEdu microservices. Ensures type safety, serialization consistency, and architectural compliance.

## 2. Model Configuration

### 2.1. Use ConfigDict
- **MUST** use `ConfigDict` for complex configurations
- **FORBIDDEN**: Dictionary syntax for complex configs in new code
- **REQUIRED** for new models with custom settings

```python
from pydantic import BaseModel, ConfigDict
from enum import Enum

class ApiResponseModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={Enum: lambda v: v.value},
        str_strip_whitespace=True,
        validate_assignment=True
    )
    id: str
    status: MyStatusEnum
```

### 2.2. Simple Dictionary Config
- **ALLOWED** for backward compatibility only
- **RESTRICTED** to simple cases

```python
class EventEnvelope(BaseModel, Generic[T_EventData]):
    model_config = {
        "populate_by_name": True,
        "json_encoders": {Enum: lambda v: v.value},
    }
```

## 3. Serialization

### 3.1. Kafka Message Serialization
- **MUST** send bytes to Kafka, not Python objects
- **USE**: `json.dumps().encode('utf-8')` for manual serialization
- **PREFER**: `KafkaBus` from `huleedu_service_libs`

```python
# ✅ Correct
import json
await producer.send_and_wait(
    topic,
    json.dumps(envelope.model_dump(mode="json")).encode('utf-8'),
    key=key.encode("utf-8")
)
```

## 4. Field and Validation

### 4.1. Field Definitions
- **USE** `Field()` for validation, defaults, metadata
- **REQUIRED** for complex field definitions

```python
class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

### 4.2. Field Validation
- **USE** `@field_validator` (not `@validator`)
- **MUST** be class methods

```python
class Config(BaseModel):
    path: Path

    @field_validator('path')
    @classmethod
    def validate_path(cls, v: Path) -> Path:
        return v if v.is_absolute() else Path.cwd() / v
```

## 5. Settings Management

### 5.1. pydantic-settings
- **MUST** use for service config
- **REQUIRED** `SettingsConfigDict`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env')
    kafka_servers: str = "kafka:9092"
    log_level: str = "INFO"
```

## 6. Type Safety

### 6.1. Type Annotations
- **USE** precise types, avoid `Any`
- **REQUIRED** `from __future__ import annotations`

```python
class EventEnvelope(BaseModel, Generic[T_EventData]):
    data: T_EventData
    correlation_id: UUID | None = None
```

### 6.2. Model Validation
- **USE** `model_validate()`
- **DEPRECATED**: `parse_obj()`, `parse_raw()`

## 7. Migration

### 7.1. v2 Syntax
- **FORBIDDEN**: Mixing v1/v2 config
- **REQUIRED**: Full v2 compliance

```python
# ✅ v2 only
class GoodModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={Enum: lambda v: v.value}
    )
```

## 8. Testing Standards

### 8.1. Rule: Test Serialization Round-trips
    - **MUST** test serialization/deserialization for Kafka event models.
    - **Your Directive**: Include serialization tests for new event models.

```python
import json
from common_core.events.envelope import EventEnvelope

def test_event_envelope_serialization():
    """Test EventEnvelope Kafka serialization."""
    envelope = EventEnvelope[MyEventData](
        event_type="test.event.v1",
        source_service="test-service",
        data=MyEventData(...)
    )

    # Test serialization to bytes (Kafka format)
    serialized = json.dumps(envelope.model_dump(mode="json")).encode('utf-8')
    assert isinstance(serialized, bytes)

    # Test round-trip
    deserialized = json.loads(serialized.decode('utf-8'))
    reconstructed = EventEnvelope[MyEventData].model_validate(deserialized)
    assert reconstructed.event_id == envelope.event_id
```

## 9. Common Pitfalls to Avoid

### 9.1. Serialization Type Mismatches
```python
# ❌ WRONG: Type mismatch
kafka_value = envelope.model_dump(mode="json")  # dict
await producer.send_and_wait(topic, kafka_value)  # Expects bytes

# ✅ CORRECT: Proper types
kafka_value = json.dumps(envelope.model_dump(mode="json")).encode('utf-8')  # bytes
```

### 9.2. Missing Imports
```python
# ❌ WRONG: Missing ConfigDict import
from pydantic import BaseModel
model_config = ConfigDict(...)  # NameError

# ✅ CORRECT: Proper import
from pydantic import BaseModel, ConfigDict
```

## 10. Architecture Compliance

These standards ensure compliance with:
- **020-architectural-mandates.mdc**: Explicit contracts via Pydantic models
- **030-event-driven-architecture-eda-standards.mdc**: Proper EventEnvelope usage
- **050-python-coding-standards.mdc**: Type safety and precise annotations

---
**Strict Pydantic v2 compliance ensures type safety and reliable inter-service communication.**
===
