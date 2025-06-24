"""
Content validator for File Service validation framework.

This module provides content validation logic to ensure uploaded files
meet quality standards before processing by downstream services.
"""

from __future__ import annotations

from common_core.error_enums import FileValidationErrorCode
from services.file_service.validation_models import ValidationResult


class FileContentValidator:
    """
    Validates file content against business rules.

    This validator implements content quality gates to prevent
    problematic content from reaching downstream services and
    provides clear feedback for content issues.
    """

    def __init__(self, min_length: int = 50, max_length: int = 50000) -> None:
        """
        Initialize validator with configurable length limits.

        Args:
            min_length: Minimum acceptable content length in characters
            max_length: Maximum acceptable content length in characters
        """
        self.min_length = min_length
        self.max_length = max_length

    async def validate_content(self, text: str, file_name: str) -> ValidationResult:
        """
        Validate extracted text content against business rules.

        Args:
            text: Extracted text content to validate
            file_name: Original filename for context in error messages

        Returns:
            ValidationResult indicating success/failure with details
        """
        # Empty content check
        if not text or not text.strip():
            return ValidationResult(
                is_valid=False,
                error_code=FileValidationErrorCode.EMPTY_CONTENT,
                error_message=f"File '{file_name}' contains no readable text content.",
            )

        # Length validation
        content_length = len(text.strip())
        if content_length < self.min_length:
            return ValidationResult(
                is_valid=False,
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                error_message=(
                    f"File '{file_name}' contains only "
                    f"{content_length} characters. Essays must contain at least "
                    f"{self.min_length} characters."
                ),
            )

        if content_length > self.max_length:
            return ValidationResult(
                is_valid=False,
                error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
                error_message=(
                    f"File '{file_name}' contains "
                    f"{content_length} characters. Essays must not exceed "
                    f"{self.max_length} characters."
                ),
            )

        # Valid content
        return ValidationResult(is_valid=True)
