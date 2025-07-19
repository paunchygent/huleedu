"""
Factory functions for creating and raising HuleEduError exceptions.

This module provides standardized factory functions for generic error codes
from the ErrorCode enum. Service-specific error factories are in separate modules.
"""

from typing import Any, NoReturn, Optional
from uuid import UUID

from common_core.error_enums import ErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

# =============================================================================
# Generic Error Code Factories (ErrorCode enum)
# =============================================================================


def raise_unknown_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an unknown error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.UNKNOWN_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_validation_error(
    service: str,
    operation: str,
    field: str,
    message: str,
    correlation_id: UUID,
    value: Optional[Any] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a validation error."""
    details = {"field": field, **additional_context}
    if value is not None:
        details["value"] = value

    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.VALIDATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_resource_not_found(
    service: str,
    operation: str,
    resource_type: str,
    resource_id: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a resource not found error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        message=f"{resource_type} with ID '{resource_id}' not found",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "resource_type": resource_type,
            "resource_id": resource_id,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_configuration_error(
    service: str,
    operation: str,
    config_key: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a configuration error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.CONFIGURATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"config_key": config_key, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_external_service_error(
    service: str,
    operation: str,
    external_service: str,
    message: str,
    correlation_id: UUID,
    status_code: Optional[int] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an external service error."""
    details = {"external_service": external_service, **additional_context}
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


def raise_kafka_publish_error(
    service: str,
    operation: str,
    topic: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a Kafka publish error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"topic": topic, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_content_service_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a content service error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.CONTENT_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_spellcheck_service_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a spellcheck service error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.SPELLCHECK_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_nlp_service_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an NLP service error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.NLP_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_ai_feedback_service_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an AI feedback service error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.AI_FEEDBACK_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_cj_assessment_service_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ assessment service error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.CJ_ASSESSMENT_SERVICE_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_missing_required_field(
    service: str,
    operation: str,
    field_name: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a missing required field error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.MISSING_REQUIRED_FIELD,
        message=f"Required field '{field_name}' is missing",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"field_name": field_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_invalid_configuration(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an invalid configuration error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.INVALID_CONFIGURATION,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_timeout_error(
    service: str,
    operation: str,
    timeout_seconds: float,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a timeout error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.TIMEOUT,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"timeout_seconds": timeout_seconds, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_connection_error(
    service: str,
    operation: str,
    target: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a connection error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.CONNECTION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"target": target, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_service_unavailable(
    service: str,
    operation: str,
    unavailable_service: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a service unavailable error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.SERVICE_UNAVAILABLE,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"unavailable_service": unavailable_service, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_rate_limit_error(
    service: str,
    operation: str,
    limit: int,
    window_seconds: int,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a rate limit error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.RATE_LIMIT,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "limit": limit,
            "window_seconds": window_seconds,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_quota_exceeded(
    service: str,
    operation: str,
    quota_type: str,
    limit: int,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a quota exceeded error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.QUOTA_EXCEEDED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={
            "quota_type": quota_type,
            "limit": limit,
            **additional_context,
        },
    )
    raise HuleEduError(error_detail)


def raise_authentication_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an authentication error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.AUTHENTICATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_authorization_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an authorization error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.AUTHORIZATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_invalid_api_key(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an invalid API key error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.INVALID_API_KEY,
        message="Invalid or missing API key",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_invalid_request(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an invalid request error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.INVALID_REQUEST,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_invalid_response(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an invalid response error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.INVALID_RESPONSE,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_parsing_error(
    service: str,
    operation: str,
    parse_target: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a parsing error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.PARSING_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"parse_target": parse_target, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_circuit_breaker_open(
    service: str,
    operation: str,
    circuit_name: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a circuit breaker open error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.CIRCUIT_BREAKER_OPEN,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"circuit_name": circuit_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_request_queued(
    service: str,
    operation: str,
    queue_name: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a request queued error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.REQUEST_QUEUED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"queue_name": queue_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_processing_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a processing error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.PROCESSING_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_initialization_failed(
    service: str,
    operation: str,
    component: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an initialization failed error."""
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.INITIALIZATION_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"component": component, **additional_context},
    )
    raise HuleEduError(error_detail)
