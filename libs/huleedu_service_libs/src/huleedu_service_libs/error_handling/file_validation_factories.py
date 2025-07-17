"""
Factory functions for creating and raising FileValidationErrorCode exceptions.

This module provides standardized factory functions for file validation
specific error codes.
"""

from typing import Any, NoReturn
from uuid import UUID

from common_core.error_enums import FileValidationErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError


def raise_empty_content_error(
    service: str,
    operation: str,
    file_name: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an empty content error."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.EMPTY_CONTENT,
        message=f"File '{file_name}' has empty content",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"file_name": file_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_content_too_short(
    service: str,
    operation: str,
    file_name: str,
    min_length: int,
    actual_length: int,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a content too short error."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
        message=(
            f"File '{file_name}' content is too short "
            f"(minimum: {min_length}, actual: {actual_length})"
        ),
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "file_name": file_name,
            "min_length": min_length,
            "actual_length": actual_length,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_content_too_long(
    service: str,
    operation: str,
    file_name: str,
    max_length: int,
    actual_length: int,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a content too long error."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
        message=(
            f"File '{file_name}' content is too long "
            f"(maximum: {max_length}, actual: {actual_length})"
        ),
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "file_name": file_name,
            "max_length": max_length,
            "actual_length": actual_length,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_raw_storage_failed(
    service: str,
    operation: str,
    file_name: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a raw storage failed error."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.RAW_STORAGE_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"file_name": file_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_text_extraction_failed(
    service: str,
    operation: str,
    file_name: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a text extraction failed error."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.TEXT_EXTRACTION_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"file_name": file_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_unknown_validation_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an unknown validation error."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)
