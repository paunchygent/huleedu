# Prometheus Metrics Specialist - Detailed Reference

Comprehensive guide for instrumenting HuleEdu services with Prometheus metrics and querying them.

## Table of Contents

1. [Prometheus Architecture in HuleEdu](#prometheus-architecture-in-huleedu)
2. [Metric Types and Usage](#metric-types-and-usage)
3. [Naming Conventions](#naming-conventions)
4. [Service Instrumentation Patterns](#service-instrumentation-patterns)
5. [PromQL Query Patterns](#promql-query-patterns)
6. [Grafana Dashboard Integration](#grafana-dashboard-integration)
7. [Context7 Integration](#context7-integration)
8. [Best Practices](#best-practices)

---

## Prometheus Architecture in HuleEdu

### Stack Components

**Prometheus Service**:
- **External Port**: 9091
- **Internal URL**: `http://prometheus:9090`
- **Purpose**: Metrics collection and storage
- **Config**: `/observability/prometheus/prometheus.yml`
- **Scrape Interval**: 15 seconds (default)

**Exporters**:
- **Kafka Exporter**: Port 9308 - Kafka cluster metrics
- **PostgreSQL Exporter**: Port 9187 - Database metrics (6 services)
- **Redis Exporter**: Port 9121 - Redis cache metrics
- **Node Exporter**: Port 9100 - System metrics

### Service Metrics Endpoints

All HuleEdu services expose `/metrics` endpoint:

| Service | Port | Metrics Endpoint |
|---------|------|------------------|
| content_service | 8000 | http://content_service:8000/metrics |
| batch_orchestrator_service | 5000 | http://batch_orchestrator_service:5000/metrics |
| essay_lifecycle_service | 5001 | http://essay_lifecycle_service:5001/metrics |
| spellchecker_service | 5002 | http://spellchecker_service:5002/metrics |
| llm_provider_service | 5003 | http://llm_provider_service:5003/metrics |
| cj_assessment_service | 5004 | http://cj_assessment_service:5004/metrics |
| file_service | 5005 | http://file_service:5005/metrics |
| class_management_service | 5006 | http://class_management_service:5006/metrics |

**Status**: 9/10 services exposing metrics correctly (essay_lifecycle_api has known issue documented in CRITICAL_METRICS_AUDIT.md)

---

## Metric Types and Usage

### Counter

**Purpose**: Count events (monotonically increasing, resets to 0 on restart)

**Use Cases**:
- Total HTTP requests
- Total operations performed
- Total errors encountered
- Total events processed

**Python Example**:
```python
from prometheus_client import Counter

http_requests_total = Counter(
    "spell_checker_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],  # Labels
)

# Increment counter
http_requests_total.labels(
    method="GET",
    endpoint="/api/spellcheck",
    status_code="200"
).inc()

# Increment by value
http_requests_total.labels(method="POST", endpoint="/api/batch", status_code="201").inc(10)
```

**PromQL Queries**:
```promql
# Rate of requests per second (5-minute window)
rate(spell_checker_http_requests_total[5m])

# Total requests in last hour
increase(spell_checker_http_requests_total[1h])

# Error rate (4xx + 5xx responses)
sum(rate(spell_checker_http_requests_total{status_code=~"4..|5.."}[5m]))
```

---

### Histogram

**Purpose**: Track distributions and calculate quantiles (P50, P95, P99)

**Use Cases**:
- Request duration/latency
- Response sizes
- Distribution of corrections/scores
- Queue processing time

**Python Example**:
```python
from prometheus_client import Histogram

request_duration_seconds = Histogram(
    "spell_checker_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Record observation
request_duration_seconds.labels(
    method="POST",
    endpoint="/api/spellcheck"
).observe(0.23)  # 230ms

# Context manager for automatic timing
with request_duration_seconds.labels(method="GET", endpoint="/api/health").time():
    # Code to measure
    result = await perform_health_check()
```

**Custom Buckets**:
```python
# For corrections distribution (discrete counts)
corrections_made = Histogram(
    "huleedu_spellcheck_corrections_made",
    "Distribution of corrections per essay",
    buckets=(0, 1, 2, 5, 10, 20, 50, 100),
)

# For duration (sub-second to minutes)
processing_duration = Histogram(
    "huleedu_essay_processing_duration_seconds",
    "Essay processing duration",
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
```

**PromQL Queries**:
```promql
# P95 latency
histogram_quantile(0.95,
  rate(spell_checker_http_request_duration_seconds_bucket[5m])
)

# P50 (median) latency by endpoint
histogram_quantile(0.50,
  sum by (endpoint, le) (rate(spell_checker_http_request_duration_seconds_bucket[5m]))
)

# Average duration
rate(spell_checker_http_request_duration_seconds_sum[5m]) /
rate(spell_checker_http_request_duration_seconds_count[5m])
```

---

### Gauge

**Purpose**: Track values that can go up or down

**Use Cases**:
- Active connections
- Queue size
- In-progress operations
- Cache hit rate
- Resource usage

**Python Example**:
```python
from prometheus_client import Gauge

active_connections = Gauge(
    "spell_checker_active_connections",
    "Number of active HTTP connections",
)

# Set value
active_connections.set(15)

# Increment/Decrement
active_connections.inc()    # Increment by 1
active_connections.dec()    # Decrement by 1
active_connections.inc(5)   # Increment by 5

# Track in-progress operations
in_progress_requests = Gauge(
    "spell_checker_in_progress_requests",
    "Requests currently being processed",
)

@in_progress_requests.track_inprogress()
async def process_request():
    # Gauge automatically incremented on entry, decremented on exit
    result = await perform_spellcheck()
    return result
```

**PromQL Queries**:
```promql
# Current active connections
spell_checker_active_connections

# Max active connections in last hour
max_over_time(spell_checker_active_connections[1h])

# Average queue size
avg_over_time(kafka_consumer_lag[5m])
```

---

### Summary

**Purpose**: Similar to Histogram but calculates quantiles on client side

**Use Cases**: Less common in HuleEdu (Histogram preferred)

**Python Example**:
```python
from prometheus_client import Summary

request_latency = Summary(
    "spell_checker_request_latency_seconds",
    "Request latency in seconds",
)

# Record observation
request_latency.observe(0.15)
```

**Note**: Histograms are generally preferred over Summaries in HuleEdu because:
- Histograms can be aggregated across instances
- Summaries calculate quantiles client-side (less flexible)
- Histogram buckets can be adjusted in PromQL queries

---

## Naming Conventions

### Pattern 1: Service-Prefixed Metrics

**Format**: `<service_name>_<metric>_<unit>`

**Usage**: Most services use this pattern for operational metrics

**Examples**:
```python
spell_checker_http_requests_total
spell_checker_http_request_duration_seconds
spell_checker_operations_total
spell_checker_active_connections

batch_orchestrator_http_requests_total
batch_orchestrator_batch_processing_duration_seconds
batch_orchestrator_batches_processed_total

llm_provider_requests_total
llm_provider_token_usage_total
llm_provider_rate_limit_hits_total
```

**Advantages**:
- Clear service ownership
- No naming conflicts across services
- Easy to filter by service in PromQL

---

### Pattern 2: Business Metrics (Cross-Service)

**Format**: `huleedu_<business_metric>_<unit>`

**Usage**: Business-level metrics that may be collected by multiple services

**Examples**:
```python
huleedu_spellcheck_corrections_made
huleedu_essay_processing_duration_seconds
huleedu_llm_prompt_tokens_total
huleedu_llm_completion_tokens_total
huleedu_assessment_score_distribution
huleedu_student_submissions_total
```

**Advantages**:
- Cross-service aggregation
- Business-focused dashboards
- Consistent naming for related metrics

---

### Pattern 3: Standard Names (Legacy)

**Format**: Generic names without service prefix

**Usage**: Some legacy services (being migrated to Pattern 1)

**Examples**:
```python
request_count
request_duration
http_requests_total
```

**Status**: Being phased out in favor of Pattern 1 or Pattern 2

---

### Choosing a Pattern

**Use Pattern 1** (Service-Prefixed) when:
- Metric is specific to one service
- Operational/technical metric (HTTP, DB, Kafka)
- Default choice for new metrics

**Use Pattern 2** (Business Metrics) when:
- Metric represents business logic
- May be collected by multiple services
- Used in business-focused dashboards
- Needs cross-service aggregation

---

## Service Instrumentation Patterns

### Standard HTTP Metrics Middleware

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/metrics_middleware.py`

**Setup**:
```python
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware

# In app.py
app = HuleEduApp(__name__)

@app.before_serving
async def startup():
    setup_standard_service_metrics_middleware(app, "spell_checker")
```

**Metrics Created**:
- `{service}_request_count` (Counter)
- `{service}_request_duration` (Histogram)

**Automatic Instrumentation**:
- Counts all HTTP requests
- Tracks request duration
- Labels: method, endpoint, status_code

---

### Service-Specific Metrics Module

**Pattern**: Create `metrics.py` in service root

**Example**: `/services/spellchecker_service/metrics.py`

```python
from prometheus_client import REGISTRY, Counter, Histogram

def _create_metrics() -> dict[str, Any]:
    """Create service-specific Prometheus metrics."""
    return {
        # HTTP operational metrics
        "http_requests_total": Counter(
            "spell_checker_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=REGISTRY,
        ),
        "http_request_duration_seconds": Histogram(
            "spell_checker_http_request_duration_seconds",
            "HTTP request duration",
            ["method", "endpoint"],
            registry=REGISTRY,
        ),

        # Business metrics
        "spell_check_operations_total": Counter(
            "spell_checker_operations_total",
            "Total spell check operations",
            ["language", "status"],
            registry=REGISTRY,
        ),
        "spellcheck_corrections_made": Histogram(
            "huleedu_spellcheck_corrections_made",
            "Distribution of corrections per essay",
            buckets=(0, 1, 2, 5, 10, 20, 50, 100),
            registry=REGISTRY,
        ),

        # Queue metrics
        "kafka_queue_latency_seconds": Histogram(
            "kafka_message_queue_latency_seconds",
            "Latency between event timestamp and processing",
            registry=REGISTRY,
        ),
    }

# Module-level metrics instance
metrics = _create_metrics()
```

**Usage in Service Code**:
```python
from spellchecker_service.metrics import metrics

# Increment counter
metrics["spell_check_operations_total"].labels(
    language="en",
    status="success"
).inc()

# Record histogram observation
metrics["spellcheck_corrections_made"].observe(len(corrections))

# Record queue latency
queue_latency = (datetime.utcnow() - envelope.timestamp).total_seconds()
metrics["kafka_queue_latency_seconds"].observe(queue_latency)
```

---

### Kafka Event Processing Metrics

**Pattern**: Instrument Kafka consumer and event processor

```python
from huleedu_service_libs.logging_utils import create_service_logger
from spellchecker_service.metrics import metrics

logger = create_service_logger("spellchecker_service.event_processor")

async def process_event(envelope: EventEnvelope) -> None:
    """Process event with metrics instrumentation."""

    # Record queue latency
    queue_latency = (datetime.utcnow() - envelope.timestamp).total_seconds()
    metrics["kafka_queue_latency_seconds"].observe(queue_latency)

    try:
        # Process event
        result = await spell_checker.check(envelope.data.content)

        # Record success metrics
        metrics["spell_check_operations_total"].labels(
            language="en",
            status="success"
        ).inc()

        metrics["spellcheck_corrections_made"].observe(len(result.corrections))

    except Exception as e:
        # Record error metrics
        metrics["spell_check_operations_total"].labels(
            language="en",
            status="error"
        ).inc()

        logger.error("Event processing failed", exc_info=True)
        raise
```

---

### Database Connection Pool Metrics

**Pattern**: Expose pool metrics via Gauge

```python
from prometheus_client import Gauge

db_pool_size = Gauge(
    "spell_checker_db_pool_size",
    "Database connection pool size",
)

db_pool_active_connections = Gauge(
    "spell_checker_db_pool_active_connections",
    "Active database connections",
)

db_pool_idle_connections = Gauge(
    "spell_checker_db_pool_idle_connections",
    "Idle database connections",
)

# Update metrics periodically (in background task or on request)
async def update_db_pool_metrics():
    pool = get_db_pool()
    db_pool_size.set(pool.size)
    db_pool_active_connections.set(pool.active_count)
    db_pool_idle_connections.set(pool.idle_count)
```

---

### LLM Provider Metrics

**Pattern**: Track token usage, costs, and rate limits

```python
llm_metrics = {
    "llm_requests_total": Counter(
        "huleedu_llm_requests_total",
        "Total LLM API requests",
        ["provider", "model", "status"],
    ),
    "llm_prompt_tokens_total": Counter(
        "huleedu_llm_prompt_tokens_total",
        "Total prompt tokens consumed",
        ["provider", "model"],
    ),
    "llm_completion_tokens_total": Counter(
        "huleedu_llm_completion_tokens_total",
        "Total completion tokens consumed",
        ["provider", "model"],
    ),
    "llm_request_duration_seconds": Histogram(
        "huleedu_llm_request_duration_seconds",
        "LLM API request duration",
        ["provider", "model"],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    ),
    "llm_rate_limit_hits_total": Counter(
        "huleedu_llm_rate_limit_hits_total",
        "Total rate limit hits",
        ["provider"],
    ),
}

# Usage
llm_metrics["llm_requests_total"].labels(
    provider="openai",
    model="gpt-4",
    status="success"
).inc()

llm_metrics["llm_prompt_tokens_total"].labels(
    provider="openai",
    model="gpt-4"
).inc(response.usage.prompt_tokens)

llm_metrics["llm_completion_tokens_total"].labels(
    provider="openai",
    model="gpt-4"
).inc(response.usage.completion_tokens)
```

---

## PromQL Query Patterns

### Basic Queries

**Current Value**:
```promql
# Gauge value
spell_checker_active_connections

# Counter value (total)
spell_checker_operations_total
```

**Rate Over Time**:
```promql
# Requests per second (5-minute window)
rate(spell_checker_http_requests_total[5m])

# Operations per minute
rate(spell_checker_operations_total[1m]) * 60
```

**Increase Over Time**:
```promql
# Total requests in last hour
increase(spell_checker_http_requests_total[1h])

# Total errors in last 24 hours
increase(spell_checker_operations_total{status="error"}[24h])
```

---

### Aggregation

**Sum Across Labels**:
```promql
# Total requests across all endpoints
sum(rate(spell_checker_http_requests_total[5m]))

# Total requests by endpoint (preserve endpoint label)
sum by (endpoint) (rate(spell_checker_http_requests_total[5m]))
```

**Average**:
```promql
# Average active connections across all instances
avg(spell_checker_active_connections)

# Average request duration
avg(rate(spell_checker_http_request_duration_seconds_sum[5m])) /
avg(rate(spell_checker_http_request_duration_seconds_count[5m]))
```

**Max/Min**:
```promql
# Max active connections in last hour
max_over_time(spell_checker_active_connections[1h])

# Min queue size
min(kafka_consumer_lag)
```

---

### Error Rates

**HTTP Error Rate**:
```promql
# Error rate (4xx + 5xx)
sum(rate(spell_checker_http_requests_total{status_code=~"4..|5.."}[5m])) /
sum(rate(spell_checker_http_requests_total[5m]))

# 5xx error rate only
sum(rate(spell_checker_http_requests_total{status_code=~"5.."}[5m])) /
sum(rate(spell_checker_http_requests_total[5m]))
```

**Operation Error Rate**:
```promql
# Spell check error rate
sum(rate(spell_checker_operations_total{status="error"}[5m])) /
sum(rate(spell_checker_operations_total[5m]))
```

---

### Percentiles (Histogram)

**P50, P95, P99**:
```promql
# P95 request duration
histogram_quantile(0.95,
  sum by (le) (rate(spell_checker_http_request_duration_seconds_bucket[5m]))
)

# P99 by endpoint
histogram_quantile(0.99,
  sum by (endpoint, le) (rate(spell_checker_http_request_duration_seconds_bucket[5m]))
)

# P50 (median)
histogram_quantile(0.50,
  rate(spell_checker_http_request_duration_seconds_bucket[5m])
)
```

---

### Rate Calculations

**Success Rate**:
```promql
# Spell check success rate
sum(rate(spell_checker_operations_total{status="success"}[5m])) /
sum(rate(spell_checker_operations_total[5m]))
```

**Throughput**:
```promql
# Requests per second
sum(rate(spell_checker_http_requests_total[5m]))

# Events processed per minute
sum(rate(spell_checker_operations_total[1m])) * 60
```

---

### Multi-Service Queries

**All Services Request Rate**:
```promql
# Total requests across all HuleEdu services
sum(rate({__name__=~".*_http_requests_total"}[5m]))

# By service
sum by (service) (rate({__name__=~".*_http_requests_total"}[5m]))
```

**Cross-Service Business Metrics**:
```promql
# Total LLM tokens consumed (all services)
sum(rate(huleedu_llm_prompt_tokens_total[5m]))

# By provider
sum by (provider) (rate(huleedu_llm_prompt_tokens_total[5m]))
```

---

## Grafana Dashboard Integration

### System Health Overview

**Location**: `/observability/grafana/dashboards/HuleEdu_System_Health_Overview.json`

**Key Panels**:

**Service Availability**:
```promql
# 1 if service is up, 0 if down
up{job=~".*_service"}
```

**Global Error Rate**:
```promql
sum(rate({__name__=~".*_http_requests_total", status_code=~"5.."}[5m])) /
sum(rate({__name__=~".*_http_requests_total"}[5m]))
```

**Request Rate by Service**:
```promql
sum by (job) (rate({__name__=~".*_http_requests_total"}[5m]))
```

---

### Service Deep Dive

**Location**: `/observability/grafana/dashboards/HuleEdu_Service_Deep_Dive_Template.json`

**HTTP Request Rate**:
```promql
sum(rate(spell_checker_http_requests_total{job="spell_checker"}[5m]))
```

**HTTP Request Duration (P95)**:
```promql
histogram_quantile(0.95,
  sum by (le) (rate(spell_checker_http_request_duration_seconds_bucket{job="spell_checker"}[5m]))
)
```

**Error Rate by Status Code**:
```promql
sum by (status_code) (rate(spell_checker_http_requests_total{job="spell_checker", status_code=~"4..|5.."}[5m]))
```

**Business Metrics** (conditional panels):
```promql
# Spellchecker: Corrections distribution
sum(rate(huleedu_spellcheck_corrections_made_bucket[5m]))

# LLM Provider: Token usage
sum by (provider) (rate(huleedu_llm_prompt_tokens_total[5m]))
```

---

### Database Monitoring

**Location**: `/observability/grafana/dashboards/HuleEdu_Database_Deep_Dive.json`

**Connection Pool Usage**:
```promql
# Active connections
spell_checker_db_pool_active_connections

# Pool utilization (%)
(spell_checker_db_pool_active_connections / spell_checker_db_pool_size) * 100
```

**Query Duration**:
```promql
# P95 query duration
histogram_quantile(0.95,
  rate(spell_checker_db_query_duration_seconds_bucket[5m])
)
```

---

## Context7 Integration

### When to Use Context7

Fetch latest Prometheus/PromQL documentation when:
- User asks about advanced PromQL functions (e.g., `predict_linear`, `deriv`, `holt_winters`)
- Need examples of complex aggregations or subqueries
- Troubleshooting Prometheus configuration issues
- Understanding recording rules or alerting rules
- New Prometheus features or syntax changes

### Example Context7 Usage

```python
# Fetch Prometheus documentation
from context7 import get_library_docs

prometheus_docs = get_library_docs(
    library_id="/prometheus/prometheus",
    topic="promql query examples"
)

# Fetch specific PromQL functions
promql_functions = get_library_docs(
    library_id="/prometheus/prometheus",
    topic="histogram_quantile function"
)
```

**Library IDs**:
- Prometheus: `/prometheus/prometheus`
- PromQL: Part of Prometheus docs, use topic filtering

---

## Best Practices

### 1. Choose Appropriate Metric Types

**Counter** for:
- Counts that only increase (requests, errors, events)
- Never use for values that can decrease

**Histogram** for:
- Durations and latencies
- Sizes (request/response sizes)
- Distributions

**Gauge** for:
- Current values (connections, queue size)
- Values that go up and down

### 2. Use Meaningful Labels

**Good**:
```python
http_requests_total.labels(
    method="POST",
    endpoint="/api/spellcheck",
    status_code="200"
)
```

**Bad** (too many labels, high cardinality):
```python
http_requests_total.labels(
    user_id="12345",        # High cardinality!
    request_id="abc-123",   # Unique per request!
    correlation_id="xyz"    # High cardinality!
)
```

**Label Cardinality Guidelines**:
- Keep total label combinations under 10,000
- Avoid user IDs, request IDs, timestamps
- Use labels for dimensions you'll aggregate by

### 3. Name Metrics Consistently

**Follow conventions**:
- Use base units: `_seconds`, `_bytes`, `_total`
- Use descriptive names: `http_request_duration_seconds` not `duration`
- Include service prefix or `huleedu_` prefix

### 4. Set Appropriate Histogram Buckets

**Default buckets** (0.005s to 10s):
```python
# Good for most API requests
buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
```

**Custom buckets** for specific use cases:
```python
# LLM requests (slower, up to 60s)
buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

# Discrete counts (corrections)
buckets=(0, 1, 2, 5, 10, 20, 50, 100)
```

### 5. Document Business Metrics

Add comments explaining business logic:
```python
"huleedu_spellcheck_corrections_made": Histogram(
    "huleedu_spellcheck_corrections_made",
    "Distribution of spelling/grammar corrections per essay. "
    "Higher values may indicate lower writing quality or non-native speakers.",
    buckets=(0, 1, 2, 5, 10, 20, 50, 100),
)
```

### 6. Expose Metrics Endpoint

Always ensure `/metrics` endpoint is accessible:
```python
from prometheus_client import make_asgi_app

# In app.py
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

Verify in Prometheus targets:
```bash
curl http://localhost:9091/api/v1/targets | jq '.data.activeTargets[] | select(.job == "spell_checker")'
```

### 7. Use Recording Rules for Expensive Queries

For complex queries used in multiple dashboards:
```yaml
# prometheus-rules.yml
groups:
  - name: huleedu_business_metrics
    interval: 1m
    rules:
      - record: huleedu:spellcheck_corrections:rate1m
        expr: sum(rate(huleedu_spellcheck_corrections_made_count[1m]))

      - record: huleedu:http_error_rate:5m
        expr: |
          sum(rate({__name__=~".*_http_requests_total", status_code=~"5.."}[5m])) /
          sum(rate({__name__=~".*_http_requests_total"}[5m]))
```

### 8. Monitor Metric Cardinality

Check metric cardinality in Prometheus:
```promql
# Count of unique time series per metric
count by (__name__) ({__name__=~"spell_checker_.*"})
```

**Warning signs**:
- Metric has > 10,000 time series
- Prometheus memory usage increasing
- Slow query performance

**Solution**: Reduce label cardinality or remove high-cardinality labels

---

## Related Resources

- **examples.md**: Real-world metrics instrumentation examples
- **SKILL.md**: Quick reference and activation criteria
- `/observability/CRITICAL_METRICS_AUDIT.md`: Current metrics status and issues
- `/observability/prometheus/prometheus.yml`: Scrape configuration
- `.claude/rules/071.1-service-observability-core-patterns.md`: Observability standards
