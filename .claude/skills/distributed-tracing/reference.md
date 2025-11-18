# Distributed Tracing Specialist - Detailed Reference

Comprehensive guide for OpenTelemetry distributed tracing with Jaeger in HuleEdu.

## Table of Contents

1. [Tracing Architecture](#tracing-architecture)
2. [Tracer Initialization](#tracer-initialization)
3. [Span Creation and Management](#span-creation-and-management)
4. [Trace Context Propagation](#trace-context-propagation)
5. [Middleware Integration](#middleware-integration)
6. [Correlation with Logs and Metrics](#correlation-with-logs-and-metrics)
7. [Jaeger UI Usage](#jaeger-ui-usage)
8. [Context7 Integration](#context7-integration)
9. [Best Practices](#best-practices)

---

## Tracing Architecture

### Stack Components

**Jaeger Service**:
- **UI Port**: 16686 (<http://localhost:16686>)
- **OTLP gRPC Port**: 4317 (collector endpoint)
- **Purpose**: Distributed tracing backend
- **Protocol**: OpenTelemetry Protocol (OTLP)

**OpenTelemetry SDK**:
- **Library**: `opentelemetry-sdk`
- **Exporter**: `opentelemetry-exporter-otlp-proto-grpc`
- **Propagation**: W3C Trace Context

---

## Tracer Initialization

### Initialization Function

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/observability/tracing.py`

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

def init_tracing(service_name: str) -> trace.Tracer:
    """Initialize Jaeger tracing for a service."""

    # Define service resource
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        "service.namespace": "huleedu",
    })

    # Configure OTLP exporter
    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        insecure=True,
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Set W3C Trace Context propagation
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    set_global_textmap(TraceContextTextMapPropagator())

    # Return tracer for service
    return trace.get_tracer(service_name)
```

**Usage**:
```python
# In app.py
tracer = init_tracing("spellchecker_service")
```

---

## Span Creation and Management

### Manual Span Creation

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def process_essay(essay_id: str) -> None:
    # Create span manually
    with tracer.start_as_current_span("process_essay") as span:
        # Add attributes
        span.set_attribute("essay_id", essay_id)
        span.set_attribute("service", "spellchecker_service")

        # Do work (span timed automatically)
        result = await spell_checker.check(essay)

        # Add result attributes
        span.set_attribute("corrections_count", len(result.corrections))
```

---

### Using `trace_operation` Helper

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/observability/tracing.py`

```python
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

@contextmanager
def trace_operation(
    tracer: trace.Tracer,
    operation_name: str,
    attributes: Optional[Dict[str, Any]] = None
):
    """Context manager for tracing with automatic error handling."""

    with tracer.start_as_current_span(operation_name) as span:
        # Set attributes
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))

        # Auto-add correlation ID from Quart context
        if has_request_context() and hasattr(g, "correlation_id"):
            span.set_attribute("correlation_id", str(g.correlation_id))

        try:
            yield span
        except Exception as e:
            # Record exception in span
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
```

**Usage**:
```python
from huleedu_service_libs.observability.tracing import trace_operation

async def score_essay(essay_id: str) -> AssessmentResult:
    with trace_operation(
        tracer,
        "score_essay",
        attributes={
            "essay_id": essay_id,
            "operation": "assessment"
        }
    ) as span:
        result = await llm_service.score(essay)
        span.set_attribute("total_score", result.total_score)
        return result
```

---

### Nested Spans

```python
async def process_batch(batch_id: str) -> None:
    # Parent span
    with trace_operation(tracer, "process_batch", {"batch_id": batch_id}) as parent_span:

        essays = await fetch_essays(batch_id)
        parent_span.set_attribute("essay_count", len(essays))

        # Child spans
        for essay in essays:
            with trace_operation(tracer, "process_essay", {"essay_id": essay.id}):
                await process_essay(essay)
```

**Result**: Jaeger shows parent-child relationship in trace timeline.

---

## Trace Context Propagation

### HTTP Request Propagation

**Automatic** (via middleware):
```python
# Request headers automatically include trace context:
# traceparent: 00-<trace-id>-<span-id>-01
# tracestate: ...
```

**Manual Extraction** (if needed):
```python
from opentelemetry.propagate import extract

# Extract trace context from headers
ctx = extract(request.headers)

# Start span with extracted context
with tracer.start_as_current_span("operation", context=ctx) as span:
    ...
```

---

### Kafka Event Propagation

**Inject Trace Context into Event Metadata**:
```python
from huleedu_service_libs.observability.tracing import inject_trace_context

async def publish_event(event_data: Any) -> None:
    # Create event envelope
    envelope = EventEnvelope(
        correlation_id=g.correlation_context.uuid,
        event_type="SpellCheckRequestedEvent",
        source_service="essay_lifecycle_service",
        data=event_data,
        metadata={},  # Empty metadata
    )

    # Inject trace context into metadata
    inject_trace_context(envelope.metadata)

    # Publish event
    await kafka_producer.send(envelope)
```

**Extract Trace Context from Event Metadata**:
```python
from huleedu_service_libs.observability.tracing import extract_trace_context

async def process_event(envelope: EventEnvelope) -> None:
    # Extract trace context from metadata
    ctx = extract_trace_context(envelope.metadata)

    # Start span with extracted context (continues the trace)
    with tracer.start_as_current_span("process_event", context=ctx) as span:
        span.set_attribute("event_type", envelope.event_type)
        span.set_attribute("correlation_id", str(envelope.correlation_id))

        # Process event
        await event_processor.process(envelope.data)
```

**Result**: Traces span across HTTP → Kafka → Service boundaries.

---

## Middleware Integration

### Quart Tracing Middleware

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/middleware/frameworks/quart_middleware.py`

```python
def setup_tracing_middleware(app: Quart, tracer: trace.Tracer) -> None:
    """Setup OpenTelemetry tracing for Quart app."""

    @app.before_request
    async def start_trace():
        # Extract parent trace context from headers
        ctx = extract(request.headers)

        # Start span for request
        span = tracer.start_span(
            f"{request.method} {request.path}",
            context=ctx,
        )

        # Set HTTP attributes
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))
        span.set_attribute("http.target", request.path)

        # Add correlation ID if available
        if hasattr(g, "correlation_id"):
            span.set_attribute("correlation_id", str(g.correlation_id))

        # Store span in context
        g.trace_span = span

    @app.after_request
    async def end_trace(response):
        if hasattr(g, "trace_span"):
            span = g.trace_span

            # Set response attributes
            span.set_attribute("http.status_code", response.status_code)

            # Set status
            if response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR))
            else:
                span.set_status(Status(StatusCode.OK))

            # Inject trace context into response headers
            inject(response.headers)

            # Add trace ID to response header
            span.set_attribute("trace_id", format(span.get_span_context().trace_id, "032x"))
            response.headers["X-Trace-ID"] = format(span.get_span_context().trace_id, "032x")
            response.headers["X-Span-ID"] = format(span.get_span_context().span_id, "016x")

            # End span
            span.end()

        return response
```

**Usage**:
```python
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware
)

@app.before_serving
async def startup():
    setup_tracing_middleware(app, tracer)
```

---

## Correlation with Logs and Metrics

### Trace ID in Logs

```python
from huleedu_service_libs.observability.tracing import get_current_trace_id

logger.info(
    "Processing request",
    trace_id=get_current_trace_id(),  # Add trace ID to logs
    correlation_id=correlation_id,
)
```

**Benefit**: Search Loki logs by trace ID, or find trace from log entry.

---

### Span Attributes from Metrics

```python
with trace_operation(tracer, "spell_check") as span:
    result = await spell_checker.check(essay)

    # Record in both metrics and span
    corrections_count = len(result.corrections)

    metrics["spellcheck_corrections_made"].observe(corrections_count)
    span.set_attribute("corrections_count", corrections_count)
```

**Benefit**: Correlate metrics values with specific traces in Jaeger.

---

## Jaeger UI Usage

### Accessing Jaeger

**URL**: <http://localhost:16686>

### Finding Traces

**By Service**:
1. Select service from dropdown (e.g., "spellchecker_service")
2. Click "Find Traces"

**By Operation**:
1. Select service
2. Select operation (e.g., "POST /api/spellcheck")
3. Click "Find Traces"

**By Tags**:
1. Select service
2. Add tags (e.g., `correlation_id=abc-123`)
3. Click "Find Traces"

**By Trace ID**:
1. Enter trace ID in search box
2. Click "Find Traces"

---

### Trace Details

**Timeline View**:
- Shows all spans in chronological order
- Parent-child relationships visible
- Span duration and timing

**Span Details**:
- Operation name
- Attributes (tags)
- Events (e.g., exceptions)
- Duration

**Service Graph**:
- Shows service dependencies
- Visualizes cross-service calls

---

## Context7 Integration

### When to Use Context7

Fetch latest OpenTelemetry/Jaeger documentation when:
- User asks about advanced span features (events, links)
- Need examples of custom propagators
- Troubleshooting trace context issues
- Understanding OpenTelemetry semantic conventions
- New OpenTelemetry features or API changes

### Example Context7 Usage

```python
from context7 import get_library_docs

otel_docs = get_library_docs(
    library_id="/open-telemetry/opentelemetry-python",
    topic="span attributes and events"
)

jaeger_docs = get_library_docs(
    library_id="/jaegertracing/jaeger",
    topic="trace context propagation"
)
```

**Library IDs**:
- OpenTelemetry Python: `/open-telemetry/opentelemetry-python`
- Jaeger: `/jaegertracing/jaeger`

---

## Best Practices

### 1. Initialize Tracing Early

```python
# Good: Initialize at app startup
@app.before_serving
async def startup():
    tracer = init_tracing("my_service")
    setup_tracing_middleware(app, tracer)

# Bad: Late initialization (misses early requests)
@app.route("/api/endpoint")
async def handler():
    tracer = init_tracing("my_service")  # Too late!
```

---

### 2. Use Meaningful Span Names

```python
# Good: Descriptive operation names
with trace_operation(tracer, "score_essay"):
    ...

with trace_operation(tracer, "fetch_from_database"):
    ...

# Bad: Generic names
with trace_operation(tracer, "operation"):
    ...

with trace_operation(tracer, "do_work"):
    ...
```

---

### 3. Add Relevant Attributes

```python
# Good: Rich attributes
with trace_operation(
    tracer,
    "process_batch",
    attributes={
        "batch_id": batch_id,
        "essay_count": len(essays),
        "user_id": user_id,
    }
):
    ...

# Bad: Missing context
with trace_operation(tracer, "process_batch"):
    ...
```

---

### 4. Record Exceptions in Spans

```python
# Good: Automatic exception recording with trace_operation
with trace_operation(tracer, "risky_operation") as span:
    result = await might_fail()  # Exceptions auto-recorded

# Manual exception recording
with tracer.start_as_current_span("operation") as span:
    try:
        result = await might_fail()
    except Exception as e:
        span.record_exception(e)
        span.set_status(Status(StatusCode.ERROR, str(e)))
        raise
```

---

### 5. Propagate Traces Across Boundaries

```python
# HTTP: Automatic with middleware

# Kafka: Manual injection/extraction
# Publisher
inject_trace_context(envelope.metadata)

# Consumer
ctx = extract_trace_context(envelope.metadata)
with tracer.start_as_current_span("process_event", context=ctx):
    ...
```

---

### 6. Use Correlation IDs in Spans

```python
with trace_operation(
    tracer,
    "process_request",
    attributes={"correlation_id": str(correlation_id)}
):
    ...
```

**Benefit**: Search Jaeger by correlation ID tag, correlate with logs.

---

## Related Resources

- **examples.md**: Real-world tracing examples from HuleEdu
- **SKILL.md**: Quick reference and activation criteria
- `/libs/huleedu_service_libs/src/huleedu_service_libs/observability/tracing.py`: Tracing utilities
- **Jaeger UI**: <http://localhost:16686>
