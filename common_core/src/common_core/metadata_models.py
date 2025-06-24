"""common_core.metadata_models – Strongly-typed metadata building blocks"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .domain_enums import ContentType
from .status_enums import ProcessingStage

__all__ = [
    "EntityReference",
    "EssayProcessingInputRefV1",
    "StorageReferenceMetadata",
    "SystemProcessingMetadata",
]


class EntityReference(BaseModel):
    entity_id: str
    entity_type: str
    parent_id: str | None = None
    model_config = {
        "frozen": True,
        "json_schema_extra": {"examples": [{"entity_id": "123", "entity_type": "essay"}]},
    }


class SystemProcessingMetadata(BaseModel):
    entity: EntityReference
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processing_stage: ProcessingStage | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    event: str | None = None  # Actual event name string, e.g., from ProcessingEvent enum
    error_info: dict[str, Any] = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


class StorageReferenceMetadata(BaseModel):
    references: dict[ContentType, dict[str, str]] = Field(default_factory=dict)

    def add_reference(
        self,
        ctype: ContentType,
        storage_id: str,
        path_hint: str | None = None,
    ) -> None:
        self.references[ctype] = {"storage_id": storage_id, "path": path_hint or ""}


class EssayProcessingInputRefV1(BaseModel):
    """Reference to an essay and its text content for processing requests.

    This is the minimal general-purpose contract for essay processing.
    Specialized services should define their own input contracts when they
    need additional metadata (following the pattern of AIFeedbackInputDataV1).
    """

    essay_id: str
    text_storage_id: str
