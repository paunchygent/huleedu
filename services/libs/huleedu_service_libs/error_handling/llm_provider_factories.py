"""Factory functions for LLM Provider Service specific errors."""

from typing import Any, NoReturn, Optional
from uuid import UUID

from common_core.error_enums import ErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError


def raise_llm_provider_service_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an LLM provider service error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.LLM_PROVIDER_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_llm_provider_error(
    service: str,
    operation: str,
    provider_name: str,
    message: str,
    correlation_id: UUID,
    status_code: Optional[int] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an LLM provider error."""
    details = {"provider_name": provider_name, **additional_context}
    if status_code is not None:
        details["status_code"] = status_code

    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_llm_model_not_found(
    service: str,
    operation: str,
    provider_name: str,
    model_name: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an LLM model not found error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        message=f"Model '{model_name}' not found for provider '{provider_name}'",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "provider_name": provider_name,
            "model_name": model_name,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_llm_response_validation_error(
    service: str,
    operation: str,
    provider_name: str,
    validation_error: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an LLM response validation error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.PARSING_ERROR,
        message=f"LLM response validation failed: {validation_error}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "provider_name": provider_name,
            "validation_error": validation_error,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_llm_queue_full_error(
    service: str,
    operation: str,
    queue_size: int,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an LLM queue full error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.REQUEST_QUEUED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"queue_size": queue_size, **additional_context},
    )
    raise HuleEduError(error_detail)
