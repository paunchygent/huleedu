"""
FastAPI integration for HuleEdu error handling.

This module provides error handlers and utilities for integrating
the exception-based error handling with FastAPI applications.
"""

import logging
from uuid import uuid4

from common_core.error_enums import ErrorCode
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError
from .logging_utils import format_error_for_logging
from .quart_handlers import ERROR_CODE_TO_HTTP_STATUS

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register error handlers with a FastAPI application."""

    @app.exception_handler(HuleEduError)
    async def huleedu_error_handler(request: Request, exc: HuleEduError):
        # Log the error
        log_context = format_error_for_logging(exc.error_detail)
        logger.error("HuleEduError occurred", extra=log_context, exc_info=True)

        # Get HTTP status
        status_code = ERROR_CODE_TO_HTTP_STATUS.get(exc.error_detail.error_code, 500)

        # Create response
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.error_detail.error_code.value,
                    "message": exc.error_detail.message,
                    "correlation_id": str(exc.error_detail.correlation_id),
                    "service": exc.error_detail.service,
                    "timestamp": exc.error_detail.timestamp.isoformat(),
                    "details": exc.error_detail.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        correlation_id = getattr(request.state, "correlation_id", uuid4())

        # Extract first validation error
        errors = exc.errors()
        first_error = errors[0] if errors else {"msg": "Validation failed"}

        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=first_error.get("msg", "Invalid request"),
            service=app.title.lower().replace(" ", "_"),
            operation=f"{request.method} {request.url.path}",
            correlation_id=correlation_id,
            details={"validation_errors": errors},
        )

        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": error_detail.error_code.value,
                    "message": error_detail.message,
                    "correlation_id": str(error_detail.correlation_id),
                    "service": error_detail.service,
                    "timestamp": error_detail.timestamp.isoformat(),
                    "details": error_detail.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", uuid4())

        logger.exception(
            "Unexpected error occurred",
            extra={
                "error.type": type(exc).__name__,
                "error.message": str(exc),
                "correlation_id": str(correlation_id),
            },
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.UNKNOWN_ERROR.value,
                    "message": "An unexpected error occurred",
                    "correlation_id": str(correlation_id),
                    "service": app.title.lower().replace(" ", "_"),
                    "timestamp": create_error_detail_with_context(
                        error_code=ErrorCode.UNKNOWN_ERROR,
                        message=str(exc),
                        service=app.title.lower().replace(" ", "_"),
                        operation="handle_unexpected_error",
                        correlation_id=correlation_id,
                    ).timestamp.isoformat(),
                    "details": {"error_type": type(exc).__name__},
                }
            },
        )


def extract_correlation_id(request: Request) -> str:
    """Extract or generate correlation ID from request."""
    # Try state first (set by middleware)
    if hasattr(request.state, "correlation_id"):
        return str(request.state.correlation_id)

    # Try header
    correlation_id = request.headers.get("X-Correlation-ID")

    # Try query parameter
    if not correlation_id:
        correlation_id = request.query_params.get("correlation_id")

    # Generate new
    if not correlation_id:
        correlation_id = str(uuid4())

    return correlation_id
