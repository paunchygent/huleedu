"""
Utilities for formatting error details for structured logging.
"""

from __future__ import annotations

from typing import Any

from common_core.models.error_models import ErrorDetail


def format_error_for_logging(error_detail: ErrorDetail) -> dict[str, Any]:
    """
    Convert an ErrorDetail instance to a flat dictionary for structured logging.

    This function takes the canonical error data object and transforms it into
    a format suitable for ingestion by logging systems like Logstash or Datadog.

    Args:
        error_detail: The error data object to format.

    Returns:
        A flat dictionary with prefixed keys.
    """
    context = {
        "error.code": error_detail.error_code.value,
        "error.message": error_detail.message,
        "error.service": error_detail.service,
        "error.operation": error_detail.operation,
        "error.timestamp": error_detail.timestamp.isoformat(),
        "correlation_id": str(error_detail.correlation_id),
    }

    if error_detail.trace_id:
        context["trace.id"] = error_detail.trace_id
    if error_detail.span_id:
        context["span.id"] = error_detail.span_id

    for key, value in error_detail.details.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            context[f"error.details.{key}"] = value
        else:
            context[f"error.details.{key}"] = str(value)

    return context
