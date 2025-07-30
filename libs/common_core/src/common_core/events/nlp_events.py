"""Event data models specific to NLP processing, particularly student matching."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base_event_models import BaseEventData, ProcessingUpdate


class EssayStudentMatchingRequestedV1(BaseEventData):
    """
    Command sent by ELS to NLP Service to match a specific essay to a student.
    
    Part of Phase 1 batch preparation, sent after BOS commands student matching.
    """
    
    essay_id: str = Field(description="Essay to process for student matching")
    text_storage_id: str = Field(description="Content Service storage ID for essay text")
    class_id: str = Field(description="Class ID for roster lookup")
    filename: str = Field(description="Original filename for extraction hints")
    language: str = Field(description="Language for name parsing (from course code)")


class StudentMatchSuggestion(BaseModel):
    """Represents a potential student match from NLP analysis."""

    student_id: str = Field(description="Unique identifier of the matched student")
    student_name: str = Field(description="Full name of the matched student")
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence score of the match (0.0 to 1.0)"
    )
    match_reason: str = Field(
        description="Reason for the match: 'exact_name', 'fuzzy_name', or 'email'"
    )


class EssayAuthorMatchSuggestedV1(ProcessingUpdate):
    """
    Data representing the result of NLP student matching analysis.
    'event_name' (from BaseEventData) should be ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED.value
    'status' (from ProcessingUpdate) should be the essay's processing status.
    'system_metadata' provides context for this result event.
    """

    essay_id: str = Field(description="The essay that was analyzed for author matching")
    suggestions: list[StudentMatchSuggestion] = Field(
        default_factory=list, description="List of potential student matches, ordered by confidence"
    )
    match_status: str = Field(
        description="Overall match status: 'HIGH_CONFIDENCE', 'NEEDS_REVIEW', or 'NO_MATCH'"
    )
