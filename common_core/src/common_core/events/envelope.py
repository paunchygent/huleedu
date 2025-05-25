from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, Optional, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

T_EventData = TypeVar("T_EventData", bound=BaseModel)


class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str  # e.g., "huleedu.essay.spellcheck_completed.v1"
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_service: str
    correlation_id: Optional[UUID] = None
    data_schema_uri: Optional[str] = None
    data: T_EventData
    model_config = {
        "populate_by_name": True,
        "json_encoders": {Enum: lambda v: v.value},
    }
