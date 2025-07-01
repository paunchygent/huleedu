# HuleEdu Observability Implementation - Quick Start Plan

## Overview

This plan provides a practical, phased approach to adding distributed tracing to HuleEdu, focusing on immediate debugging capability with minimal disruption.

## Current Status: Phase 3 Complete ✅

### Completed Work

1. **Phase 1: Jaeger Infrastructure** ✅
   - Added Jaeger service to observability stack
   - Configured OTLP endpoints for all services
   - Created Grafana datasource for Jaeger
   - Infrastructure running and accessible

2. **Phase 2: Service Library Enhancement** ✅
   - Added OpenTelemetry dependencies to service library
   - Created observability module with tracing utilities
   - Implemented middleware for automatic HTTP request tracing
   - All code is linted, formatted, and type-checked

3. **Phase 3: Service Instrumentation** ✅ COMPLETE
   - Instrumented Batch Orchestrator Service
   - Instrumented Essay Lifecycle Service API
   - Instrumented Spell Checker Service (HTTP API and Kafka worker)
   - Instrumented CJ Assessment Service
   - Added tracing to critical storage reference handler
   - Added metadata field to EventEnvelope for trace propagation
   - Implemented trace context injection in all event publishers
   - Implemented trace context extraction in all event processors
   - Verified end-to-end trace propagation through complete pipeline

### Available Tracing Utilities

The following utilities are now available in `huleedu_service_libs`:

- **`init_tracing(service_name)`** - Initialize tracing for a service
- **`get_tracer(service_name)`** - Get tracer without reinitializing provider
- **`trace_operation(tracer, name, attributes)`** - Context manager for tracing operations
- **`use_trace_context(metadata)`** - Extract and apply trace context from event metadata
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

## Current Implementation Status

### What's Working Now

1. **Infrastructure** ✅
   - Jaeger UI: <http://localhost:16686>
   - All services configured with OTLP endpoints
   - Grafana datasource for Jaeger configured

2. **Instrumented Services** ✅
   - Batch Orchestrator Service: HTTP requests traced automatically
   - Essay Lifecycle Service API: HTTP requests traced automatically
   - Storage reference extraction: Critical path instrumented with custom spans

3. **Event System** ✅
   - EventEnvelope now supports metadata field for trace propagation
   - Ready for trace context injection/extraction

### What's Implemented Now

1. **Complete Trace Propagation** ✅
   - All services extract and inject trace context
   - Correlation IDs preserved across all service boundaries
   - Verified with end-to-end pipeline testing
   - **Achievement**: 82+ spans in distributed traces across full pipeline

2. **Service Coverage** ✅
   - Batch Orchestrator Service (HTTP + Kafka)
   - Essay Lifecycle Service (HTTP + Kafka)
   - Spell Checker Service (HTTP + Kafka worker)
   - CJ Assessment Service (Kafka worker)
   - **Critical Fix**: Added trace context extraction to all batch orchestrator handlers

3. **Trace Context Flow** ✅
   - HTTP requests: Auto-traced via middleware
   - Kafka events: Manual injection/extraction via metadata field
   - Correlation ID: Preserved throughout entire pipeline
   - **Pattern**: `get_tracer()` function implemented for consistent tracer access

### Next Steps

1. **Phase 4: Debugging Tools** (Ready to implement):
   - Create trace search script
   - Build Grafana dashboards for trace visualization
   - Add trace links to existing dashboards

2. **Phase 5: Testing & Validation**:
   - Create automated tests for trace validation
   - Document debugging workflows
   - Add trace-based alerts

## Implementation Timeline

- **Day 1 Morning**: ✅ Deploy Jaeger infrastructure (Phase 1) - COMPLETE
- **Day 1 Afternoon**: ✅ Service library enhancement (Phase 2) - COMPLETE
- **Day 2 Morning**: ✅ Instrument critical services (Phase 3) - COMPLETE
- **Day 2 Afternoon**: 🚧 Create debugging tools (Phase 4) - NEXT
- **Day 3**: Testing and validation (Phase 5)

## Success Metrics

1. **Trace Coverage**: ✅ All critical operations in BOS → ELS → CJ flow have spans (82+ spans achieved)
2. **Error Visibility**: ✅ Storage reference errors include trace context
3. **Debug Time**: ✅ Reduce investigation time from hours to minutes
4. **Zero Disruption**: ✅ No impact on existing functionality
5. **Distributed Spans**: ✅ Successfully achieving multi-service traces instead of single spans

## Additional Resources

- **Detailed Enhancement Plan**: `/documentation/TASKS/OBSERVABILITY_ENHANCEMENT_PLAN.md`
- **Quick Start Guide**: `/documentation/QUICK_START_OBSERVABILITY.md`
- **Debugging Scenarios**: `/documentation/DEBUGGING_SCENARIOS_WITH_TRACING.md`
