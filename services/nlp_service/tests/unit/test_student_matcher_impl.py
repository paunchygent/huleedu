"""
Unit tests for DefaultStudentMatcher implementation.

Tests the core business logic orchestrating extraction and matching pipelines
with only boundary mocking. Follows battle-tested patterns - testing actual
implementation behavior, error handling robustness, and correlation ID propagation.

ULTRATHINK Requirements:
- Use REAL business logic: DefaultStudentMatcher
- Mock ONLY boundaries: ExtractionPipeline, RosterMatcher
- Test actual error handling robustness, not just passing tests
- Verify correlation ID propagation through real business flows
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.events.nlp_events import StudentMatchSuggestion

from services.nlp_service.features.student_matching.models import (
    ExtractedIdentifier,
    ExtractionResult,
    MatchStatus,
    StudentInfo,
)
from services.nlp_service.implementations.student_matcher_impl import DefaultStudentMatcher


class TestDefaultStudentMatcher:
    """Test real DefaultStudentMatcher business logic with boundary mocking only."""

    @pytest.fixture
    def mock_extraction_pipeline(self) -> AsyncMock:
        """Mock extraction pipeline boundary."""
        return AsyncMock()

    @pytest.fixture
    def mock_roster_matcher(self) -> AsyncMock:
        """Mock roster matcher boundary."""
        return AsyncMock()

    @pytest.fixture
    def student_matcher(
        self,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
    ) -> DefaultStudentMatcher:
        """Create DefaultStudentMatcher with mocked boundaries."""
        return DefaultStudentMatcher(
            extraction_pipeline=mock_extraction_pipeline,
            roster_matcher=mock_roster_matcher,
        )

    @pytest.fixture
    def sample_roster_dicts(self) -> list[dict]:
        """Sample roster as raw dictionaries (from Class Management Service)."""
        return [
            {
                "student_id": "student-1",
                "first_name": "Anna",
                "last_name": "Andersson",
                "full_legal_name": "Anna Karin Andersson",
                "email": "anna.andersson@student.se",
            },
            {
                "student_id": "student-2",
                "first_name": "Erik",
                "last_name": "Johansson",
                "full_legal_name": "Erik Lars Johansson",
                "email": "erik.johansson@student.se",
            },
            {
                "student_id": "student-3",
                "first_name": "Maria",
                "last_name": "Nilsson",
                "full_legal_name": "Maria Elisabet Nilsson",
                "email": "maria.nilsson@student.se",
            },
        ]

    @pytest.mark.asyncio
    async def test_successful_matching_flow(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test successful end-to-end matching flow with real business logic."""
        # Arrange
        essay_text = """Anna Andersson

        Kurs: Svenska 1
        anna.andersson@student.se

        Detta är min uppsats om klimatförändringar..."""

        correlation_id = uuid4()

        # Mock extraction pipeline result
        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(
                    value="Anna Andersson",
                    source_strategy="examnet",
                    confidence=0.8,
                    location_hint="paragraph_1",
                )
            ],
            possible_emails=[
                ExtractedIdentifier(
                    value="anna.andersson@student.se",
                    source_strategy="examnet",
                    confidence=0.9,
                    location_hint="paragraph_3",
                )
            ],
        )
        mock_extraction_pipeline.extract.return_value = extraction_result

        # Mock roster matcher result
        class MockSuggestion:
            def __init__(self, student_id: str, student_name: str, confidence: float):
                self.student_id = student_id
                self.student_name = student_name
                self.confidence_score = confidence
                self.match_reasons = ["name_exact", "email_exact"]

        mock_suggestions = [MockSuggestion("student-1", "Anna Andersson", 0.95)]
        mock_roster_matcher.match_student.return_value = (
            mock_suggestions,
            MatchStatus.HIGH_CONFIDENCE,
        )

        # Act
        results = await student_matcher.find_matches(
            essay_text, sample_roster_dicts, correlation_id
        )

        # Assert - Verify real business logic orchestration
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, StudentMatchSuggestion)
        assert result.student_id == "student-1"
        assert result.student_name == "Anna Andersson"
        assert result.confidence_score == 0.95
        assert result.match_reasons == ["name_exact", "email_exact"]

        # Verify boundary calls with correct parameters
        mock_extraction_pipeline.extract.assert_called_once_with(
            text=essay_text,
            filename=None,
            metadata={"correlation_id": str(correlation_id)},
        )

        # Verify roster was converted to StudentInfo models
        call_args = mock_roster_matcher.match_student.call_args
        extracted_arg = call_args[1]["extracted"]
        roster_arg = call_args[1]["roster"]

        assert extracted_arg == extraction_result
        assert len(roster_arg) == 3
        assert all(isinstance(student, StudentInfo) for student in roster_arg)
        assert roster_arg[0].student_id == "student-1"
        assert roster_arg[0].first_name == "Anna"

    @pytest.mark.asyncio
    async def test_roster_parsing_error_resilience(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
    ) -> None:
        """Test resilience when roster contains invalid student records."""
        # Arrange - Roster with invalid/malformed data
        malformed_roster: list[dict[str, Any]] = [
            {
                "student_id": "student-1",
                "first_name": "Anna",
                "last_name": "Andersson",
                "full_legal_name": "Anna Karin Andersson",
                "email": "anna.andersson@student.se",
            },
            {
                # Missing required fields
                "student_id": "student-2",
                "first_name": "Erik",
                # Missing last_name, full_legal_name
            },
            {
                # Invalid data types
                "student_id": None,
                "first_name": 12345,
                "last_name": "Invalid",
                "full_legal_name": "Invalid Student",
                "email": "invalid@test.se",
            },
            {
                "student_id": "student-3",
                "first_name": "Maria",
                "last_name": "Nilsson",
                "full_legal_name": "Maria Elisabet Nilsson",
                "email": "maria.nilsson@student.se",
            },
        ]

        correlation_id = uuid4()
        essay_text = "Test essay text"

        # Mock extraction returning some results
        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(value="Test Name", source_strategy="test", confidence=0.7)
            ]
        )
        mock_extraction_pipeline.extract.return_value = extraction_result
        mock_roster_matcher.match_student.return_value = ([], MatchStatus.NO_MATCH)

        # Act - Should handle malformed roster gracefully
        results = await student_matcher.find_matches(essay_text, malformed_roster, correlation_id)

        # Assert - Only valid students should be processed
        call_args = mock_roster_matcher.match_student.call_args
        roster_arg = call_args[1]["roster"]

        # Should only have 2 valid students (student-1 and student-3)
        assert len(roster_arg) == 2
        assert roster_arg[0].student_id == "student-1"
        assert roster_arg[1].student_id == "student-3"

        # Should continue processing despite parsing errors
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_empty_roster_handling(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
    ) -> None:
        """Test behavior with empty or all-invalid roster."""
        # Arrange
        empty_roster: list[dict] = []
        correlation_id = uuid4()
        essay_text = "Test essay text"

        # Act
        results = await student_matcher.find_matches(essay_text, empty_roster, correlation_id)

        # Assert - Should return empty list without calling downstream services
        assert results == []
        mock_extraction_pipeline.extract.assert_not_called()
        mock_roster_matcher.match_student.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_identifiers_extracted(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test behavior when extraction pipeline finds no identifiers."""
        # Arrange
        essay_text = "This essay has no names or emails in it."
        correlation_id = uuid4()

        # Mock extraction returning empty result
        empty_extraction = ExtractionResult()  # No names or emails
        mock_extraction_pipeline.extract.return_value = empty_extraction

        # Act
        results = await student_matcher.find_matches(
            essay_text, sample_roster_dicts, correlation_id
        )

        # Assert - Should return empty list and not call roster matcher
        assert results == []
        mock_extraction_pipeline.extract.assert_called_once()
        mock_roster_matcher.match_student.assert_not_called()

    @pytest.mark.asyncio
    async def test_roster_matcher_returns_no_matches(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test behavior when roster matcher finds no matches."""
        # Arrange
        essay_text = "Unknown Student"
        correlation_id = uuid4()

        # Mock extraction finding identifier
        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(value="Unknown Student", source_strategy="test", confidence=0.6)
            ]
        )
        mock_extraction_pipeline.extract.return_value = extraction_result

        # Mock roster matcher finding no matches
        mock_roster_matcher.match_student.return_value = ([], MatchStatus.NO_MATCH)

        # Act
        results = await student_matcher.find_matches(
            essay_text, sample_roster_dicts, correlation_id
        )

        # Assert - Should return empty list
        assert results == []
        mock_extraction_pipeline.extract.assert_called_once()
        mock_roster_matcher.match_student.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_match_suggestions_conversion(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test conversion of multiple internal matches to API format."""
        # Arrange
        essay_text = "Anna or Erik"
        correlation_id = uuid4()

        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(value="Anna", source_strategy="test", confidence=0.7),
                ExtractedIdentifier(value="Erik", source_strategy="test", confidence=0.6),
            ]
        )
        mock_extraction_pipeline.extract.return_value = extraction_result

        # Mock multiple suggestions from roster matcher
        class MockSuggestion:
            def __init__(
                self, student_id: str, student_name: str, confidence: float, reasons: list[str]
            ):
                self.student_id = student_id
                self.student_name = student_name
                self.confidence_score = confidence
                self.match_reasons = reasons

        mock_suggestions = [
            MockSuggestion("student-1", "Anna Andersson", 0.85, ["name_fuzzy"]),
            MockSuggestion("student-2", "Erik Johansson", 0.75, ["name_partial"]),
        ]
        mock_roster_matcher.match_student.return_value = (
            mock_suggestions,
            MatchStatus.NEEDS_REVIEW,
        )

        # Act
        results = await student_matcher.find_matches(
            essay_text, sample_roster_dicts, correlation_id
        )

        # Assert - All suggestions should be converted to API format
        assert len(results) == 2

        # First suggestion
        assert results[0].student_id == "student-1"
        assert results[0].student_name == "Anna Andersson"
        assert results[0].confidence_score == 0.85
        assert results[0].match_reasons == ["name_fuzzy"]

        # Second suggestion
        assert results[1].student_id == "student-2"
        assert results[1].student_name == "Erik Johansson"
        assert results[1].confidence_score == 0.75
        assert results[1].match_reasons == ["name_partial"]

    @pytest.mark.asyncio
    async def test_suggestion_attributes_handling(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test handling of optional attributes in suggestion conversion."""
        # Arrange
        essay_text = "Test"
        correlation_id = uuid4()

        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(value="Test", source_strategy="test", confidence=0.7)
            ]
        )
        mock_extraction_pipeline.extract.return_value = extraction_result

        # Mock suggestion with minimal attributes (missing optional ones)
        class MinimalSuggestion:
            def __init__(self) -> None:
                self.student_id = "student-1"
                self.student_name = "Test Student"
                self.confidence_score = 0.8
                # Missing match_reasons and student_email

        mock_suggestions = [MinimalSuggestion()]
        mock_roster_matcher.match_student.return_value = (
            mock_suggestions,
            MatchStatus.HIGH_CONFIDENCE,
        )

        # Act
        results = await student_matcher.find_matches(
            essay_text, sample_roster_dicts, correlation_id
        )

        # Assert - Should handle missing attributes gracefully
        assert len(results) == 1
        result = results[0]
        assert result.student_id == "student-1"
        assert result.student_name == "Test Student"
        assert result.confidence_score == 0.8
        assert result.match_reasons == []  # Default for missing attribute
        assert result.student_email is None  # Default for missing attribute
        assert result.extraction_metadata == {}  # Always empty dict

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test that correlation ID is properly propagated through the pipeline."""
        # Arrange
        essay_text = "Test essay"
        correlation_id = uuid4()

        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(value="Test", source_strategy="test", confidence=0.7)
            ]
        )
        mock_extraction_pipeline.extract.return_value = extraction_result
        mock_roster_matcher.match_student.return_value = ([], MatchStatus.NO_MATCH)

        # Act
        await student_matcher.find_matches(essay_text, sample_roster_dicts, correlation_id)

        # Assert - Correlation ID should be passed to extraction pipeline
        extraction_call = mock_extraction_pipeline.extract.call_args
        assert extraction_call[1]["metadata"]["correlation_id"] == str(correlation_id)

    @pytest.mark.asyncio
    async def test_extraction_pipeline_failure_propagation(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test that extraction pipeline failures are properly propagated."""
        # Arrange
        essay_text = "Test essay"
        correlation_id = uuid4()

        # Mock extraction pipeline failure
        mock_extraction_pipeline.extract.side_effect = Exception("Extraction failed")

        # Act & Assert - Exception should propagate (not be swallowed)
        with pytest.raises(Exception, match="Extraction failed"):
            await student_matcher.find_matches(essay_text, sample_roster_dicts, correlation_id)

        # Verify roster matcher was not called
        mock_roster_matcher.match_student.assert_not_called()

    @pytest.mark.asyncio
    async def test_roster_matcher_failure_propagation(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test that roster matcher failures are properly propagated."""
        # Arrange
        essay_text = "Test essay"
        correlation_id = uuid4()

        extraction_result = ExtractionResult(
            possible_names=[
                ExtractedIdentifier(value="Test", source_strategy="test", confidence=0.7)
            ]
        )
        mock_extraction_pipeline.extract.return_value = extraction_result

        # Mock roster matcher failure
        mock_roster_matcher.match_student.side_effect = Exception("Matching failed")

        # Act & Assert - Exception should propagate
        with pytest.raises(Exception, match="Matching failed"):
            await student_matcher.find_matches(essay_text, sample_roster_dicts, correlation_id)

        # Verify extraction was called but matching failed
        mock_extraction_pipeline.extract.assert_called_once()
        mock_roster_matcher.match_student.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_essay_text_handling(
        self,
        student_matcher: DefaultStudentMatcher,
        mock_extraction_pipeline: AsyncMock,
        mock_roster_matcher: AsyncMock,
        sample_roster_dicts: list[dict],
    ) -> None:
        """Test behavior with empty or whitespace-only essay text."""
        # Arrange
        correlation_id = uuid4()

        test_cases = ["", "   ", "\n\t\n", " \t "]

        for empty_text in test_cases:
            # Mock extraction returning empty result for empty text
            empty_extraction = ExtractionResult()
            mock_extraction_pipeline.extract.return_value = empty_extraction

            # Act
            results = await student_matcher.find_matches(
                empty_text, sample_roster_dicts, correlation_id
            )

            # Assert - Should handle gracefully
            assert results == []

            # Verify extraction was called with empty text
            assert mock_extraction_pipeline.extract.call_args[1]["text"] == empty_text
