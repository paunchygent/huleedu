from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Generic, Optional, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

T_EventData = TypeVar("T_EventData", bound=BaseModel)


class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str  # e.g., "huleedu.essay.spellcheck_completed.v1"
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_service: str
    schema_version: int = 1
    correlation_id: UUID = Field(default_factory=uuid4)
    data_schema_uri: str | None = None
    data: T_EventData
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional metadata for tracing and other cross-cutting concerns"
    )
    model_config = ConfigDict(
        populate_by_name=True,
        # In Pydantic v2, enums are automatically serialized to their values in JSON mode
        # No need for json_encoders
    )
