# Common Core - Contract Library

Centralized contracts for HuleEdu event-driven microservices architecture.

## Purpose

Single source of truth for inter-service contracts (Rule `.claude/rules/020-architectural-mandates.md`). All services import from here to prevent contract drift and ensure typed boundaries.

## Library Structure

```
common_core/
├── events/                    # Kafka event contracts
│   ├── envelope.py           # EventEnvelope - wraps all events
│   ├── base_event_models.py  # BaseEventData, ProcessingUpdate
│   ├── cj_assessment_events.py
│   ├── batch_coordination_events.py
│   ├── essay_lifecycle_events.py
│   └── [service]_events.py   # Per-service event contracts
├── api_models/                # HTTP request/response contracts
│   ├── batch_registration.py
│   ├── assessment_instructions.py
│   └── language_tool.py
├── event_enums.py            # ProcessingEvent enum + topic_name()
├── status_enums.py           # ProcessingStage, EssayStatus, BatchStatus
├── error_enums.py            # ErrorCode + service-specific enums
├── domain_enums.py           # ContentType, CourseCode, Language
├── identity_enums.py         # Login, auth enums
├── metadata_models.py        # StorageReferenceMetadata, SystemProcessingMetadata
├── batch_service_models.py   # BOS command contracts
├── pipeline_models.py        # Pipeline configuration
├── identity_models.py        # User, auth models
├── grade_scales.py           # GRADE_SCALES registry
└── [domain]_models.py        # Domain-specific models
```

## Installation

```toml
# In service pyproject.toml
dependencies = [
    "-e file:///${PROJECT_ROOT}/libs/common_core",
]
```

Import with full path from repo root:

```python
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
```

## Documentation Structure

Documentation organized for fast pattern lookup. Each doc <400 lines.

### Event Architecture
- **[Event Envelope](docs/event-envelope.md)** - EventEnvelope structure, Generic[T_EventData], serialization
- **[Event Registry](docs/event-registry.md)** - ProcessingEvent enum, topic_name(), adding events
- **[Dual-Event Pattern](docs/dual-event-pattern.md)** - Thin (state) + Rich (business data) events
- **[Storage References](docs/storage-references.md)** - Large payload handling (>50KB threshold)

### Contracts & Threading
- **[API Contracts](docs/api-contracts.md)** - HTTP boundaries, versioning strategy
- **[Identity Threading](docs/identity-threading.md)** - user_id/org_id propagation for entitlements
- **[Error Patterns](docs/error-patterns.md)** - ErrorCode hierarchy, SystemProcessingMetadata.error_info

### Domain Models
- **[Grade Scales](docs/grade-scales.md)** - GRADE_SCALES registry, anchor patterns
- **[Status State Machines](docs/status-state-machines.md)** - Essay/Batch status transitions
- **[Critical Parameters](docs/critical-parameters.md)** - Non-obvious constants, decision rules

## Critical Patterns

### EventEnvelope - Wrap ALL Kafka Events

```python
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name

# Creating event
envelope = EventEnvelope[MyEventDataV1](
    event_type=topic_name(ProcessingEvent.MY_EVENT),
    source_service="my_service",
    correlation_id=correlation_id,
    data=MyEventDataV1(field1="value1")
)

# Serialization for Kafka
event_bytes = envelope.model_dump_json().encode('utf-8')

# Deserialization (two-phase)
envelope_generic = EventEnvelope[Any].model_validate_json(event_bytes)
typed_data = MyEventDataV1.model_validate(envelope_generic.data)
```

### topic_name() - Convert Enum to Kafka Topic

```python
from common_core.event_enums import ProcessingEvent, topic_name

# Get Kafka topic for event
topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
# Returns: "huleedu.cj_assessment.completed.v1"

# Raises ValueError if event not in _TOPIC_MAPPING
```

### Dual-Event Pattern - State + Business Data

```python
# THIN event to ELS (state tracking only)
thin_event = CJAssessmentCompletedV1(
    entity_ref=batch_id,
    status=ProcessingStage.COMPLETED,
    system_metadata=metadata,
    cj_assessment_job_id=job_id,
    processing_summary={"successful": 50, "failed": 0}
)

# RICH event to RAS (full business data)
rich_event = AssessmentResultV1(
    batch_id=batch_id,
    cj_assessment_job_id=job_id,
    essay_results=[EssayResultV1(...), ...],  # Typed results
    assessment_metadata={...}
)
```

### StorageReference - Large Payloads (>50KB)

```python
from common_core.metadata_models import StorageReferenceMetadata
from common_core.domain_enums import ContentType

# Instead of embedding large data in event:
storage_ref = StorageReferenceMetadata()
storage_ref.add_reference(
    ctype=ContentType.CJ_RESULTS_JSON,
    storage_id=content_service_id,
    path_hint="cj/batch_123/results.json"
)

# In event data
event_data = MyEventV1(
    essay_id="essay_123",
    results_ref=storage_ref  # Reference instead of data
)
```

### Identity Threading - user_id/org_id Propagation

```python
# API Gateway extracts from JWT, adds to request
request = BatchRegistrationRequestV1(
    user_id=jwt_claims["sub"],          # Required
    org_id=jwt_claims.get("org_id"),    # Optional, org-first attribution
    # ... other fields
)

# BOS/ELS propagate through all events
event_data = ELS_CJAssessmentRequestV1(
    user_id=batch.user_id,
    org_id=batch.org_id,
    # ... processing fields
)

# CJ Service uses for credit tracking
# Entitlements Service enforces quotas
```

## Pattern Selection Rules

Use these decision rules for contract design:

| Scenario | Pattern | Location |
|----------|---------|----------|
| Event payload >50KB | StorageReferenceMetadata | metadata_models.py |
| State transition only | Thin event (ProcessingUpdate) | events/base_event_models.py |
| Business data for aggregation | Rich event (BaseEventData) | events/[service]_events.py |
| Cross-service HTTP | API model with .v1 suffix | api_models/ |
| New error domain | Service-specific enum | error_enums.py |
| Processing stage tracking | SystemProcessingMetadata | metadata_models.py |
| Essay reference for processing | EssayProcessingInputRefV1 | metadata_models.py |
| Grade projection context | GradeScaleMetadata from registry | grade_scales.py |

## Canonical Example Service

**CJ Assessment Service** (`services/cj_assessment_service/`) demonstrates all patterns:

- **Event Consumption**: `ELS_CJAssessmentRequestV1` with identity threading
- **Dual-Event Production**: `CJAssessmentCompletedV1` (thin) + `AssessmentResultV1` (rich)
- **Error Handling**: `CJAssessmentErrorCode` + `SystemProcessingMetadata.error_info`
- **Storage References**: Large result JSON stored via Content Service
- **Grade Scales**: Uses `get_scale()` for anchor essay calibration
- **Typed Results**: `EssayResultV1` establishes pattern for all assessment services

Study CJ Assessment Service implementation when implementing new processing services.

## Quick Reference

### Common Imports

```python
# Event infrastructure
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.base_event_models import BaseEventData, ProcessingUpdate

# Metadata
from common_core.metadata_models import (
    SystemProcessingMetadata,
    StorageReferenceMetadata,
    EssayProcessingInputRefV1,
)

# Status & errors
from common_core.status_enums import ProcessingStage, EssayStatus, BatchStatus
from common_core.error_enums import ErrorCode

# Domain
from common_core.domain_enums import ContentType, CourseCode, Language
```

### Adding New Events

1. Add enum value to `ProcessingEvent` in `event_enums.py`
2. Add topic mapping in `_TOPIC_MAPPING` dict
3. Create event data model in `events/[service]_events.py`
4. Extend `BaseEventData` or `ProcessingUpdate`
5. Add to `__all__` exports
6. Document producer/consumer in docstring if relationships clear

### Versioning Strategy

- **Breaking changes**: Create `.v2` version (e.g., `MyEventV1` → `MyEventV2`)
- **Topic names**: Include version suffix (e.g., `huleedu.my.event.v1` → `.v2`)
- **Additive changes**: Add optional fields to existing version (Pydantic default values)
- **Migration**: Both versions coexist during transition, consumers check `event_type`

## Environment Variables

Common core has no runtime dependencies or environment variables. Pure contract definitions.

## Related Documentation

- `.claude/rules/020-architectural-mandates.md` - Contract-only communication
- `.claude/rules/051-pydantic-v2-standards.md` - Pydantic v2 patterns
- `.claude/rules/052-event-contract-standards.md` - Event structure requirements
- `libs/huleedu_service_libs/docs/kafka-redis.md` - Event publishing implementation
- `services/cj_assessment_service/README.md` - Canonical pattern example
