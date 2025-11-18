---
name: prometheus-metrics-specialist
description: Instrument services with Prometheus metrics and write PromQL queries. Guides HuleEdu naming conventions, metrics middleware setup, and business vs operational metrics. Integrates with Context7 for latest Prometheus documentation.
---

# Prometheus Metrics Specialist

Compact skill for instrumenting HuleEdu services with Prometheus metrics and querying them with PromQL.

## When to Use

Activate when the user:
- Needs to add metrics instrumentation to a service
- Wants to write PromQL queries for dashboards or alerts
- Asks about metrics naming conventions
- Needs help with metrics middleware setup
- Wants to understand business vs operational metrics
- Mentions Prometheus, PromQL, metrics, instrumentation, or monitoring
- Needs to expose `/metrics` endpoint

## Core Capabilities

- **Naming Conventions**: HuleEdu's 3 metric naming patterns (service-prefixed, business, standard)
- **Instrumentation**: Counter, Histogram, Gauge, Summary usage patterns
- **Middleware Setup**: Standard HTTP metrics middleware
- **Service-Specific Metrics**: Business logic metrics patterns
- **PromQL Queries**: Query patterns for troubleshooting and dashboards
- **Scrape Configuration**: Prometheus service discovery and targets
- **Best Practices**: Metric types, cardinality, aggregation
- **Context7 Integration**: Fetch latest Prometheus/PromQL documentation

## Quick Workflow

1. Identify metric type (Counter, Histogram, Gauge, Summary)
2. Choose naming pattern based on metric scope (service-specific vs cross-service)
3. Add metric declaration to service metrics module
4. Instrument code at appropriate points
5. Verify `/metrics` endpoint exposes new metric
6. Add to Grafana dashboard if needed

## HuleEdu Naming Patterns

### Pattern 1: Service-Prefixed (Most Common)
```python
<service>_http_requests_total
<service>_http_request_duration_seconds
<service>_operations_total

# Example
spell_checker_operations_total
```

### Pattern 2: Business Metrics (Cross-Service)
```python
huleedu_<metric>_<unit>

# Example
huleedu_spellcheck_corrections_made
huleedu_essay_processing_duration_seconds
```

### Pattern 3: Standard Names (Legacy)
```python
request_count
request_duration
```

## Common Metric Types

**Counter** (monotonically increasing):
```python
operations_total  # Total operations count
errors_total      # Total errors count
```

**Histogram** (distributions):
```python
request_duration_seconds  # Request latency distribution
corrections_made          # Distribution of corrections per essay
```

**Gauge** (point-in-time value):
```python
active_connections  # Current active connections
queue_size          # Current queue size
```

## Reference Documentation

- **Detailed Instrumentation Patterns**: See `reference.md` in this directory
- **Real-World Metrics Examples**: See `examples.md` in this directory
- **Prometheus Configuration**: `/observability/prometheus/prometheus.yml`
- **Critical Metrics Audit**: `/observability/CRITICAL_METRICS_AUDIT.md`
