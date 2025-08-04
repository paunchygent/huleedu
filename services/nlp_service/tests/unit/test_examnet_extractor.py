"""
Unit tests for ExamnetExtractor - test extraction behavior from exam.net format essays.

Tests the core business logic of extracting student names and emails from the standardized
exam.net 4-paragraph header format. Follows behavioral testing patterns - testing actual
extraction results, confidence scores, and edge cases, not log messages.
"""

from __future__ import annotations

import pytest

from services.nlp_service.features.student_matching.extraction.examnet_extractor import (
    ExamnetExtractor,
)
from services.nlp_service.features.student_matching.models import ExtractionResult


class TestExamnetExtractor:
    """Test ExamnetExtractor business logic with various input scenarios."""

    @pytest.fixture
    def extractor(self) -> ExamnetExtractor:
        """Create ExamnetExtractor instance for testing."""
        return ExamnetExtractor()

    @pytest.mark.asyncio
    async def test_standard_examnet_format_extraction(self, extractor: ExamnetExtractor) -> None:
        """Test extraction from standard exam.net 4-paragraph format."""
        # Arrange - Standard exam.net format
        text = """Anna Andersson

Kurs: Svenska 1
Lärare: Eva Eriksson
anna.andersson@student.example.se

Antal ord: 247

Detta är början på essän där studenten skriver sitt svar..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Name extraction
        assert len(result.possible_names) == 1
        name_result = result.possible_names[0]
        assert name_result.value == "Anna Andersson"
        assert name_result.source_strategy == "examnet"
        assert name_result.confidence == 0.8
        assert name_result.location_hint == "line_1"

        # Assert - Email extraction
        assert len(result.possible_emails) == 1
        email_result = result.possible_emails[0]
        assert email_result.value == "anna.andersson@student.example.se"
        assert email_result.source_strategy == "examnet"
        assert email_result.confidence == 0.9
        assert email_result.location_hint == "paragraph_2"

        # Assert - Metadata
        assert result.metadata["format_detected"] == "examnet"
        assert result.metadata["paragraph_count"] == 4

    @pytest.mark.asyncio
    async def test_name_with_trailing_numbers_cleanup(self, extractor: ExamnetExtractor) -> None:
        """Test that trailing numbers are cleaned from student names."""
        # Arrange - Name with trailing numbers (common in exam.net)
        text = """Erik Johansson 123

Kurs: Matematik
Lärare: Lars Larsson
erik.j@school.se

Detta är essän..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Numbers should be cleaned from name
        assert len(result.possible_names) == 1
        assert result.possible_names[0].value == "Erik Johansson"
        assert "123" not in result.possible_names[0].value

    @pytest.mark.asyncio
    async def test_multiple_emails_in_header(self, extractor: ExamnetExtractor) -> None:
        """Test extraction when multiple emails appear in header paragraphs."""
        # Arrange - Multiple emails in different paragraphs
        text = """Maria Svensson

Kurs: Engelska, student.email@domain.com
Lärare: John Smith, john.smith@teacher.com
maria.svensson@student.se

Essay content starts here..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Should find all emails from paragraphs 2-4
        assert len(result.possible_emails) >= 2
        email_values = [email.value for email in result.possible_emails]
        assert "student.email@domain.com" in email_values
        assert "maria.svensson@student.se" in email_values
        # Teacher email should also be found (may or may not be relevant, but extracted)

    @pytest.mark.asyncio
    async def test_name_detection_rejects_sentences(self, extractor: ExamnetExtractor) -> None:
        """Test that sentence-like text in first paragraph is not extracted as name."""
        # Arrange - Sentence instead of name in first paragraph
        text = """This is my essay about climate change and its effects.

Student: Per Persson
Course: Environmental Science
per.persson@eco.se

The climate crisis is a major challenge..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Should not extract the sentence as a name
        assert len(result.possible_names) == 0
        # Should still find email
        assert len(result.possible_emails) == 1
        assert result.possible_emails[0].value == "per.persson@eco.se"

    @pytest.mark.asyncio
    async def test_name_detection_rejects_titles_and_assignments(
        self, extractor: ExamnetExtractor
    ) -> None:
        """Test that titles and assignment text are not extracted as names."""
        # Arrange - Title/assignment text in first paragraph
        test_cases = [
            "Essay Assignment: Climate Change",
            "Uppsats om miljöfrågor",
            "Question 1: Discuss the impact",
            "Task: Write about Swedish culture",
            "Answer to question 3",
        ]

        for title_text in test_cases:
            text = f"""{title_text}

Course: Biology
Teacher: Anna Svensson
student@test.se

Essay content..."""

            # Act
            result = await extractor.extract(text)

            # Assert - Should not extract title as name
            assert len(result.possible_names) == 0, f"Should not extract '{title_text}' as name"

    @pytest.mark.asyncio
    async def test_valid_name_variations(self, extractor: ExamnetExtractor) -> None:
        """Test that various valid name formats are correctly extracted."""
        # Arrange - Various valid name formats
        valid_names = [
            "Erik Andersson",
            "Anna-Lisa Svensson",
            "Lars Johan Persson",
            "Maria Elena Rodriguez Lopez",
            "Nils von Sydow",
            "Emma de la Torre",
        ]

        for name in valid_names:
            text = f"""{name}

Course info
Teacher info
email@test.se

Essay content..."""

            # Act
            result = await extractor.extract(text, metadata={"test_name": name})

            # Assert - Should extract the name
            assert len(result.possible_names) == 1, f"Should extract name: {name}"
            assert result.possible_names[0].value == name
            assert result.possible_names[0].confidence == 0.8

    @pytest.mark.asyncio
    async def test_empty_input_handling(self, extractor: ExamnetExtractor) -> None:
        """Test handling of empty or minimal input."""
        # Test empty text
        result_empty = await extractor.extract("")
        assert result_empty.is_empty()
        # Empty input returns early without setting metadata
        assert "format_detected" not in result_empty.metadata

        # Test whitespace only
        result_whitespace = await extractor.extract("   \n\n   ")
        assert result_whitespace.is_empty()

        # Test single paragraph
        result_single = await extractor.extract("Just one paragraph with no structure")
        # May or may not extract depending on content, but should not crash
        assert isinstance(result_single, ExtractionResult)

    @pytest.mark.asyncio
    async def test_email_case_normalization(self, extractor: ExamnetExtractor) -> None:
        """Test that extracted emails are normalized to lowercase."""
        # Arrange - Email with mixed case
        text = """Johan Eriksson

Course: Swedish
Teacher: Test Teacher
Johan.ERIKSSON@STUDENT.University.SE

Essay content..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Email should be normalized to lowercase
        assert len(result.possible_emails) == 1
        assert result.possible_emails[0].value == "johan.eriksson@student.university.se"

    @pytest.mark.asyncio
    async def test_malformed_paragraph_structure(self, extractor: ExamnetExtractor) -> None:
        """Test handling of malformed paragraph structures."""
        # Arrange - Non-standard paragraph breaks
        text = """Lisa Nilsson
Course: Math\nTeacher: Test\nlisa@test.se\n\nEssay starts here..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Should still attempt extraction
        assert isinstance(result, ExtractionResult)
        # Should find name if first "paragraph" looks like a name
        if result.possible_names:
            assert result.possible_names[0].value == "Lisa Nilsson"

    @pytest.mark.asyncio
    async def test_confidence_scores_and_location_hints(self, extractor: ExamnetExtractor) -> None:
        """Test that confidence scores and location hints are correctly assigned."""
        # Arrange
        text = """Sofia Lindberg

Course: History
Teacher: Anna Teacher
sofia.lindberg@test.se

Essay content..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Name confidence and location
        name_result = result.possible_names[0]
        assert name_result.confidence == 0.8
        assert name_result.location_hint == "line_1"

        # Assert - Email confidence and location
        email_result = result.possible_emails[0]
        assert email_result.confidence == 0.9
        assert email_result.location_hint == "paragraph_2"

    @pytest.mark.asyncio
    async def test_no_email_in_header(self, extractor: ExamnetExtractor) -> None:
        """Test extraction when no email is present in header."""
        # Arrange - No email in header paragraphs
        text = """Magnus Blomqvist

Course: Physics
Teacher: Erik Teacher
Word count: 156

This is the essay content without any email addresses..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Should find name but no email
        assert len(result.possible_names) == 1
        assert result.possible_names[0].value == "Magnus Blomqvist"
        assert len(result.possible_emails) == 0

    @pytest.mark.asyncio
    async def test_extremely_long_first_paragraph_rejected(
        self, extractor: ExamnetExtractor
    ) -> None:
        """Test that very long first paragraphs (likely sentences) are rejected as names."""
        # Arrange - Very long first paragraph
        long_text = "This is a very long sentence that goes on and on and contains many words and phrases that make it clearly not a student name but rather the beginning of an essay or some other content"

        text = f"""{long_text}

Course: Literature
teacher@school.se

Essay continues..."""

        # Act
        result = await extractor.extract(text)

        # Assert - Should not extract long text as name
        assert len(result.possible_names) == 0
        # Should still find email
        assert len(result.possible_emails) == 1

    @pytest.mark.asyncio
    async def test_metadata_population(self, extractor: ExamnetExtractor) -> None:
        """Test that extraction metadata is properly populated."""
        # Arrange
        text = """Test Student

Para 2
Para 3
Para 4
Para 5

Essay content..."""

        # Act
        result = await extractor.extract(text, filename="test.txt", metadata={"source": "test"})

        # Assert - Metadata should be populated
        assert result.metadata["format_detected"] == "examnet"
        assert result.metadata["paragraph_count"] == 3
        # Original metadata should be preserved (though not used by examnet extractor)

    @pytest.mark.asyncio
    async def test_edge_case_name_patterns(self, extractor: ExamnetExtractor) -> None:
        """Test edge cases in name pattern detection."""
        # Test cases that should NOT be recognized as names
        non_names = [
            "Essay: Climate Change",  # Contains colon
            "Question 1?",  # Contains question mark
            "Assignment (Part A)",  # Contains parentheses
            "Answer.",  # Contains period
            "Name,Address,Phone",  # Contains commas
            "A B C D E F G",  # Too many space-separated parts
            "SingleWord",  # No space (no first+last name)
            "123 456",  # Only numbers
        ]

        for non_name in non_names:
            text = f"""{non_name}

Course info
test@email.com

Content..."""

            result = await extractor.extract(text)
            assert len(result.possible_names) == 0, f"Should not extract '{non_name}' as name"

        # Test cases that SHOULD be recognized as names
        valid_names = [
            "Anna Svensson",
            "Lars Erik Johansson",
            "Maria de la Cruz",
            "Nils von Euler",
        ]

        for valid_name in valid_names:
            text = f"""{valid_name}

Course info
test@email.com

Content..."""

            result = await extractor.extract(text)
            assert len(result.possible_names) == 1, f"Should extract '{valid_name}' as name"
            assert result.possible_names[0].value == valid_name

    @pytest.mark.asyncio
    async def test_lowercase_name_extraction(self, extractor: ExamnetExtractor) -> None:
        """Test that lowercase names are recognized and extracted (case-insensitive recognition)."""
        # Test cases that were previously failing
        test_cases = [
            ("tindra cruz", "tindra cruz"),  # Preserve original case
            ("simon pub", "simon pub"),  # Preserve original case
            ("anna andersson", "anna andersson"),
            ("ERIK JOHANSSON", "ERIK JOHANSSON"),  # Also test all caps
            ("Mixed Case Name", "Mixed Case Name"),  # Mixed case should still work
        ]

        for input_name, expected_output in test_cases:
            # Arrange - Essay with lowercase name in first line
            text = f"""{input_name} 2025-03-06
Prov: Book Report ES24B
Antal ord: 499

Essay content starts here and continues..."""

            # Act
            result = await extractor.extract(text)

            # Assert - Should extract name with original case preserved
            assert len(result.possible_names) == 1, f"Should extract lowercase name: '{input_name}'"
            assert result.possible_names[0].value == expected_output
            assert result.possible_names[0].source_strategy == "examnet"
            assert result.possible_names[0].confidence == 0.85  # Date pattern confidence
            assert result.possible_names[0].location_hint == "line_1"
