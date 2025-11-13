"""Tests for response validation utilities."""

import json
from typing import Any, Dict
from uuid import uuid4

import pytest

from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.response_validator import (
    StandardizedLLMResponse,
    validate_and_normalize_response,
)


class TestStandardizedLLMResponse:
    """Test the StandardizedLLMResponse Pydantic model."""

    def test_valid_response_creation(self) -> None:
        """Test creating a valid standardized response."""
        response = StandardizedLLMResponse(
            winner="Essay A",
            justification="This essay demonstrates superior clarity.",
            confidence=4.2,
        )

        assert response.winner == "Essay A"
        assert len(response.justification) <= 50
        assert 1.0 <= response.confidence <= 5.0

    def test_justification_too_short_passes(self) -> None:
        """Test that short justifications are accepted."""
        response = StandardizedLLMResponse(
            winner="Essay B",
            justification="Short text",  # Less than 50 chars but still valid
            confidence=3.0,
        )
        assert response.justification == "Short text"

    def test_justification_too_long_fails(self) -> None:
        """Test that long justifications fail strict validation."""
        long_text = "A" * 501  # More than 500 chars
        with pytest.raises(ValueError):
            StandardizedLLMResponse(winner="Essay A", justification=long_text, confidence=2.5)

    def test_confidence_out_of_range_fails(self) -> None:
        """Test that confidence values outside range fail strict validation."""
        # Test lower bound
        with pytest.raises(ValueError):
            StandardizedLLMResponse(
                winner="Essay A",
                justification="This essay has better structure.",
                confidence=0.5,  # Below minimum
            )

        # Test upper bound
        with pytest.raises(ValueError):
            StandardizedLLMResponse(
                winner="Essay B",
                justification="This essay demonstrates exceptional writing.",
                confidence=6.0,  # Above maximum
            )

    def test_invalid_winner_format(self) -> None:
        """Test that invalid winner formats are rejected."""
        with pytest.raises(ValueError):
            StandardizedLLMResponse(
                winner="A",  # Should be "Essay A"
                justification="This essay is better for various reasons.",
                confidence=3.0,
            )


class TestValidateAndNormalizeResponse:
    """Test the validate_and_normalize_response function."""

    def test_valid_json_string(self) -> None:
        """Test validation with valid JSON string."""
        json_response = json.dumps(
            {
                "winner": "Essay A",
                "justification": "This essay demonstrates superior clarity.",
                "confidence": 4.2,
            }
        )

        correlation_id = uuid4()
        validated = validate_and_normalize_response(json_response, correlation_id=correlation_id)

        assert validated is not None
        assert validated.winner == "Essay A"
        assert validated.confidence == 4.2

    def test_valid_dict_input(self) -> None:
        """Test validation with valid dictionary input."""
        dict_response = {
            "winner": "Essay B",
            "justification": "This essay has better arguments.",
            "confidence": 3.5,
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(dict_response, correlation_id=correlation_id)

        assert validated is not None
        assert validated.winner == "Essay B"

    def test_invalid_json_string(self) -> None:
        """Test validation with invalid JSON string."""
        invalid_json = (
            '{"winner": "Essay A", "justification": "Good essay"'  # Missing closing brace
        )

        correlation_id = uuid4()
        with pytest.raises(HuleEduError) as exc_info:
            validate_and_normalize_response(invalid_json, correlation_id=correlation_id)

        assert "Invalid JSON format" in str(exc_info.value)

    def test_missing_required_fields_gets_defaults(self) -> None:
        """Test validation with missing required fields gets default values."""
        incomplete_response = {
            "winner": "Essay A"
            # Missing justification and confidence - should get defaults
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(
            incomplete_response, correlation_id=correlation_id
        )

        assert validated is not None
        assert validated.winner == "Essay A"
        assert len(validated.justification) >= 10
        assert validated.confidence == 3.0

    def test_invalid_winner_value_gets_normalized(self) -> None:
        """Test validation with invalid winner value gets normalized."""
        invalid_response = {
            "winner": "A",  # Should be "Essay A" or "Essay B" - gets normalized to "Essay A"
            "justification": "This essay demonstrates better writing quality.",
            "confidence": 3.0,
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(invalid_response, correlation_id=correlation_id)

        assert validated is not None
        assert validated.winner == "Essay A"  # Normalized from "A"

    def test_confidence_out_of_range(self) -> None:
        """Test that confidence values are automatically clamped."""
        response_with_high_confidence = {
            "winner": "Essay A",
            "justification": "This essay shows exceptional quality.",
            "confidence": 10.0,  # Will be clamped to 5.0
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(
            response_with_high_confidence, correlation_id=correlation_id
        )

        assert validated is not None
        assert validated.confidence == 5.0

    def test_justification_normalization(self) -> None:
        """Test that justifications are preserved up to 500 characters."""
        # Test short justification is preserved as-is
        short_response = {
            "winner": "Essay A",
            "justification": "Short",  # Less than 10 chars
            "confidence": 3.0,
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(short_response, correlation_id=correlation_id)
        assert validated is not None
        assert validated.justification == "Short"

        # Test medium justification is preserved (up to 500 chars)
        medium_text = "A" * 100  # 100 chars - well within limit
        medium_response = {
            "winner": "Essay B",
            "justification": medium_text,
            "confidence": 4.0,
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(medium_response, correlation_id=correlation_id)
        assert validated is not None
        assert validated.justification == medium_text
        assert len(validated.justification) == 100


class TestProviderFormatCompatibility:
    """Test compatibility with different provider response formats."""

    def test_anthropic_tool_format(self) -> None:
        """Test validation with Anthropic tool response format."""
        anthropic_response = {
            "winner": "Essay A",
            "justification": "Essay A demonstrates superior organization.",
            "confidence": 4.3,
        }

        correlation_id = uuid4()
        validated = validate_and_normalize_response(
            anthropic_response, correlation_id=correlation_id
        )

        assert validated is not None
        assert validated.winner == "Essay A"
        assert validated.justification == anthropic_response["justification"]

    def test_openai_json_schema_format(self) -> None:
        """Test validation with OpenAI JSON schema response format."""
        openai_response = json.dumps(
            {
                "winner": "Essay B",
                "justification": "Essay B provides more compelling evidence.",
                "confidence": 2.8,
            }
        )

        correlation_id = uuid4()
        validated = validate_and_normalize_response(openai_response, correlation_id=correlation_id)

        assert validated is not None
        assert validated.winner == "Essay B"

    def test_google_structured_output_format(self) -> None:
        """Test validation with Google structured output format."""
        google_response = json.dumps(
            {
                "winner": "Essay A",
                "justification": "Essay A shows better mastery of writing.",
                "confidence": 3.7,
            }
        )

        correlation_id = uuid4()
        validated = validate_and_normalize_response(google_response, correlation_id=correlation_id)

        assert validated is not None

    def test_openrouter_json_mode_format(self) -> None:
        """Test validation with OpenRouter JSON mode response format."""
        openrouter_response = json.dumps(
            {
                "winner": "Essay B",
                "justification": "Essay B demonstrates more sophisticated analysis.",
                "confidence": 4.1,
            }
        )

        correlation_id = uuid4()
        validated = validate_and_normalize_response(
            openrouter_response, correlation_id=correlation_id
        )

        assert validated is not None


class TestResponseFormatStandardization:
    """Test that all provider formats convert to the same internal format."""

    @pytest.mark.parametrize(
        "provider_response,expected_choice",
        [
            (
                {
                    "winner": "Essay A",
                    "justification": "Essay A is better written.",
                    "confidence": 3.0,
                },
                "A",
            ),
            (
                {
                    "winner": "Essay B",
                    "justification": "Essay B demonstrates superior structure.",
                    "confidence": 4.0,
                },
                "B",
            ),
        ],
    )
    def test_standardized_format_conversion(
        self, provider_response: Dict[str, Any], expected_choice: str
    ) -> None:
        """Test that standardized responses convert correctly to internal format."""
        correlation_id = uuid4()
        validated = validate_and_normalize_response(
            provider_response, correlation_id=correlation_id
        )

        assert validated is not None
        assert validated.winner == f"Essay {expected_choice}"
        assert len(validated.justification) <= 50  # Justification length validation
        assert 1.0 <= validated.confidence <= 5.0  # Confidence range validation
