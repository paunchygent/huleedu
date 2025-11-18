# Troubleshooting Jaeger Traces

**Responsibility**: Common issues, debugging patterns, Jaeger UI queries

**Prerequisites**: See [../fundamentals.md](../fundamentals.md) for context pollution symptoms.

---

## 1. Missing Spans in Jaeger UI

### Symptom: Trace Not Appearing

**Common Causes**:

1. **Sampling Disabled**:
   ```python
   # Check: Is service configured with sampler?
   # In init_tracing, should see:
   AlwaysOnSampler()  # Development
   # or
   TraceIdRatioBased(0.1)  # Production (10% sampling)
   ```

2. **OTLP Exporter Not Configured**:
   ```python
   # Check: Is OTLP endpoint reachable?
   # Environment variable should be set:
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
   ```

3. **Span Not Ended**:
   ```python
   # WRONG: Span never ends (won't export)
   span = tracer.start_span("operation")
   # ... forgot span.end()

   # CORRECT: Use context manager
   with tracer.start_as_current_span("operation"):
       # Span automatically ended on exit
       pass
   ```

**Debug**: Check service logs for OTLP export errors:
```
grep "OTLP" logs/service.log
```

---

## 2. Broken Trace Chains

### Symptom: Child Spans Not Linked to Parent

**Cause 1**: Context not propagated across async boundary.

**Fix**: See [async-propagation.md](async-propagation.md) for queue/Kafka patterns.

**Cause 2**: Token not attached/detached correctly.

**Debug Pattern**:
```python
from opentelemetry import trace

# Before starting child operation
current_span = trace.get_current_span()
print(f"Current span: {current_span.get_span_context().span_id}")

# Should NOT be invalid span
if not current_span.is_recording():
    print("WARNING: No active span in context!")
```

**Cause 3**: Threading without manual activation (see [fundamentals.md](../fundamentals.md)).

---

## 3. Duplicate Spans

### Symptom: Same Operation Appears Twice in Trace

**Cause**: Middleware + manual instrumentation creating overlapping spans.

**Example**:
```python
# WRONG: Middleware already creates HTTP span
@app.route("/api/process")
async def process():
    with tracer.start_as_current_span("POST /api/process"):  # Duplicate!
        return await process_data()

# CORRECT: Let middleware handle HTTP span
@app.route("/api/process")
async def process():
    # Create child span for business logic only
    with tracer.start_as_current_span("business.process_data"):
        return await process_data()
```

---

## 4. High Cardinality Attributes

### Symptom: Jaeger UI Slow, Large Trace Sizes

**Cause**: High-cardinality values in attributes (user IDs, request IDs).

**Anti-Pattern**:
```python
# BAD: Unique value per request
span.set_attribute("request_id", str(uuid4()))  # Millions of unique values
span.set_attribute("user_id", user_id)  # Thousands of users
```

**HuleEdu Pattern**:
```python
# GOOD: Use correlation_id (bounded cardinality via sampling)
span.set_attribute("correlation_id", str(correlation_id))

# GOOD: Use baggage sparingly (if needed across services)
# But prefer correlation_id in logs instead
```

**Rule**: Keep attribute value set bounded (< 1000 unique values per attribute).

---

## 5. Common Jaeger UI Queries

### Find Expensive Operations

**Query**: `maxDuration > 1s`

**Use Case**: Find slow operations across all services.

---

### Find Failed Requests

**Query**: `error=true`

**Use Case**: Locate traces with exceptions.

---

### Find LLM Calls by Model

**Query**: `llm.model="gpt-4"`

**Use Case**: Analyze model-specific performance.

---

### Find High-Cost LLM Calls

**Query**: `llm.total_cost_dollars > 0.10`

**Use Case**: Budget tracking, cost optimization.

---

### Find Queue Processing with Restored Context

**Query**: `context_restored=true`

**Use Case**: Verify queue tracing working correctly.

---

### Find Traces by Correlation ID

**Query**: `correlation_id="550e8400-e29b-41d4-a716-446655440000"`

**Use Case**: Follow specific request across services.

---

## 6. Context Pollution Debugging

### Symptom: Spans Under Wrong Parent

**Cause**: Token leak (see [fundamentals.md](../fundamentals.md)).

**Debug**:
```python
import opentelemetry.context as otel_context

# Check current context stack
def debug_context():
    current_span = trace.get_current_span()
    print(f"Current span: {current_span.name}")
    print(f"Span ID: {current_span.get_span_context().span_id}")
    print(f"Trace ID: {current_span.get_span_context().trace_id}")

    # Should match expected parent
```

**Fix**: Ensure token detach in `finally` block:
```python
token = otel_context.attach(ctx)
try:
    # Work
    pass
finally:
    otel_context.detach(token)  # Guaranteed cleanup
```

---

## 7. Missing Attributes

### Symptom: Expected Attributes Not in Jaeger

**Cause 1**: Attribute set after span ended.

```python
# WRONG: Span already ended
span = tracer.start_span("operation")
span.end()
span.set_attribute("key", "value")  # Too late!

# CORRECT: Set before ending
span = tracer.start_span("operation")
span.set_attribute("key", "value")
span.end()
```

**Cause 2**: Attribute value is `None` (silently dropped).

```python
# WRONG: None values not recorded
span.set_attribute("optional_field", None)  # Dropped!

# CORRECT: Check for None first
if value is not None:
    span.set_attribute("optional_field", value)
```

---

## 8. Jaeger UI Navigation Tips

### View Trace Timeline

**Click**: Trace → Timeline view

**Shows**: Waterfall of spans with durations, reveals sequential vs parallel operations.

---

### Compare Traces

**Select**: Multiple traces → Compare

**Use Case**: Compare fast vs slow requests to identify bottlenecks.

---

### Deep Link to Trace

**Pattern**: `http://localhost:16686/trace/{trace_id}`

**Use Case**: Share specific trace in issue reports, link from logs.

---

## 9. Cross-References

- **Fundamentals**: [../fundamentals.md](../fundamentals.md) - Context pollution, token management
- **HuleEdu Patterns**: [../huleedu-patterns.md](../huleedu-patterns.md) - Attribute standards
- **Async Propagation**: [async-propagation.md](async-propagation.md) - Fixing broken chains
- **Advanced Instrumentation**: [advanced-instrumentation.md](advanced-instrumentation.md) - Custom attributes

---

**LoC**: 80
