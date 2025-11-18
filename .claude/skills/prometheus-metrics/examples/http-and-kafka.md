# HTTP and Kafka Examples

**Responsibility**: Novel HTTP/Kafka instrumentation patterns only (assumes basic Prometheus knowledge)

**Prerequisites**: See [fundamentals.md](../fundamentals.md) and [huleedu-patterns.md](../huleedu-patterns.md).

---

## 1. Singleton Pattern with Duplicate Handling

**HuleEdu Pattern** (test-safe metrics registration):

```python
from typing import Any
from prometheus_client import REGISTRY, Counter

_metrics: dict[str, Any] | None = None

def _create_metrics() -> dict[str, Any]:
    """Create metrics (raises ValueError if already registered)."""
    return {
        "http_requests_total": Counter(
            "spell_checker_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=REGISTRY,
        ),
    }

def _get_existing_metrics() -> dict[str, Any]:
    """Recover metrics from REGISTRY if already registered."""
    # Access REGISTRY._names_to_collectors or iterate collectors
    # to recover already-registered metrics by name
    pass

def get_metrics() -> dict[str, Any]:
    """Get or create metrics singleton."""
    global _metrics
    if _metrics is None:
        try:
            _metrics = _create_metrics()
        except ValueError as e:
            if "Duplicated timeseries" in str(e):
                # Test re-import scenario
                _metrics = _get_existing_metrics()
            else:
                raise
    return _metrics
```

**Novel Gotcha**: Test re-imports cause `ValueError: Duplicated timeseries`. Recovery via `_get_existing_metrics()` prevents test failures.

---

## 2. HTTP Middleware Gotchas

### Skip Metrics Endpoint

**Critical Pattern**:

```python
@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after request completes."""
    # Skip to avoid recursive tracking!
    if request.path == "/metrics":
        return response

    # Record metrics...
    metrics["http_requests_total"].labels(...).inc()
    return response
```

**Why**: Tracking `/metrics` requests creates recursive loop (Prometheus scrape triggers metric recording triggers scrape...).

### Endpoint Normalization for Cardinality

**Anti-Pattern** (high cardinality):
```python
# Creates unique label per request!
endpoint = "/api/essays/12345"  # Different for every essay
```

**HuleEdu Pattern** (bounded cardinality):
```python
import re

def _normalize_endpoint(path: str) -> str:
    """Normalize endpoints to prevent cardinality explosion."""
    # UUID: /api/batches/abc-def-ghi -> /api/batches/:uuid
    path = re.sub(
        r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '/:uuid',
        path,
        flags=re.IGNORECASE
    )

    # Numeric IDs: /api/essays/12345 -> /api/essays/:id
    path = re.sub(r'/\d+', '/:id', path)

    return path
```

**Critical**: Without normalization, each unique ID creates a new time series → cardinality explosion → Prometheus performance degradation.

---

## 3. Kafka Queue Latency Calculation

**HuleEdu Pattern** (end-to-end async delay):

```python
import time
from datetime import datetime

async def handle_event(envelope: EventEnvelope, metrics: dict) -> None:
    """Process Kafka event with queue latency tracking."""
    processing_start = time.time()

    # Parse ISO timestamp from event envelope
    event_time = datetime.fromisoformat(
        envelope.timestamp.replace('Z', '+00:00')  # ISO format gotcha
    )
    queue_latency = processing_start - event_time.timestamp()

    # Record latency
    metrics["kafka_queue_latency_seconds"].observe(queue_latency)
```

**Novel Patterns**:
1. **ISO Format Gotcha**: `.replace('Z', '+00:00')` required for Python's `fromisoformat()`
2. **Measures End-to-End Delay**: Event creation → processing start (critical for async SLO tracking)

---

## 4. Context Manager vs Decorator

**HuleEdu Decision**: Prefer context managers over decorators.

**Context Manager** (preferred):
```python
# Explicit timing context for correlation ID logging
with metrics["duration"].labels(endpoint=endpoint).time():
    logger.info("Starting request", correlation_id=corr_id)
    result = await process()
    logger.info("Request complete", correlation_id=corr_id)
```

**Decorator** (avoided):
```python
# Decorator hides timing context from logger
@metrics["duration"].labels(endpoint=endpoint).time()
async def process():
    # Timing implicit, harder to correlate with logs
    pass
```

**Why Context Manager**: Explicit timing boundaries enable structured logging with correlation IDs at entry/exit points.

---

## 5. Middleware Order Significance

**HuleEdu Pattern** (from `app.py`):

```python
# Order matters!
setup_correlation_middleware(app)     # 1. First: Sets correlation_id
setup_metrics_middleware(app, metrics) # 2. Second: Needs correlation_id for labels
setup_error_handling_middleware(app)   # 3. Third: Catches exceptions
```

**Critical Gotcha**: If metrics run before correlation middleware, `correlation_id` is unavailable for metric labels → breaks observability correlation.

---

## 6. DatabaseMetrics Integration

**HuleEdu Pattern** (merge DB metrics into service metrics):

```python
from huleedu_service_libs.database.metrics import DatabaseMetrics

def get_metrics(database_metrics: DatabaseMetrics | None = None) -> dict:
    """Get metrics with optional DB metrics merge."""
    metrics = _create_service_metrics()

    if database_metrics:
        db_metrics = database_metrics.get_metrics()
        metrics.update(db_metrics)  # Merge into single dict

    return metrics
```

**Novel**: Centralized `DatabaseMetrics` library ensures consistent DB instrumentation across all services.

---

## 7. Custom Buckets for Discrete Distributions

**HuleEdu Pattern** (spell check corrections):

```python
from prometheus_client import Histogram

spellcheck_corrections_made = Histogram(
    "huleedu_spellcheck_corrections_made",
    "Distribution of spelling corrections per essay",
    buckets=(0, 1, 2, 5, 10, 20, 50, 100),  # Discrete counts, not durations
)

# Usage:
metrics["spellcheck_corrections_made"].observe(len(corrections))
```

**Novel**: Custom buckets for **counts** (not durations). Default Prometheus buckets (0.005–10.0) are time-oriented and don't fit correction distributions.

---

## 8. Cross-References

- **Fundamentals**: [fundamentals.md](../fundamentals.md) - Histogram gotchas, label cardinality
- **HuleEdu Patterns**: [huleedu-patterns.md](../huleedu-patterns.md) - Service setup, naming conventions
- **PromQL**: [promql-guide.md](../promql-guide.md) - Query patterns, edge cases
- **LLM Metrics**: [llm-and-batch.md](./llm-and-batch.md) - Token tracking, cost tracking
- **Database Metrics**: [database-and-business.md](./database-and-business.md) - DB patterns

---

**LoC**: 150
