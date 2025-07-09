"""Custom exception classes for CJ Assessment Service.

This module provides a comprehensive exception hierarchy for the CJ Assessment Service,
implementing proper error categorization, correlation ID tracking, and structured error details
for effective observability and debugging.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_core.error_enums import ErrorCode


class CJAssessmentError(Exception):
    """Base exception for CJ Assessment Service.

    All service-specific exceptions should inherit from this class to ensure
    consistent error handling with proper correlation ID tracking and error codes.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        correlation_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Initialize the base CJ Assessment error.

        Args:
            error_code: The ErrorCode enum value for categorization
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            details: Optional dictionary of additional error context
            timestamp: Optional error timestamp (defaults to current UTC time)
        """
        self.error_code = error_code
        self.message = message
        self.correlation_id = correlation_id
        self.details = details or {}
        self.timestamp = timestamp or datetime.now(UTC)
        super().__init__(message)


class LLMProviderError(CJAssessmentError):
    """LLM Provider Service communication errors.

    Used for all errors related to communication with the LLM Provider Service,
    including HTTP errors, timeouts, and invalid responses.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        status_code: int | None = None,
        is_retryable: bool = False,
        retry_after: int | None = None,
        provider: str | None = None,
        queue_id: str | None = None,
    ) -> None:
        """Initialize LLM Provider Service error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            status_code: HTTP status code from the LLM Provider Service
            is_retryable: Whether this error should trigger retry logic
            retry_after: Optional retry delay in seconds
            provider: Optional LLM provider name (e.g., "anthropic", "openai")
            queue_id: Optional queue ID for queued requests
        """
        details = {
            "status_code": status_code,
            "is_retryable": is_retryable,
            "retry_after": retry_after,
            "provider": provider,
            "queue_id": queue_id,
        }
        super().__init__(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


class ContentServiceError(CJAssessmentError):
    """Content Service communication errors.

    Used for all errors related to fetching essay content from the Content Service.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        status_code: int | None = None,
        storage_id: str | None = None,
        is_retryable: bool = False,
    ) -> None:
        """Initialize Content Service error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            status_code: HTTP status code from the Content Service
            storage_id: Optional storage ID that failed to fetch
            is_retryable: Whether this error should trigger retry logic
        """
        details = {
            "status_code": status_code,
            "storage_id": storage_id,
            "is_retryable": is_retryable,
        }
        super().__init__(
            error_code=ErrorCode.CONTENT_SERVICE_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


class AssessmentProcessingError(CJAssessmentError):
    """Internal assessment processing errors.

    Used for errors that occur during CJ assessment workflow processing,
    including batch preparation, comparison processing, and scoring.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        batch_id: str | None = None,
        essay_ids: list[str] | None = None,
        processing_stage: str | None = None,
    ) -> None:
        """Initialize assessment processing error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            batch_id: Optional batch ID being processed
            essay_ids: Optional list of essay IDs involved in the error
            processing_stage: Optional processing stage where error occurred
        """
        details = {
            "batch_id": batch_id,
            "essay_ids": essay_ids,
            "processing_stage": processing_stage,
        }
        super().__init__(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


class InvalidPromptError(CJAssessmentError):
    """Invalid prompt format errors.

    Used when the prompt format is invalid or cannot be parsed for essay extraction.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        prompt_length: int | None = None,
    ) -> None:
        """Initialize invalid prompt error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            prompt_length: Optional length of the invalid prompt
        """
        details = {
            "prompt_length": prompt_length,
        }
        super().__init__(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


class EventPublishingError(CJAssessmentError):
    """Event publishing errors.

    Used for errors that occur when publishing events to Kafka.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        event_type: str | None = None,
        topic: str | None = None,
    ) -> None:
        """Initialize event publishing error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            event_type: Optional event type that failed to publish
            topic: Optional Kafka topic that failed
        """
        details = {
            "event_type": event_type,
            "topic": topic,
        }
        super().__init__(
            error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


class DatabaseOperationError(CJAssessmentError):
    """Database operation errors.

    Used for errors that occur during database operations.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        operation: str | None = None,
        entity_id: str | None = None,
    ) -> None:
        """Initialize database operation error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            operation: Optional database operation that failed
            entity_id: Optional entity ID involved in the operation
        """
        details = {
            "operation": operation,
            "entity_id": entity_id,
        }
        super().__init__(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


class QueueOperationError(CJAssessmentError):
    """Queue operation errors.

    Used for errors that occur during queue status checks and result retrieval.
    """

    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        queue_id: str | None = None,
        operation: str | None = None,
        status_code: int | None = None,
        is_retryable: bool = False,
    ) -> None:
        """Initialize queue operation error.

        Args:
            message: Human-readable error message
            correlation_id: Optional correlation ID for request tracing
            queue_id: Optional queue ID involved in the operation
            operation: Optional queue operation that failed
            status_code: Optional HTTP status code from queue service
            is_retryable: Whether this error should trigger retry logic
        """
        details = {
            "queue_id": queue_id,
            "operation": operation,
            "status_code": status_code,
            "is_retryable": is_retryable,
        }
        super().__init__(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )


# Utility functions for error code mapping


def map_status_to_error_code(status: int) -> ErrorCode:
    """Map HTTP status codes to ErrorCode enums.

    Args:
        status: HTTP status code

    Returns:
        Corresponding ErrorCode enum value
    """
    mapping = {
        400: ErrorCode.INVALID_REQUEST,
        401: ErrorCode.AUTHENTICATION_ERROR,
        403: ErrorCode.AUTHENTICATION_ERROR,
        404: ErrorCode.RESOURCE_NOT_FOUND,
        408: ErrorCode.TIMEOUT,
        429: ErrorCode.RATE_LIMIT,
        500: ErrorCode.EXTERNAL_SERVICE_ERROR,
        502: ErrorCode.SERVICE_UNAVAILABLE,
        503: ErrorCode.SERVICE_UNAVAILABLE,
        504: ErrorCode.TIMEOUT,
    }
    return mapping.get(status, ErrorCode.EXTERNAL_SERVICE_ERROR)


def map_error_to_status(error_code: ErrorCode) -> int:
    """Map ErrorCode to HTTP status for API responses.

    Args:
        error_code: ErrorCode enum value

    Returns:
        Corresponding HTTP status code
    """
    mapping = {
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.AUTHENTICATION_ERROR: 401,
        ErrorCode.RESOURCE_NOT_FOUND: 404,
        ErrorCode.TIMEOUT: 408,
        ErrorCode.RATE_LIMIT: 429,
        ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
        ErrorCode.SERVICE_UNAVAILABLE: 503,
        ErrorCode.PROCESSING_ERROR: 500,
        ErrorCode.CONTENT_SERVICE_ERROR: 502,
        ErrorCode.KAFKA_PUBLISH_ERROR: 500,
    }
    return mapping.get(error_code, 500)


def is_retryable_error(error_code: ErrorCode) -> bool:
    """Determine if an error should trigger retry.

    Args:
        error_code: ErrorCode enum value

    Returns:
        True if the error is retryable, False otherwise
    """
    retryable_codes = {
        ErrorCode.TIMEOUT,
        ErrorCode.SERVICE_UNAVAILABLE,
        ErrorCode.RATE_LIMIT,
        ErrorCode.CONNECTION_ERROR,
        ErrorCode.EXTERNAL_SERVICE_ERROR,  # HTTP 5xx errors
    }
    return error_code in retryable_codes
