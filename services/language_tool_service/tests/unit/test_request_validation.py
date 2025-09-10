"""Request validation tests for grammar routes.

Tests focus on request body validation, JSON parsing, and field validation
following Rule 075 behavioral testing methodology.
"""

from __future__ import annotations

from typing import Any

import pytest


class TestRequestBodyValidation:
    """Tests for request body validation scenarios."""

    @pytest.mark.parametrize(
        "request_body, expected_status, expected_error_field",
        [
            # Missing request body cases
            (None, 400, "json_body"),
            # Empty JSON object
            ({}, 400, "json_body"),
            # Missing required text field
            ({"language": "en-US"}, 400, "request_format"),
        ],
    )
    async def test_missing_request_body_scenarios(
        self,
        test_client: Any,
        request_body: dict[str, Any] | None,
        expected_status: int,
        expected_error_field: str,
    ) -> None:
        """Test grammar check endpoint handles missing or incomplete request bodies."""
        # Act
        if request_body is None:
            response = await test_client.post("/v1/check")
        else:
            response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == expected_status

        response_data = await response.get_json()
        assert "error" in response_data
        assert response_data["error"]["details"]["field"] == expected_error_field
        assert response_data["error"]["service"] == "language-tool-service"
        assert response_data["error"]["code"] == "VALIDATION_ERROR"
        assert "correlation_id" in response_data["error"]

    async def test_invalid_json_body(self, test_client: Any) -> None:
        """Test grammar check endpoint handles malformed JSON."""
        # Act
        response = await test_client.post(
            "/v1/check", data="invalid json content", headers={"Content-Type": "application/json"}
        )

        # Assert
        assert response.status_code == 400

        response_data = await response.get_json()
        assert "error" in response_data
        assert response_data["error"]["details"]["field"] == "json_body"
        assert "Invalid JSON" in response_data["error"]["message"]

    @pytest.mark.parametrize(
        "extra_fields",
        [
            {"extra_field": "should_be_ignored"},
            {"unknown": "value", "another": 123},
            {"extra1": "test", "extra2": [1, 2, 3], "extra3": {"nested": "object"}},
        ],
    )
    async def test_ignores_extra_fields(
        self, test_client: Any, extra_fields: dict[str, Any]
    ) -> None:
        """Test grammar check endpoint ignores unexpected extra fields."""
        # Arrange
        request_body = {
            "text": "Valid test text for grammar checking.",
            "language": "en-US",
            **extra_fields,
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert "errors" in response_data
        assert "total_grammar_errors" in response_data


class TestFieldTypeValidation:
    """Tests for field type validation."""

    @pytest.mark.parametrize(
        "invalid_body, expected_error",
        [
            # Text field type validation
            ({"text": 123, "language": "en-US"}, "Input should be a valid string"),
            ({"text": None, "language": "en-US"}, "Input should be a valid string"),
            ({"text": [], "language": "en-US"}, "Input should be a valid string"),
            ({"text": {}, "language": "en-US"}, "Input should be a valid string"),
            ({"text": True, "language": "en-US"}, "Input should be a valid string"),
            # Language field type validation
            ({"text": "Valid text", "language": 123}, "Input should be a valid string"),
            ({"text": "Valid text", "language": []}, "Input should be a valid string"),
            ({"text": "Valid text", "language": {}}, "Input should be a valid string"),
            ({"text": "Valid text", "language": True}, "Input should be a valid string"),
        ],
    )
    async def test_invalid_field_types(
        self,
        test_client: Any,
        invalid_body: dict[str, Any],
        expected_error: str,
    ) -> None:
        """Test grammar check endpoint validates field types."""
        # Act
        response = await test_client.post("/v1/check", json=invalid_body)

        # Assert
        assert response.status_code == 400

        response_data = await response.get_json()
        assert "error" in response_data
        assert response_data["error"]["code"] == "VALIDATION_ERROR"
        assert expected_error in response_data["error"]["message"]

    async def test_null_text_field_rejected(self, test_client: Any) -> None:
        """Test that null text field is properly rejected."""
        # Arrange
        request_body = {"text": None, "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
        assert "Input should be a valid string" in response_data["error"]["message"]


class TestRequestStructureValidation:
    """Tests for overall request structure validation."""

    async def test_nested_json_structure_rejected(self, test_client: Any) -> None:
        """Test that incorrectly nested JSON structures are rejected."""
        # Arrange
        request_body = {"data": {"text": "This is nested incorrectly", "language": "en-US"}}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
        assert response_data["error"]["code"] == "VALIDATION_ERROR"

    async def test_array_instead_of_object_rejected(self, test_client: Any) -> None:
        """Test that arrays are rejected when object is expected."""
        # Arrange
        request_array = ["text", "en-US"]

        # Act
        response = await test_client.post("/v1/check", json=request_array)

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
        assert "json_body" in response_data["error"]["details"]["field"]

    @pytest.mark.parametrize(
        "content_type",
        [
            "text/plain",
            "application/xml",
            "multipart/form-data",
            "application/x-www-form-urlencoded",
        ],
    )
    async def test_non_json_content_types_rejected(
        self, test_client: Any, content_type: str
    ) -> None:
        """Test that non-JSON content types are properly rejected."""
        # Act
        response = await test_client.post(
            "/v1/check", data="text=test&language=en-US", headers={"Content-Type": content_type}
        )

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
