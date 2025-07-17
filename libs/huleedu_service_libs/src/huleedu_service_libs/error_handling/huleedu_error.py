"""
HuleEdu platform exception that wraps the canonical ErrorDetail model.

This module provides the standard platform exception for error propagation
using the exception-based error handling pattern.
"""

from typing import Any

from common_core.models.error_models import ErrorDetail
from opentelemetry import trace


class HuleEduError(Exception):
    """
    The standard platform exception. It wraps the canonical ErrorDetail model
    and integrates with the observability stack.

    This exception should be raised by all service functions to signal
    business or operational failures, following the exception-based
    error handling pattern.
    """

    def __init__(self, error_detail: ErrorDetail) -> None:
        """
        Initialize HuleEduError with an ErrorDetail instance.

        Args:
            error_detail: The ErrorDetail instance containing all error information
        """
        super().__init__(error_detail.message)
        self.error_detail = error_detail

        # Auto-record to OpenTelemetry span
        self._record_to_span()

    @property
    def correlation_id(self) -> str:
        """Convenient access to correlation ID."""
        return str(self.error_detail.correlation_id)

    @property
    def error_code(self) -> str:
        """Convenient access to error code."""
        # ErrorCode is a str enum, so we can return it directly
        error_code: str = self.error_detail.error_code.value
        return error_code

    @property
    def service(self) -> str:
        """Convenient access to service name."""
        service: str = self.error_detail.service
        return service

    @property
    def operation(self) -> str:
        """Convenient access to operation name."""
        operation: str = self.error_detail.operation
        return operation

    def _record_to_span(self) -> None:
        """Record this error to the current OpenTelemetry span."""
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            # Record the exception
            current_span.record_exception(self)

            # Set error status on span
            current_span.set_status(trace.Status(trace.StatusCode.ERROR, self.error_detail.message))

            # Add error attributes
            current_span.set_attribute("error", True)
            current_span.set_attribute("error.code", self.error_detail.error_code.value)
            current_span.set_attribute("error.message", self.error_detail.message)
            current_span.set_attribute("error.service", self.error_detail.service)
            current_span.set_attribute("error.operation", self.error_detail.operation)
            current_span.set_attribute("correlation_id", str(self.error_detail.correlation_id))

            # Add details as span attributes
            for key, value in self.error_detail.details.items():
                if isinstance(value, (str, int, float, bool)):
                    current_span.set_attribute(f"error.details.{key}", value)
                else:
                    current_span.set_attribute(f"error.details.{key}", str(value))

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the error to a dictionary for serialization.

        Returns:
            Dictionary representation of the error
        """
        return {
            "error": str(self),
            "error_detail": self.error_detail.model_dump(),
        }

    def add_detail(self, key: str, value: Any) -> "HuleEduError":
        """
        Create a new HuleEduError with additional detail.

        Since ErrorDetail is immutable, this creates a new instance.

        Args:
            key: The detail key to add
            value: The detail value to add

        Returns:
            New HuleEduError instance with the added detail
        """
        # Create new details dict with the additional key
        new_details = {**self.error_detail.details, key: value}

        # Create new ErrorDetail with updated details
        new_error_detail = ErrorDetail(
            error_code=self.error_detail.error_code,
            message=self.error_detail.message,
            correlation_id=self.error_detail.correlation_id,
            timestamp=self.error_detail.timestamp,
            service=self.error_detail.service,
            operation=self.error_detail.operation,
            details=new_details,
            stack_trace=self.error_detail.stack_trace,
            trace_id=self.error_detail.trace_id,
            span_id=self.error_detail.span_id,
        )

        return HuleEduError(new_error_detail)

    def __str__(self) -> str:
        """String representation of the error."""
        return f"[{self.error_detail.error_code.value}] {self.error_detail.message}"

    def __repr__(self) -> str:
        """Developer-friendly representation of the error."""
        return (
            f"HuleEduError("
            f"code={self.error_detail.error_code.value}, "
            f"message={self.error_detail.message!r}, "
            f"service={self.error_detail.service}, "
            f"operation={self.error_detail.operation}, "
            f"correlation_id={self.correlation_id}"
            f")"
        )
