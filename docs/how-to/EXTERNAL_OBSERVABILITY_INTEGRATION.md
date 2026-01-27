# HuleEdu Observability Integration Guide

> **Purpose**: Enable external development teams to build services that integrate with HuleEdu's observability infrastructure.

---

## Overview

HuleEdu uses a comprehensive observability stack based on open standards:

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Logging** | Structlog + Loki | Structured JSON logs with correlation |
| **Tracing** | OpenTelemetry + Jaeger | Distributed trace propagation |
| **Metrics** | Prometheus + Grafana | Service and business metrics |
| **Alerting** | Alertmanager | Threshold-based notifications |

---

## 1. Structured Logging

### Log Format Specification

All services emit **JSON-formatted logs** with these standard fields:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "event": "Content created",
  "service.name": "your_service",
  "deployment.environment": "production",
  "correlation_id": "abc-123-def-456",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331",
  "filename": "handler.py",
  "func_name": "create_content",
  "lineno": 42
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | Event timestamp (RFC 3339 format) |
| `level` | string | Log level: `debug`, `info`, `warning`, `error`, `critical` |
| `event` | string | Human-readable event description |
| `service.name` | string | Service identifier (OTEL semantic convention) |
| `deployment.environment` | string | Environment: `development`, `staging`, `production` |

### Recommended Fields

| Field | Type | Description |
|-------|------|-------------|
| `correlation_id` | UUID string | Request correlation across services |
| `trace_id` | 32-char hex | OpenTelemetry trace ID |
| `span_id` | 16-char hex | OpenTelemetry span ID |
| `event_type` | string | For event-driven: Kafka event type |
| `source_service` | string | For event-driven: originating service |

### Python Implementation Example

```python
import structlog
import os
from typing import Any

def add_service_context(logger: Any, method_name: str, event_dict: dict) -> dict:
    """Add OTEL-compatible service context to all logs."""
    event_dict["service.name"] = os.getenv("SERVICE_NAME", "unknown")
    event_dict["deployment.environment"] = os.getenv("ENVIRONMENT", "development")
    return event_dict

def add_trace_context(logger: Any, method_name: str, event_dict: dict) -> dict:
    """Add OpenTelemetry trace context when available."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            if ctx.is_valid:
                event_dict["trace_id"] = format(ctx.trace_id, "032x")
                event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:
        pass
    return event_dict

def configure_logging(service_name: str, log_level: str = "INFO"):
    """Configure structured JSON logging."""
    import logging
    
    os.environ.setdefault("SERVICE_NAME", service_name)
    
    processors = [
        structlog.contextvars.merge_contextvars,
        add_service_context,
        add_trace_context,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
        ),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
    
    logging.basicConfig(format="%(message)s", level=getattr(logging, log_level))
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
```

### Correlation ID Propagation

For cross-service request correlation:

```python
from structlog.contextvars import bind_contextvars, clear_contextvars
import uuid

# At request entry point (middleware)
async def before_request():
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    clear_contextvars()
    bind_contextvars(correlation_id=correlation_id)

# All subsequent logs automatically include correlation_id
logger.info("Processing request", user_id="123")
```

---

## 2. Distributed Tracing

### OpenTelemetry Configuration

Services use **OpenTelemetry** with OTLP export to Jaeger.

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import set_global_textmap
import os

def init_tracing(service_name: str) -> trace.Tracer:
    """Initialize distributed tracing."""
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        "service.namespace": "huleedu",
    })
    
    # OTLP exporter (Jaeger supports OTLP on port 4317)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    
    # W3C Trace Context for cross-service propagation
    set_global_textmap(TraceContextTextMapPropagator())
    
    return trace.get_tracer(service_name)
```

### Operation Tracing Pattern

```python
from contextlib import contextmanager
from opentelemetry.trace import Status, StatusCode

@contextmanager
def trace_operation(tracer, operation_name: str, attributes: dict = None):
    """Trace an operation with automatic error handling."""
    with tracer.start_as_current_span(operation_name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value) if value else "")
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            raise

# Usage
async def process_order(order_id: str):
    with trace_operation(tracer, "process_order", {"order.id": order_id}) as span:
        result = await do_processing()
        span.set_attribute("order.status", result.status)
        return result
```

### Cross-Service Context Propagation

For event-driven architectures (Kafka):

```python
from opentelemetry.propagate import inject, extract

# Producer: Inject context into event metadata
def publish_event(event_data: dict, metadata: dict):
    inject(metadata)  # Adds traceparent header
    kafka_producer.send(topic, value=event_data, headers=metadata)

# Consumer: Extract context from event metadata
def process_event(message):
    ctx = extract(message.headers)
    with trace.use_context(ctx):
        with tracer.start_as_current_span("process_event"):
            handle_event(message.value)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://jaeger:4317` | OTLP collector endpoint |
| `OTEL_SERVICE_NAME` | - | Service name (auto-set if using init_tracing) |
| `SERVICE_VERSION` | `1.0.0` | Service version for resource attributes |

---

## 3. Prometheus Metrics

### Metric Naming Convention

```
{service_name}_{subsystem}_{metric_name}_{unit}
```

Examples:
- `content_service_http_requests_total`
- `content_service_http_request_duration_seconds`
- `batch_orchestrator_database_query_duration_seconds`

### Standard HTTP Metrics

All HTTP services expose these metrics:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `{service}_http_requests_total` | Counter | method, endpoint, status_code | Total HTTP requests |
| `{service}_http_request_duration_seconds` | Histogram | method, endpoint | Request latency |

### Implementation Pattern

```python
from prometheus_client import Counter, Histogram, Gauge, REGISTRY, generate_latest
import time

# Define metrics
http_requests = Counter(
    "myservice_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

http_duration = Histogram(
    "myservice_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# Middleware pattern
async def metrics_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    
    http_requests.labels(
        method=request.method,
        endpoint=request.path,
        status_code=str(response.status_code),
    ).inc()
    
    http_duration.labels(
        method=request.method,
        endpoint=request.path,
    ).observe(duration)
    
    return response
```

### Database Metrics

For database-backed services:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `{service}_database_query_duration_seconds` | Histogram | operation, table, result | Query latency |
| `{service}_database_connections_active` | Gauge | - | Active connections |
| `{service}_database_connections_idle` | Gauge | - | Idle connections |
| `{service}_database_errors_total` | Counter | error_type, operation | Database errors |

### Business Metrics Examples

```python
# Batch processing metrics
batches_processed = Counter(
    "myservice_batches_processed_total",
    "Total batches processed",
    ["status", "type"],
)

processing_queue_size = Gauge(
    "myservice_processing_queue_size",
    "Current processing queue depth",
)

# Usage
batches_processed.labels(status="success", type="essay").inc()
processing_queue_size.set(queue.size())
```

---

## 4. Health Check Endpoint

### Standard Response Format

All services expose `/healthz` returning:

```json
{
  "service": "your_service_name",
  "status": "healthy",
  "message": "Service is healthy",
  "version": "1.0.0",
  "environment": "production",
  "checks": {
    "service_responsive": true,
    "dependencies_available": true
  },
  "dependencies": {
    "database": {"status": "healthy"},
    "kafka": {"status": "healthy"},
    "redis": {"status": "healthy"}
  }
}
```

### Implementation Pattern

```python
from quart import Blueprint, jsonify
from sqlalchemy import text

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz")
async def health_check():
    """Standardized health check endpoint."""
    checks = {"service_responsive": True, "dependencies_available": True}
    dependencies = {}
    overall_status = "healthy"
    
    # Check database
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        dependencies["database"] = {"status": "healthy"}
    except Exception as e:
        dependencies["database"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
        checks["dependencies_available"] = False
    
    # Check other dependencies (Redis, Kafka, etc.)
    # ...
    
    status_code = 200 if overall_status == "healthy" else 503
    return jsonify({
        "service": settings.SERVICE_NAME,
        "status": overall_status,
        "message": f"Service is {overall_status}",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "checks": checks,
        "dependencies": dependencies,
    }), status_code
```

---

## 5. Metrics Endpoint

### Standard Metrics Exposure

All services expose `/metrics` for Prometheus scraping:

```python
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, REGISTRY
from quart import Blueprint, Response

metrics_bp = Blueprint("metrics", __name__)

@metrics_bp.route("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest(REGISTRY)
    return Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
```

---

## 6. Infrastructure Integration

### Prometheus Scrape Configuration

Register your service in Prometheus config:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'your_service'
    static_configs:
      - targets: ['your_service:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Loki/Promtail Log Collection

Logs are collected from Docker containers automatically. Ensure your service:

1. **Outputs to stdout/stderr** (no file logging required)
2. **Emits JSON format** (parsed by Promtail)
3. **Includes standard fields** (level, timestamp, service.name)

Promtail extracts and indexes:
- `level` → Label (for filtering: `{level="error"}`)
- `service` → Label (for filtering: `{service="your_service"}`)
- Other fields → Available via JSON parsing in queries

### Jaeger Trace Collection

Services send traces via OTLP gRPC:
- **Endpoint**: `http://jaeger:4317` (internal Docker network)
- **External UI**: `http://localhost:16686`

---

## 7. Alert Integration

### Standard Alert Rules

HuleEdu uses threshold-based alerting. Example alert:

```yaml
# prometheus/rules/your-service-alerts.yml
groups:
- name: YourServiceAlerts
  rules:
  - alert: ServiceDown
    expr: up{job="your_service"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "{{ $labels.job }} is down"
      description: "Service has been down for more than 1 minute."

  - alert: HighErrorRate
    expr: rate(your_service_http_requests_total{status_code=~"5.."}[5m]) > 0.1
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "High error rate in {{ $labels.job }}"
      description: "5xx error rate exceeds 10% over 5 minutes."
```

### Alertmanager Webhook Integration

Configure alertmanager to send notifications:

```yaml
# alertmanager.yml
receivers:
- name: 'your-team'
  webhook_configs:
  - url: 'https://your-notification-endpoint/webhook'
    send_resolved: true
```

---

## 8. Quick Start Checklist

### Minimum Requirements

- [ ] **JSON logging** with `timestamp`, `level`, `event`, `service.name`
- [ ] **`/healthz` endpoint** returning standard health response
- [ ] **`/metrics` endpoint** exposing Prometheus metrics
- [ ] **Correlation ID** propagation via `X-Correlation-ID` header

### Recommended Additions

- [ ] **OpenTelemetry tracing** with OTLP export
- [ ] **HTTP request metrics** (requests_total, request_duration_seconds)
- [ ] **Database metrics** (query_duration, connection_pool status)
- [ ] **Business metrics** for key operations

### Environment Variables

```bash
# Required
SERVICE_NAME=your_service
ENVIRONMENT=development|staging|production

# Logging
LOG_LEVEL=INFO|DEBUG|WARNING|ERROR
LOG_FORMAT=json|console

# Tracing
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# Optional: File logging
LOG_TO_FILE=false
LOG_FILE_PATH=/app/logs/your_service.log
LOG_MAX_BYTES=104857600
LOG_BACKUP_COUNT=10
```

---

## 9. Dependencies

### Python Packages

```txt
# Logging
structlog>=25.3.0

# Metrics
prometheus-client>=0.20.0

# Tracing
opentelemetry-api>=1.25.0
opentelemetry-sdk>=1.25.0
opentelemetry-exporter-otlp-proto-grpc>=1.25.0
opentelemetry-instrumentation>=0.46b0
```

### Docker Network

Services must connect to `huleedu_internal_network` for observability components:

```yaml
# docker-compose.yml
services:
  your_service:
    networks:
      - huleedu_internal_network
```

---

## 10. Observability Stack Ports Reference

| Service | Internal Port | External Port | Purpose |
|---------|--------------|---------------|---------|
| Prometheus | 9090 | 9091 | Metrics storage |
| Grafana | 3000 | 3000 | Dashboards |
| Jaeger UI | 16686 | 16686 | Trace visualization |
| Jaeger OTLP | 4317 | 4317 | Trace ingestion (gRPC) |
| Loki | 3100 | 3100 | Log aggregation |
| Alertmanager | 9093 | 9094 | Alert routing |

---

## Reference Implementation

See these HuleEdu services for complete examples:

- **File Service**: Simple HTTP service with health checks and metrics
- **Batch Orchestrator Service**: Complex service with database monitoring
- **LLM Provider Service**: Service with custom business metrics

---

*Last Updated: December 2024*
