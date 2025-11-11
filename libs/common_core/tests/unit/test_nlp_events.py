"""Unit tests for NLP events."""

from __future__ import annotations

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.nlp_events import (
    BatchAuthorMatchesSuggestedV1,
    EssayMatchResult,
    StudentMatchSuggestion,
)


class TestStudentMatchSuggestion:
    """Test StudentMatchSuggestion model."""

    def test_valid_student_match_suggestion(self) -> None:
        """Test creating a valid StudentMatchSuggestion."""
        suggestion = StudentMatchSuggestion(
            student_id="student-123",
            student_name="John Doe",
            confidence_score=0.95,
            match_reasons=["exact_name"],
        )

        assert suggestion.student_id == "student-123"
        assert suggestion.student_name == "John Doe"
        assert suggestion.confidence_score == 0.95
        assert suggestion.match_reasons == ["exact_name"]

    def test_confidence_score_validation(self) -> None:
        """Test confidence score must be between 0 and 1."""
        # Valid scores
        StudentMatchSuggestion(
            student_id="123",
            student_name="Test",
            confidence_score=0.0,
            match_reasons=["fuzzy_name"],
        )
        StudentMatchSuggestion(
            student_id="123", student_name="Test", confidence_score=1.0, match_reasons=["email"]
        )

        # Invalid scores
        with pytest.raises(ValueError):
            StudentMatchSuggestion(
                student_id="123",
                student_name="Test",
                confidence_score=1.1,
                match_reasons=["exact_name"],
            )

        with pytest.raises(ValueError):
            StudentMatchSuggestion(
                student_id="123",
                student_name="Test",
                confidence_score=-0.1,
                match_reasons=["exact_name"],
            )


class TestBatchAuthorMatchesSuggestedV1:
    """Test BatchAuthorMatchesSuggestedV1 event model."""

    def test_valid_event_creation(self) -> None:
        """Test creating a valid BatchAuthorMatchesSuggestedV1 event."""
        suggestions = [
            StudentMatchSuggestion(
                student_id="student-123",
                student_name="John Doe",
                confidence_score=0.95,
                match_reasons=["exact_name"],
            ),
            StudentMatchSuggestion(
                student_id="student-456",
                student_name="Jane Doe",
                confidence_score=0.75,
                match_reasons=["fuzzy_name"],
            ),
        ]

        match_results = [
            EssayMatchResult(
                essay_id="essay-789",
                text_storage_id="storage-123",
                filename="essay.txt",
                suggestions=suggestions,
            )
        ]

        event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            entity_id="batch-123",
            entity_type="batch",
            batch_id="batch-123",
            class_id="class-456",
            course_code=CourseCode.ENG5,
            match_results=match_results,
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        assert event.batch_id == "batch-123"
        assert event.class_id == "class-456"
        assert len(event.match_results) == 1
        assert len(event.match_results[0].suggestions) == 2
        assert event.event_name == ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED

    def test_empty_suggestions(self) -> None:
        """Test batch event with no matches found."""
        match_results = [
            EssayMatchResult(
                essay_id="essay-no-match",
                text_storage_id="storage-456",
                filename="essay2.txt",
                suggestions=[],
                no_match_reason="No identifiers found in text",
            )
        ]

        event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            entity_id="batch-no-match",
            entity_type="batch",
            batch_id="batch-no-match",
            class_id="class-789",
            course_code=CourseCode.ENG5,
            match_results=match_results,
            processing_summary={"total_essays": 1, "matched": 0, "no_match": 1, "errors": 0},
        )

        assert event.batch_id == "batch-no-match"
        assert len(event.match_results) == 1
        assert len(event.match_results[0].suggestions) == 0
        assert event.match_results[0].no_match_reason == "No identifiers found in text"

    def test_topic_mapping(self) -> None:
        """Test that BATCH_AUTHOR_MATCHES_SUGGESTED has correct topic mapping."""
        topic = topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED)
        assert topic == "huleedu.batch.author.matches.suggested.v1"
