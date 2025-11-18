# Database and Business Metrics Examples

**Responsibility**: Novel database and business metric patterns only (assumes basic Prometheus knowledge)

**Prerequisites**: See [fundamentals.md](../fundamentals.md) and [http-and-kafka.md](./http-and-kafka.md).

---

## 1. DatabaseMetrics Library Pattern

**HuleEdu Pattern** (centralized DB metrics across all services):

```python
from huleedu_service_libs.database.metrics import DatabaseMetrics

# In service metrics setup
database_metrics = DatabaseMetrics("spell_checker")
metrics = {
    **_create_service_metrics(),
    **database_metrics.get_metrics(),  # Merge DB metrics
}
```

**Provides**:
- `{service}_database_query_duration_seconds` (by operation: select/insert/update/delete)
- `{service}_database_transaction_duration_seconds` (by result: success/error)
- `{service}_database_errors_total` (by error_type)
- Connection pool gauges (size, checked_out, overflow)

**Novel**: Centralized library in `huleedu_service_libs` ensures **consistent DB metrics** across all services with service-prefixed naming.

---

## 2. Query Duration by Operation Type

**HuleEdu Pattern** (categorize queries by SQL operation):

```python
# In DatabaseMetrics class
self.query_duration = Histogram(
    f"{service_name}_database_query_duration_seconds",
    "Database query duration",
    ["operation"],  # select, insert, update, delete
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Usage
metrics["database_query_duration_seconds"].labels(operation="select").observe(duration)
```

**Novel**: `operation` label enables **per-operation analysis** (e.g., "SELECT queries slow, but INSERTs fast").

---

## 3. Transaction Outcome Tracking

**HuleEdu Pattern** (automatic success/failure tracking):

```python
async def tracked_transaction(session: AsyncSession, metrics: dict):
    """Context manager for transaction tracking."""
    start_time = time.time()
    try:
        yield  # Execute transaction
        await session.commit()

        # Record success
        duration = time.time() - start_time
        metrics["database_transaction_duration_seconds"].labels(
            result="success"
        ).observe(duration)

        metrics["database_transactions_total"].labels(
            result="success"
        ).inc()

    except Exception as e:
        await session.rollback()

        # Record failure
        duration = time.time() - start_time
        metrics["database_transaction_duration_seconds"].labels(
            result="error"
        ).observe(duration)

        metrics["database_errors_total"].labels(
            error_type="transaction"
        ).inc()

        raise
```

**Novel**: Single context manager handles **all transaction outcomes**—duration (success/error), count (success/error), and error type tracking.

---

## 4. Connection Pool Dynamic Gauges

**HuleEdu Pattern** (callback-based gauges for real-time pool stats):

```python
from sqlalchemy.pool import Pool

def setup_pool_metrics(pool: Pool, metrics: dict) -> None:
    """Setup dynamic gauges for connection pool monitoring."""

    # Callback functions return current values
    metrics["database_pool_size"].set_function(lambda: pool.size())
    metrics["database_pool_checked_out"].set_function(lambda: pool.checkedout())
    metrics["database_pool_overflow"].set_function(lambda: pool.overflow())
```

**PromQL**: Pool utilization percentage:
```promql
(database_pool_checked_out / database_pool_size) * 100
```

**Novel**: `.set_function()` with **lambda callbacks** provides real-time pool stats without manual updates.

---

## 5. Business Metrics: Discrete Distribution Buckets

**HuleEdu Pattern** (spell check corrections):

```python
Histogram(
    "huleedu_spellcheck_corrections_made",
    "Spelling corrections per essay",
    buckets=(0, 1, 2, 5, 10, 20, 50, 100),  # Discrete counts
)
```

**Novel**: Custom buckets for **correction counts** (not durations)—buckets match expected distribution (most essays have 0–10 corrections, few have 50+).

---

## 6. Business Metrics: Categorical Outcomes

**HuleEdu Pattern** (CJ Assessment outcomes):

```python
Counter(
    "huleedu_cj_assessment_outcomes_total",
    "CJ assessment comparison outcomes",
    ["outcome"],  # left_preferred, right_preferred, tie
)

# Usage
metrics["cj_assessment_outcomes_total"].labels(
    outcome="left_preferred"
).inc()
```

**PromQL**: Outcome distribution:
```promql
sum by (outcome) (rate(huleedu_cj_assessment_outcomes_total[5m]))
```

**Novel**: **Categorical business logic** tracked as metrics (not just operational counters).

---

## 7. Business Metrics: Phase Transitions with Bounded Cardinality

**HuleEdu Pattern** (batch orchestrator phase tracking):

```python
Histogram(
    "huleedu_phase_transition_duration_seconds",
    "Batch phase transition duration",
    ["from_phase", "to_phase", "batch_id"],  # batch_id: bounded cardinality
)

# Usage (batch_id included for debugging)
metrics["huleedu_phase_transition_duration_seconds"].labels(
    from_phase="SUBMITTED",
    to_phase="PROCESSING",
    batch_id=batch_id
).observe(duration)
```

**Gotcha**: `batch_id` label has **bounded cardinality** (max ~100 concurrent batches) making it safe for debugging without cardinality explosion.

---

## 8. Multi-Service Aggregation with Fallback

**HuleEdu Pattern** (total database errors across all services):

```promql
# or vector(0) fallback for services with no recent errors
sum(rate(batch_orchestrator_service_database_errors_total[1m]) or vector(0))
  + sum(rate(essay_lifecycle_service_database_errors_total[1m]) or vector(0))
  + sum(rate(cj_assessment_service_database_errors_total[1m]) or vector(0))
  + sum(rate(class_management_service_database_errors_total[1m]) or vector(0))
  + sum(rate(result_aggregator_service_database_errors_total[1m]) or vector(0))
  + sum(rate(spellchecker_service_database_errors_total[1m]) or vector(0))
```

**Novel**: `or vector(0)` fallback ensures newly started or error-free services don't break aggregation with NaN.

---

## 9. Transaction Success Rate Query

**HuleEdu Pattern** (Database Deep Dive dashboard):

```promql
# Calculate transaction success rate
rate(${service}_database_transaction_duration_seconds_count{result="success"}[5m])
/
(rate(${service}_database_transaction_duration_seconds_count[5m]) or vector(1))
* 100
```

**Gotcha**: `or vector(1)` prevents division by zero for services with no transactions.

---

## 10. Cross-References

- **Fundamentals**: [fundamentals.md](../fundamentals.md) - Histogram gotchas, custom buckets
- **HuleEdu Patterns**: [huleedu-patterns.md](../huleedu-patterns.md) - Service setup, naming
- **PromQL**: [promql-guide.md](../promql-guide.md) - Query patterns, edge cases
- **HTTP/Kafka**: [http-and-kafka.md](./http-and-kafka.md) - Basic instrumentation
- **LLM Metrics**: [llm-and-batch.md](./llm-and-batch.md) - LLM/queue patterns

---

**LoC**: 150
