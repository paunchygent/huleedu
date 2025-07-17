"""
Unit tests for File Service validation protocols.

Tests the protocol contracts to ensure proper interface definitions
and compatibility with dependency injection patterns.
"""

from __future__ import annotations

from common_core.error_enums import FileValidationErrorCode

from services.file_service.protocols import ContentValidatorProtocol
from services.file_service.validation_models import ValidationResult


class TestContentValidatorProtocol:
    """Test suite for ContentValidatorProtocol interface."""

    def test_protocol_defines_required_method(self) -> None:
        """Test that protocol defines the required validate_content method."""
        # Check that the protocol has the expected method signature
        assert hasattr(ContentValidatorProtocol, "validate_content")

    async def test_protocol_implementation_compatibility(self) -> None:
        """Test that a concrete implementation satisfies the protocol."""

        class MockValidator:
            """Mock implementation of ContentValidatorProtocol for testing."""

            async def validate_content(self, text: str, file_name: str) -> ValidationResult:
                """Mock implementation that always returns valid result."""
                return ValidationResult(is_valid=True)

        # Verify that the mock implementation satisfies the protocol
        validator: ContentValidatorProtocol = MockValidator()

        # Test that the protocol method can be called
        result = await validator.validate_content("test content", "test.txt")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    async def test_protocol_method_signature(self) -> None:
        """Test that protocol method has correct signature requirements."""

        class TestValidator:
            """Test validator to verify protocol compliance."""

            async def validate_content(self, text: str, file_name: str) -> ValidationResult:
                """Implementation for testing method signature compliance."""
                return ValidationResult(
                    is_valid=len(text) > 0,
                    error_code=FileValidationErrorCode.EMPTY_CONTENT if not text else None,
                    error_message="Content is empty" if not text else None,
                )

        validator = TestValidator()

        # Test with various inputs to verify signature works correctly
        valid_result = await validator.validate_content("Valid content", "valid.txt")
        assert valid_result.is_valid is True

        empty_result = await validator.validate_content("", "empty.txt")
        assert empty_result.is_valid is False
        assert empty_result.error_code == FileValidationErrorCode.EMPTY_CONTENT
