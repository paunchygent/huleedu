"""
Unit tests for File Service validation models.

Tests the ValidationResult Pydantic model to ensure proper validation,
serialization, and configuration behavior according to Pydantic v2 standards.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from services.file_service.validation_models import ValidationResult


class TestValidationResult:
    """Test suite for ValidationResult model."""

    def test_valid_result_creation(self) -> None:
        """Test creating a successful validation result."""
        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.error_code is None
        assert result.error_message is None
        assert result.warnings == []

    def test_invalid_result_with_error_details(self) -> None:
        """Test creating a failed validation result with error information."""
        result = ValidationResult(
            is_valid=False,
            error_code="EMPTY_CONTENT",
            error_message="File contains no readable text content.",
            warnings=["File size is unusually small"]
        )

        assert result.is_valid is False
        assert result.error_code == "EMPTY_CONTENT"
        assert result.error_message == "File contains no readable text content."
        assert result.warnings == ["File size is unusually small"]

    def test_str_strip_whitespace_configuration(self) -> None:
        """Test that whitespace is automatically stripped from string fields."""
        result = ValidationResult(
            is_valid=False,
            error_code="  CONTENT_TOO_SHORT  ",
            error_message="  Content is too short.  "
        )

        assert result.error_code == "CONTENT_TOO_SHORT"
        assert result.error_message == "Content is too short."

    def test_validate_assignment_configuration(self) -> None:
        """Test that assignment validation is enabled."""
        result = ValidationResult(is_valid=True)

        # This should trigger validation on assignment
        result.error_code = "  TEST_CODE  "
        assert result.error_code == "TEST_CODE"

    def test_optional_fields_defaults(self) -> None:
        """Test that optional fields have proper default values."""
        result = ValidationResult(is_valid=True)

        assert result.error_code is None
        assert result.error_message is None
        assert result.warnings == []

    def test_warnings_list_handling(self) -> None:
        """Test proper handling of warnings list."""
        warnings = ["Warning 1", "Warning 2", "Warning 3"]
        result = ValidationResult(
            is_valid=True,
            warnings=warnings
        )

        assert result.warnings == warnings
        assert len(result.warnings) == 3

    def test_empty_warnings_list(self) -> None:
        """Test handling of empty warnings list."""
        result = ValidationResult(is_valid=True, warnings=[])

        assert result.warnings == []

    def test_serialization_round_trip(self) -> None:
        """Test serialization and deserialization maintains data integrity."""
        original = ValidationResult(
            is_valid=False,
            error_code="CONTENT_TOO_SHORT",
            error_message="Content must be at least 50 characters.",
            warnings=["Consider adding more detail"]
        )

        # Serialize to JSON
        serialized = json.dumps(original.model_dump(mode="json"))

        # Deserialize back to model
        data = json.loads(serialized)
        reconstructed = ValidationResult.model_validate(data)

        assert reconstructed.is_valid == original.is_valid
        assert reconstructed.error_code == original.error_code
        assert reconstructed.error_message == original.error_message
        assert reconstructed.warnings == original.warnings

    def test_json_serialization_format(self) -> None:
        """Test that JSON serialization produces expected format."""
        result = ValidationResult(
            is_valid=False,
            error_code="EMPTY_CONTENT",
            error_message="No content found",
            warnings=["File seems empty"]
        )

        json_data = result.model_dump(mode="json")

        assert json_data["is_valid"] is False
        assert json_data["error_code"] == "EMPTY_CONTENT"
        assert json_data["error_message"] == "No content found"
        assert json_data["warnings"] == ["File seems empty"]

    def test_required_field_validation(self) -> None:
        """Test that is_valid field is required."""
        with pytest.raises(ValidationError) as exc_info:
            ValidationResult()  # type: ignore[call-arg]

        assert "is_valid" in str(exc_info.value)

    def test_type_validation(self) -> None:
        """Test proper type validation for all fields."""
        # Test invalid type for is_valid
        with pytest.raises(ValidationError):
            ValidationResult(is_valid="not_a_boolean")  # type: ignore[arg-type]

        # Test invalid type for warnings
        with pytest.raises(ValidationError):
            ValidationResult(is_valid=True, warnings="not_a_list")  # type: ignore[arg-type]

    def test_none_values_handling(self) -> None:
        """Test proper handling of None values for optional fields."""
        result = ValidationResult(
            is_valid=True,
            error_code=None,
            error_message=None
        )

        assert result.error_code is None
        assert result.error_message is None

    def test_model_equality(self) -> None:
        """Test model equality comparison."""
        result1 = ValidationResult(
            is_valid=False,
            error_code="TEST_ERROR",
            error_message="Test message"
        )

        result2 = ValidationResult(
            is_valid=False,
            error_code="TEST_ERROR",
            error_message="Test message"
        )

        assert result1 == result2

    def test_model_repr(self) -> None:
        """Test string representation of the model."""
        result = ValidationResult(
            is_valid=False,
            error_code="TEST_ERROR"
        )

        repr_str = repr(result)
        assert "ValidationResult" in repr_str
        assert "is_valid=False" in repr_str
        assert "error_code='TEST_ERROR'" in repr_str
