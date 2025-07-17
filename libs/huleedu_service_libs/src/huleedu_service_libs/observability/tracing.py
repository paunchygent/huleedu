"""Distributed tracing utilities for HuleEdu services."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract, inject, set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def init_tracing(service_name: str) -> trace.Tracer:
    """Initialize Jaeger tracing for a service.

    Args:
        service_name: Name of the service for tracing

    Returns:
        Configured tracer instance
    """
    # Create resource with service info
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
            "service.namespace": "huleedu",
        }
    )

    # Configure OTLP exporter
    # Jaeger now supports OTLP natively on port 4317
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    exporter = OTLPSpanExporter(
        endpoint=otlp_endpoint,
        insecure=True,  # For local development
    )

    # Set up tracer provider
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Set up W3C Trace Context propagator for distributed tracing
    # This ensures trace context is properly propagated across service boundaries
    set_global_textmap(TraceContextTextMapPropagator())

    return trace.get_tracer(service_name)


def get_tracer(service_name: str) -> trace.Tracer:
    """Get a tracer for the service without reinitializing the provider.

    Args:
        service_name: Name of the service for tracing

    Returns:
        Tracer instance
    """
    return trace.get_tracer(service_name)


@contextmanager
def trace_operation(
    tracer: trace.Tracer, operation_name: str, attributes: Optional[Dict[str, Any]] = None
):
    """Context manager for tracing operations with automatic error handling.

    Args:
        tracer: The tracer instance
        operation_name: Name of the operation being traced
        attributes: Optional attributes to add to the span

    Yields:
        The current span
    """
    with tracer.start_as_current_span(operation_name) as span:
        if attributes:
            for key, value in attributes.items():
                # Convert values to string for safety
                span.set_attribute(key, str(value) if value is not None else "")

        # Add correlation ID if available in Quart context
        try:
            from quart import g, has_request_context

            if has_request_context() and hasattr(g, "correlation_id"):
                span.set_attribute("correlation_id", str(g.correlation_id))
        except ImportError:
            # Quart not available, skip correlation ID
            pass

        try:
            yield span
        except Exception as e:
            # Record exception details
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            raise


def get_current_trace_id() -> Optional[str]:
    """Get the current trace ID if available.

    Returns:
        Hex string of trace ID or None if no active trace
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        context = span.get_span_context()
        if context.is_valid:
            return format(context.trace_id, "032x")
    return None


def inject_trace_context(carrier: Dict[str, Any]) -> None:
    """Inject current trace context into a carrier (e.g., event metadata).

    Args:
        carrier: Dictionary to inject trace context into
    """
    inject(carrier)


def extract_trace_context(carrier: Dict[str, Any]) -> Any:
    """Extract trace context from a carrier.

    Args:
        carrier: Dictionary containing trace context

    Returns:
        Extracted context
    """
    return extract(carrier)


@contextmanager
def use_trace_context(carrier: Dict[str, Any]):
    """Extract and use trace context from a carrier as the current context.

    This context manager extracts trace context and makes it the current context
    for the duration of the block, allowing child spans to be created.

    Args:
        carrier: Dictionary containing trace context

    Yields:
        The extracted context
    """
    # Extract the context from the carrier
    ctx = extract(carrier)

    # Use the extracted context
    from opentelemetry import context as otel_context

    token = otel_context.attach(ctx)
    try:
        yield ctx
    finally:
        otel_context.detach(token)


def get_current_span() -> Optional[trace.Span]:
    """Get the current active span.

    Returns:
        Current span or None if no active span
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        return span
    return None


def add_event_to_span(event_name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add an event to the current span.

    Args:
        event_name: Name of the event
        attributes: Optional attributes for the event
    """
    span = get_current_span()
    if span:
        span.add_event(event_name, attributes=attributes or {})
