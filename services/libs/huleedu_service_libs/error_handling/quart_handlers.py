"""
Quart integration for HuleEdu error handling.

This module provides error handlers and utilities for integrating
the exception-based error handling with Quart applications.
"""

import logging
from typing import Any, Tuple
from uuid import uuid4

from quart import Quart, Response, jsonify

from common_core.error_enums import (
    ClassManagementErrorCode,
    ErrorCode,
    FileValidationErrorCode,
)
from common_core.models.error_models import ErrorDetail

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError
from .logging_utils import format_error_for_logging

# Get logger for this module
logger = logging.getLogger(__name__)

# Mapping of error codes to HTTP status codes
ERROR_CODE_TO_HTTP_STATUS = {
    # Generic error codes
    ErrorCode.UNKNOWN_ERROR: 500,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.CONFIGURATION_ERROR: 500,
    ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
    ErrorCode.KAFKA_PUBLISH_ERROR: 500,
    ErrorCode.CONTENT_SERVICE_ERROR: 502,
    ErrorCode.SPELLCHECK_SERVICE_ERROR: 502,
    ErrorCode.NLP_SERVICE_ERROR: 502,
    ErrorCode.AI_FEEDBACK_SERVICE_ERROR: 502,
    ErrorCode.CJ_ASSESSMENT_SERVICE_ERROR: 502,
    ErrorCode.MISSING_REQUIRED_FIELD: 400,
    ErrorCode.INVALID_CONFIGURATION: 500,
    ErrorCode.TIMEOUT: 504,
    ErrorCode.CONNECTION_ERROR: 503,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.RATE_LIMIT: 429,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.AUTHENTICATION_ERROR: 401,
    ErrorCode.INVALID_API_KEY: 401,
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.INVALID_RESPONSE: 502,
    ErrorCode.PARSING_ERROR: 400,
    ErrorCode.CIRCUIT_BREAKER_OPEN: 503,
    ErrorCode.REQUEST_QUEUED: 202,
    ErrorCode.PROCESSING_ERROR: 500,
    ErrorCode.INITIALIZATION_FAILED: 500,
    # Class management error codes
    ClassManagementErrorCode.COURSE_NOT_FOUND: 404,
    ClassManagementErrorCode.COURSE_VALIDATION_ERROR: 400,
    ClassManagementErrorCode.MULTIPLE_COURSE_ERROR: 409,
    ClassManagementErrorCode.CLASS_NOT_FOUND: 404,
    ClassManagementErrorCode.STUDENT_NOT_FOUND: 404,
    # File validation error codes
    FileValidationErrorCode.EMPTY_CONTENT: 400,
    FileValidationErrorCode.CONTENT_TOO_SHORT: 400,
    FileValidationErrorCode.CONTENT_TOO_LONG: 400,
    FileValidationErrorCode.RAW_STORAGE_FAILED: 500,
    FileValidationErrorCode.TEXT_EXTRACTION_FAILED: 500,
    FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR: 400,
}


def register_error_handlers(app: Quart) -> None:
    """
    Register error handlers with a Quart application.

    This function sets up handlers for:
    - HuleEduError exceptions
    - Unexpected exceptions

    Args:
        app: The Quart application instance
    """

    @app.errorhandler(HuleEduError)
    async def handle_huleedu_error(error: HuleEduError) -> Tuple[Response, int]:
        """Handle HuleEduError exceptions."""
        # Log the full error context
        log_context = format_error_for_logging(error.error_detail)
        logger.error(
            "HuleEduError occurred",
            extra=log_context,
            exc_info=True,
        )

        # Get HTTP status code
        status_code = ERROR_CODE_TO_HTTP_STATUS.get(
            error.error_detail.error_code,
            500,  # Default to 500 if not mapped
        )

        # Create error response
        response_data = {
            "error": {
                "code": error.error_detail.error_code.value,
                "message": error.error_detail.message,
                "correlation_id": str(error.error_detail.correlation_id),
                "service": error.error_detail.service,
                "timestamp": error.error_detail.timestamp.isoformat(),
                "details": error.error_detail.details,
            }
        }

        return jsonify(response_data), status_code

    @app.errorhandler(Exception)
    async def handle_unexpected_error(error: Exception) -> Tuple[Response, int]:
        """Handle unexpected exceptions."""
        # Generate correlation ID for tracking
        correlation_id = uuid4()

        # Log the unexpected error
        logger.exception(
            "Unexpected error occurred",
            extra={
                "error.type": type(error).__name__,
                "error.message": str(error),
                "correlation_id": str(correlation_id),
            },
        )

        # Create generic error response
        response_data = {
            "error": {
                "code": ErrorCode.UNKNOWN_ERROR.value,
                "message": "An unexpected error occurred",
                "correlation_id": str(correlation_id),
                "service": app.config.get("SERVICE_NAME", "unknown"),
                "timestamp": create_error_detail_with_context(
                    error_code=ErrorCode.UNKNOWN_ERROR,
                    message=str(error),
                    service=app.config.get("SERVICE_NAME", "unknown"),
                    operation="handle_unexpected_error",
                    correlation_id=correlation_id,
                ).timestamp.isoformat(),
                "details": {
                    "error_type": type(error).__name__,
                },
            }
        }

        return jsonify(response_data), 500


def create_error_response(
    error_detail: ErrorDetail,
    status_code: int | None = None,
) -> Tuple[Response, int]:
    """
    Create a standardized error response from an ErrorDetail.

    This utility function can be used in route handlers to create
    consistent error responses.

    Args:
        error_detail: The ErrorDetail instance
        status_code: Optional HTTP status code override

    Returns:
        Tuple of (response, status_code)
    """
    if status_code is None:
        status_code = ERROR_CODE_TO_HTTP_STATUS.get(error_detail.error_code, 500)

    response_data = {
        "error": {
            "code": error_detail.error_code.value,
            "message": error_detail.message,
            "correlation_id": str(error_detail.correlation_id),
            "service": error_detail.service,
            "timestamp": error_detail.timestamp.isoformat(),
            "details": error_detail.details,
        }
    }

    return jsonify(response_data), status_code


def extract_correlation_id(request: Any) -> str:
    """
    Extract or generate a correlation ID from a request.

    Looks for correlation ID in:
    1. X-Correlation-ID header
    2. correlation_id query parameter
    3. Generates new UUID if not found

    Args:
        request: The Quart request object

    Returns:
        Correlation ID string
    """
    # Try header first
    correlation_id = request.headers.get("X-Correlation-ID")

    # Try query parameter if not in header
    if not correlation_id:
        correlation_id = request.args.get("correlation_id")

    # Generate new if not found
    if not correlation_id:
        correlation_id = str(uuid4())
        logger.debug(f"Generated new correlation ID: {correlation_id}")

    result: str = correlation_id
    return result
