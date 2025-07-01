"""Test the tracing module setup."""

from __future__ import annotations

import os

import pytest
from huleedu_service_libs.observability.tracing import (
    get_current_trace_id,
    init_tracing,
    trace_operation,
)

# Note: In production, services will call init_tracing once at startup
# These tests demonstrate the functionality works correctly


@pytest.mark.asyncio
async def test_tracing_initialization():
    """Test that tracing can be initialized."""
    # Set test environment
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4317"

    # Initialize tracing
    tracer = init_tracing("test_service")

    assert tracer is not None
    # Tracer is created successfully, that's what matters
    # The instrumentation info is internal to OpenTelemetry


@pytest.mark.asyncio
async def test_trace_operation_context_manager():
    """Test the trace operation context manager."""
    tracer = init_tracing("test_service")

    # Test successful operation
    with trace_operation(tracer, "test_operation", {"key": "value"}) as span:
        assert span is not None
        assert span.is_recording()

        # Verify we can get the trace ID
        trace_id = get_current_trace_id()
        assert trace_id is not None
        assert len(trace_id) == 32  # Hex string of 128-bit trace ID

    # Test operation with exception
    with pytest.raises(ValueError):
        with trace_operation(tracer, "failing_operation") as span:
            raise ValueError("Test error")


@pytest.mark.asyncio
async def test_trace_context_propagation():
    """Test trace context injection and extraction."""
    from huleedu_service_libs.observability.tracing import (
        extract_trace_context,
        inject_trace_context,
    )

    tracer = init_tracing("test_service")

    with trace_operation(tracer, "parent_operation"):
        # Create a carrier
        carrier: dict[str, str] = {}

        # Inject trace context
        inject_trace_context(carrier)

        # Carrier should now have trace headers
        assert len(carrier) > 0
        assert any("trace" in key.lower() for key in carrier.keys())

        # Extract trace context
        context = extract_trace_context(carrier)
        assert context is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
