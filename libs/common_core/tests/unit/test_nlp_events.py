"""Unit tests for NLP events."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.nlp_events import EssayAuthorMatchSuggestedV1, StudentMatchSuggestion
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage


class TestStudentMatchSuggestion:
    """Test StudentMatchSuggestion model."""

    def test_valid_student_match_suggestion(self) -> None:
        """Test creating a valid StudentMatchSuggestion."""
        suggestion = StudentMatchSuggestion(
            student_id="student-123",
            student_name="John Doe",
            confidence_score=0.95,
            match_reason="exact_name"
        )

        assert suggestion.student_id == "student-123"
        assert suggestion.student_name == "John Doe"
        assert suggestion.confidence_score == 0.95
        assert suggestion.match_reason == "exact_name"

    def test_confidence_score_validation(self) -> None:
        """Test confidence score must be between 0 and 1."""
        # Valid scores
        StudentMatchSuggestion(
            student_id="123",
            student_name="Test",
            confidence_score=0.0,
            match_reason="fuzzy_name"
        )
        StudentMatchSuggestion(
            student_id="123",
            student_name="Test",
            confidence_score=1.0,
            match_reason="email"
        )

        # Invalid scores
        with pytest.raises(ValueError):
            StudentMatchSuggestion(
                student_id="123",
                student_name="Test",
                confidence_score=1.1,
                match_reason="exact_name"
            )

        with pytest.raises(ValueError):
            StudentMatchSuggestion(
                student_id="123",
                student_name="Test",
                confidence_score=-0.1,
                match_reason="exact_name"
            )


class TestEssayAuthorMatchSuggestedV1:
    """Test EssayAuthorMatchSuggestedV1 event model."""

    def test_valid_event_creation(self) -> None:
        """Test creating a valid EssayAuthorMatchSuggestedV1 event."""
        suggestions = [
            StudentMatchSuggestion(
                student_id="student-123",
                student_name="John Doe",
                confidence_score=0.95,
                match_reason="exact_name"
            ),
            StudentMatchSuggestion(
                student_id="student-456",
                student_name="Jane Doe",
                confidence_score=0.75,
                match_reason="fuzzy_name"
            )
        ]

        event = EssayAuthorMatchSuggestedV1(
            event_name=ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED,
            entity_ref=EntityReference(entity_type="essay", entity_id="essay-789"),
            timestamp=datetime.now(UTC),
            status=EssayStatus.NLP_SUCCESS,
            system_metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="essay", entity_id="essay-789"),
                event=ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED.value,
                processing_stage=ProcessingStage.COMPLETED
            ),
            essay_id="essay-789",
            suggestions=suggestions,
            match_status="HIGH_CONFIDENCE"
        )

        assert event.essay_id == "essay-789"
        assert len(event.suggestions) == 2
        assert event.match_status == "HIGH_CONFIDENCE"
        assert event.event_name == ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED

    def test_empty_suggestions(self) -> None:
        """Test event with no suggestions (no match found)."""
        event = EssayAuthorMatchSuggestedV1(
            event_name=ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED,
            entity_ref=EntityReference(entity_type="essay", entity_id="essay-no-match"),
            timestamp=datetime.now(UTC),
            status=EssayStatus.NLP_SUCCESS,
            system_metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_type="essay", entity_id="essay-789"),
                event=ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED.value,
                processing_stage=ProcessingStage.COMPLETED
            ),
            essay_id="essay-no-match",
            suggestions=[],
            match_status="NO_MATCH"
        )

        assert event.essay_id == "essay-no-match"
        assert len(event.suggestions) == 0
        assert event.match_status == "NO_MATCH"

    def test_topic_mapping(self) -> None:
        """Test that ESSAY_AUTHOR_MATCH_SUGGESTED has correct topic mapping."""
        topic = topic_name(ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED)
        assert topic == "huleedu.essay.author.match.suggested.v1"
