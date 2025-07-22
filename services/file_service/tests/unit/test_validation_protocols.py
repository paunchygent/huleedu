"""
Unit tests for File Service validation protocols.

Tests the protocol contracts to ensure proper interface definitions
and compatibility with dependency injection patterns.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from common_core.error_enums import FileValidationErrorCode
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_empty_content_error,
)

from services.file_service.protocols import ContentValidatorProtocol


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

            async def validate_content(
                self, text: str, file_name: str, correlation_id: UUID
            ) -> None:
                """Mock implementation that always returns valid result."""
                # No exception means validation passed
                pass

        # Verify that the mock implementation satisfies the protocol
        validator: ContentValidatorProtocol = MockValidator()

        # Test that the protocol method can be called
        correlation_id = uuid.uuid4()
        # Should not raise exception for valid content
        await validator.validate_content("test content", "test.txt", correlation_id)

    async def test_protocol_method_signature(self) -> None:
        """Test that protocol method has correct signature requirements."""

        class TestValidator:
            """Test validator to verify protocol compliance."""

            async def validate_content(
                self, text: str, file_name: str, correlation_id: UUID
            ) -> None:
                """Implementation for testing method signature compliance."""
                if not text:
                    raise_empty_content_error(
                        service="file_service",
                        operation="validate_content",
                        file_name=file_name,
                        correlation_id=correlation_id,
                    )
                # No exception means validation passed

        validator = TestValidator()

        # Test with various inputs to verify signature works correctly
        correlation_id = uuid.uuid4()

        # Valid content should not raise exception
        await validator.validate_content("Valid content", "valid.txt", correlation_id)

        # Empty content should raise exception
        import pytest
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content("", "empty.txt", correlation_id)

        assert exc_info.value.error_detail.error_code == FileValidationErrorCode.EMPTY_CONTENT
