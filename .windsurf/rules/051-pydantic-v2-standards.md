---
trigger: model_decision
description: "Pydantic v2 standards. Follow when defining data models, schemas, or validation logic to ensure type safety and data consistency."
---

---
description: Pydantic v2 standards. Follow when defining data models, schemas, or validation logic to ensure type safety and data consistency.
globs: 
alwaysApply: false
---
---
trigger: model_decision
description: "Pydantic v2 standards. Follow when defining data models, schemas, or validation logic to ensure type safety and data consistency."
---

# 051: Pydantic v2 Standards

## 1. Model Configuration

### 1.1. ConfigDict
- **MUST** use `ConfigDict` for complex configurations
- **FORBIDDEN**: Dictionary syntax for complex configs in new code

```python
class ApiResponseModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={Enum: lambda v: v.value},
        str_strip_whitespace=True,
        validate_assignment=True
    )
```

### 1.2. Simple Dictionary Config
- **ALLOWED** for backward compatibility only

```python
class EventEnvelope(BaseModel, Generic[T_EventData]):
    model_config = {
        "populate_by_name": True,
        "json_encoders": {Enum: lambda v: v.value},
    }
```

## 2. Serialization

### 2.1. Kafka Message Serialization
- **MUST** send bytes to Kafka, not Python objects
- **USE**: `json.dumps().encode('utf-8')` for manual serialization

```python
await producer.send_and_wait(
    topic,
    json.dumps(envelope.model_dump(mode="json")).encode('utf-8'),
    key=key.encode("utf-8")
)
```

## 3. Field and Validation

### 3.1. Field Definitions
- **USE** `Field()` for validation, defaults, metadata

```python
class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

### 3.2. Field Validation
- **USE** `@field_validator` (not `@validator`)
- **MUST** be class methods

```python
@field_validator('path')
@classmethod
def validate_path(cls, v: Path) -> Path:
    return v if v.is_absolute() else Path.cwd() / v
```

## 4. Settings Management
- **MUST** use `pydantic-settings` for service config
- **REQUIRED** `SettingsConfigDict`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env')
    kafka_servers: str = "kafka:9092"
    log_level: str = "INFO"
```

## 5. Type Safety
- **USE** precise types, avoid `Any`
- **REQUIRED** `from __future__ import annotations`
- **USE** `model_validate()` (not `parse_obj()`, `parse_raw()`)

```python
class EventEnvelope(BaseModel, Generic[T_EventData]):
    data: T_EventData
    correlation_id: UUID | None = None
```

## 6. v2 Compliance
- **FORBIDDEN**: Mixing v1/v2 config
- **REQUIRED**: Full v2 compliance

```python
class GoodModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={Enum: lambda v: v.value}
    )
```

## 7. Testing Standards

### 7.1. Serialization Round-trips
**MUST** test serialization/deserialization for Kafka event models.

```python
def test_event_envelope_serialization():
    envelope = EventEnvelope[MyEventData](
        event_type="test.event.v1",
        source_service="test-service",
        data=MyEventData(...)
    )
    
    serialized = json.dumps(envelope.model_dump(mode="json")).encode('utf-8')
    deserialized = json.loads(serialized.decode('utf-8'))
    reconstructed = EventEnvelope[MyEventData].model_validate(deserialized)
    assert reconstructed.event_id == envelope.event_id
```

### 7.2. Model Rebuilding in Test Environments
**Pattern for conftest.py**:
```python
# Import order: enums first, models second, rebuild third
from common_core.enums import BatchStatus, EssayStatus
from common_core.events.envelope import EventEnvelope

# Explicit rebuilding with error reporting
EventEnvelope.model_rebuild(raise_errors=True)
```

**FORBIDDEN**: `try/except pass` blocks that hide model rebuilding failures.

## 8. Common Pitfalls

### 8.1. Serialization Type Mismatches
```python
# ❌ WRONG: Type mismatch
kafka_value = envelope.model_dump(mode="json")  # dict

# ✅ CORRECT: Proper types
kafka_value = json.dumps(envelope.model_dump(mode="json")).encode('utf-8')  # bytes
```

### 8.2. Missing Imports
```python
# ❌ WRONG: Missing ConfigDict import
from pydantic import BaseModel
model_config = ConfigDict(...)  # NameError

# ✅ CORRECT: Proper import
from pydantic import BaseModel, ConfigDict
```