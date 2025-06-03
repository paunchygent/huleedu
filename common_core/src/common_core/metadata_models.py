"""common_core.metadata_models – Strongly-typed metadata building blocks"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field

from .enums import (  # Assuming enums.py is in the same directory
    ContentType,
    ProcessingStage,
)

__all__ = [
    "EntityReference",
    "SystemProcessingMetadata",
    "StorageReferenceMetadata",
    "UserActivityMetadata",
    "CancellationMetadata",
    "EssayProcessingInputRefV1",
]


class EntityReference(BaseModel):
    entity_id: str
    entity_type: str
    parent_id: Optional[str] = None
    model_config = {
        "frozen": True,
        "json_schema_extra": {"examples": [{"entity_id": "123", "entity_type": "essay"}]},
    }


class SystemProcessingMetadata(BaseModel):
    entity: EntityReference
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_stage: Optional[ProcessingStage] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    event: Optional[str] = None  # Actual event name string, e.g., from ProcessingEvent enum
    error_info: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


class StorageReferenceMetadata(BaseModel):
    references: Dict[ContentType, Dict[str, str]] = Field(default_factory=dict)

    def add_reference(
        self, ctype: ContentType, storage_id: str, path_hint: Optional[str] = None
    ) -> None:
        self.references[ctype] = {"storage_id": storage_id, "path": path_hint or ""}


class UserActivityMetadata(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    event_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: Optional[str] = None
    previous_status: Optional[str] = None
    activity_details: Optional[Dict[str, Any]] = None


class CancellationMetadata(BaseModel):
    cancelled_by: Optional[str] = None
    reason: Optional[str] = None
    cancellation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EssayProcessingInputRefV1(BaseModel):
    """Reference to an essay and its text content for processing requests.

    This is the minimal general-purpose contract for essay processing.
    Specialized services should define their own input contracts when they 
    need additional metadata (following the pattern of AIFeedbackInputDataV1).
    """

    essay_id: str
    text_storage_id: str
