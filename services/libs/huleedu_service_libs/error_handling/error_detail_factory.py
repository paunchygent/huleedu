"""
Factory for creating ErrorDetail instances with automatic context capture.
"""

import traceback
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from opentelemetry import trace

from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail


def create_error_detail_with_context(
    error_code: ErrorCode,
    message: str,
    service: str,
    operation: str,
    correlation_id: Optional[UUID] = None,
    details: Optional[dict[str, Any]] = None,
    capture_stack: bool = True,
) -> ErrorDetail:
    """
    Create an ErrorDetail with automatic context capture.

    This function automatically:
    - Captures stack trace (if capture_stack=True)
    - Extracts OpenTelemetry trace/span IDs
    - Sets timestamp
    - Generates correlation_id if not provided

    Args:
        error_code: The error code from the ErrorCode enum
        message: Human-readable error message
        service: The service where the error occurred
        operation: The operation being performed when the error occurred
        correlation_id: Optional correlation ID for request tracking
        details: Optional additional error details
        capture_stack: Whether to capture the stack trace

    Returns:
        A fully populated ErrorDetail instance
    """
    # Generate correlation_id if not provided
    if correlation_id is None:
        correlation_id = uuid4()

    # Capture stack trace if requested
    stack_trace = None
    if capture_stack:
        stack_trace = traceback.format_exc()
        # If no exception is being handled, capture current stack
        if stack_trace == "NoneType: None\n":
            stack_trace = "".join(traceback.format_stack()[:-1])  # Exclude this frame

    # Extract OpenTelemetry trace information
    trace_id = None
    span_id = None
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_context = current_span.get_span_context()
        if span_context.is_valid:
            trace_id = format(span_context.trace_id, "032x")
            span_id = format(span_context.span_id, "016x")

    return ErrorDetail(
        error_code=error_code,
        message=message,
        correlation_id=correlation_id,
        timestamp=datetime.now(timezone.utc),
        service=service,
        operation=operation,
        details=details or {},
        stack_trace=stack_trace,
        trace_id=trace_id,
        span_id=span_id,
    )
