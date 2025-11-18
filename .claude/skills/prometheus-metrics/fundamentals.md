# Prometheus Metrics Fundamentals

**Responsibility**: Context7 surprises + non-obvious gotchas only (assumes Claude already knows Prometheus basics)

**Prerequisites**: This document assumes familiarity with basic Counter/Histogram/Gauge concepts. For complete API documentation, use Context7 `/prometheus/client_python`.

---

## 1. Histogram Gotchas (Context7 Surprises)

### histogram_quantile() Extrapolates Beyond Buckets

**Surprising Behavior**: `histogram_quantile()` **extrapolates** when the requested quantile falls outside bucket boundaries, producing potentially misleading results.

```promql
# Can extrapolate wildly if P95 exceeds largest bucket
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Always include +Inf bucket to bound extrapolation
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**Mitigation**: Design bucket upper bounds to exceed expected P99 values.

### Aggregation Requires `by (le)`

**Critical**: When aggregating histograms across instances, you **must** preserve the `le` label or bucket boundaries are lost:

```promql
# WRONG: Loses bucket boundaries
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])))

# CORRECT: Preserves le (bucket upper bounds)
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

### Cannot Average Pre-Calculated Quantiles

**Anti-Pattern**: Averaging Summary quantiles is **statistically meaningless**:

```promql
# WRONG: Invalid math
avg(http_request_duration_seconds{quantile="0.95"})

# CORRECT: Use Histogram + histogram_quantile
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**HuleEdu Decision**: Use Histograms (not Summaries) for cross-instance aggregation.

---

## 2. rate() Edge Cases (Context7 Surprises)

### Requires Minimum 2 Samples

**Gotcha**: `rate()` returns `NaN` if fewer than 2 samples exist in the time window:

```promql
# Returns NaN for newly started services (< 2 scrapes)
rate(http_requests_total[1m])

# Mitigation: Use fallback
rate(http_requests_total[5m]) or vector(0)
```

**HuleEdu Pattern**: Always use `or vector(0)` for multi-service aggregation to handle services with no recent data.

---

## 3. Custom Histogram Buckets by Use Case

**Context**: Default buckets (0.005 to 10.0) don't fit all distributions.

### LLM API Calls (0.1s to 60s)
```python
buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
```

### Discrete Counts (0 to 100)
```python
# Spell check corrections, items per batch
buckets=(0, 1, 2, 5, 10, 20, 50, 100)
```

### Database Queries (1ms to 5s)
```python
buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
```

### Response Sizes (1KB to 10MB)
```python
buckets=(1024, 10240, 102400, 1048576, 10485760)
```

**Principle**: Design buckets to cover expected range + capture critical thresholds (e.g., SLO targets).

---

## 4. Label Cardinality Gotcha

**Rule**: Keep total label combinations < 10,000 per metric.

**Anti-Pattern**:
```python
# High cardinality: user_id × request_id = infinite combinations
http_requests_total.labels(user_id="12345", request_id="abc-123")
```

**HuleEdu Pattern**:
```python
# Low cardinality: method × endpoint × status = ~50 combinations
http_requests_total.labels(method="POST", endpoint="/api/users", status_code="200")
```

**Critical**: High-cardinality labels (user_id, correlation_id, IP address) belong in logs, not metrics.

---

## 5. Naming Conventions (Edge Cases)

### Always Use Base Units

- `_seconds` (not milliseconds, minutes)
- `_bytes` (not kilobytes, megabytes)
- `_ratio` (0.0 to 1.0, not percentage)
- `_total` (for Counters)

**Rationale**: Prometheus functions expect base units (e.g., `rate()` assumes seconds for time windows).

### HuleEdu Convention: Service Prefix

**Pattern**: `{service}_{metric}_{unit}`

```python
spell_checker_http_requests_total
batch_orchestrator_phase_transition_duration_seconds
```

**Exception**: Business metrics use `huleedu_` prefix:

```python
huleedu_spellcheck_corrections_made
huleedu_llm_cost_dollars_total
```

---

## 6. Python Library Gotchas

### Metric Must Be Defined at Module Level

**Anti-Pattern** (creates new metric on every call):
```python
def process():
    # DON'T: Raises ValueError on second call!
    counter = Counter("operations_total", "desc")
    counter.inc()
```

**HuleEdu Pattern** (module-level singleton):
```python
# metrics.py
operations_total = Counter("operations_total", "desc")

def process():
    operations_total.inc()
```

### Registry Collision Handling in Tests

**Gotcha**: Re-importing metrics in tests causes `ValueError: Duplicated timeseries`.

**HuleEdu Pattern**:
```python
def _get_existing_metrics() -> dict[str, Any]:
    """Recover metrics from REGISTRY if already registered."""
    try:
        return _create_metrics()
    except ValueError:
        # Metric already registered (test re-import scenario)
        return {name: REGISTRY._collector_to_names[...]}
```

### Context Manager for Automatic Timing

```python
with request_duration_seconds.time():
    result = expensive_operation()  # Duration recorded on exit
```

**Novel Pattern**: Combine with correlation ID logging:
```python
with request_duration_seconds.labels(endpoint=endpoint).time():
    logger.info("Processing started", correlation_id=correlation_id)
    result = process()
    logger.info("Processing complete", correlation_id=correlation_id)
```

---

## 7. Cross-References

- **HuleEdu Patterns**: [huleedu-patterns.md](huleedu-patterns.md) - Service setup, naming, middleware
- **PromQL Gotchas**: [promql-guide.md](promql-guide.md) - Query edge cases, HuleEdu patterns
- **Examples**: [examples/](examples/) - Real-world instrumentation snippets
- **Context7**: For complete API docs, use `/prometheus/client_python`

---

**LoC**: 150
