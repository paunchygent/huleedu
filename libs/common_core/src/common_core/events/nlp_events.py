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
from common_core.events.base_event_models import BaseEventData, ProcessingUpdate


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


# Phase 2: NLP Analysis Events


class NlpMetrics(BaseModel):
    """Basic spaCy-derived text metrics."""

    word_count: int = Field(description="Total number of words in the text")
    sentence_count: int = Field(description="Total number of sentences")
    avg_sentence_length: float = Field(description="Average sentence length in words")
    language_detected: str = Field(description="ISO 639-1 language code (en, sv, etc.)")
    processing_time_ms: int = Field(default=0, description="Time taken for NLP processing in milliseconds")


class GrammarError(BaseModel):
    """Individual grammar error from Language Tool Service."""

    rule_id: str = Field(description="Language Tool rule identifier")
    message: str = Field(description="Error description")
    short_message: str = Field(description="Brief error description")
    offset: int = Field(description="Character position where error starts")
    length: int = Field(description="Length of the problematic text")
    replacements: list[str] = Field(default_factory=list, description="Suggested corrections")
    category: str = Field(description="Error category (grammar, spelling, style, etc.)")
    severity: str = Field(default="info", description="Error severity (error, warning, info)")


class GrammarAnalysis(BaseModel):
    """Grammar analysis results from Language Tool Service."""

    error_count: int = Field(description="Total number of grammar/spelling errors")
    errors: list[GrammarError] = Field(default_factory=list, description="List of detected errors")
    language: str = Field(description="Language used for analysis")
    processing_time_ms: int = Field(default=0, description="Time taken for grammar check in milliseconds")


class EssayNlpCompletedV1(BaseEventData):
    """
    NLP analysis completion event for a single essay.

    Publisher: NLP Service
    Consumer: Result Aggregator Service
    Topic: huleedu.essay.nlp.completed.v1
    
    Flow (Phase 2 - Text Analysis):
    1. Batch Orchestrator sends BATCH_NLP_INITIATE_COMMAND
    2. NLP Service fetches essay content from Content Service
    3. NLP Service performs spaCy text analysis
    4. NLP Service calls Language Tool Service for grammar checking
    5. NLP Service publishes this event for each essay
    6. Result Aggregator collects and stores NLP results
    
    Note: This is a Phase 2 event - part of the post-readiness text analysis flow.
    """

    event_name: ProcessingEvent = ProcessingEvent.ESSAY_NLP_COMPLETED
    essay_id: str = Field(description="Essay identifier")
    text_storage_id: str = Field(description="Storage ID of essay content")
    nlp_metrics: NlpMetrics = Field(description="Basic text metrics from spaCy analysis")
    grammar_analysis: GrammarAnalysis = Field(description="Grammar analysis from Language Tool Service")
    processing_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the NLP processing"
    )


class BatchNlpAnalysisCompletedV1(ProcessingUpdate):
    """
    Thin completion event for ELS state management (Phase 2).
    
    Publisher: NLP Service
    Consumer: Essay Lifecycle Service (ELS)
    Topic: huleedu.batch.nlp.analysis.completed.v1
    
    This is the thin event for state machine updates, following the CJ Assessment pattern.
    Rich business data goes to RAS via EssayNlpCompletedV1 events.
    
    Flow:
    1. NLP Service processes batch of essays
    2. Publishes EssayNlpCompletedV1 to RAS for each essay (rich data)
    3. Publishes this event to ELS when batch completes (thin, state only)
    4. ELS updates essay state machine to mark phase complete
    """
    
    event_name: ProcessingEvent = ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED
    # entity_id (from BaseEventData) is the batch_id
    # status (from ProcessingUpdate) indicates batch outcome
    # system_metadata (from ProcessingUpdate) populated by NLP Service
    
    batch_id: str = Field(description="Batch identifier")
    processing_summary: dict[str, Any] = Field(
        description="Summary of batch processing results",
        default_factory=lambda: {
            "total_essays": 0,
            "successful": 0,
            "failed": 0,
            "successful_essay_ids": [],  # List of essay IDs that were successfully processed
            "failed_essay_ids": [],      # List of essay IDs that failed processing
            "processing_time_seconds": 0.0,
        },
    )
