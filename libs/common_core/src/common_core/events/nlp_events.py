"""
NLP Service event models for HuleEdu microservices.

This module contains events related to NLP processing, including
Phase 1 student matching and Phase 2 text analysis.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.base_event_models import BaseEventData


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
    Batch-level student match suggestions from NLP Service.

    Publisher: NLP Service
    Consumer: Class Management Service
    Topic: batch.author.matches.suggested
    Handler: Class Management - MatchSuggestionHandler.handle_batch_match_suggestions()

    Flow (REGULAR batches only):
    1. NLP receives BatchStudentMatchingRequestedV1 from ELS
    2. NLP extracts student names from all essays in parallel
    3. NLP matches extracted names against class roster
    4. NLP publishes this event with all match suggestions
    5. Class Management stores suggestions for human validation
    6. Class Management notifies teacher via WebSocket
    7. After validation/timeout, Class Management publishes StudentAssociationsConfirmedV1

    Note: This is a Phase 1 event - part of the pre-readiness student matching flow.
    """

    event_name: ProcessingEvent = ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED
    batch_id: str = Field(description="Batch identifier")
    class_id: str = Field(description="Class ID for which matching was performed")
    course_code: CourseCode = Field(description="Course code for the batch")
    match_results: list[EssayMatchResult] = Field(
        description="Match results for all essays in batch"
    )
    processing_summary: dict[str, int] = Field(
        description="Summary statistics e.g., "
        "{'total_essays': 10, 'matched': 8, 'no_match': 1, 'errors': 1}"
    )
    processing_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional processing metadata"
    )
