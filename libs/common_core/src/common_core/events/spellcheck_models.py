"""Event data models specific to spell checking processes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..metadata_models import StorageReferenceMetadata
from ..status_enums import ProcessingStatus
from .base_event_models import ProcessingUpdate


class SpellcheckRequestedDataV1(ProcessingUpdate):
    """
    Data for requesting a spellcheck.
    'event_name' (from BaseEventData) should be ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value
    'status' (from ProcessingUpdate) should be EssayStatus.AWAITING_SPELLCHECK.value
    'system_metadata' provides context for this request event.
    """

    text_storage_id: str = Field(description="Storage ID of the original text to be spellchecked.")
    # No need to repeat system_metadata, it's inherited.


class SpellcheckResultDataV1(ProcessingUpdate):
    """
    Data representing the result of a spellcheck.
    'event_name' (from BaseEventData) should be
        ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value
    'status' (from ProcessingUpdate) indicates outcome
        (e.g., SPELLCHECKED_SUCCESS or _FAILED).
    'system_metadata' provides context for this result event, including error_info if failed.
    """

    original_text_storage_id: str = Field(
        description="Storage ID of the original text that was spellchecked.",
    )
    storage_metadata: StorageReferenceMetadata | None = Field(
        default=None,
        description="Ref to corrected text, logs.",
    )
    corrections_made: int | None = Field(default=None, description="Number of corrections made.")


# Dual Event Pattern Models


class SpellcheckPhaseCompletedV1(BaseModel):
    """
    Thin event for ELS state management and BCS batch coordination.

    Published to: huleedu.batch.spellcheck.phase.completed.v1
    Consumers: ELS, BCS

    Minimal data needed for state transitions (~300 bytes).
    """

    # Core identifiers
    entity_id: str = Field(description="Essay ID")
    batch_id: str = Field(description="Batch ID")
    correlation_id: str = Field(description="Correlation ID for tracing")

    # State transition data
    status: ProcessingStatus = Field(description="SUCCESS or FAILED")
    corrected_text_storage_id: str | None = Field(
        default=None, description="Storage ID of corrected text if successful"
    )

    # Minimal error info for state decisions
    error_code: str | None = Field(default=None, description="Error code if failed")

    # Basic metrics
    processing_duration_ms: int = Field(description="Processing duration in milliseconds")
    timestamp: datetime = Field(description="Event timestamp")


class SpellcheckMetricsV1(BaseModel):
    """Metrics that spellchecker can ACTUALLY provide."""

    total_corrections: int = Field(description="Total number of corrections made")
    l2_dictionary_corrections: int = Field(
        description="Number of Swedish learner error corrections"
    )
    spellchecker_corrections: int = Field(description="Number of general spelling corrections")
    word_count: int = Field(description="Total word count for density calculation")
    correction_density: float = Field(description="Corrections per 100 words")


class SpellcheckResultV1(ProcessingUpdate):
    """
    Rich event for RAS business data aggregation.

    Published to: huleedu.essay.spellcheck.results.v1
    Consumers: RAS, future NLP services

    Contains full business results from spellcheck processing.
    """

    # Identifiers (inherited entity_id, entity_type, parent_id from ProcessingUpdate)
    correlation_id: str = Field(description="Correlation ID for tracing")
    user_id: str | None = Field(default=None, description="User ID if available")

    # Business results
    corrections_made: int = Field(description="Total number of corrections")

    # Realistic metrics
    correction_metrics: SpellcheckMetricsV1 = Field(description="Detailed correction metrics")

    # Storage references
    original_text_storage_id: str = Field(description="Storage ID of original text")
    corrected_text_storage_id: str | None = Field(
        default=None, description="Storage ID of corrected text if successful"
    )

    # Processing metadata
    processing_duration_ms: int = Field(description="Processing duration in milliseconds")
    processor_version: str = Field(
        default="pyspellchecker_1.0_L2_swedish", description="Version of the spellchecker processor"
    )
