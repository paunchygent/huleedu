"""Strongly-typed metadata building blocks for events and processing.

SystemProcessingMetadata: Processing state and error tracking.
StorageReferenceMetadata: Large payload references (>50KB threshold).
EssayProcessingInputRefV1: Standard essay reference for processing services.
PersonNameV1: Structured name model for identity and class management.

See: libs/common_core/docs/storage-references.md
"""

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
    """Processing state metadata for thin events (ProcessingUpdate).

    Tracks processing lifecycle: timestamps, stage, errors. Used in thin events
    for state management (ELS, BOS). Contains NO business data.

    error_info structure:
        {
            "error_code": str,      # From ErrorCode or service-specific enum
            "error_message": str,   # Human-readable description
            "error_type": str,      # Exception class name
            "context": dict         # Optional additional context
        }

    See: libs/common_core/docs/error-patterns.md
    """

    entity_id: str = Field(description="ID of entity being processed (batch_id, essay_id, etc.)")
    entity_type: str = Field(description="Entity type (batch, essay, job, etc.)")
    parent_id: str | None = Field(default=None, description="Parent entity ID if hierarchical")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Metadata creation timestamp UTC"
    )
    processing_stage: ProcessingStage | None = Field(
        default=None, description="Current processing stage (PENDING, PROCESSING, COMPLETED, FAILED, etc.)"
    )
    started_at: datetime | None = Field(default=None, description="Processing start timestamp UTC")
    completed_at: datetime | None = Field(default=None, description="Processing completion timestamp UTC")
    event: str | None = Field(
        default=None, description="Event name string from ProcessingEvent enum value"
    )
    error_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Error details on failure: error_code, error_message, error_type, context. See docs/error-patterns.md",
    )
    model_config = {"populate_by_name": True}


class StorageReferenceMetadata(BaseModel):
    """References to Content Service for large payloads (>50KB).

    Pattern for handling event data >50KB. Store data in Content Service,
    include storage_id reference in event instead of inline data.

    Multiple ContentType references can exist in single instance. Each reference
    contains storage_id (required) and path_hint (optional debugging aid).

    Usage:
        storage_ref = StorageReferenceMetadata()
        storage_ref.add_reference(ContentType.CJ_RESULTS_JSON, storage_id, "cj/batch_123/results.json")
        event_data.results_ref = storage_ref

    Retrieval:
        ref = event.results_ref.references[ContentType.CJ_RESULTS_JSON]
        data = await content_service.fetch(ref["storage_id"], correlation_id)

    See: libs/common_core/docs/storage-references.md
    """

    references: dict[ContentType, dict[str, str]] = Field(
        default_factory=dict,
        description='ContentType to {"storage_id": str, "path": str} mapping. storage_id required, path optional.',
    )

    def add_reference(
        self,
        ctype: ContentType,
        storage_id: str,
        path_hint: str | None = None,
    ) -> None:
        """Add storage reference for ContentType.

        Args:
            ctype: ContentType enum value (CJ_RESULTS_JSON, STUDENT_PROMPT_TEXT, etc.)
            storage_id: Content Service storage ID (required)
            path_hint: Optional path for debugging (e.g., "cj/batch_123/results.json")
        """
        self.references[ctype] = {"storage_id": storage_id, "path": path_hint or ""}


class EssayProcessingInputRefV1(BaseModel):
    """Standard essay reference for processing service requests.

    Minimal general-purpose contract used across ALL processing services (CJ, NLP, Spellcheck, AI Feedback).
    Contains essay_id and text_storage_id (Content Service reference).

    Specialized services define extended contracts when additional metadata needed
    (e.g., AIFeedbackInputDataV1 adds student_id, class_context).

    Producer: Essay Lifecycle Service (ELS)
    Consumers: All processing services
    """

    essay_id: str = Field(description="Unique essay identifier")
    text_storage_id: str = Field(description="Content Service storage_id for essay text")
    spellcheck_metrics: "SpellcheckMetricsV1 | None" = Field(
        default=None,
        description="Spellcheck metrics from Phase 2 (error_count, correction_count). Available for downstream services after spellcheck completes.",
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
