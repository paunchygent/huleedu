# Quick Start: Minimal Observability Implementation

## Goal
Get basic distributed tracing working in 1-2 days to immediately improve debugging capability.

## Step 1: Deploy Jaeger (30 minutes)

### 1.1 Add to observability stack
```yaml
# observability/docker-compose.observability.yml
  jaeger:
    image: jaegertracing/all-in-one:1.50
    container_name: huleedu_jaeger
    networks:
      - huleedu_observability_network
    ports:
      - "16686:16686"    # Jaeger UI
      - "6831:6831/udp"  # Jaeger agent
    environment:
      - COLLECTOR_OTLP_ENABLED=true
```

### 1.2 Start Jaeger
```bash
pdm run obs-down
pdm run obs-up
# Verify at http://localhost:16686
```

## Step 2: Add Basic Tracing to Service Library (2 hours)

### 2.1 Update dependencies
```toml
# services/libs/huleedu_service_libs/pyproject.toml
dependencies = [
    # existing deps...
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-instrumentation-aiohttp>=0.41b0",
    "opentelemetry-exporter-jaeger>=1.20.0",
]
```

### 2.2 Create minimal tracing module
```python
# services/libs/huleedu_service_libs/src/huleedu_service_libs/tracing/__init__.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import os

def init_tracing(service_name: str) -> trace.Tracer:
    """Initialize Jaeger tracing for a service."""
    resource = Resource.create({"service.name": service_name})
    
    jaeger_host = os.getenv("JAEGER_AGENT_HOST", "localhost")
    jaeger_port = int(os.getenv("JAEGER_AGENT_PORT", "6831"))
    
    exporter = JaegerExporter(
        agent_host_name=jaeger_host,
        agent_port=jaeger_port,
    )
    
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    
    return trace.get_tracer(service_name)
```

## Step 3: Add Tracing to Critical Services (4 hours)

### 3.1 Batch Orchestrator Service
```python
# services/batch_orchestrator_service/startup_setup.py
from huleedu_service_libs.tracing import init_tracing

async def initialize_app(app: Quart) -> None:
    """Initialize application with all required components."""
    # Existing setup...
    
    # Initialize tracing
    app.tracer = init_tracing("batch_orchestrator_service")
    
    # Add simple middleware
    @app.before_request
    async def start_trace():
        from quart import request, g
        span = app.tracer.start_span(
            f"{request.method} {request.path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.path": request.path,
            }
        )
        g.span = span
    
    @app.after_request
    async def end_trace(response):
        from quart import g
        if hasattr(g, 'span'):
            g.span.set_attribute("http.status_code", response.status_code)
            g.span.end()
        return response
```

### 3.2 Essay Lifecycle Service - Critical Handler
```python
# services/essay_lifecycle_service/implementations/service_result_handler_impl.py

# At the top of the file
from opentelemetry import trace
tracer = trace.get_tracer("essay_lifecycle_service")

# In handle_spell_check_complete method
async def handle_spell_check_complete(self, event_data: SpellCheckCompleteEvent) -> None:
    """Handle spell check completion with tracing."""
    with tracer.start_as_current_span(
        "handle_spell_check_complete",
        attributes={
            "batch_id": event_data.batch_id,
            "essay_id": event_data.essay_id,
            "correlation_id": str(event_data.correlation_id) if hasattr(event_data, 'correlation_id') else None
        }
    ) as span:
        try:
            # Get content reference
            content_ref = event_data.output
            
            # CRITICAL SECTION - Add detailed logging
            with tracer.start_as_current_span("extract_storage_reference") as subspan:
                spellchecked_ref = content_ref.get(ContentType.SPELLCHECKED)
                
                if spellchecked_ref:
                    # Log what keys are available
                    available_keys = list(spellchecked_ref.keys())
                    subspan.set_attribute("available_keys", str(available_keys))
                    
                    # Try both possible keys
                    storage_id = spellchecked_ref.get("storage_id") or spellchecked_ref.get("default")
                    
                    subspan.set_attribute("storage_id", storage_id or "NOT_FOUND")
                    subspan.set_attribute("spellchecked_data", str(spellchecked_ref))
                    
                    if not storage_id:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        self._logger.error(
                            f"No storage ID found. Available keys: {available_keys}",
                            extra={
                                "batch_id": event_data.batch_id,
                                "essay_id": event_data.essay_id,
                                "spellchecked_ref": spellchecked_ref
                            }
                        )
            
            # Continue with existing logic...
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
```

### 3.3 CJ Assessment Service - Error Context
```python
# services/cj_assessment_service/core_assessment_logic.py

# In fetch_essay_content method
async def fetch_essay_content(self, content_id: str) -> str:
    """Fetch essay content with enhanced error context."""
    with self.tracer.start_as_current_span(
        "fetch_essay_content",
        attributes={"content_id": content_id}
    ) as span:
        try:
            # Validate content ID format
            if content_id.startswith("original-"):
                span.set_attribute("content_id_type", "legacy_format")
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                
                # Rich error message
                error_msg = (
                    f"Invalid content ID format: '{content_id}'. "
                    f"Expected storage service ID, got legacy format. "
                    f"This suggests the storage reference was not properly updated "
                    f"after spell checking."
                )
                self._logger.error(error_msg, extra={"content_id": content_id})
                raise ValueError(error_msg)
            
            # Fetch content
            span.set_attribute("content_id_type", "storage_service")
            content = await self._content_client.fetch_content(content_id)
            span.set_attribute("content_length", len(content))
            return content
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
```

## Step 4: Add Kafka Tracing (2 hours)

### 4.1 Enhance EventEnvelope
```python
# common_core/src/common_core/events/envelope.py
from typing import Optional, Dict, Any

class EventEnvelope(BaseModel, Generic[T_EventData]):
    # Existing fields...
    
    # Add metadata field for trace context
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
```

### 4.2 Producer with Trace Context
```python
# services/libs/huleedu_service_libs/src/huleedu_service_libs/kafka_utils/kafka_bus.py
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

async def publish_event(self, topic: str, event: EventEnvelope) -> None:
    """Publish event with trace context."""
    span = trace.get_current_span()
    
    if span and span.is_recording():
        # Inject trace context into event metadata
        carrier = {}
        TraceContextTextMapPropagator().inject(carrier)
        event.metadata["trace_context"] = carrier
        
        # Add span attributes
        span.set_attribute("messaging.system", "kafka")
        span.set_attribute("messaging.destination", topic)
        span.set_attribute("event.type", event.event_type)
    
    # Continue with existing publish logic...
```

### 4.3 Consumer with Trace Context
```python
# In Kafka consumer handlers
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

async def _process_message(self, message: ConsumerRecord) -> None:
    """Process message with trace context extraction."""
    event = EventEnvelope.model_validate_json(message.value)
    
    # Extract trace context if available
    ctx = None
    if event.metadata and "trace_context" in event.metadata:
        carrier = event.metadata["trace_context"]
        ctx = TraceContextTextMapPropagator().extract(carrier)
    
    # Start span with parent context
    with self.tracer.start_as_current_span(
        f"consume.{event.event_type}",
        context=ctx,
        attributes={
            "messaging.system": "kafka",
            "messaging.source": message.topic,
            "event.type": event.event_type,
            "event.id": str(event.event_id),
            "correlation_id": str(event.correlation_id) if event.correlation_id else None
        }
    ) as span:
        try:
            # Process event
            await self._handle_event(event)
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
```

## Step 5: Quick Debugging Dashboard (1 hour)

### 5.1 Add Jaeger Data Source to Grafana
```bash
# Access Grafana at http://localhost:3000
# Add data source:
# - Type: Jaeger
# - URL: http://jaeger:16686
```

### 5.2 Create Debug Panel
```json
{
  "dashboard": {
    "title": "Quick Debug - Trace Search",
    "panels": [
      {
        "title": "Find Traces by Correlation ID",
        "type": "text",
        "content": "1. Go to Jaeger UI: http://localhost:16686\n2. Select Service: any\n3. Tags: correlation_id=YOUR_ID\n4. Click Find Traces"
      },
      {
        "title": "Recent Errors",
        "datasource": "Loki",
        "targets": [{
          "expr": "{level=\"ERROR\"} | json | line_format \"{{.timestamp}} [{{.service_name}}] {{.message}}\""
        }]
      }
    ]
  }
}
```

## Step 6: Test the Setup (30 minutes)

### 6.1 Restart services with Jaeger
```bash
# Update docker-compose.yml environment for each service
JAEGER_AGENT_HOST=jaeger

# Restart
pdm run dc-down
pdm run dc-up
```

### 6.2 Run a test and view traces
```bash
# Run functional test
pdm run pytest tests/functional/test_e2e_comprehensive_real_batch.py -v

# Open Jaeger UI
open http://localhost:16686

# Search for traces
# Service: batch_orchestrator_service
# Operation: POST /api/v1/batches/register
```

## What You Get Immediately

1. **Service Communication Visibility**
   - See which services are called in what order
   - Identify where requests fail or timeout

2. **Performance Bottlenecks**
   - See slow operations highlighted in red
   - Identify which service is the bottleneck

3. **Error Context**
   - Click on error spans to see exception details
   - See exact data that caused failures

4. **Correlation**
   - Link logs to traces using correlation ID
   - Follow a request through the entire system

## Next Enhancements (When Time Permits)

1. **Add Circuit Breakers** (2 hours)
   - Prevent cascade failures
   - Fail fast with clear errors

2. **Enhance Error Messages** (1 hour)
   - Add context to all errors
   - Include troubleshooting hints

3. **Create Alert Rules** (1 hour)
   - Alert on high error rates
   - Alert on missing traces

4. **Add Custom Dashboards** (2 hours)
   - Pipeline flow visualization
   - Service health overview

## Debugging Workflow with Basic Tracing

1. **Test Fails**
   ```bash
   # Get correlation ID from test output
   correlation_id = "batch_abc123"
   ```

2. **Find Trace**
   ```
   Open: http://localhost:16686
   Service: <any>
   Tags: correlation_id=batch_abc123
   Click: Find Traces
   ```

3. **Analyze**
   - Red spans = errors (click for details)
   - Long spans = performance issues
   - Missing spans = service didn't receive request

4. **Check Logs**
   ```
   Open: http://localhost:3000
   Query: {service_name="essay_lifecycle_service"} |= "batch_abc123"
   ```

This minimal setup gives you 80% of the debugging capability with 20% of the effort!
