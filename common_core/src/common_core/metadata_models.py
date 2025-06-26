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
    "PersonNameV1",
    "ParsedNameMetadata",
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


class PersonNameV1(BaseModel):
    """Standardized model for person names.

    Attributes:
        first_name (str): The person's given name.
        last_name (str): The person's family name.
        legal_full_name (str): The full legal name, defaults to a combination of first and last name.
    """

    first_name: str
    last_name: str
    legal_full_name: str | None = None

    def __pydantic_post_init__(self, **kwargs: Any) -> None:
        if self.legal_full_name is None:
            self.legal_full_name = f"{self.first_name} {self.last_name}".strip()

    model_config = {
        "frozen": True,
        "populate_by_name": True,
    }


class ParsedNameMetadata(BaseModel):
    """
    Metadata about a parsed person's name.

    Attributes:
        parsed_name (PersonNameV1): The structured person name (first, last, legal full name).
    """
    parsed_name: PersonNameV1 = Field(..., description="The structured person name.")
