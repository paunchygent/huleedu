"""Thin wrappers that most concrete event payloads inherit from"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..metadata_models import SystemProcessingMetadata

if TYPE_CHECKING:
    from ..event_enums import ProcessingEvent
    from ..status_enums import BatchStatus, EssayStatus


class BaseEventData(BaseModel):
    event_name: ProcessingEvent  # Specific event name enum, Pydantic will coerce from string
    entity_id: str | None = None
    entity_type: str | None = None
    parent_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # SystemProcessingMetadata is now part of the concrete event data models below


class ProcessingUpdate(BaseEventData):
    status: EssayStatus | BatchStatus  # New status of the entity using proper enum types
    system_metadata: SystemProcessingMetadata  # Context of THIS event's creation


class EventTracker(BaseEventData):
    """For informational / progress events that do not necessarily change primary status."""

    system_metadata: SystemProcessingMetadata  # Context of THIS event's creation


# Note: Model rebuilding is now handled explicitly in test environments (conftest.py)
# and at the package level (__init__.py) after all imports are complete.
# We no longer silently ignore rebuild failures as they indicate real issues.
