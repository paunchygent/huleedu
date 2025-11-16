"""Error categorization and structured error handling for CJ Assessment Service.

This module provides utilities for categorizing exceptions into appropriate
error codes and creating structured error details for event processing failures.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)


def create_parsing_error_detail(error_message: str, exception_type: str) -> ErrorDetail:
    """Create structured error detail for message parsing failures."""
    return create_error_detail_with_context(
        error_code=ErrorCode.PARSING_ERROR,
        message=f"Failed to parse CJ assessment message: {error_message}",
        service="cj_assessment_service",
        operation="parse_kafka_message",
        correlation_id=uuid4(),  # Generate correlation_id for parsing stage
        details={
            "exception_type": exception_type,
            "parsing_stage": "event_envelope",
        },
    )


def categorize_processing_error(
    exception: Exception, correlation_id: UUID | None = None
) -> ErrorDetail:
    """Categorize processing exceptions into appropriate ErrorCode types."""
    if isinstance(exception, HuleEduError):
        # Already a structured HuleEdu error - return the error detail directly
        return exception.error_detail

    # Categorize based on exception type
    if "timeout" in str(exception).lower() or "TimeoutError" in type(exception).__name__:
        error_code = ErrorCode.TIMEOUT
    elif "connection" in str(exception).lower() or "ConnectionError" in type(exception).__name__:
        error_code = ErrorCode.CONNECTION_ERROR
    elif "validation" in str(exception).lower() or "ValidationError" in type(exception).__name__:
        error_code = ErrorCode.VALIDATION_ERROR
    elif "not found" in str(exception).lower() or "NotFound" in type(exception).__name__:
        error_code = ErrorCode.RESOURCE_NOT_FOUND
    else:
        error_code = ErrorCode.PROCESSING_ERROR

    return create_error_detail_with_context(
        error_code=error_code,
        message=f"CJ assessment processing failed: {str(exception)}",
        service="cj_assessment_service",
        operation="categorize_processing_error",
        correlation_id=correlation_id or uuid4(),  # Use provided correlation_id or generate new one
        details={
            "exception_type": type(exception).__name__,
            "processing_stage": "cj_assessment_workflow",
        },
    )


def create_publishing_error_detail(
    exception: Exception, correlation_id: UUID | None = None
) -> ErrorDetail:
    """Create structured error detail for event publishing failures."""
    return create_error_detail_with_context(
        error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
        message=f"Failed to publish failure event: {str(exception)}",
        service="cj_assessment_service",
        operation="publish_failure_event",
        correlation_id=correlation_id or uuid4(),
        details={
            "exception_type": type(exception).__name__,
            "publishing_stage": "assessment_failed_event",
        },
    )
