# Async Trace Propagation Examples

**Responsibility**: Context preservation across async boundaries (queues, events, background tasks)

**Prerequisites**: See [fundamentals.md](../fundamentals.md) for async propagation gotchas.

---

## 1. Redis Queue Processing (TraceContextManagerImpl)

### Problem: Trace Context Lost Across Queue

**Scenario**: API handler enqueues request, background worker processes it.

**Without trace context**: Two disconnected traces in Jaeger (API trace stops at enqueue, worker trace is orphaned).

### Solution: Capture + Restore Pattern

**Enqueue** (API handler):
```python
from huleedu_service_libs.observability.tracing import (
    capture_trace_context_for_queue,
    trace_operation
)

@trace_operation("api.submit_request")
async def submit_request(correlation_id: UUID, data: dict):
    """Submit request to processing queue."""

    # Capture current trace context
    trace_context = capture_trace_context_for_queue()

    queued_request = QueuedRequest(
        request_id=str(uuid4()),
        data=data,
        trace_context=trace_context  # Serialized: traceparent, tracestate
    )

    await redis.lpush(queue_key, queued_request.json())
    return {"request_id": queued_request.request_id}
```

**Dequeue** (background worker):
```python
from huleedu_service_libs.observability.tracing import (
    restore_trace_context_for_queue_processing
)

async def process_queue():
    """Background worker processing queue."""
    while True:
        request_json = await redis.brpop(queue_key)
        request = QueuedRequest.parse_raw(request_json)

        # Restore trace context from queue
        with restore_trace_context_for_queue_processing(
            request.trace_context,
            request.request_id
        ) as span:
            span.set_attribute("context_restored", True)

            # Process request (child spans automatically linked!)
            result = await process_request(request.data)

            span.set_attribute("processing.result", "success")
```

**Jaeger View**: Unbroken span chain `api.submit_request` → `queue_processing` → child operations.

---

## 2. Kafka Event Chaining

### Problem: Trace Context Not Propagated Across Services

**Scenario**: Service A publishes event, Service B consumes it.

### Solution: Inject + Extract Pattern

**Publisher** (Service A):
```python
from huleedu_service_libs.observability.tracing import inject_trace_context

async def publish_essay_submitted_event(essay_id: UUID, correlation_id: UUID):
    """Publish event with trace context."""
    envelope = EventEnvelope(
        event_type="essay_submitted",
        payload={"essay_id": str(essay_id)},
        correlation_id=correlation_id,
        metadata={}
    )

    # Inject current trace context into metadata
    inject_trace_context(envelope.metadata)
    # metadata now contains: {"traceparent": "00-...", "tracestate": "..."}

    await kafka_producer.send("essay_events", envelope)
```

**Consumer** (Service B):
```python
from huleedu_service_libs.observability.tracing import extract_trace_context

async def handle_essay_submitted(envelope: EventEnvelope):
    """Handle event with restored trace context."""

    # Extract trace context from metadata
    ctx = extract_trace_context(envelope.metadata or {})

    # Start span with restored context
    with tracer.start_as_current_span(
        envelope.event_type,
        context=ctx,
        attributes={
            "correlation_id": str(envelope.correlation_id),
            "event.source": "essay_lifecycle_service"
        }
    ):
        # Process event (child spans linked to original trace!)
        await run_spell_check(envelope.payload["essay_id"])
```

**Jaeger View**: Trace spans across service boundaries `essay_lifecycle_service` → `spellchecker_service`.

---

## 3. Background Task Context Preservation

### Problem: asyncio.create_task() Loses Context

**Gotcha**: Creating tasks in asyncio automatically propagates context (unlike threading).

**Correct Pattern** (context auto-propagates):
```python
async def api_handler():
    with tracer.start_as_current_span("api.process"):
        # Create background task
        task = asyncio.create_task(background_work())
        # Context automatically propagated to task!
        return {"status": "processing"}

async def background_work():
    # Parent span context automatically available
    with tracer.start_as_current_span("background.process"):
        await long_running_operation()
```

**Wrong Pattern** (manual management not needed):
```python
# DON'T DO THIS - unnecessary in asyncio!
async def api_handler():
    span = trace.get_current_span()
    task = asyncio.create_task(background_work(span))  # No need to pass!
```

---

## 4. Threading Context Activation

### Problem: Threads Don't Auto-Propagate Context

**Gotcha**: Threading requires manual scope activation (see [fundamentals.md](../fundamentals.md)).

**Pattern**:
```python
from threading import Thread

def parent_operation():
    with tracer.start_as_current_span("parent") as span:
        # Must pass span to thread explicitly
        thread = Thread(target=child_operation, args=(span,))
        thread.start()
        thread.join()

def child_operation(parent_span):
    # Must manually activate scope
    with tracer.scope_manager.activate(parent_span, False):  # False = don't finish
        with tracer.start_as_current_span("child"):
            process()
```

**HuleEdu**: Threading rare (asyncio preferred). Use only when required for CPU-bound work.

---

## 5. Cross-References

- **Fundamentals**: [../fundamentals.md](../fundamentals.md) - Async vs threading gotchas, token management
- **HuleEdu Patterns**: [../huleedu-patterns.md](../huleedu-patterns.md) - Service setup, naming conventions
- **Advanced Instrumentation**: [advanced-instrumentation.md](advanced-instrumentation.md) - Custom attributes
- **Troubleshooting**: [troubleshooting.md](troubleshooting.md) - Debugging broken traces

---

**LoC**: 80
