# Advanced Instrumentation Examples

**Responsibility**: Custom attributes, span events, domain-specific patterns (LLM, DB, business logic)

**Prerequisites**: See [../huleedu-patterns.md](../huleedu-patterns.md) for attribute standards.

---

## 1. LLM Provider Call Instrumentation

### Pattern: Rich Metadata for Cost Tracking

```python
from huleedu_service_libs.observability.tracing import trace_operation

@trace_operation("llm_provider.openai.call")
async def call_openai_api(
    model: str,
    prompt: str,
    correlation_id: UUID
) -> dict:
    """Call OpenAI API with comprehensive tracing."""
    span = trace.get_current_span()

    # Pre-request attributes
    span.set_attribute("llm.provider", "openai")
    span.set_attribute("llm.model", model)
    span.set_attribute("llm.prompt_length", len(prompt))

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )

        # Post-response attributes (for cost analysis)
        span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
        span.set_attribute("llm.completion_tokens", response.usage.completion_tokens)
        span.set_attribute("llm.total_tokens", response.usage.total_tokens)

        # Calculate cost (pricing from config)
        cost = calculate_cost(model, response.usage)
        span.set_attribute("llm.total_cost_dollars", cost)

        span.set_attribute("llm.response_length", len(response.choices[0].message.content))

        return response

    except Exception as e:
        span.record_exception(e)
        span.set_attribute("llm.error_type", type(e).__name__)
        raise
```

**Jaeger Query**: Find expensive LLM calls:
```
llm.total_cost_dollars > 0.10
```

---

## 2. Span Events for Debugging

### Pattern: Time-Stamped Markers vs Attributes

**When to Use Events**:
- Cache hits/misses (point-in-time)
- Retry attempts (multiple events per span)
- Validation failures (with context)
- State transitions (with before/after values)

**Example**:
```python
async def process_essay_with_retries(essay_id: UUID, max_retries: int = 3):
    """Process essay with retry logic and debug events."""
    span = trace.get_current_span()

    for attempt in range(1, max_retries + 1):
        try:
            # Check cache first
            cached_result = await cache.get(f"essay:{essay_id}")
            if cached_result:
                span.add_event("cache_hit", {
                    "essay_id": str(essay_id),
                    "cache_key": f"essay:{essay_id}"
                })
                return cached_result

            span.add_event("cache_miss", {"essay_id": str(essay_id)})

            # Process essay
            result = await process_essay(essay_id)

            # Cache result
            await cache.set(f"essay:{essay_id}", result, ttl=3600)
            span.add_event("cache_updated", {"ttl_seconds": 3600})

            return result

        except RetryableError as e:
            span.add_event("retry_attempt", {
                "attempt": attempt,
                "max_retries": max_retries,
                "error": str(e),
                "delay_seconds": 2 ** attempt  # Exponential backoff
            })

            if attempt == max_retries:
                raise

            await asyncio.sleep(2 ** attempt)
```

**Jaeger UI**: Events appear in span timeline with timestamps, revealing retry patterns.

---

## 3. Multi-Span Operations

### Pattern: Child Spans for Sub-Operations

```python
async def process_batch_submission(batch_id: UUID):
    """Process batch with child spans for each phase."""

    # Parent span (from decorator)
    with tracer.start_as_current_span("batch.validate") as validate_span:
        validate_span.set_attribute("batch_id", str(batch_id))
        validation_result = await validate_batch(batch_id)
        validate_span.set_attribute("validation.errors_count", len(validation_result.errors))

    # Second child span
    with tracer.start_as_current_span("batch.transform") as transform_span:
        transform_span.set_attribute("batch_id", str(batch_id))
        transformed_data = await transform_batch_data(batch_id)
        transform_span.set_attribute("transform.items_count", len(transformed_data))

    # Third child span
    with tracer.start_as_current_span("batch.store") as store_span:
        store_span.set_attribute("batch_id", str(batch_id))
        await store_batch_results(batch_id, transformed_data)
        store_span.set_attribute("store.bytes_written", len(json.dumps(transformed_data)))
```

**Jaeger UI**: Three sequential child spans showing phase durations independently.

---

## 4. Database Query Instrumentation

### Pattern: Operation Type + Duration Tracking

```python
async def execute_complex_query(session: AsyncSession, essay_id: UUID):
    """Execute DB query with detailed tracing."""

    with tracer.start_as_current_span("db.query") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", "select")
        span.set_attribute("db.table", "essays")
        span.set_attribute("essay_id", str(essay_id))

        start_time = time.time()

        try:
            result = await session.execute(
                select(Essay)
                .where(Essay.id == essay_id)
                .options(joinedload(Essay.submissions))
            )
            essay = result.scalar_one_or_none()

            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("db.duration_ms", duration_ms)
            span.set_attribute("db.rows_returned", 1 if essay else 0)

            if essay:
                span.set_attribute("db.joins_count", 1)  # joinedload(submissions)

            return essay

        except Exception as e:
            span.record_exception(e)
            span.set_attribute("db.error_type", type(e).__name__)
            raise
```

---

## 5. Business Logic Metrics

### Pattern: Domain Events + Outcomes

```python
async def run_cj_comparison(left_essay_id: UUID, right_essay_id: UUID):
    """Run CJ assessment comparison with outcome tracking."""

    with tracer.start_as_current_span("cj_assessment.compare") as span:
        span.set_attribute("comparison.left_essay_id", str(left_essay_id))
        span.set_attribute("comparison.right_essay_id", str(right_essay_id))

        # Run LLM comparison
        result = await llm_compare(left_essay_id, right_essay_id)

        # Record outcome (for business analytics)
        span.set_attribute("comparison.outcome", result.outcome)  # left_preferred, right_preferred, tie
        span.set_attribute("comparison.confidence", result.confidence)
        span.set_attribute("comparison.llm_duration_seconds", result.duration)

        # Event for outcome decision point
        span.add_event("outcome_determined", {
            "outcome": result.outcome,
            "confidence": result.confidence,
            "reasoning_length": len(result.reasoning)
        })

        return result
```

**Jaeger Query**: Find low-confidence comparisons:
```
comparison.confidence < 0.7
```

---

## 6. Custom Context Injection

### Pattern: Explicit Context for Non-Standard Propagation

```python
from opentelemetry.propagate import inject, extract

async def call_external_service_with_trace(url: str, data: dict):
    """Call external service with manual trace context injection."""

    # Prepare carrier (HTTP headers)
    headers = {
        "Content-Type": "application/json",
        "X-Correlation-ID": get_correlation_id()
    }

    # Inject trace context into headers
    inject(headers)  # Adds traceparent, tracestate headers

    with tracer.start_as_current_span("external.http_call") as span:
        span.set_attribute("http.url", url)
        span.set_attribute("http.method", "POST")

        try:
            response = await httpx.post(url, json=data, headers=headers)

            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("http.response_size_bytes", len(response.content))

            return response.json()

        except Exception as e:
            span.record_exception(e)
            raise
```

---

## 7. Cross-References

- **Fundamentals**: [../fundamentals.md](../fundamentals.md) - Span events vs attributes, baggage gotchas
- **HuleEdu Patterns**: [../huleedu-patterns.md](../huleedu-patterns.md) - Attribute standards, naming
- **Async Propagation**: [async-propagation.md](async-propagation.md) - Queue/Kafka context preservation
- **Troubleshooting**: [troubleshooting.md](troubleshooting.md) - Debugging missing attributes

---

**LoC**: 90
