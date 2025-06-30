"""Tracing middleware for FastAPI applications."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from fastapi import Request, Response
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Status, StatusCode

if TYPE_CHECKING:
    from fastapi import FastAPI


class TracingMiddleware:
    """Middleware to add distributed tracing to FastAPI applications."""

    def __init__(self, app: FastAPI, tracer: trace.Tracer):
        """Initialize tracing middleware.

        Args:
            app: FastAPI application instance
            tracer: OpenTelemetry tracer instance
        """
        self.app = app
        self.tracer = tracer

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process the request with tracing.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            The response
        """
        # Extract trace context from headers
        context = extract(dict(request.headers))

        # Start span
        span_name = f"{request.method} {request.url.path}"
        with self.tracer.start_as_current_span(
            span_name, context=context, kind=trace.SpanKind.SERVER
        ) as span:
            # Set span attributes
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.scheme", request.url.scheme)
            span.set_attribute("http.host", request.url.hostname or "")
            span.set_attribute("http.target", request.url.path)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.user_agent", request.headers.get("User-Agent", ""))

            # Add query parameters if present
            if request.url.query:
                span.set_attribute("http.query", request.url.query)

            # Add correlation ID if present
            correlation_id = request.headers.get("X-Correlation-ID")
            if correlation_id:
                span.set_attribute("correlation_id", correlation_id)

            # Store trace context in request state
            request.state.trace_id = format(span.get_span_context().trace_id, "032x")
            request.state.span_id = format(span.get_span_context().span_id, "016x")

            start_time = time.time()

            try:
                # Process the request
                response = await call_next(request)

                # Set response attributes
                span.set_attribute("http.status_code", response.status_code)

                # Set status based on HTTP code
                if response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                else:
                    span.set_status(Status(StatusCode.OK))

                # Add response time
                duration = time.time() - start_time
                span.set_attribute("http.response_time_ms", round(duration * 1000, 2))

                # Inject trace context into response headers
                response_headers = dict(response.headers)
                inject(response_headers)
                
                # Add trace ID to response headers for debugging
                response_headers["X-Trace-ID"] = request.state.trace_id
                response_headers["X-Span-ID"] = request.state.span_id
                
                # Update response headers
                for key, value in response_headers.items():
                    response.headers[key] = value

                return response

            except Exception as e:
                # Record exception
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise


def setup_tracing_middleware(app: FastAPI, tracer: trace.Tracer) -> None:
    """Set up tracing middleware for a FastAPI app.

    Args:
        app: The FastAPI application
        tracer: OpenTelemetry tracer instance
    """
    app.add_middleware(TracingMiddleware, tracer=tracer)