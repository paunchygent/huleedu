"""Factory functions for CJ Assessment Service specific errors.

This module provides standardized factory functions for CJ Assessment Service
specific error scenarios that require additional context beyond generic factories.

For common operations, use generic factory functions from factories.py:
- Content service errors: raise_content_service_error
- Kafka errors: raise_kafka_publish_error  
- Validation errors: raise_validation_error
- Database processing: raise_processing_error
"""

from typing import Any, NoReturn, Optional
from uuid import UUID

from common_core.error_enums import ErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

# =============================================================================
# CJ Assessment Service Specific Business Logic Error Factories
# =============================================================================


def raise_cj_llm_provider_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    status_code: Optional[int] = None,
    is_retryable: bool = False,
    retry_after: Optional[int] = None,
    provider: Optional[str] = None,
    queue_id: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ Assessment LLM Provider Service error.
    
    Use this for LLM Provider Service communication errors that require
    CJ Assessment specific context like retry logic, queue IDs, and provider details.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        status_code: HTTP status code from the LLM Provider Service
        is_retryable: Whether this error should trigger retry logic
        retry_after: Optional retry delay in seconds
        provider: Optional LLM provider name (e.g., "anthropic", "openai")
        queue_id: Optional queue ID for queued requests
        **additional_context: Additional error context details
    """
    details = {
        "status_code": status_code,
        "is_retryable": is_retryable, 
        "retry_after": retry_after,
        "provider": provider,
        "queue_id": queue_id,
        **additional_context,
    }
    
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_cj_assessment_processing_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    batch_id: Optional[str] = None,
    essay_ids: Optional[list[str]] = None,
    processing_stage: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ Assessment batch processing error.
    
    Use this for internal CJ assessment workflow processing errors that require
    batch context, essay collection information, and processing stage details.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        batch_id: Optional batch ID being processed
        essay_ids: Optional list of essay IDs involved in the error
        processing_stage: Optional processing stage where error occurred
        **additional_context: Additional error context details
    """
    details = {
        "batch_id": batch_id,
        "essay_ids": essay_ids,
        "processing_stage": processing_stage,
        **additional_context,
    }
    
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.PROCESSING_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_cj_queue_operation_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    queue_id: Optional[str] = None,
    queue_operation: Optional[str] = None,
    status_code: Optional[int] = None,
    is_retryable: bool = False,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ Assessment queue operation error.
    
    Use this for LLM Provider Service queue status and result operations
    that require queue-specific context and retry logic.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        queue_id: Optional queue ID involved in the operation
        queue_operation: Optional queue operation that failed (e.g., "status_check", "result_retrieval")
        status_code: Optional HTTP status code from queue service
        is_retryable: Whether this error should trigger retry logic
        **additional_context: Additional error context details
    """
    details = {
        "queue_id": queue_id,
        "queue_operation": queue_operation,
        "status_code": status_code,
        "is_retryable": is_retryable,
        **additional_context,
    }
    
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)