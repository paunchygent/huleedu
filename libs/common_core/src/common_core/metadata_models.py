"""common_core.metadata_models – Strongly-typed metadata building blocks"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, model_validator

from .domain_enums import ContentType
from .status_enums import ProcessingStage

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .events.spellcheck_models import SpellcheckMetricsV1
else:  # pragma: no cover - runtime placeholder to avoid circular imports
    SpellcheckMetricsV1 = Any  # type: ignore[assignment]

__all__ = [
    "EssayProcessingInputRefV1",
    "StorageReferenceMetadata",
    "SystemProcessingMetadata",
    "PersonNameV1",
    "ParsedNameMetadata",
]


# EntityReference removed - use primitive parameters directly


class SystemProcessingMetadata(BaseModel):
    entity_id: str
    entity_type: str
    parent_id: str | None = None
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
    spellcheck_metrics: "SpellcheckMetricsV1 | None" = Field(
        default=None,
        description="Optional spellcheck metrics computed during previous phase",
    )


class PersonNameV1(BaseModel):
    """Standardized model for person names.

    Attributes:
        first_name (str): The person's given name.
        last_name (str): The person's family name.
        legal_full_name (str): The full legal name, defaults to a
            combination of first and last name.
    """

    first_name: str
    last_name: str
    legal_full_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def set_legal_full_name(cls, values: dict[str, Any]) -> dict[str, Any]:
        if isinstance(values, dict):
            if values.get("legal_full_name") is None:
                first_name = values.get("first_name", "")
                last_name = values.get("last_name", "")
                values["legal_full_name"] = f"{first_name} {last_name}".strip()
        return values

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
