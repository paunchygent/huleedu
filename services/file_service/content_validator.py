"""
Content validator for File Service validation framework.

This module provides content validation logic to ensure uploaded files
meet quality standards before processing by downstream services.
"""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_content_too_long,
    raise_content_too_short,
    raise_empty_content_error,
)


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

    async def validate_content(self, text: str, file_name: str, correlation_id: UUID) -> None:
        """
        Validate extracted text content against business rules.

        Args:
            text: Extracted text content to validate
            file_name: Original filename for context in error messages
            correlation_id: Request correlation ID for tracing

        Returns:
            None if validation passes

        Raises:
            HuleEduError: If validation fails with specific error code
        """
        # Empty content check
        if not text or not text.strip():
            raise_empty_content_error(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                correlation_id=correlation_id,
            )

        # Length validation
        content_length = len(text.strip())
        if content_length < self.min_length:
            raise_content_too_short(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                min_length=self.min_length,
                actual_length=content_length,
                correlation_id=correlation_id,
            )

        if content_length > self.max_length:
            raise_content_too_long(
                service="file_service",
                operation="validate_content",
                file_name=file_name,
                max_length=self.max_length,
                actual_length=content_length,
                correlation_id=correlation_id,
            )

        # Valid content - no exception raised
