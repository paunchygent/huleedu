"""Error aggregation tests for grammar routes.

Tests focus on category and rule counting, error structure handling.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.language_tool_service.protocols import LanguageToolWrapperProtocol
from services.language_tool_service.tests.unit.conftest import create_mock_grammar_error


class TestErrorAggregation:
    """Tests for error aggregation and counting logic."""

    async def test_category_aggregation_single_category(self, test_client, test_app) -> None:
        """Test category counting with single category."""
        # Arrange
        request_body = {"text": "Test text with errors.", "language": "en-US"}

        # Mock wrapper to return errors of same category
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        mock_errors = [
            create_mock_grammar_error("GRAMMAR", "RULE1", "Error 1"),
            create_mock_grammar_error("GRAMMAR", "RULE2", "Error 2"),
            create_mock_grammar_error("GRAMMAR", "RULE3", "Error 3"),
        ]
        wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        assert response_data["grammar_category_counts"]["GRAMMAR"] == 3
        assert len(response_data["grammar_category_counts"]) == 1

    async def test_category_aggregation_multiple_categories(self, test_client, test_app) -> None:
        """Test category counting with multiple categories."""
        # Arrange
        request_body = {"text": "Test text with various errors.", "language": "en-US"}

        # Mock wrapper to return errors of different categories
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        mock_errors = [
            create_mock_grammar_error("GRAMMAR", "RULE1", "Grammar error"),
            create_mock_grammar_error("SPELLING", "RULE2", "Spelling error"),
            create_mock_grammar_error("GRAMMAR", "RULE3", "Another grammar error"),
            create_mock_grammar_error("STYLE", "RULE4", "Style issue"),
            create_mock_grammar_error("SPELLING", "RULE5", "Another spelling error"),
        ]
        wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        assert response_data["grammar_category_counts"]["GRAMMAR"] == 2
        assert response_data["grammar_category_counts"]["SPELLING"] == 2
        assert response_data["grammar_category_counts"]["STYLE"] == 1
        assert len(response_data["grammar_category_counts"]) == 3

    async def test_rule_aggregation_with_duplicates(self, test_client, test_app) -> None:
        """Test rule counting with duplicate rule IDs."""
        # Arrange
        request_body = {"text": "Text with repeated rule violations.", "language": "en-US"}

        # Mock wrapper to return errors with same rule IDs
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        mock_errors = [
            create_mock_grammar_error("GRAMMAR", "AGREEMENT", "Error 1"),
            create_mock_grammar_error("GRAMMAR", "AGREEMENT", "Error 2"),
            create_mock_grammar_error("SPELLING", "TYPO", "Error 3"),
            create_mock_grammar_error("GRAMMAR", "AGREEMENT", "Error 4"),
        ]
        wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        assert response_data["grammar_rule_counts"]["AGREEMENT"] == 3
        assert response_data["grammar_rule_counts"]["TYPO"] == 1
        assert len(response_data["grammar_rule_counts"]) == 2

    async def test_error_with_missing_type_field(self, test_client, test_app) -> None:
        """Test handling of errors with missing type field."""
        # Arrange
        request_body = {"text": "Text with malformed errors.", "language": "en-US"}

        # Mock wrapper to return errors with missing fields
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        mock_errors = [
            {
                "rule": {"id": "RULE1"},
                "message": "Error without type",
                "offset": 0,
                "length": 5,
            },
            create_mock_grammar_error("GRAMMAR", "RULE2", "Normal error"),
        ]
        wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        # Missing type should default to "UNKNOWN"
        assert response_data["grammar_category_counts"]["UNKNOWN"] == 1
        assert response_data["grammar_category_counts"]["GRAMMAR"] == 1

    async def test_error_with_missing_rule_field(self, test_client, test_app) -> None:
        """Test handling of errors with missing rule field."""
        # Arrange
        request_body = {"text": "Text with incomplete errors.", "language": "en-US"}

        # Mock wrapper to return errors with missing rule
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        mock_errors = [
            {
                "type": {"typeName": "GRAMMAR"},
                "message": "Error without rule",
                "offset": 0,
                "length": 5,
            },
            create_mock_grammar_error("SPELLING", "TYPO", "Normal error"),
        ]
        wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        # Missing rule should default to "UNKNOWN_RULE"
        assert response_data["grammar_rule_counts"]["UNKNOWN_RULE"] == 1
        assert response_data["grammar_rule_counts"]["TYPO"] == 1

    async def test_error_with_non_dict_type_field(self, test_client, test_app) -> None:
        """Test handling of errors where type field is not a dict."""
        # Arrange
        request_body = {"text": "Text with invalid error structure.", "language": "en-US"}

        # Mock wrapper to return errors with non-dict type
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        mock_errors = [
            {
                "type": "STRING_TYPE",  # Not a dict
                "rule": {"id": "RULE1"},
                "message": "Error with string type",
                "offset": 0,
                "length": 5,
            },
        ]
        wrapper.check_text.return_value = mock_errors

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        # Non-dict type should default to "UNKNOWN"
        assert response_data["grammar_category_counts"]["UNKNOWN"] == 1

    async def test_empty_error_list(self, test_client, test_app) -> None:
        """Test that empty error list produces empty counts."""
        # Arrange
        request_body = {"text": "Perfect text with no errors.", "language": "en-US"}

        # Mock wrapper to return empty list
        container = test_app.extensions["dishka_app"]
        wrapper = await container.get(LanguageToolWrapperProtocol)
        wrapper.check_text.return_value = []

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        
        assert response_data["total_grammar_errors"] == 0
        assert response_data["grammar_category_counts"] == {}
        assert response_data["grammar_rule_counts"] == {}