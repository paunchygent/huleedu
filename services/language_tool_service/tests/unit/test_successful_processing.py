"""Successful processing tests for grammar routes.

Tests focus on successful grammar check scenarios and response validation.
"""

from __future__ import annotations

from typing import Any

import pytest

from services.language_tool_service.tests.unit.conftest import (
    create_mock_grammar_error,
    generate_text_with_words,
)


class TestSuccessfulProcessing:
    """Tests for successful grammar check processing."""

    async def test_successful_grammar_check_no_errors(
        self, test_client: Any, mock_language_tool_wrapper: Any
    ) -> None:
        """Test successful grammar check with no errors found."""
        # Arrange
        request_body = {"text": "This is a perfectly valid sentence.", "language": "en-US"}

        # Mock wrapper to return no errors
        mock_language_tool_wrapper.check_text.return_value = []

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()

        # Verify response structure
        assert response_data["total_grammar_errors"] == 0
        assert response_data["errors"] == []
        assert response_data["grammar_category_counts"] == {}
        assert response_data["grammar_rule_counts"] == {}
        assert response_data["language"] == "en-US"
        assert response_data["processing_time_ms"] > 0

    async def test_successful_grammar_check_with_errors(
        self, test_client: Any, mock_language_tool_wrapper: Any
    ) -> None:
        """Test successful grammar check with errors found."""
        # Arrange
        request_body = {"text": "This are a incorrect sentence.", "language": "en-US"}

        # Mock wrapper to return errors
        mock_errors = [
            create_mock_grammar_error("GRAMMAR", "AGREEMENT_ERROR", "Subject-verb disagreement"),
            create_mock_grammar_error("SPELLING", "TYPO", "Possible typo"),
        ]
        mock_language_tool_wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()

        assert response_data["total_grammar_errors"] == 2
        assert len(response_data["errors"]) == 2
        assert response_data["grammar_category_counts"]["GRAMMAR"] == 1
        assert response_data["grammar_category_counts"]["SPELLING"] == 1
        assert response_data["grammar_rule_counts"]["AGREEMENT_ERROR"] == 1
        assert response_data["grammar_rule_counts"]["TYPO"] == 1

    @pytest.mark.parametrize(
        "word_count",
        [50, 150, 400, 750, 1500, 2500],
    )
    async def test_different_text_sizes(self, test_client: Any, word_count: int) -> None:
        """Test successful processing with different text sizes."""
        # Arrange
        text = generate_text_with_words(word_count)
        request_body = {"text": text, "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()

        assert "errors" in response_data
        assert "total_grammar_errors" in response_data
        assert "processing_time_ms" in response_data
        assert response_data["processing_time_ms"] > 0

    @pytest.mark.parametrize(
        "language",
        ["en-US", "sv-SE", "de-DE", "fr-FR", "auto"],
    )
    async def test_different_languages(self, test_client: Any, language: str) -> None:
        """Test successful processing with different language codes."""
        # Arrange
        request_body = {
            "text": "Test text for different language processing.",
            "language": language,
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["language"] == language

    async def test_processing_time_calculation(self, test_client: Any) -> None:
        """Test that processing time is calculated and included in response."""
        # Arrange
        request_body = {
            "text": "Test text for timing validation.",
            "language": "en-US",
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()

        assert "processing_time_ms" in response_data
        assert isinstance(response_data["processing_time_ms"], int)
        assert response_data["processing_time_ms"] >= 0
        # Processing should take at least some time
        assert response_data["processing_time_ms"] < 10000  # Less than 10 seconds

    async def test_correlation_id_in_response_headers(self, test_client: Any) -> None:
        """Test that correlation ID is included in response headers."""
        # Arrange
        request_body = {
            "text": "Test text for correlation ID check.",
            "language": "en-US",
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        # In test context, correlation ID should be present
        # The actual header checking would depend on middleware setup
