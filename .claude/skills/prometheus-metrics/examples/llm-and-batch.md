# LLM and Batch Processing Examples

**Responsibility**: Novel LLM-specific patterns only (assumes basic Prometheus knowledge)

**Prerequisites**: See [fundamentals.md](../fundamentals.md) and [http-and-kafka.md](./http-and-kafka.md).

---

## 1. Dual-Granularity Histogram Pattern

**HuleEdu Pattern** (Phase 7 sub-500ms optimization):

```python
# Main histogram: Broad LLM response time range
"llm_response_duration_seconds": Histogram(
    "llm_provider_response_duration_seconds",
    "LLM API response time",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
),

# Optimization histogram: Fine-grained sub-500ms tracking
"llm_response_time_percentiles": Histogram(
    "llm_provider_response_time_percentiles",
    "Sub-500ms optimization tracking",
    ["provider", "model", "request_type"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
),
```

**Novel**: Track **same metric twice** with different bucket granularity—broad histogram for general monitoring, fine-grained histogram for optimization targets.

---

## 2. Token Tracking by Type

**HuleEdu Pattern** (token-level cost breakdown):

```python
# Extract from LLM response
prompt_tokens = response["usage"]["prompt_tokens"]
completion_tokens = response["usage"]["completion_tokens"]

# Track separately by token_type label
metrics["llm_tokens_used_total"].labels(
    provider=provider,
    model=model,
    token_type="prompt"
).inc(prompt_tokens)

metrics["llm_tokens_used_total"].labels(
    provider=provider,
    model=model,
    token_type="completion"
).inc(completion_tokens)
```

**Novel**: Separate labels for prompt vs completion tokens enable per-type cost analysis (completion tokens often cost 2–3x prompt tokens).

---

## 3. Cost Tracking in Prometheus

**HuleEdu Pattern** (financial metrics):

```python
# Calculate cost per request
cost = (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate

# Increment cumulative cost counter
metrics["llm_cost_dollars_total"].labels(
    provider=provider,
    model=model
).inc(cost)
```

**PromQL**: Daily cost projection:
```promql
# Project daily spend from 1-hour rate
sum(rate(llm_provider_cost_dollars_total[1h])) * 24
```

**Novel**: Financial metrics in Prometheus (not just operational metrics). Enables cost alerting and budget tracking.

---

## 4. Concurrent Request Tracking

**HuleEdu Pattern** (in-flight LLM requests):

```python
async def execute_llm_request(...):
    """Execute LLM request with concurrent tracking."""
    metrics["llm_concurrent_requests"].labels(provider=provider).inc()
    try:
        response = await call_llm_api(provider, model, prompt)
        return response
    finally:
        metrics["llm_concurrent_requests"].labels(provider=provider).dec()
```

**Novel**: Gauge tracks in-flight operations—increment on start, decrement in `finally` block (ensures decrement even on exception).

---

## 5. Queue Depth Tracking

**HuleEdu Pattern** (queue size monitoring):

```python
async def process_queue_batch(queue: list, metrics: dict) -> None:
    """Process queue batch with depth tracking."""
    metrics["llm_queue_depth"].labels(queue_type="comparison").set(len(queue))
    try:
        # Process items in queue
        for item in queue:
            await process_item(item)
    finally:
        metrics["llm_queue_depth"].set(0)  # Reset after processing
```

**Novel**: Gauge updated at processing boundaries (not continuously) to track current queue size without excessive metric updates.

---

## 6. Queue Wait Time vs Processing Time

**HuleEdu Pattern** (distinguish queue delay from execution):

```python
async def process_queued_item(item: dict, metrics: dict) -> None:
    """Process queued item tracking wait vs processing time separately."""
    processing_start = time.time()

    # Wait time: How long item sat in queue
    wait_time = processing_start - item["timestamp"]
    metrics["llm_queue_wait_time_seconds"].observe(wait_time)

    # Processing time: Actual execution duration
    result = await execute_llm_request(...)
    processing_duration = time.time() - processing_start

    metrics["llm_processing_duration_seconds"].observe(processing_duration)
```

**Novel**: Separate histograms for queue wait time vs processing time—critical for identifying whether delays are from queue backup or slow execution.

---

## 7. Queue Expiry Tracking

**HuleEdu Pattern** (stale request cleanup):

```python
async def expire_stale_requests(queue: list, metrics: dict, max_age_seconds: int) -> None:
    """Remove stale requests and track expiry metrics."""
    now = time.time()

    for item in queue[:]:  # Copy to allow removal during iteration
        age = now - item["timestamp"]

        if age > max_age_seconds:
            # Record expiry
            metrics["llm_queue_expiry_total"].labels(
                reason="timeout"
            ).inc()

            metrics["llm_queue_expiry_age_seconds"].observe(age)

            queue.remove(item)
```

**Novel**: Track both **count** (counter) and **age distribution** (histogram) of expired items—reveals whether timeouts are gradual or sudden spikes.

---

## 8. Serial Bundle Efficiency

**HuleEdu Pattern** (batch size tracking):

```python
# Histogram with custom buckets for batch sizes
"llm_serial_bundle_items_per_call": Histogram(
    "llm_serial_bundle_items_per_call",
    "Items processed per bundled LLM call",
    buckets=(1, 2, 4, 8, 16, 32, 64),  # Powers of 2
)

# Usage:
async def process_serial_bundle(items: list, metrics: dict) -> None:
    """Process bundled items and track efficiency."""
    bundle_size = len(items)
    metrics["llm_serial_bundle_items_per_call"].observe(bundle_size)

    # Process bundle...
```

**Novel**: Custom buckets (powers of 2) for batch sizes reveal bundling efficiency—low values indicate under-utilization, high values indicate good batching.

---

## 9. Circuit Breaker State Encoding

**HuleEdu Pattern** (enum state as gauge):

```python
# Map circuit breaker states to numeric values
state_map = {"closed": 0, "open": 1, "half_open": 2}

# Update gauge on state transition
metrics["circuit_breaker_state"].labels(
    service="llm_provider",
    circuit_name="openai_circuit"
).set(state_map[self.state])
```

**PromQL**: Alert on open state:
```promql
circuit_breaker_state{circuit_name="openai_circuit"} == 1
```

**Novel**: Encode enum states as numeric gauge values (0/1/2) for PromQL queries and alerts.

---

## 10. Cross-References

- **Fundamentals**: [fundamentals.md](../fundamentals.md) - Histogram gotchas, custom buckets
- **HuleEdu Patterns**: [huleedu-patterns.md](../huleedu-patterns.md) - Service setup, naming
- **PromQL**: [promql-guide.md](../promql-guide.md) - Query patterns, edge cases
- **HTTP/Kafka**: [http-and-kafka.md](./http-and-kafka.md) - Basic instrumentation patterns
- **Database**: [database-and-business.md](./database-and-business.md) - DB patterns

---

**LoC**: 150
