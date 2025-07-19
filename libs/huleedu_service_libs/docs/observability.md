# Observability

Comprehensive logging, tracing, and metrics collection for HuleEdu microservices.

## Overview

The observability utilities provide structured logging, distributed tracing, and Prometheus metrics collection with OpenTelemetry integration. These tools enable comprehensive monitoring and debugging of distributed systems.

### Key Features

- **Structured Logging**: JSON-formatted logs with correlation IDs and context
- **Distributed Tracing**: OpenTelemetry integration with trace propagation
- **Prometheus Metrics**: HTTP metrics, database monitoring, and business metrics
- **Correlation Context**: Automatic correlation ID propagation across service boundaries
- **Request Tracking**: HTTP middleware for request/response logging and timing

## Logging Utilities

**Module**: `logging_utils.py`  
**Purpose**: Structured logging configuration with service-specific context

### Configuration

```python
from huleedu_service_libs.logging_utils import configure_service_logging

# Configure structured logging for service
configure_service_logging(
    service_name="content_service",
    environment="production",
    log_level="INFO"
)

# Logger is now configured globally
import structlog
logger = structlog.get_logger()
```

### Usage Examples

```python
import structlog

logger = structlog.get_logger()

# Structured logging with context
logger.info(
    "Content created",
    content_id="content123",
    user_id="user456",
    correlation_id="abc-123-def",
    operation="create_content"
)

# Error logging with exception context
try:
    await risky_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        operation="risky_operation",
        error=str(e),
        correlation_id="abc-123-def"
    )
```

### Log Format

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "message": "Content created",
  "service": "content_service",
  "environment": "production",
  "content_id": "content123",
  "user_id": "user456",
  "correlation_id": "abc-123-def",
  "operation": "create_content"
}
```

## Distributed Tracing

**Module**: `observability/tracing.py`  
**Purpose**: OpenTelemetry tracing with correlation context propagation

### Setup

```python
from huleedu_service_libs.observability import init_tracing, trace_operation

# Initialize tracing for service
tracer = init_tracing(service_name="content_service")

# Store in app for access
app.tracer = tracer
```

### Operation Tracing

```python
from huleedu_service_libs.observability import trace_operation

class ContentService:
    def __init__(self, tracer):
        self.tracer = tracer
    
    async def create_content(self, data: dict) -> Content:
        with trace_operation(self.tracer, "create_content") as span:
            # Add operation context
            span.set_attribute("content.title", data["title"])
            span.set_attribute("content.user_id", data["user_id"])
            
            # Business logic
            content = await self._process_content(data)
            
            # Add result context
            span.set_attribute("content.id", content.id)
            span.set_status(Status(StatusCode.OK))
            
            return content
```

### Context Propagation

```python
from huleedu_service_libs.observability import inject_trace_context, extract_trace_context

# Inject context into outgoing events
async def publish_event(envelope: EventEnvelope):
    # Add trace context to event metadata
    envelope.metadata = inject_trace_context(envelope.metadata or {})
    await kafka_bus.publish("events", envelope)

# Extract context from incoming events
async def process_event(envelope: EventEnvelope):
    # Extract and use trace context
    with extract_trace_context(envelope.metadata or {}):
        await handle_event(envelope.data)
```

### Middleware Integration

```python
from huleedu_service_libs.observability import setup_tracing_middleware

# Add tracing to HTTP requests
setup_tracing_middleware(app, tracer)

# Automatic request tracing with:
# - Span per HTTP request
# - Request/response attributes
# - Error tracking
# - Correlation ID propagation
```

## Metrics Collection

**Module**: `metrics_middleware.py`  
**Purpose**: HTTP request metrics and custom business metrics

### Standard HTTP Metrics

```python
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware

# Add standard HTTP metrics
setup_standard_service_metrics_middleware(app, service_name="content_service")

# Collected metrics:
# - {service}_http_requests_total
# - {service}_http_request_duration_seconds  
# - {service}_http_request_size_bytes
# - {service}_http_response_size_bytes
```

### Custom Business Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Define business metrics
content_created_total = Counter(
    "content_service_content_created_total",
    "Total content items created",
    ["user_type", "content_type"]
)

processing_duration = Histogram(
    "content_service_processing_duration_seconds",
    "Time spent processing content",
    ["operation", "content_type"]
)

active_users = Gauge(
    "content_service_active_users",
    "Number of active users"
)

# Use in service implementation
class ContentService:
    async def create_content(self, data: dict) -> Content:
        with processing_duration.labels(
            operation="create", 
            content_type=data["type"]
        ).time():
            content = await self._create_content(data)
            
            content_created_total.labels(
                user_type=data["user_type"],
                content_type=data["type"]
            ).inc()
            
            return content
```

## Request Context Management

### Correlation ID Handling

```python
from huleedu_service_libs.observability import get_correlation_id, set_correlation_id

# In middleware or route handlers
@app.before_request
async def before_request():
    # Extract or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    set_correlation_id(correlation_id)

# Use throughout request processing
async def process_request():
    correlation_id = get_correlation_id()
    logger.info("Processing request", correlation_id=correlation_id)
```

### Error Tracking

```python
from huleedu_service_libs.observability import track_error

async def handle_request():
    try:
        result = await process_request()
        return result
    except Exception as e:
        # Track error with context
        track_error(
            error=e,
            operation="handle_request",
            correlation_id=get_correlation_id(),
            additional_context={"user_id": user_id}
        )
        raise
```

## Integration Patterns

### Complete Service Setup

```python
# In startup_setup.py
from huleedu_service_libs.logging_utils import configure_service_logging
from huleedu_service_libs.observability import init_tracing, setup_tracing_middleware
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware

async def setup_observability(app: Quart, settings: Settings):
    # Configure structured logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL
    )
    
    # Initialize distributed tracing
    tracer = init_tracing(settings.SERVICE_NAME)
    app.tracer = tracer
    
    # Setup middleware
    setup_tracing_middleware(app, tracer)
    setup_standard_service_metrics_middleware(app, settings.SERVICE_NAME)
    
    logger.info("Observability configured", service=settings.SERVICE_NAME)
```

### Event Processing with Tracing

```python
from huleedu_service_libs.observability import trace_operation, extract_trace_context

class EventProcessor:
    def __init__(self, tracer):
        self.tracer = tracer
    
    async def process_event(self, msg: ConsumerRecord):
        envelope = EventEnvelope.model_validate_json(msg.value)
        
        # Extract trace context from event
        with extract_trace_context(envelope.metadata or {}):
            with trace_operation(self.tracer, "process_event") as span:
                span.set_attribute("event.type", envelope.event_type)
                span.set_attribute("event.source", envelope.source_service)
                
                await self._handle_event(envelope)
```

## Configuration

### Environment Variables

- `OTEL_EXPORTER_OTLP_ENDPOINT`: OpenTelemetry collector endpoint
- `OTEL_SERVICE_NAME`: Service name for tracing (auto-set from SERVICE_NAME)
- `OTEL_RESOURCE_ATTRIBUTES`: Additional resource attributes
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `ENVIRONMENT`: Environment name for context

### Tracing Configuration

```python
# Custom tracing configuration
from huleedu_service_libs.observability import configure_tracing

configure_tracing(
    service_name="content_service",
    service_version="1.2.0",
    environment="production",
    otlp_endpoint="http://jaeger:4317",
    sample_rate=0.1  # 10% sampling for high-volume services
)
```

## Testing

### Mock Tracing in Tests

```python
from unittest.mock import Mock
from huleedu_service_libs.observability import trace_operation

def test_traced_operation():
    mock_tracer = Mock()
    mock_span = Mock()
    mock_tracer.start_span.return_value.__enter__.return_value = mock_span
    
    async def traced_function():
        with trace_operation(mock_tracer, "test_operation") as span:
            span.set_attribute("test.value", "example")
            return "result"
    
    result = await traced_function()
    
    assert result == "result"
    mock_tracer.start_span.assert_called_once_with("test_operation")
    mock_span.set_attribute.assert_called_once_with("test.value", "example")
```

### Test Log Assertions

```python
from huleedu_service_libs.testing import LogCapture

async def test_logging():
    with LogCapture() as log_capture:
        logger.info("Test message", user_id="123", operation="test")
        
        # Assert log content
        log_capture.assert_log_contains(
            level="info",
            message="Test message",
            user_id="123"
        )
```

## Best Practices

1. **Structured Logging**: Always use keyword arguments for context
2. **Correlation IDs**: Propagate correlation IDs across all operations
3. **Trace Context**: Extract and inject trace context for distributed calls
4. **Error Tracking**: Log errors with full context and correlation IDs
5. **Business Metrics**: Track key business operations and outcomes
6. **Sampling**: Use appropriate sampling rates for high-volume services
7. **Resource Attribution**: Include service name, version, and environment
8. **Middleware Setup**: Configure observability early in application startup

## Anti-Patterns to Avoid

1. **Unstructured Logging**: Don't use string formatting in log messages
2. **Missing Correlation**: Always include correlation IDs in logs and traces
3. **Synchronous Operations**: Use async throughout observability stack
4. **Resource Leaks**: Properly close spans and release resources
5. **Over-instrumentation**: Don't trace every tiny operation
6. **Missing Context**: Include operation context in all traces
7. **Hardcoded Configuration**: Use environment variables for configuration
8. **Ignoring Errors**: Always handle and log errors appropriately