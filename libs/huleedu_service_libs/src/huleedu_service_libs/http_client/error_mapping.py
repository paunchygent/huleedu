"""Error mapping utilities for HTTP client operations.

This module provides standardized mapping from aiohttp exceptions to
HuleEdu structured error types, ensuring consistent error handling
across all HTTP client operations.
"""

from typing import Any, NoReturn
from uuid import UUID

import aiohttp

from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_external_service_error,
    raise_invalid_response,
    raise_rate_limit_error,
    raise_resource_not_found,
    raise_service_unavailable,
    raise_timeout_error,
    raise_unknown_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("huleedu_service_libs.http_client.error_mapping")


def map_aiohttp_error_to_huleedu_error(
    error: Exception,
    service: str,
    operation: str,
    correlation_id: UUID,
    url: str,
    timeout_seconds: int | None = None,
    **context: Any,
) -> NoReturn:
    """Map aiohttp exceptions to structured HuleEduError exceptions.

    Args:
        error: The original aiohttp exception
        service: Name of the service making the request
        operation: Name of the operation being performed
        correlation_id: Request correlation ID for tracing
        url: Target URL of the failed request
        timeout_seconds: Request timeout in seconds (if applicable)
        **context: Additional context for error reporting

    Raises:
        HuleEduError: Structured error based on the original exception type
    """
    # Add common context for all HTTP errors
    error_context = {"url": url, **context}

    if timeout_seconds is not None:
        error_context["timeout_seconds"] = timeout_seconds

    if isinstance(error, aiohttp.ClientResponseError):
        # Handle HTTP response errors (4xx, 5xx status codes)
        _handle_http_response_error(
            error=error,
            service=service,
            operation=operation,
            correlation_id=correlation_id,
            **error_context,
        )

    elif isinstance(error, aiohttp.ServerTimeoutError):
        # Handle timeout errors
        timeout = timeout_seconds or 10  # Default timeout for error reporting
        raise_timeout_error(
            service=service,
            operation=operation,
            timeout_seconds=timeout,
            message=f"HTTP request timed out after {timeout} seconds",
            correlation_id=correlation_id,
            **error_context,
        )

    elif isinstance(error, aiohttp.ClientConnectionError):
        # Handle connection errors (DNS, connection refused, etc.)
        raise_connection_error(
            service=service,
            operation=operation,
            target=url,
            message=f"Connection error: {str(error)}",
            correlation_id=correlation_id,
            client_error_type=type(error).__name__,
            **error_context,
        )

    elif isinstance(error, aiohttp.ClientError):
        # Handle other aiohttp client errors
        raise_connection_error(
            service=service,
            operation=operation,
            target=url,
            message=f"HTTP client error: {str(error)}",
            correlation_id=correlation_id,
            client_error_type=type(error).__name__,
            **error_context,
        )

    else:
        # Handle unexpected errors
        logger.error(
            f"Unexpected error in HTTP request to {url}: {error}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id),
                "url": url,
                "error_type": type(error).__name__,
                **context,
            },
        )
        raise_unknown_error(
            service=service,
            operation=operation,
            message=f"Unexpected HTTP client error: {str(error)}",
            correlation_id=correlation_id,
            error_type=type(error).__name__,
            **error_context,
        )


def _handle_http_response_error(
    error: aiohttp.ClientResponseError,
    service: str,
    operation: str,
    correlation_id: UUID,
    **context: Any,
) -> NoReturn:
    """Handle HTTP response errors based on status code.

    Args:
        error: The ClientResponseError to handle
        service: Name of the service making the request
        operation: Name of the operation being performed
        correlation_id: Request correlation ID for tracing
        **context: Additional context for error reporting

    Raises:
        HuleEduError: Structured error based on HTTP status code
    """
    status_code = error.status
    error_message = error.message or f"HTTP {status_code}"

    # Add HTTP error specific context
    http_context = {
        "status_code": status_code,
        "error_message": error_message[:500] if error_message else "",
        **context,
    }

    if status_code == 404:
        # Resource not found - handle specially for content operations
        resource_id = context.get("storage_id", "unknown")
        raise_resource_not_found(
            service=service,
            operation=operation,
            resource_type="Content",
            resource_id=resource_id,
            correlation_id=correlation_id,
            **http_context,
        )

    elif status_code == 429:
        # Rate limiting
        raise_rate_limit_error(
            service=service,
            operation=operation,
            message=f"Rate limited by external service: {error_message}",
            correlation_id=correlation_id,
            **http_context,
        )

    elif status_code in (500, 502, 503, 504):
        # Server errors - service unavailable
        raise_service_unavailable(
            service=service,
            operation=operation,
            external_service=context.get("external_service", "content_service"),
            message=f"External service error: HTTP {status_code} - {error_message}",
            correlation_id=correlation_id,
            **http_context,
        )

    elif 400 <= status_code < 500:
        # Client errors (other than 404, 429)
        raise_invalid_response(
            service=service,
            operation=operation,
            message=f"HTTP client error: {status_code} - {error_message}",
            correlation_id=correlation_id,
            response_status=status_code,
            **http_context,
        )

    else:
        # Other HTTP errors
        raise_external_service_error(
            service=service,
            operation=operation,
            external_service=context.get("external_service", "content_service"),
            message=f"HTTP error: {status_code} - {error_message}",
            correlation_id=correlation_id,
            status_code=status_code,
            **http_context,
        )
