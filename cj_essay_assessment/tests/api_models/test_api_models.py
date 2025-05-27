"""Tests for API data models."""

import pytest
from pydantic import ValidationError

from src.cj_essay_assessment.models_api import (ComparisonResult,
                                                ComparisonTask,
                                                EssayForComparison,
                                                LLMAssessmentResponseSchema)


class TestEssayForComparison:
    """Test cases for the EssayForComparison model."""

    def test_valid_data(self) -> None:
        """Test creating an EssayForComparison with valid data."""
        essay = EssayForComparison(
            id=1,
            original_filename="essay1.docx",
            text_content="This is an essay about science.",
            current_bt_score=0.75,
        )

        assert essay.id == 1
        assert essay.original_filename == "essay1.docx"
        assert essay.text_content == "This is an essay about science."
        assert essay.current_bt_score == 0.75

    def test_missing_required_fields(self) -> None:
        """Test that ValidationError is raised for missing required fields."""
        # Explicitly set text_content to None to ensure validation error
        # rather than missing argument error from MyPy
        with pytest.raises(ValidationError):
            # Use model_validate to allow testing validation with missing fields
            EssayForComparison.model_validate(
                {
                    "id": 1,
                    "original_filename": "essay1.docx",
                    # text_content is missing, causing ValidationError
                },
            )

    def test_optional_bt_score(self) -> None:
        """Test that current_bt_score is optional."""
        essay = EssayForComparison(
            id=1,
            original_filename="essay1.docx",
            text_content="This is an essay about science.",
            # No bt_score provided
        )

        assert essay.current_bt_score is None


class TestLLMAssessmentResponseSchema:
    """Test cases for the LLMAssessmentResponseSchema model."""

    def test_valid_data(self) -> None:
        """Test with valid assessment data."""
        assessment = LLMAssessmentResponseSchema(
            winner="Essay A",
            justification="Essay A had better arguments and clarity.",
            confidence=4.5,
        )

        assert assessment.winner == "Essay A"
        assert assessment.justification == "Essay A had better arguments and clarity."
        assert assessment.confidence == 4.5

    def test_error_response(self) -> None:
        """Test creating an error response."""
        assessment = LLMAssessmentResponseSchema(
            winner="Error",
            justification="Could not compare essays due to content issues.",
            confidence=None,
        )

        assert assessment.winner == "Error"
        assert (
            assessment.justification == "Could not compare essays due to content issues."
        )
        assert assessment.confidence is None

    def test_invalid_winner(self) -> None:
        """Test that ValidationError is raised for invalid winner value."""
        with pytest.raises(ValidationError):
            LLMAssessmentResponseSchema(
                winner="Essay C",  # type: ignore
                justification="Essay C was best.",
                confidence=3.0,  # Added a valid confidence for other checks
            )

    def test_confidence_range_validation(self) -> None:
        """Test validation of confidence score range."""
        # Test below minimum
        with pytest.raises(ValidationError):
            LLMAssessmentResponseSchema(
                winner="Essay A",
                justification="Good essay.",
                confidence=0.5,  # Below minimum of 1.0
            )

        # Test above maximum
        with pytest.raises(ValidationError):
            LLMAssessmentResponseSchema(
                winner="Essay B",
                justification="Good essay.",
                confidence=5.5,  # Above maximum of 5.0
            )


class TestComparisonTask:
    """Test cases for the ComparisonTask model."""

    def test_valid_data(self) -> None:
        """Test creating a ComparisonTask with valid data."""
        essay_a = EssayForComparison(
            id=1,
            original_filename="essay1.docx",
            text_content="This is essay A.",
        )

        essay_b = EssayForComparison(
            id=2,
            original_filename="essay2.docx",
            text_content="This is essay B.",
        )

        prompt = "Compare these two essays based on clarity and coherence."

        task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt=prompt)

        assert task.essay_a.id == 1
        assert task.essay_b.id == 2
        assert task.prompt == prompt

    def test_serialization_deserialization(self) -> None:
        """Test serialization and deserialization of ComparisonTask."""
        # Create a task
        essay_a = EssayForComparison(
            id=1,
            original_filename="essay1.docx",
            text_content="This is essay A.",
        )

        essay_b = EssayForComparison(
            id=2,
            original_filename="essay2.docx",
            text_content="This is essay B.",
        )

        original_task = ComparisonTask(
            essay_a=essay_a,
            essay_b=essay_b,
            prompt="Compare these essays.",
        )

        # Serialize to dict
        task_dict = original_task.model_dump()

        # Deserialize
        deserialized_task = ComparisonTask.model_validate(task_dict)

        # Verify equality
        assert deserialized_task.essay_a.id == original_task.essay_a.id
        assert deserialized_task.essay_b.id == original_task.essay_b.id
        assert deserialized_task.prompt == original_task.prompt


class TestComparisonResult:
    """Test cases for the ComparisonResult model."""

    def test_valid_result_with_assessment(self) -> None:
        """Test creating a ComparisonResult with a valid assessment."""
        # Create a task
        essay_a = EssayForComparison(id=1, original_filename="a.docx", text_content="A")
        essay_b = EssayForComparison(id=2, original_filename="b.docx", text_content="B")
        task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt="Compare.")

        # Create an assessment
        assessment = LLMAssessmentResponseSchema(
            winner="Essay A",
            justification="Better essay.",
            confidence=4.0,
        )

        # Create the result
        result = ComparisonResult(
            task=task,
            llm_assessment=assessment,
            raw_llm_response_content=(
                '{"winner": "Essay A", '
                '"justification": "Better essay.", '
                '"confidence": 4.0}'
            ),
            from_cache=False,
            prompt_hash="abcdef123456",
        )

        assert result.task.essay_a.id == 1
        assert result.llm_assessment is not None
        assert result.llm_assessment.winner == "Essay A"
        assert result.from_cache is False
        assert result.prompt_hash == "abcdef123456"

    def test_error_result(self) -> None:
        """Test creating a ComparisonResult with an error."""
        # Create a task
        essay_a = EssayForComparison(id=1, original_filename="a.docx", text_content="A")
        essay_b = EssayForComparison(id=2, original_filename="b.docx", text_content="B")
        task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt="Compare.")

        # Create the result with an error
        result = ComparisonResult(
            task=task,
            llm_assessment=None,
            raw_llm_response_content=None,
            error_message="API request failed with status 429",
            from_cache=False,
            prompt_hash="abcdef123456",
        )

        assert result.llm_assessment is None
        assert result.error_message == "API request failed with status 429"

    def test_cached_result(self) -> None:
        """Test creating a ComparisonResult from cache."""
        # Create a task
        essay_a = EssayForComparison(id=1, original_filename="a.docx", text_content="A")
        essay_b = EssayForComparison(id=2, original_filename="b.docx", text_content="B")
        task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt="Compare.")

        # Create an assessment
        assessment = LLMAssessmentResponseSchema(
            winner="Essay B",
            justification="Better essay.",
            confidence=3.5,
        )

        # Create the result from cache
        result = ComparisonResult(
            task=task,
            llm_assessment=assessment,
            raw_llm_response_content=(
                '{"winner": "Essay B", '
                '"justification": "Better essay.", '
                '"confidence": 3.5}'
            ),
            from_cache=True,
            prompt_hash="abcdef123456",
        )

        assert result.from_cache is True
        assert result.llm_assessment is not None
        assert result.llm_assessment.winner == "Essay B"
