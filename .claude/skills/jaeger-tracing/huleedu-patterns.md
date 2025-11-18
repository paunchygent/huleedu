# HuleEdu Jaeger Tracing Patterns

**Responsibility**: HuleEdu codebase tracing conventions only (not generic OpenTelemetry patterns)

**Prerequisites**: See [fundamentals.md](fundamentals.md) for OpenTelemetry gotchas.

---

## 1. Service Initialization

### Standard Pattern

**Location**: `services/<service>/app.py`

```python
from huleedu_service_libs.observability import init_tracing
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware
)

app = Quart(__name__)

# Initialize tracer (returns configured tracer instance)
app.tracer = init_tracing("service_name")

# Setup automatic HTTP instrumentation
setup_tracing_middleware(app, app.tracer)
```

**What `init_tracing` Does**:
- Configures OpenTelemetry SDK with OTLP exporter
- Sets service.name and service.namespace attributes
- Configures W3C Trace Context propagator
- Sets up Jaeger endpoint (localhost:4317 in development)

**Middleware Behavior**:
- Creates span for each HTTP request
- Propagates trace context from `traceparent` header
- Records request duration, status code, method, path
- Handles exceptions (records in span)

---

## 2. Span Naming Conventions

### HuleEdu Standard Patterns

**API Requests**:
```python
# Format: api.{operation}
span_name = "api.submit_request"
span_name = "api.get_status"
span_name = "api.update_batch"
```

**Provider Calls**:
```python
# Format: llm_provider.{provider}.call
span_name = "llm_provider.openai.call"
span_name = "llm_provider.anthropic.call"
```

**HTTP Middleware** (automatic):
```python
# Format: {METHOD} {path}
"POST /api/batches"
"GET /api/batches/:batch_id"
"PUT /api/essays/:id"
```

**Queue Processing**:
```python
span_name = "queue_processing"  # With context_restored=True attribute
```

**Kafka Event Handling**:
```python
# Format: {event_type}
span_name = "spell_check_requested"
span_name = "essay_submitted"
```

---

## 3. Attribute Standards

### Required Attributes (Always Set)

**Service Attributes** (set by `init_tracing`):
```python
"service.name": "llm_provider_service"
"service.namespace": "huleedu"
"service.version": "1.0.0"  # Optional
```

**Correlation ID** (set by `trace_operation` decorator):
```python
"correlation_id": str(correlation_id)  # UUID as string
```

### Domain-Specific Attributes

**HTTP Requests** (set by middleware):
```python
"http.method": "POST"
"http.url": "/api/batches"
"http.status_code": 200
"http.response_time_ms": 45.2
```

**LLM Provider Calls**:
```python
"llm.provider": "openai"
"llm.model": "gpt-4"
"llm.prompt_tokens": 150
"llm.completion_tokens": 75
"llm.total_cost_dollars": 0.0045
```

**Database Queries**:
```python
"db.system": "postgresql"
"db.operation": "select"  # select, insert, update, delete
"db.table": "essays"
```

**Queue Processing**:
```python
"queue.type": "redis"
"queue.request_id": request_id
"context_restored": True  # Indicates trace context was restored
```

---

## 4. Trace Context Propagation

### Kafka Events

**Publisher** (inject trace context into metadata):
```python
from huleedu_service_libs.observability.tracing import inject_trace_context

envelope = EventEnvelope(
    event_type="spell_check_requested",
    payload=payload,
    correlation_id=correlation_id,
    metadata={}  # Empty dict to populate
)

# Inject current trace context into metadata
inject_trace_context(envelope.metadata)

await kafka_producer.send(topic, envelope)
```

**Consumer** (extract and restore trace context):
```python
from huleedu_service_libs.observability.tracing import extract_trace_context

async def handle_event(envelope: EventEnvelope):
    # Extract trace context from metadata
    ctx = extract_trace_context(envelope.metadata or {})

    # Start span with restored context
    with tracer.start_as_current_span(
        envelope.event_type,
        context=ctx,
        attributes={"correlation_id": str(envelope.correlation_id)}
    ):
        await process_event(envelope)
```

### Redis Queues (TraceContextManagerImpl Pattern)

**Enqueue** (capture trace context):
```python
from huleedu_service_libs.observability.tracing import capture_trace_context_for_queue

# In API handler (span active)
trace_context = capture_trace_context_for_queue()

queued_request = QueuedRequest(
    request_id=request_id,
    data=data,
    trace_context=trace_context  # Serialized trace context
)

await redis.enqueue(queue_key, queued_request)
```

**Dequeue** (restore trace context):
```python
from huleedu_service_libs.observability.tracing import (
    restore_trace_context_for_queue_processing
)

# In background worker
queued_request = await redis.dequeue(queue_key)

with restore_trace_context_for_queue_processing(
    queued_request.trace_context,
    queued_request.request_id
) as span:
    # Span is now linked to original API request!
    span.set_attribute("context_restored", True)
    result = await process_request(queued_request)
```

### HTTP (Automatic via Middleware)

Trace context automatically propagated via `traceparent` header (W3C Trace Context standard).

**Outgoing Requests** (manual injection if not using instrumented client):
```python
import httpx
from opentelemetry.propagate import inject

headers = {}
inject(headers)  # Injects traceparent header

response = await httpx.get(url, headers=headers)
```

---

## 5. Correlation ID Integration

### trace_operation Decorator

**Pattern** (automatic correlation ID injection):
```python
from huleedu_service_libs.observability.tracing import trace_operation

@trace_operation("api.submit_request")
async def submit_request(correlation_id: UUID, data: dict):
    # Span automatically created with:
    # - name: "api.submit_request"
    # - attribute: "correlation_id": str(correlation_id)
    # - exception handling (span.record_exception on error)

    result = await process_data(data)
    return result
```

**What `trace_operation` Does**:
1. Creates span with given name
2. Adds `correlation_id` attribute
3. Records exceptions automatically
4. Ends span on function exit
5. Propagates correlation_id to child spans (via context)

---

## 6. Error Handling

### Exception Recording

**Pattern**:
```python
from opentelemetry import trace

with tracer.start_as_current_span("operation") as span:
    try:
        result = await risky_operation()
    except Exception as e:
        # Record exception in span
        span.record_exception(e)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        raise  # Re-raise after recording
```

**What Gets Recorded**:
- Exception type (exception.type)
- Exception message (exception.message)
- Stack trace (exception.stacktrace)
- Span status set to ERROR

**Jaeger UI**: Exception details appear in span tags and events.

---

## 7. TraceContextManagerImpl Pattern

### Queue Processing with Unbroken Trace Chains

**Use Case**: Preserve trace continuity across Redis queue boundaries.

**Implementation** (from `huleedu_service_libs`):
```python
class TraceContextManagerImpl:
    """Manages trace context capture and restoration for queue processing."""

    def capture_trace_context_for_queue(self) -> dict[str, Any]:
        """Serialize current trace context for queue storage."""
        carrier = {}
        propagator.inject(carrier)  # Injects traceparent, tracestate

        return {
            "traceparent": carrier.get("traceparent"),
            "tracestate": carrier.get("tracestate"),
            "correlation_id": get_correlation_id()
        }

    @contextmanager
    def restore_trace_context_for_queue_processing(
        self,
        trace_context: dict[str, Any],
        request_id: str
    ):
        """Restore trace context and create linked span."""
        # Extract parent context from serialized data
        extracted_ctx = propagator.extract(trace_context)

        # Attach to current context
        context_token = otel_context.attach(extracted_ctx)

        # Create span linked to original request
        span = tracer.start_span(
            "queue_processing",
            context=extracted_ctx,
            attributes={
                "queue.request_id": request_id,
                "context_restored": True
            }
        )
        span_token = otel_context.attach(trace.set_span_in_context(span))

        try:
            yield span
        finally:
            span.end()
            otel_context.detach(span_token)
            otel_context.detach(context_token)
```

**Result**: Unbroken span chain from API request → Queue → Processing in Jaeger UI.

---

## 8. Cross-References

- **Fundamentals**: [fundamentals.md](fundamentals.md) - Async propagation gotchas, token management
- **Async Examples**: [examples/async-propagation.md](examples/async-propagation.md) - Queue/Kafka patterns
- **Advanced Patterns**: [examples/advanced-instrumentation.md](examples/advanced-instrumentation.md) - Custom attributes, events
- **Troubleshooting**: [examples/troubleshooting.md](examples/troubleshooting.md) - Debugging missing spans
- **Observability Rules**: `.claude/rules/071.1-service-observability-core-patterns.md`

---

**LoC**: 180
