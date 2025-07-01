"""
Enhanced error context management for HuleEdu services.

This module provides rich error context for debugging distributed systems,
including trace information, service context, and structured error data.
"""

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from opentelemetry import trace


@dataclass
class ErrorContext:
    """Rich error context for debugging distributed systems."""

    error_type: str
    error_message: str
    service_name: str
    operation: str
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    stack_trace: Optional[str] = None
    context_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "service_name": self.service_name,
            "operation": self.operation,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace,
            "context_data": self.context_data,
        }

    def to_log_context(self) -> Dict[str, Any]:
        """Convert to structured logging context."""
        context = {
            "error.type": self.error_type,
            "error.message": self.error_message,
            "error.service": self.service_name,
            "error.operation": self.operation,
            "error.timestamp": self.timestamp.isoformat(),
        }

        if self.correlation_id:
            context["correlation_id"] = self.correlation_id
        if self.trace_id:
            context["trace.id"] = self.trace_id
        if self.span_id:
            context["span.id"] = self.span_id

        # Flatten context data with prefix
        for key, value in self.context_data.items():
            context[f"error.context.{key}"] = value

        return context

    def add_context(self, key: str, value: Any) -> None:
        """Add additional context data."""
        self.context_data[key] = value

    def set_trace_info(self) -> None:
        """Automatically extract and set trace information from current span."""
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()
            if span_context.is_valid:
                self.trace_id = format(span_context.trace_id, "032x")
                self.span_id = format(span_context.span_id, "016x")

                # Try to get correlation ID from span attributes
                if not self.correlation_id:
                    attributes = getattr(current_span, "_attributes", {})
                    self.correlation_id = str(attributes.get("correlation_id", ""))


class EnhancedError(Exception):
    """Base exception with rich error context."""

    def __init__(self, message: str, context: ErrorContext):
        super().__init__(message)
        self.context = context
        # Automatically set trace info
        self.context.set_trace_info()

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        service_name: str,
        operation: str,
        correlation_id: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> "EnhancedError":
        """Create EnhancedError from an existing exception."""
        error_context = ErrorContext(
            error_type=type(exception).__name__,
            error_message=str(exception),
            service_name=service_name,
            operation=operation,
            correlation_id=correlation_id,
            stack_trace=traceback.format_exc(),
            context_data=context_data or {},
        )

        # Set trace information
        error_context.set_trace_info()

        return cls(str(exception), error_context)

    def record_to_span(self) -> None:
        """Record this error to the current OpenTelemetry span."""
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            # Record the exception
            current_span.record_exception(self)

            # Add error attributes
            current_span.set_attribute("error", True)
            current_span.set_attribute("error.type", self.context.error_type)
            current_span.set_attribute("error.message", self.context.error_message)
            current_span.set_attribute("error.service", self.context.service_name)
            current_span.set_attribute("error.operation", self.context.operation)

            # Add context data as span attributes
            for key, value in self.context.context_data.items():
                if isinstance(value, (str, int, float, bool)):
                    current_span.set_attribute(f"error.context.{key}", value)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the error and its context to a dictionary."""
        return {
            "error": str(self),
            "context": self.context.to_dict(),
        }


def capture_error_context(
    service_name: str,
    operation: str,
    correlation_id: str,
) -> Callable:
    """
    Decorator to automatically capture error context.

    Usage:
        @capture_error_context("my_service", "process_request")
        async def my_function():
            ...
    """

    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, EnhancedError):
                    # Already enhanced, just re-raise
                    e.record_to_span()
                    raise
                else:
                    # Enhance the error
                    enhanced = EnhancedError.from_exception(
                        e,
                        service_name=service_name,
                        operation=operation,
                        correlation_id=correlation_id,
                    )
                    enhanced.record_to_span()
                    raise enhanced from e

        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, EnhancedError):
                    # Already enhanced, just re-raise
                    e.record_to_span()
                    raise
                else:
                    # Enhance the error
                    enhanced = EnhancedError.from_exception(
                        e,
                        service_name=service_name,
                        operation=operation,
                        correlation_id=correlation_id,
                    )
                    enhanced.record_to_span()
                    raise enhanced from e

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator