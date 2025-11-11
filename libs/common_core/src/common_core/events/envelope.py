"""EventEnvelope - Mandatory wrapper for all Kafka events in HuleEdu architecture."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Generic, Optional, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

T_EventData = TypeVar("T_EventData", bound=BaseModel)


class EventEnvelope(BaseModel, Generic[T_EventData]):
    """Envelope wrapper for all Kafka event messages.

    ALL Kafka events MUST use EventEnvelope. Provides standardized metadata
    (correlation, timestamps, source) and generic data wrapping.

    Pydantic v2 Limitation: data field typed as Any to prevent malformed
    BaseModel instances during JSON deserialization (issues #6895, #7815).
    Use two-phase deserialization: EventEnvelope[Any].model_validate_json()
    then MyEventV1.model_validate(envelope.data).

    See: libs/common_core/docs/event-envelope.md
    """

    event_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this event instance. For idempotency, generate deterministically from business data using uuid5().",
    )
    event_type: str = Field(
        description="Kafka topic name from topic_name(ProcessingEvent). Format: 'huleedu.service.event.v1'. Use topic_name() not hardcoded strings.",
    )
    event_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event creation timestamp in UTC. Auto-generated.",
    )
    source_service: str = Field(
        description="Service that published this event. Match SERVICE_NAME from service settings.",
    )
    schema_version: int = Field(
        default=1,
        description="Envelope structure version. Always 1 in current architecture. Reserved for future envelope evolution (not event data versioning).",
    )
    correlation_id: UUID = Field(
        default_factory=uuid4,
        description="Distributed tracing ID. MUST propagate through entire request chain. Extract from received envelope, include in published events.",
    )
    data_schema_uri: str | None = Field(
        default=None,
        description="Optional JSON Schema URI for event data model. Currently unused, reserved for future schema registry integration.",
    )
    data: Any = Field(
        description="Event-specific data payload. Type T_EventData when creating envelope, dict when deserializing. CRITICAL: Any type prevents Pydantic v2 malformed BaseModel bug. Two-phase deserialization required: envelope=EventEnvelope[Any].model_validate_json(bytes), typed_data=MyEventV1.model_validate(envelope.data).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional cross-cutting metadata (retry_count, original_timestamp, batch_context). Not for business data.",
    )
    model_config = ConfigDict(
        populate_by_name=True,
        # Pydantic v2 auto-serializes enums to values in JSON mode
    )
