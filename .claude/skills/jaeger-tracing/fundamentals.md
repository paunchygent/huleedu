# Jaeger Tracing Fundamentals

**Responsibility**: Context7 novel patterns + non-obvious OpenTelemetry gotchas only

**Prerequisites**: Assumes knowledge of basic tracing concepts (spans, traces, context). For complete API docs, use Context7 `/open-telemetry/opentelemetry-python`.

---

## 1. Async Context Propagation Gotchas

### Asyncio vs Threading Behavior

**Surprising**: Context propagation differs fundamentally between asyncio and threading.

**Asyncio** (automatic propagation via context vars):
```python
async def parent():
    with tracer.start_as_current_span("parent"):
        # Child automatically inherits parent span context
        await child()

async def child():
    # No need to pass parent span - automatically available!
    with tracer.start_as_current_span("child"):
        await process()
```

**Threading** (requires manual activation):
```python
def parent():
    with tracer.start_as_current_span("parent") as span:
        # MUST pass span to child thread explicitly
        thread = Thread(target=child, args=(span,))
        thread.start()

def child(parent_span):
    # MUST manually activate span context
    with tracer.scope_manager.activate(parent_span, False):  # False = don't finish on exit
        with tracer.start_as_current_span("child"):
            process()
```

**Why**: Asyncio uses `contextvars` (task-local), threading uses thread-local storage (requires manual management).

**HuleEdu Impact**: Kafka consumers (asyncio) propagate automatically, but any threading-based code (rare in HuleEdu) requires manual activation.

---

## 2. Context Token Management

### Token Lifecycle (Critical Ordering)

**Gotcha**: Token detach must be in **reverse order** of attach or context gets corrupted.

**Pattern** (from HuleEdu TraceContextManagerImpl):
```python
# Extract context from carrier (e.g., Kafka metadata)
extracted_ctx = propagator.extract(carrier)

# Attach context (returns token for cleanup)
context_token = otel_context.attach(extracted_ctx)

# Attach span to context (returns second token)
span = tracer.start_span("operation")
span_token = otel_context.attach(trace.set_span_in_context(span))

try:
    yield span  # Execute operation
finally:
    # CRITICAL: Detach in REVERSE order!
    otel_context.detach(span_token)    # Span first
    otel_context.detach(context_token)  # Context second
    span.end()
```

**Why Reverse Order**: Context forms a stack. Detaching out of order leaves orphaned contexts → memory leaks and context pollution.

**Symptom of Wrong Order**: Spans appear under wrong parents, correlation IDs mismatch in logs.

---

## 3. Baggage vs Tags vs Events

### Three Distinct Propagation Mechanisms

**Context7 Insight**: These have fundamentally different scopes and propagation behaviors.

| Feature | Scope | Propagated to Children? | Use Case | Cardinality Risk |
|---------|-------|-------------------------|----------|------------------|
| **Attributes/Tags** | Span-local | ❌ No | Span metadata | Low |
| **Baggage** | Global (trace-wide) | ✅ Yes (all descendants!) | Cross-service correlation | **HIGH** |
| **Events** | Span-local | ❌ No | Debug markers with timestamps | Low |

**Attributes** (span metadata):
```python
span.set_attribute("http.method", "POST")
span.set_attribute("http.status_code", 200)
# NOT propagated to child spans
```

**Baggage** (cross-service propagation):
```python
# Set baggage (propagates to ALL children across services!)
from opentelemetry.baggage import set_baggage
ctx = set_baggage("user_id", "12345")  # DANGEROUS: high cardinality!
```

**Events** (debugging markers):
```python
span.add_event("cache_miss", {"key": cache_key})
span.add_event("retry_attempt", {"attempt": 2, "delay_ms": 500})
# Timestamped, appear in Jaeger UI timeline
```

**Cardinality Gotcha**: Baggage propagates to **every descendant span** across service boundaries. Setting high-cardinality values (user IDs, request IDs) creates exponential trace size growth.

**HuleEdu Decision**: Use baggage **only** for correlation IDs (bounded cardinality). Use attributes for everything else.

---

## 4. Sampling Strategy Edge Cases

### TraceIdRatioBased Implementation Detail

**Context7 Insight**: Sampling uses **lower 64 bits** of trace ID, not full 128 bits.

```python
# From OpenTelemetry source
TRACE_ID_LIMIT = (1 << 64) - 1

def should_sample(self, trace_id: int, ...) -> SamplingResult:
    # Only checks lower 64 bits!
    if trace_id & self.TRACE_ID_LIMIT < self.bound:
        return Decision.RECORD_AND_SAMPLE
    return Decision.DROP
```

**Implication**: Trace ID generation matters. If IDs are sequential or patterned in lower bits, sampling may be biased.

**Determinism**: Same trace ID always produces same sampling decision (consistent across services).

**Parent Sampling Override**: If parent span is sampled, child is always sampled (regardless of child's sampling probability).

---

## 5. Context Pollution Symptoms

### Token Leak Debugging

**Symptom**: Spans appear under wrong parents, correlation IDs mismatch between logs and traces.

**Cause**: Context token not detached (usually in exception path).

**Debug Pattern**:
```python
# Check current context
from opentelemetry import trace
current_span = trace.get_current_span()
print(f"Current span: {current_span.name}")  # Should match expected parent

# Inspect context stack (internal API, debugging only)
import opentelemetry.context as otel_context
print(f"Context tokens: {otel_context._CONTEXT_STORAGE}")
```

**Fix**: Always use `try/finally` for token detach:
```python
token = otel_context.attach(ctx)
try:
    # Work
    pass
finally:
    otel_context.detach(token)  # Guaranteed cleanup
```

---

## 6. Span Events vs Attributes

### When to Use Each

**Attributes** (metadata about entire span):
- Describe span characteristics (http.method, db.statement)
- Set once at span start or end
- Indexed in Jaeger for search
- Example: `span.set_attribute("llm.model", "gpt-4")`

**Events** (point-in-time markers):
- Record state changes or debugging markers **during** span execution
- Timestamped automatically
- Appear in Jaeger timeline
- Can include attributes specific to that event
- Example: `span.add_event("cache_miss", {"key": "user:123"})`

**HuleEdu Pattern**: Use events for debugging (retry attempts, cache misses, validation failures). Use attributes for span-level metadata.

---

## 7. CompositePropagator Ordering

### Propagator Override Behavior

**Context7 Insight**: Later propagators in composite can **overwrite** keys set by earlier propagators.

```python
from opentelemetry.propagators.composite import CompositePropagator

composite = CompositePropagator([
    W3CTraceContextPropagator(),      # Sets traceparent header
    B3Propagator(),                    # Could overwrite with X-B3-* headers
])
```

**Implication**: Order matters if propagators use same carrier keys.

**HuleEdu Decision**: Use W3C Trace Context exclusively (no composite needed), avoiding override issues.

---

## 8. Cross-References

- **HuleEdu Patterns**: [huleedu-patterns.md](huleedu-patterns.md) - Service setup, naming conventions
- **Async Examples**: [examples/async-propagation.md](examples/async-propagation.md) - Queue/Kafka patterns
- **Advanced Patterns**: [examples/advanced-instrumentation.md](examples/advanced-instrumentation.md) - Custom attributes, events
- **Troubleshooting**: [examples/troubleshooting.md](examples/troubleshooting.md) - Debugging missing spans
- **Context7**: For complete OpenTelemetry API, use `/open-telemetry/opentelemetry-python`

---

**LoC**: 150
