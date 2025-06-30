# HuleEdu Observability Implementation - Quick Start Plan

## Overview

This plan provides a practical, phased approach to adding distributed tracing to HuleEdu, focusing on immediate debugging capability with minimal disruption.

## Current Status: Phase 2 Complete ✅

### Completed Work

1. **Service Library Enhancement** ✅
   - Added OpenTelemetry dependencies to service library
   - Created observability module with tracing utilities
   - Implemented middleware for automatic HTTP request tracing
   - All code is linted, formatted, and type-checked

### Available Tracing Utilities

The following utilities are now available in `huleedu_service_libs`:

- **`init_tracing(service_name)`** - Initialize tracing for a service
- **`trace_operation(tracer, name, attributes)`** - Context manager for tracing operations
- **`setup_tracing_middleware(app, tracer)`** - Add automatic HTTP tracing to Quart apps
- **`get_current_trace_id()`** - Get current trace ID for logging
- **`inject_trace_context(carrier)`** - Add trace context to event metadata
- **`extract_trace_context(carrier)`** - Extract trace context from events

### Implementation File References

- **Dependencies**: `services/libs/pyproject.toml`
- **Tracing Module**: `services/libs/huleedu_service_libs/observability/tracing.py`
- **Middleware**: `services/libs/huleedu_service_libs/middleware/tracing_middleware.py`
- **Tests**: `services/libs/huleedu_service_libs/observability/test_tracing.py`

### Import Pattern

Services import the tracing utilities as follows:
```python
from huleedu_service_libs import init_tracing, setup_tracing_middleware
from huleedu_service_libs.observability import trace_operation, get_current_trace_id
```

## Next Steps for Developers

### Phase 1: Deploy Jaeger Infrastructure (30 minutes)

#### 1.1 Add Jaeger to Observability Stack

Add this service to `observability/docker-compose.observability.yml`:

```yaml
  jaeger:
    image: jaegertracing/all-in-one:1.50
    container_name: huleedu_jaeger
    restart: unless-stopped
    networks:
      - huleedu_observability_network
    ports:
      - "16686:16686"    # Jaeger UI
      - "4317:4317"      # OTLP gRPC receiver
      - "4318:4318"      # OTLP HTTP receiver
    environment:
      - COLLECTOR_OTLP_ENABLED=true
      - SPAN_STORAGE_TYPE=memory
      - MEMORY_MAX_TRACES=10000
    volumes:
      - jaeger_data:/tmp
```

#### 1.2 Update Service Environment Variables

Add to each service in `docker-compose.yml`:

```yaml
environment:
  - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
  - OTEL_SERVICE_NAME=${SERVICE_NAME}
  - OTEL_TRACES_EXPORTER=otlp
  - OTEL_METRICS_EXPORTER=none
```

#### 1.3 Add Grafana Data Source

Create `observability/grafana/provisioning/datasources/jaeger.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
    basicAuth: false
    isDefault: false
    editable: true
```

#### 1.4 Start Infrastructure

```bash
pdm run obs-up
# Verify Jaeger UI at http://localhost:16686
```

### Phase 3: Service Instrumentation (Day 2)

#### 3.1 Instrument Batch Orchestrator Service

Update `services/batch_orchestrator_service/startup_setup.py`:

1. Import tracing utilities
2. Initialize tracer in `initialize_app()`
3. Set up middleware with `setup_tracing_middleware(app, tracer)`

Example pattern:
```python
from huleedu_service_libs import init_tracing, setup_tracing_middleware

async def initialize_app(app: Quart) -> None:
    # ... existing setup ...
    
    # Initialize tracing
    app.tracer = init_tracing("batch_orchestrator_service")
    setup_tracing_middleware(app, app.tracer)
```

#### 3.2 Instrument Essay Lifecycle Service

Focus on the critical storage reference handler at:
`services/essay_lifecycle_service/implementations/service_result_handler_impl.py`

Add tracing to the `handle_spell_check_complete` method to debug storage reference issues.

#### 3.3 Add Kafka Trace Propagation

Update `common_core/src/common_core/events/envelope.py`:
1. Add `metadata: Optional[Dict[str, Any]]` field to EventEnvelope
2. Use `inject_trace_context()` when publishing events
3. Use `extract_trace_context()` when consuming events

### Phase 4: Create Debugging Tools (Day 2 Afternoon)

#### 4.1 Trace Search Script

Create `scripts/trace_search.py` for searching traces by correlation ID or batch ID.

#### 4.2 Grafana Dashboard

Create `observability/grafana-dashboards/distributed-tracing-quickstart.json` with:
- Trace search helper panel
- Service error rate by operation
- Recent errors with trace links

### Phase 5: Testing & Validation (Day 3)

#### 5.1 E2E Test with Trace Validation

Create tests in `tests/functional/test_tracing_integration.py` to verify:
- Trace propagation across services
- Expected operations are traced
- No errors in critical paths

#### 5.2 Verify Debugging Workflow

Test the complete debugging workflow:
1. Run E2E test
2. Get correlation ID from output
3. Search in Jaeger UI
4. Verify trace shows complete request flow

## Implementation Timeline

- **Day 1 Morning**: Deploy Jaeger infrastructure (Phase 1)
- **Day 1 Afternoon**: ✅ Service library enhancement (Phase 2) - COMPLETE
- **Day 2 Morning**: Instrument critical services (Phase 3)
- **Day 2 Afternoon**: Create debugging tools (Phase 4)
- **Day 3**: Testing and validation (Phase 5)

## Success Metrics

1. **Trace Coverage**: All critical operations in BOS → ELS → CJ flow have spans
2. **Error Visibility**: Storage reference errors include trace context
3. **Debug Time**: Reduce investigation time from hours to minutes
4. **Zero Disruption**: No impact on existing functionality

## Additional Resources

- **Detailed Enhancement Plan**: `/documentation/TASKS/OBSERVABILITY_ENHANCEMENT_PLAN.md`
- **Quick Start Guide**: `/documentation/QUICK_START_OBSERVABILITY.md`
- **Debugging Scenarios**: `/documentation/DEBUGGING_SCENARIOS_WITH_TRACING.md`