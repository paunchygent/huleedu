"""Quart-specific error handling for HuleEdu services."""

from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.error_handling.quart_handlers import (
    create_error_response,
    extract_correlation_id,
    register_error_handlers,
)

__all__ = [
    "register_error_handlers",
    "create_error_response",
    "extract_correlation_id",
    "CorrelationContext",
    "extract_correlation_context_from_request",
]
