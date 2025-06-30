"""Tracing middleware for Quart applications."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Status, StatusCode
from quart import Request, Response, g, request

if TYPE_CHECKING:
    from quart import Quart


class TracingMiddleware:
    """Middleware to add distributed tracing to Quart applications."""

    def __init__(self, tracer: trace.Tracer):
        """Initialize tracing middleware.

        Args:
            tracer: OpenTelemetry tracer instance
        """
        self.tracer = tracer

    async def before_request(self, req: Request) -> None:
        """Start a trace span for the incoming request.

        Args:
            req: The incoming request
        """
        # Extract trace context from headers
        context = extract(req.headers)

        # Start span
        span_name = f"{req.method} {req.path}"
        span = self.tracer.start_span(span_name, context=context, kind=trace.SpanKind.SERVER)

        # Set span attributes
        span.set_attribute("http.method", req.method)
        span.set_attribute("http.scheme", req.scheme)
        span.set_attribute("http.host", req.host)
        span.set_attribute("http.target", req.path)
        span.set_attribute("http.url", str(req.url))
        span.set_attribute("http.user_agent", req.headers.get("User-Agent", ""))

        # Add query parameters if present
        if req.query_string:
            span.set_attribute("http.query", req.query_string.decode("utf-8"))

        # Add correlation ID
        correlation_id = req.headers.get("X-Correlation-ID")
        if not correlation_id and hasattr(g, "request_id"):
            correlation_id = g.request_id

        if correlation_id:
            span.set_attribute("correlation_id", correlation_id)
            g.correlation_id = correlation_id

        # Store span and start time in context
        g.current_span = span
        g.trace_start_time = time.time()

    async def after_request(self, response: Response) -> Response:
        """Complete the trace span and inject trace context.

        Args:
            response: The response object

        Returns:
            Modified response with trace headers
        """
        if hasattr(g, "current_span"):
            span = g.current_span

            # Set response attributes
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("http.response_content_length", response.content_length or 0)

            # Set status based on HTTP code
            if response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
            else:
                span.set_status(Status(StatusCode.OK))

            # Add response time
            if hasattr(g, "trace_start_time"):
                duration = time.time() - g.trace_start_time
                span.set_attribute("http.response_time_ms", round(duration * 1000, 2))

            # Inject trace context into response headers
            inject(response.headers)

            # Add trace ID to response headers for debugging
            context = span.get_span_context()
            if context.is_valid:
                response.headers["X-Trace-ID"] = format(context.trace_id, "032x")
                response.headers["X-Span-ID"] = format(context.span_id, "016x")

            # End span
            span.end()

        return response


def setup_tracing_middleware(app: Quart, tracer: trace.Tracer) -> None:
    """Set up tracing middleware for a Quart app.

    Args:
        app: The Quart application
        tracer: OpenTelemetry tracer instance
    """
    middleware = TracingMiddleware(tracer)

    @app.before_request
    async def before_request() -> None:
        """Before request hook."""
        await middleware.before_request(request)

    @app.after_request
    async def after_request(response: Response) -> Response:
        """After request hook."""
        return await middleware.after_request(response)
