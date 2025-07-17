"""
Factory functions for creating and raising ClassManagementErrorCode exceptions.

This module provides standardized factory functions for class management
specific error codes.
"""

from typing import Any, NoReturn
from uuid import UUID

from common_core.error_enums import ClassManagementErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError


def raise_course_not_found(
    service: str,
    operation: str,
    course_id: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a course not found error."""
    error_detail = create_error_detail_with_context(
        error_code=ClassManagementErrorCode.COURSE_NOT_FOUND,
        message=f"Course with ID '{course_id}' not found",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"course_id": course_id, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_course_validation_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a course validation error."""
    error_detail = create_error_detail_with_context(
        error_code=ClassManagementErrorCode.COURSE_VALIDATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_multiple_course_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a multiple course error."""
    error_detail = create_error_detail_with_context(
        error_code=ClassManagementErrorCode.MULTIPLE_COURSE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_class_not_found(
    service: str,
    operation: str,
    class_id: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a class not found error."""
    error_detail = create_error_detail_with_context(
        error_code=ClassManagementErrorCode.CLASS_NOT_FOUND,
        message=f"Class with ID '{class_id}' not found",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"class_id": class_id, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_student_not_found(
    service: str,
    operation: str,
    student_id: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a student not found error."""
    error_detail = create_error_detail_with_context(
        error_code=ClassManagementErrorCode.STUDENT_NOT_FOUND,
        message=f"Student with ID '{student_id}' not found",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"student_id": student_id, **additional_context},
    )
    raise HuleEduError(error_detail)
