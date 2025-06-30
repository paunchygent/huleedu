# Observability Enhancement Implementation Plan

## Current Status Summary

### ✅ Completed (Phase 1-3)
- **Distributed Tracing Infrastructure**: Jaeger deployed and integrated
- **Service Library Enhancement**: OpenTelemetry utilities added
- **Full Pipeline Instrumentation**: All critical services instrumented
- **Trace Propagation**: End-to-end trace context propagation verified
- **Correlation ID Flow**: Preserved across all service boundaries

### 🚧 In Progress (Phase 4)
- **Debugging Tools**: Creating trace search scripts and dashboards
- **Enhanced Error Context**: Implementing rich error handling

### 📋 Next Steps
- Complete Phase 4: Debugging tools and dashboards
- Phase 5: Enhanced error recovery and circuit breakers
- Phase 6: Testing and validation

## Overview

This plan details how to implement distributed tracing, enhanced monitoring dashboards, and improved error recovery to enable effective debugging of container issues in the HuleEdu platform.

## Phase 1: Distributed Tracing Foundation (Week 1) ✅ COMPLETE

### 1.1 Add OpenTelemetry to Service Library ✅

**Files Modified:**

- `services/libs/huleedu_service_libs/observability/tracing.py` ✅
- `services/libs/huleedu_service_libs/pyproject.toml` ✅

**Implementation:**

```python
# tracing.py
from typing import Optional, Dict, Any
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.aiohttp import AioHttpClientInstrumentor
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import Status, StatusCode

class TracingManager:
    """Manages distributed tracing for services."""
    
    def __init__(self, service_name: str, jaeger_endpoint: str):
        self.service_name = service_name
        self.tracer = self._initialize_tracer(service_name, jaeger_endpoint)
    
    def _initialize_tracer(self, service_name: str, endpoint: str) -> trace.Tracer:
        # Set up Jaeger exporter
        jaeger_exporter = JaegerExporter(
            agent_host_name=endpoint.split(':')[0],
            agent_port=int(endpoint.split(':')[1]) if ':' in endpoint else 6831,
        )
        
        # Create tracer provider
        provider = TracerProvider()
        processor = BatchSpanProcessor(jaeger_exporter)
        provider.add_span_processor(processor)
        
        # Set global tracer provider
        trace.set_tracer_provider(provider)
        
        # Instrument aiohttp client
        AioHttpClientInstrumentor().instrument()
        
        return trace.get_tracer(service_name)
```

### 1.2 Create Tracing Middleware ✅

**Files Created:**

- `services/libs/huleedu_service_libs/middleware/frameworks/quart_middleware.py` ✅
- `services/libs/huleedu_service_libs/middleware/frameworks/fastapi_middleware.py` ✅

**Implementation:**

```python
# tracing_middleware.py
from quart import Request, Response, g
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Status, StatusCode
import json

async def tracing_before_request(tracer: trace.Tracer) -> None:
    """Extract trace context and start span for incoming requests."""
    from quart import request
    
    # Extract trace context from headers
    context = extract(request.headers)
    
    # Start new span
    span = tracer.start_span(
        f"{request.method} {request.path}",
        context=context,
        kind=trace.SpanKind.SERVER
    )
    
    # Store span in request context
    g.current_span = span
    
    # Add span attributes
    span.set_attribute("http.method", request.method)
    span.set_attribute("http.url", str(request.url))
    span.set_attribute("http.path", request.path)
    
    # Extract or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID", g.request_id)
    span.set_attribute("correlation_id", correlation_id)
    g.correlation_id = correlation_id

async def tracing_after_request(response: Response) -> Response:
    """Complete span and inject trace context into response."""
    if hasattr(g, 'current_span'):
        span = g.current_span
        
        # Set response attributes
        span.set_attribute("http.status_code", response.status_code)
        
        # Set span status based on HTTP status
        if response.status_code >= 400:
            span.set_status(Status(StatusCode.ERROR))
        
        # Inject trace context into response headers
        inject(response.headers)
        
        # End span
        span.end()
    
    return response
```

### 1.3 Enhance Kafka Event Tracing ✅

**Files Modified:**

- `common_core/src/common_core/events/envelope.py` ✅ (Added metadata field)
- All event publishers and processors ✅ (Added trace injection/extraction)

**Implementation:**

```python
# In kafka_bus.py - add trace context propagation
async def publish_event(self, event: EventEnvelope) -> None:
    """Publish event with trace context."""
    # Get current span
    current_span = trace.get_current_span()
    
    if current_span:
        # Create child span for publishing
        with self._tracer.start_as_current_span(
            f"kafka.publish.{event.event_type}",
            kind=trace.SpanKind.PRODUCER
        ) as span:
            # Add event attributes
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)
            span.set_attribute("messaging.operation", "publish")
            span.set_attribute("event.type", event.event_type)
            span.set_attribute("event.id", str(event.event_id))
            
            # Inject trace context into event metadata
            trace_headers = {}
            inject(trace_headers)
            
            # Add trace context to event envelope
            if not hasattr(event, 'metadata'):
                event.metadata = {}
            event.metadata['trace_context'] = trace_headers
            
            # Publish event
            await self._producer.send_and_wait(topic, event_bytes)
```

## Phase 2: Service Integration (Week 1-2) ✅ COMPLETE

### 2.1 Update Service Startup ✅

**Files Modified:**

- `services/batch_orchestrator_service/startup_setup.py` ✅
- `services/essay_lifecycle_service/app.py` ✅
- `services/spell_checker_service/startup_setup.py` ✅
- `services/cj_assessment_service/app.py` ✅ (via DI provider)

**Example for Batch Orchestrator Service:**

```python
# In startup_setup.py
from huleedu_service_libs.observability.tracing import TracingManager

async def setup_tracing(app: Quart) -> None:
    """Initialize distributed tracing."""
    jaeger_endpoint = os.getenv("JAEGER_AGENT_HOST", "jaeger:6831")
    service_name = "batch_orchestrator_service"
    
    # Create tracing manager
    tracing_manager = TracingManager(service_name, jaeger_endpoint)
    
    # Store in app context
    app.tracing = tracing_manager
    
    # Register middleware
    @app.before_request
    async def before_request():
        await tracing_before_request(tracing_manager.tracer)
    
    @app.after_request
    async def after_request(response):
        return await tracing_after_request(response)

# Add to initialize_app function
async def initialize_app(app: Quart) -> None:
    """Initialize application with all required components."""
    await setup_logging(app)
    await setup_metrics(app)
    await setup_tracing(app)  # NEW
    await setup_dishka(app)
```

### 2.2 Instrument Kafka Consumers ✅

**Files Modified:**

- `services/spell_checker_service/event_processor.py` ✅
- `services/essay_lifecycle_service/batch_command_handlers.py` ✅
- `services/cj_assessment_service/event_processor.py` ✅

**Example Enhancement:**

```python
# In kafka consumer handling
async def handle_message(self, message: ConsumerRecord) -> None:
    """Handle Kafka message with tracing."""
    # Extract trace context from event metadata
    event_envelope = EventEnvelope.model_validate_json(message.value)
    trace_context = event_envelope.metadata.get('trace_context', {})
    
    # Start span with parent context
    context = extract(trace_context) if trace_context else None
    
    with self._tracer.start_as_current_span(
        f"kafka.consume.{event_envelope.event_type}",
        context=context,
        kind=trace.SpanKind.CONSUMER
    ) as span:
        # Add span attributes
        span.set_attribute("messaging.system", "kafka")
        span.set_attribute("messaging.source", message.topic)
        span.set_attribute("messaging.operation", "consume")
        span.set_attribute("event.type", event_envelope.event_type)
        span.set_attribute("event.id", str(event_envelope.event_id))
        span.set_attribute("correlation_id", str(event_envelope.correlation_id))
        
        try:
            # Process message
            await self._process_event(event_envelope)
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
```

## Phase 3: Deploy Jaeger (Week 1) ✅ COMPLETE

### 3.1 Add Jaeger to Observability Stack ✅

**File Modified:**

- `observability/docker-compose.observability.yml` ✅

**Addition:**

```yaml
  jaeger:
    image: jaegertracing/all-in-one:1.50
    container_name: huleedu_jaeger
    networks:
      - huleedu_observability_network
    ports:
      - "5775:5775/udp"  # Zipkin/thrift compact
      - "6831:6831/udp"  # Jaeger thrift compact
      - "6832:6832/udp"  # Jaeger thrift binary
      - "5778:5778"      # Config/sampling
      - "16686:16686"    # Jaeger UI
      - "14268:14268"    # Jaeger collector HTTP
      - "14250:14250"    # Jaeger collector gRPC
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    volumes:
      - jaeger_data:/tmp
```

### 3.2 Update Service Docker Configs ✅

**Files Modified:**

- `docker-compose.yml` ✅
- All service environment configurations ✅

**Addition:**

```yaml
    environment:
      - JAEGER_AGENT_HOST=jaeger
      - JAEGER_AGENT_PORT=6831
      - OTEL_EXPORTER_JAEGER_ENDPOINT=http://jaeger:14268/api/traces
```

## Phase 4: Enhanced Error Context (Week 2)

### 4.1 Create Error Context Manager

**File to Create:**

- `services/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/context_manager.py`

**Implementation:**

```python
# context_manager.py
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import traceback
from opentelemetry import trace

@dataclass
class ErrorContext:
    """Rich error context for debugging."""
    error_type: str
    error_message: str
    service_name: str
    operation: str
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    stack_trace: Optional[str] = None
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "service_name": self.service_name,
            "operation": operation,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace,
            "context_data": self.context_data
        }

class EnhancedError(Exception):
    """Base exception with rich context."""
    
    def __init__(self, message: str, context: ErrorContext):
        super().__init__(message)
        self.context = context
    
    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        service_name: str,
        operation: str,
        context_data: Optional[Dict[str, Any]] = None
    ) -> 'EnhancedError':
        """Create from existing exception with context."""
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context() if current_span else None
        
        error_context = ErrorContext(
            error_type=type(exception).__name__,
            error_message=str(exception),
            service_name=service_name,
            operation=operation,
            trace_id=format(span_context.trace_id, 'x') if span_context else None,
            span_id=format(span_context.span_id, 'x') if span_context else None,
            stack_trace=traceback.format_exc(),
            context_data=context_data or {}
        )
        
        return cls(str(exception), error_context)
```

### 4.2 Implement Circuit Breaker

**File to Create:**

- `services/libs/huleedu_service_libs/src/huleedu_service_libs/resilience/circuit_breaker.py`

**Implementation:**

```python
# circuit_breaker.py
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from opentelemetry import trace

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit breaker for service resilience."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: timedelta = timedelta(seconds=60),
        expected_exception: type = Exception,
        tracer: Optional[trace.Tracer] = None
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.tracer = tracer or trace.get_tracer(__name__)
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self.tracer.start_as_current_span(
            f"circuit_breaker.{func.__name__}",
            attributes={
                "circuit.state": self.state.value,
                "circuit.failure_count": self.failure_count
            }
        ) as span:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    span.set_attribute("circuit.state_change", "half_open")
                else:
                    span.set_attribute("circuit.blocked", True)
                    raise Exception(f"Circuit breaker is OPEN for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                span.set_attribute("circuit.success", True)
                return result
            except self.expected_exception as e:
                self._on_failure()
                span.record_exception(e)
                span.set_attribute("circuit.failure", True)
                raise
```

## Phase 5: Enhanced Dashboards (Week 2-3)

### 5.1 Create Distributed Tracing Dashboard

**File to Create:**

- `observability/grafana-dashboards/tier3-distributed-tracing.json`

**Key Panels:**

1. **Service Dependency Map** - Visualize service interactions
2. **Request Flow Timeline** - Trace requests through services
3. **Error Hotspots** - Services/operations with most errors
4. **Latency Distribution** - P50/P95/P99 by service
5. **Correlation ID Search** - Find all related logs/traces

### 5.2 Enhance Pipeline Dashboard

**File to Modify:**

- `observability/grafana-dashboards/tier2-batch-orchestrator.json`

**Add Panels:**

```json
{
  "title": "Pipeline Phase Status",
  "targets": [{
    "expr": "sum by (phase, status) (bos_batch_phase_status)",
    "legendFormat": "{{phase}} - {{status}}"
  }]
},
{
  "title": "Storage Reference Propagation",
  "targets": [{
    "expr": "rate(els_storage_reference_updates_total[5m])",
    "legendFormat": "Updates/sec"
  }]
},
{
  "title": "Service Error Context",
  "datasource": "Loki",
  "targets": [{
    "expr": "{service_name=~\".*\"} |= \"error_context\" | json",
    "legendFormat": "{{service_name}}"
  }]
}
```

### 5.3 Create Alert Rules for Debugging

**File to Modify:**

- `observability/prometheus/alerts.yml`

**Add Rules:**

```yaml
- name: debugging_alerts
  rules:
    - alert: HighTraceErrorRate
      expr: |
        (sum(rate(span_errors_total[5m])) by (service_name, operation))
        / (sum(rate(span_total[5m])) by (service_name, operation)) > 0.1
      for: 2m
      annotations:
        summary: "High error rate in {{ $labels.service_name }} - {{ $labels.operation }}"
        trace_search: "http://jaeger:16686/search?service={{ $labels.service_name }}&operation={{ $labels.operation }}"
    
    - alert: StorageReferencePropagationFailure
      expr: |
        rate(els_storage_reference_failures_total[5m]) > 0
      for: 1m
      annotations:
        summary: "Storage reference propagation failures detected"
        dashboard: "http://grafana:3000/d/tier2-els/essay-lifecycle-service"
```

## Phase 6: Implementation Testing (Week 3)

### 6.1 Create Tracing Test Suite

**File to Create:**

- `tests/integration/test_distributed_tracing.py`

**Test Scenarios:**

1. Trace propagation across HTTP calls
2. Trace propagation through Kafka events
3. Error context enrichment
4. Circuit breaker functionality
5. Correlation ID consistency

### 6.2 Update E2E Tests

**File to Modify:**

- `tests/functional/test_e2e_comprehensive_real_batch.py`

**Add Trace Assertions:**

```python
async def verify_trace_completeness(correlation_id: str):
    """Verify distributed trace captures full pipeline."""
    # Query Jaeger API for trace
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:16686/api/traces?service=batch_orchestrator_service&tags={{correlation_id:{correlation_id}}}"
        async with session.get(url) as response:
            traces = await response.json()
    
    # Verify expected spans exist
    expected_operations = [
        "POST /api/v1/batches/register",
        "kafka.publish.huleedu.spell_checker.check_request.v1",
        "kafka.consume.huleedu.spell_checker.check_request.v1",
        "kafka.publish.huleedu.spell_checker.check_complete.v1",
        "storage_reference_update",
        "kafka.publish.huleedu.cj_assessment.assessment_request.v1"
    ]
    
    spans = traces[0]["spans"]
    operations = [span["operationName"] for span in spans]
    
    for expected in expected_operations:
        assert expected in operations, f"Missing span: {expected}"
```

## Implementation Schedule

### Week 1 ✅ COMPLETE

- [x] Add OpenTelemetry to service library
- [x] Create tracing middleware
- [x] Deploy Jaeger
- [x] Integrate tracing in all critical services (BOS, ELS, Spell Checker, CJ Assessment)

### Week 2 (In Progress)

- [x] Roll out tracing to all services
- [ ] Implement enhanced error context
- [ ] Create circuit breaker
- [ ] Begin dashboard enhancements

### Week 3

- [ ] Complete dashboard updates
- [ ] Add alert rules
- [ ] Create test suite
- [ ] Documentation and training

## Success Metrics

1. **Trace Coverage**: 100% of service interactions traced
2. **Error Context**: All errors include trace ID and rich context
3. **Dashboard Usage**: Teams using tracing dashboard daily
4. **Debug Time**: 50% reduction in container issue resolution time
5. **Alert Accuracy**: <5% false positive rate on new alerts

## Next Steps After Implementation

1. Add custom business transaction tracking
2. Implement SLO monitoring with error budgets
3. Create automated root cause analysis
4. Add performance profiling integration
5. Implement chaos engineering with observability
