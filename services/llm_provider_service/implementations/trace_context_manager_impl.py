"""Trace context manager for preserving OpenTelemetry spans across async boundaries.

Addresses the specific challenge in event-driven architectures where trace context
can be lost across:
- Kafka event publishing/consuming
- Redis queue operations
- Async provider calls
- Request/response cycles that span multiple services

Key implementation: Captures trace context when requests are queued and restores
it when processing begins, maintaining unbroken span chains.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, ContextManager, Dict, Generator
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability.tracing import (
    extract_trace_context,
    get_current_trace_id,
    get_tracer,
    inject_trace_context,
)
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span

logger = create_service_logger("llm_provider_service.trace_context_manager")


class TraceContextManagerImpl:
    """Manages trace context preservation across async operation boundaries."""

    def __init__(self) -> None:
        self.tracer = get_tracer("llm_provider_service")

    def start_api_request_span(self, operation: str, correlation_id: UUID) -> ContextManager[Span]:
        """Start root span for API request. Returns context manager for span."""
        return self.tracer.start_as_current_span(
            f"api.{operation}",
            attributes={
                "service.name": "llm_provider_service",
                "correlation_id": str(correlation_id),
                "operation.type": "api_request",
            },
        )

    def start_provider_call_span(
        self, provider: str, model: str, correlation_id: UUID
    ) -> ContextManager[Span]:
        """Start child span for LLM provider call. Maintains parent relationship."""
        return self.tracer.start_as_current_span(
            f"llm_provider.{provider}.call",
            attributes={
                "service.name": "llm_provider_service",
                "llm.provider": provider,
                "llm.model": model,
                "correlation_id": str(correlation_id),
                "operation.type": "provider_call",
            },
        )

    def capture_trace_context_for_queue(self) -> Dict[str, Any]:
        """Capture current trace context to store with queued request.

        CRITICAL for maintaining unbroken spans when requests are queued.
        The captured context allows queue processors to restore the original
        trace context and create proper child spans.

        Returns:
            Dictionary containing serialized trace context
        """
        context: Dict[str, Any] = {}
        try:
            # Inject W3C trace context headers
            inject_trace_context(context)

            # Add metadata for debugging
            trace_id = get_current_trace_id()
            if trace_id:
                context["_huledu_trace_id"] = trace_id

            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                span_context = current_span.get_span_context()
                context["_huledu_span_id"] = format(span_context.span_id, "016x")

                # Add event to current span indicating context was captured
                current_span.add_event(
                    "trace_context_captured_for_queue",
                    {
                        "has_traceparent": "traceparent" in context,
                        "context_keys": list(context.keys()),
                    },
                )

        except Exception as e:
            logger.debug(f"Failed to capture trace context for queue: {e}")

        return context

    @contextmanager
    def restore_trace_context_for_queue_processing(
        self, trace_context: Dict[str, Any], queue_id: UUID
    ) -> Generator[Span, None, None]:
        """Restore trace context for queue processing.

        Creates a child span under the original request's trace, maintaining
        the unbroken span chain even though processing happens asynchronously.

        Args:
            trace_context: Context captured when request was queued
            queue_id: Queue request identifier

        Yields:
            Active span for queue processing
        """
        if not trace_context:
            # No context available - start orphaned span
            with self.tracer.start_as_current_span(
                "queue_processing.orphaned",
                attributes={
                    "service.name": "llm_provider_service",
                    "queue_id": str(queue_id),
                    "context_restored": False,
                },
            ) as span:
                span.add_event("no_trace_context_available")
                yield span
            return

        context_token = None
        try:
            # Extract and attach the trace context
            extracted_ctx = extract_trace_context(trace_context)
            context_token = otel_context.attach(extracted_ctx)

            # Start child span for queue processing under restored context
            with self.tracer.start_as_current_span(
                "queue_processing",
                attributes={
                    "service.name": "llm_provider_service",
                    "queue_id": str(queue_id),
                    "context_restored": True,
                    "original_trace_id": trace_context.get("_huledu_trace_id", "unknown"),
                },
            ) as span:
                span.add_event(
                    "trace_context_restored",
                    {
                        "queue_id": str(queue_id),
                        "current_trace_id": get_current_trace_id() or "unknown",
                    },
                )
                yield span

        except Exception as e:
            logger.warning(f"Failed to restore trace context for queue {queue_id}: {e}")
            # CRITICAL FIX: Don't yield again in except block - this violates 
            # generator protocol and causes "generator didn't stop after throw()" error
            # Just re-raise the exception to let the caller handle it properly
            raise
        finally:
            if context_token:
                otel_context.detach(context_token)

    def inject_trace_context_into_event(self, event_metadata: Dict[str, Any]) -> None:
        """Inject current trace context into Kafka event metadata.

        Ensures events published to Kafka carry trace context, allowing
        consuming services to maintain the distributed trace.

        Args:
            event_metadata: Event metadata dictionary to inject context into
        """
        try:
            inject_trace_context(event_metadata)

            # Add event to current span if available
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.add_event(
                    "trace_context_injected_into_event",
                    {
                        "has_traceparent": "traceparent" in event_metadata,
                        "trace_id": get_current_trace_id() or "unknown",
                    },
                )

        except Exception as e:
            logger.debug(f"Failed to inject trace context into event: {e}")

    def add_span_event(self, event_name: str, attributes: Dict[str, Any]) -> None:
        """Add an event to the current active span.

        Args:
            event_name: Name of the event
            attributes: Event attributes
        """
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.add_event(event_name, attributes)

    def set_span_attributes(self, attributes: Dict[str, Any]) -> None:
        """Set attributes on the current active span.

        Args:
            attributes: Attributes to set
        """
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            for key, value in attributes.items():
                current_span.set_attribute(key, str(value) if value is not None else "")

    def mark_span_error(self, error: Exception) -> None:
        """Mark current span as having an error.

        Args:
            error: Exception that occurred
        """
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.record_exception(error)
            current_span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
            current_span.set_attribute("error", True)
            current_span.set_attribute("error.type", type(error).__name__)

    def get_current_trace_id(self) -> str | None:
        """Get current trace ID.

        Returns:
            Current trace ID or None if no active trace
        """
        return get_current_trace_id()

    def get_current_trace_summary(self) -> Dict[str, Any]:
        """Get summary of current trace state for debugging.

        Returns:
            Dictionary with trace state information
        """
        current_span = trace.get_current_span()
        trace_id = get_current_trace_id()

        return {
            "trace_id": trace_id,
            "has_active_span": current_span is not None,
            "span_recording": current_span.is_recording() if current_span else False,
            "span_context_valid": current_span.get_span_context().is_valid
            if current_span
            else False,
        }
