"""
NLP Service event models for HuleEdu microservices.

This module contains events related to NLP processing, including
Phase 1 student matching and Phase 2 text analysis.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from common_core.event_enums import ProcessingEvent
from common_core.events.base_event_models import BaseEventData
from common_core.metadata_models import EntityReference


class StudentMatchSuggestion(BaseModel):
    """Individual student match suggestion."""

    student_id: str = Field(description="Student ID from class roster")
    student_name: str = Field(description="Student full name")
    student_email: str | None = Field(default=None, description="Student email if available")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Match confidence score")
    match_reasons: list[str] = Field(description="Reasons for the match")
    extraction_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata about the extraction process"
    )


class EssayMatchResult(BaseModel):
    """Match result for a single essay."""

    essay_id: str = Field(description="Essay identifier")
    text_storage_id: str = Field(description="Storage ID of essay content")
    filename: str = Field(description="Original filename")
    suggestions: list[StudentMatchSuggestion] = Field(
        default_factory=list, description="Suggested student matches, ordered by confidence"
    )
    no_match_reason: str | None = Field(
        default=None, description="Reason if no matches found or processing failed"
    )
    extraction_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata about extraction strategies used"
    )


class BatchAuthorMatchesSuggestedV1(BaseEventData):
    """
    Batch-level NLP Service suggestions for essay-student matching.

    Sent by NLP Service to Class Management Service after processing
    a batch of essays for student matching. Contains match results
    for all essays in the batch.
    """

    event_name: ProcessingEvent = ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED
    entity_ref: EntityReference  # Batch reference
    batch_id: str = Field(description="Batch identifier")
    class_id: str = Field(description="Class ID for which matching was performed")
    match_results: list[EssayMatchResult] = Field(
        description="Match results for all essays in batch"
    )
    processing_summary: dict[str, int] = Field(
        description="Summary statistics e.g., {'total_essays': 10, 'matched': 8, 'no_match': 1, 'errors': 1}"
    )
    processing_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional processing metadata"
    )
