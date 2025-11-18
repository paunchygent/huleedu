# HuleEdu Prometheus Patterns

**Responsibility**: HuleEdu codebase conventions only (not generic Prometheus patterns)

**Prerequisites**: See [fundamentals.md](fundamentals.md) for Prometheus basics.

---

## 1. Architecture Essentials

### Scrape Configuration
- **Scrape Interval**: 15 seconds (affects `rate()` minimum window)
- **Config Location**: `/observability/prometheus/prometheus.yml`
- **Prometheus External Port**: 9091 (<http://localhost:9091>)

**Critical**: 15s scrape interval means `rate()` windows < 30s may produce unreliable results (need ≥2 samples).

### Service Metrics Endpoints

All services expose `/metrics` on their internal ports:

| Service | Port | Endpoint |
|---------|------|----------|
| batch_orchestrator_service | 5000 | http://batch_orchestrator_service:5000/metrics |
| essay_lifecycle_service | 5001 | http://essay_lifecycle_service:5001/metrics |
| spellchecker_service | 5002 | http://spellchecker_service:5002/metrics |
| llm_provider_service | 5003 | http://llm_provider_service:5003/metrics |
| cj_assessment_service | 5004 | http://cj_assessment_service:5004/metrics |
| file_service | 5005 | http://file_service:5005/metrics |
| class_management_service | 5006 | http://class_management_service:5006/metrics |

---

## 2. Naming Patterns

### Pattern 1: Service-Prefixed (Default)

**Format**: `{service}_{metric}_{unit}`

**When**: Service-specific operational metrics (HTTP, DB, Kafka)

**Examples**:
```python
spell_checker_http_requests_total
batch_orchestrator_phase_transition_duration_seconds
llm_provider_concurrent_requests
```

### Pattern 2: Business Metrics (Cross-Service)

**Format**: `huleedu_{business_metric}_{unit}`

**When**: Business logic metrics, cross-service aggregation needed

**Examples**:
```python
huleedu_spellcheck_corrections_made
huleedu_llm_cost_dollars_total
huleedu_cj_assessment_outcomes_total
```

**Novel Convention**: `huleedu_` prefix clearly identifies business metrics in PromQL queries.

### Decision Guide

| Metric | Pattern | Reasoning |
|--------|---------|-----------|
| HTTP request count | 1 (Service) | Operational, service-specific |
| Database query duration | 1 (Service) | Operational, service-specific |
| LLM tokens consumed | 2 (Business) | Cost tracking, business metric |
| Spell check corrections | 2 (Business) | Quality indicator, cross-service |
| Kafka consumer lag | 1 (Service) | Operational, service-specific |

---

## 3. Service Setup Pattern

### metrics.py Module Pattern

**Location**: `services/<service>/metrics.py`

**HuleEdu Singleton Pattern**:
```python
from typing import Any
from prometheus_client import REGISTRY, Counter, Histogram

_metrics: dict[str, Any] | None = None

def _create_metrics() -> dict[str, Any]:
    """Create service metrics (called once)."""
    return {
        "http_requests_total": Counter(
            "spell_checker_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=REGISTRY,
        ),
        # ... more metrics
    }

def _get_existing_metrics() -> dict[str, Any]:
    """Recover metrics from REGISTRY if already registered (test scenario)."""
    # Handle ValueError: Duplicated timeseries in test re-imports
    # Implementation extracts from REGISTRY._collector_to_names
    pass

def get_metrics() -> dict[str, Any]:
    """Get or create metrics singleton."""
    global _metrics
    if _metrics is None:
        try:
            _metrics = _create_metrics()
        except ValueError:
            _metrics = _get_existing_metrics()
    return _metrics

# Module-level access
metrics = get_metrics()
```

**Why This Pattern**:
- Global `_metrics` prevents duplicate registration
- Dict access: `metrics["http_requests_total"].inc()`
- Test-safe: Handles re-import via `_get_existing_metrics()`

### app.py Setup Pattern

**Location**: `services/<service>/app.py`

**Minimal Setup** (~15 lines):
```python
from quart import Quart
from prometheus_client import make_asgi_app
from huleedu_service_libs.metrics_middleware import (
    setup_standard_service_metrics_middleware
)

app = Quart(__name__)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

@app.before_serving
async def startup():
    setup_standard_service_metrics_middleware(app, "spell_checker")
    logger.info("Service started")
```

**Critical Components**:
1. `make_asgi_app()`: Exposes Prometheus metrics endpoint
2. `app.mount("/metrics", ...)`: Mounts at `/metrics` path
3. `setup_standard_service_metrics_middleware(...)`: Adds HTTP instrumentation

---

## 4. Middleware Integration (Critical Gotcha)

### Middleware Order Significance

**HuleEdu Pattern** (from `app.py`):
```python
# Order matters!
1. Correlation ID middleware (first)
2. Metrics middleware (second)
3. Error handling middleware (third)
```

**Why**: Metrics need `correlation_id` available for labels. If metrics run before correlation middleware, correlation context is missing.

**Anti-Pattern**:
```python
# WRONG: Metrics run before correlation_id is set
setup_standard_service_metrics_middleware(app, "service")
setup_correlation_id_middleware(app)
```

### Standard HTTP Middleware

**Library**: `huleedu_service_libs/metrics_middleware.py`

**What It Provides**:
- Automatic HTTP request counting
- Request duration tracking
- Labels: `method`, `endpoint`, `status_code`
- Endpoint normalization (UUIDs → `:uuid`, IDs → `:id`)

**When to Use Manual Instrumentation**:
- Business logic metrics (not HTTP)
- Background tasks, Kafka consumers
- Database operations
- LLM API calls
- Custom labels beyond method/endpoint/status

---

## 5. DatabaseMetrics Integration

**Library**: `huleedu_service_libs/database/metrics.py`

**Pattern**:
```python
from huleedu_service_libs.database.metrics import DatabaseMetrics

# In get_metrics()
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
- Connection pool gauges

**Novel**: Centralized library ensures consistent DB metrics across all services.

---

## 6. Observability Stack Integration

### Cross-Stack Correlation

**Metrics** (Prometheus):
- Use `correlation_id` label sparingly (cardinality risk)
- Prefer service-level aggregation

**Logs** (Loki):
- Always include `correlation_id` in log context
- Query logs by correlation_id to trace specific requests

**Traces** (Jaeger):
- Span attributes include metric names
- Trace correlation with `correlation_id`

**HuleEdu Pattern**: Metrics → alert → query logs by correlation_id → trace in Jaeger.

### Scrape Interval Impact

- **15s scrape interval** → `rate()` minimum window = 30s (need ≥2 samples)
- Use `rate(...[1m])` as minimum (covers 4 scrapes)
- For alerting: `rate(...[5m])` recommended (20 scrapes, stable results)

---

## 7. Best Practices (HuleEdu-Specific)

### 1. Consistent Label Names Across Services

**Standard Labels**:
- `status`: "success", "error", "timeout"
- `operation`: operation type ("select", "insert", "update", "delete")
- `provider`: "openai", "anthropic"
- `language`: "en", "es"

**Anti-Pattern**: Using `result` in one service, `status` in another for same concept.

### 2. Group Related Metrics in Dict

```python
# Good: Grouped by domain
metrics = {
    # HTTP
    "http_requests_total": ...,
    "http_request_duration_seconds": ...,

    # Business
    "spell_check_operations_total": ...,
    "spellcheck_corrections_made": ...,

    # Queue
    "kafka_queue_latency_seconds": ...,
}
```

### 3. Verify /metrics Endpoint

```bash
curl http://localhost:5002/metrics | grep spell_checker_operations_total
```

### 4. Check Prometheus Targets

```bash
curl http://localhost:9091/api/v1/targets | jq '.data.activeTargets[] | select(.job == "spellchecker")'
```

---

## 8. Cross-References

- **Fundamentals**: [fundamentals.md](fundamentals.md) - Histogram gotchas, label cardinality, Python patterns
- **PromQL**: [promql-guide.md](promql-guide.md) - Query patterns, edge cases
- **Examples**: [examples/](examples/) - Real-world instrumentation snippets
- **Observability Rules**: `.claude/rules/071.1-service-observability-core-patterns.md`

---

**LoC**: 200
