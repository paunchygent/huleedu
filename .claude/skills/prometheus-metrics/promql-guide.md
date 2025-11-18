# PromQL Guide

**Responsibility**: Context7 PromQL surprises + HuleEdu query patterns (non-obvious content only)

**Prerequisites**: Assumes knowledge of basic PromQL syntax (`rate()`, `sum()`, `avg()`, label selectors). For basics, see [fundamentals.md](./fundamentals.md).

---

## 1. Critical histogram_quantile() Gotchas

### Context7 Insight: Extrapolation Behavior

**Surprising**: `histogram_quantile()` **extrapolates** when requested quantile falls outside bucket boundaries.

```promql
# Can produce wildly inaccurate P95 if > largest bucket
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Always include +Inf bucket to bound extrapolation
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**HuleEdu Pattern** (LLM Provider Service):
```promql
# Custom buckets prevent extrapolation beyond 300s
histogram_quantile(0.95,
  sum(rate(llm_provider_response_duration_seconds_bucket{
    provider="openai"
  }[5m])) by (le)
)
# Buckets: (0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)
```

### Context7 Insight: Aggregation Requires `by (le)`

**Critical**: When aggregating histograms across instances, **must** preserve `le` label:

```promql
# WRONG: Loses bucket boundaries
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])))

# CORRECT: Preserves le (bucket upper bounds)
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**HuleEdu Pattern** (Database Deep Dive dashboard):
```promql
# P95 query latency across all instances
histogram_quantile(0.95,
  sum(rate(${service}_database_query_duration_seconds_bucket{
    operation="select"
  }[5m])) by (le)
)
```

### Context7 Insight: Cannot Average Pre-Calculated Quantiles

**Anti-Pattern**: Averaging Summary quantiles is **statistically meaningless**:

```promql
# WRONG: Invalid math
avg(http_request_duration_seconds{quantile="0.95"})

# CORRECT: Use Histogram + histogram_quantile
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**Why This Matters**: HuleEdu uses Histograms (not Summaries) for cross-instance aggregation.

---

## 2. rate() Edge Cases

### Context7 Insight: Requires Minimum 2 Samples

**Gotcha**: `rate()` returns `NaN` if < 2 samples in time window:

```promql
# Returns NaN for newly started services (< 2 scrapes)
rate(http_requests_total[1m])

# Mitigation: Use fallback
rate(http_requests_total[5m]) or vector(0)
```

**HuleEdu Pattern** (Database Health Overview):
```promql
# Fallback to 0 if service just started
sum(rate(batch_orchestrator_service_database_errors_total[1m]) or vector(0))
  + sum(rate(essay_lifecycle_service_database_errors_total[1m]) or vector(0))
  + sum(rate(cj_assessment_service_database_errors_total[1m]) or vector(0))
```

### rate() on Histogram _sum and_count

**Pattern for Average Calculation**:

```promql
# Calculate average request duration
rate(http_request_duration_seconds_sum[5m])
/
rate(http_request_duration_seconds_count[5m])
```

**HuleEdu Pattern** (Database Deep Dive):
```promql
# Average query duration
rate(${service}_database_query_duration_seconds_sum[5m])
/
rate(${service}_database_query_duration_seconds_count[5m])
```

---

## 3. HuleEdu-Specific Query Patterns

### Pattern 1: Bucket-Based SLO Calculation

**Context7 Insight**: Calculate % requests within target bucket:

```promql
# % of requests within 0.5s (HuleEdu SLO target)
sum(rate(http_request_duration_seconds_bucket{le="0.5"}[5m])) by (service)
/
sum(rate(http_request_duration_seconds_count[5m])) by (service)
```

**HuleEdu Alert** (95% within 500ms):
```promql
# Alert if < 95% meet SLO
(
  sum(rate(http_request_duration_seconds_bucket{le="0.5"}[5m])) by (service)
  /
  sum(rate(http_request_duration_seconds_count[5m])) by (service)
) < 0.95
```

### Pattern 2: Multi-Service Aggregation with Fallback

**HuleEdu Pattern**: `or vector(0)` for services with no recent data:

```promql
# Total database errors across all services
sum(rate(batch_orchestrator_service_database_errors_total[1m]) or vector(0))
  + sum(rate(essay_lifecycle_service_database_errors_total[1m]) or vector(0))
  + sum(rate(cj_assessment_service_database_errors_total[1m]) or vector(0))
  + sum(rate(class_management_service_database_errors_total[1m]) or vector(0))
  + sum(rate(result_aggregator_service_database_errors_total[1m]) or vector(0))
  + sum(rate(spellchecker_service_database_errors_total[1m]) or vector(0))
```

### Pattern 3: Division by Zero Prevention

**HuleEdu Pattern**:

```promql
# Prevent NaN from division by zero
rate(metric_sum[5m]) / (rate(metric_count[5m]) or vector(1))
```

**Transaction Success Rate** (Database Deep Dive):
```promql
rate(${service}_database_transaction_duration_seconds_count{result="success"}[5m])
/
(rate(${service}_database_transaction_duration_seconds_count[5m]) or vector(1))
* 100
```

### Pattern 4: High-Cardinality Anti-Pattern

**Anti-Pattern**:
```promql
# Aggregates across all unique correlation_ids (high cardinality)
sum by (correlation_id) (rate(http_requests_total[5m]))
```

**HuleEdu Pattern**:
```promql
# Aggregate by service only (low cardinality)
sum by (service) (rate(http_requests_total[5m]))
```

---

## 4. Debugging Empty Query Results

**HuleEdu Debug Pattern**:

```promql
# Step 1: Verify metric exists
{__name__=~"llm_provider.*"}

# Step 2: Check specific metric
llm_provider_requests_total

# Step 3: Add label filters incrementally
llm_provider_requests_total{provider="openai"}
llm_provider_requests_total{provider="openai", model="gpt-4"}
```

**Common Causes**:
1. Label name/value mismatch (check `/metrics` endpoint)
2. Time range too narrow (`rate()` needs ≥2 samples)
3. Metric not yet scraped (wait 15s scrape interval)

---

## 5. Native vs Classic Histograms

**HuleEdu Decision**: Stick with classic histograms until Prometheus 2.40+ widely adopted.

**Classic Histograms** (current):
```promql
# Requires explicit 'by (le)'
histogram_quantile(0.9,
  sum by (job, le) (
    rate(http_request_duration_seconds_bucket[10m])
  )
)
```

**Native Histograms** (future):
```promql
# Simpler: no 'le' label required
histogram_quantile(0.9,
  sum by (job) (
    rate(http_request_duration_seconds[10m])
  )
)
```

---

## 6. Cross-References

- **Basics**: [fundamentals.md](./fundamentals.md) - Metric types, naming, labels, Python API
- **HTTP Examples**: [examples/http-and-kafka.md](./examples/http-and-kafka.md) - HTTP/Kafka patterns
- **LLM Examples**: [examples/llm-and-batch.md](./examples/llm-and-batch.md) - LLM/batch patterns
- **Database Examples**: [examples/database-and-business.md](./examples/database-and-business.md) - DB/business patterns

---

**LoC**: 200
