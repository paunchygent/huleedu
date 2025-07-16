---
inclusion: always
---

# Observability and Monitoring Patterns

## Metrics Standards

### Prometheus Metrics Integration
Every service MUST implement these standard metrics:

```python
from huleedu_service_libs.metrics import (
    request_duration_histogram,
    request_count_counter,
    error_count_counter,
    active_connections_gauge
)

# HTTP request metrics
@request_duration_histogram.time()
@request_count_counter.count()
async def handle_request():
    try:
        # Request processing
        pass
    except Exception as e:
        error_count_counter.inc(labels={"error_type": type(e).__name__})
        raise
```

### Custom Business Metrics
```python
# Service-specific metrics
essay_processing_duration = Histogram(
    'essay_processing_duration_seconds',
    'Time spent processing essays',
    ['service_name', 'processing_phase']
)

batch_size_gauge = Gauge(
    'current_batch_size',
    'Current number of essays in processing batch',
    ['batch_id']
)
```

## Logging Standards

### Structured Logging Pattern
```python
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

# Standard log format with correlation ID
logger.info(
    "Processing essay",
    extra={
        "essay_id": essay.id,
        "batch_id": batch.id,
        "processing_phase": "spellcheck",
        "correlation_id": correlation_id
    }
)
```

### Error Logging with Context
```python
try:
    await process_essay(essay)
except Exception as e:
    logger.error(
        "Essay processing failed",
        extra={
            "essay_id": essay.id,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "correlation_id": correlation_id
        },
        exc_info=True
    )
    raise
```

## Health Check Patterns

### Standard Health Endpoint
```python
from quart import Blueprint, jsonify
from huleedu_service_libs.health import HealthChecker

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz")
async def health_check():
    health_checker = HealthChecker()
    
    # Check dependencies
    db_healthy = await health_checker.check_database()
    kafka_healthy = await health_checker.check_kafka()
    redis_healthy = await health_checker.check_redis()
    
    status = "healthy" if all([db_healthy, kafka_healthy, redis_healthy]) else "unhealthy"
    
    return jsonify({
        "status": status,
        "dependencies": {
            "database": "healthy" if db_healthy else "unhealthy",
            "kafka": "healthy" if kafka_healthy else "unhealthy",
            "redis": "healthy" if redis_healthy else "unhealthy"
        },
        "timestamp": datetime.utcnow().isoformat()
    })
```

## Distributed Tracing

### Correlation ID Propagation
```python
from huleedu_service_libs.tracing import get_correlation_id, set_correlation_id

# HTTP request handling
@app.before_request
async def before_request():
    correlation_id = request.headers.get('X-Correlation-ID') or str(uuid4())
    set_correlation_id(correlation_id)

# Event processing
async def process_event(event: EventEnvelope):
    set_correlation_id(event.correlation_id)
    # Process event with correlation context
```

### Jaeger Integration
```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Service initialization
def setup_tracing(service_name: str):
    tracer = trace.get_tracer(service_name)
    
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )
    
    return tracer
```

## Alerting Patterns

### Critical Error Alerts
- Service startup failures
- Database connection failures
- High error rates (>5% over 5 minutes)
- Memory usage >80%
- Disk usage >90%

### Performance Alerts
- Response time >2 seconds (95th percentile)
- Queue depth >1000 messages
- Processing lag >5 minutes
- Connection pool exhaustion

### Business Logic Alerts
- Essay processing failures >10% in batch
- LLM service unavailable >1 minute
- Batch processing stuck >30 minutes
- Data inconsistency detected