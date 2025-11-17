---
id: 'TASK-050-CORRELATION-CONTEXT-MIGRATION'
title: 'TASK-050: CorrelationContext Migration'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-07'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-050: CorrelationContext Migration

## Status: PENDING

## Priority: HIGH

## Objective
Migrate all services from manual correlation header extraction to CorrelationContext middleware per Rule 043.2.

## Services to Migrate

### Core Services
- [ ] **batch_orchestrator_service** - High traffic, critical path
- [ ] **api_gateway_service** - Entry point, highest priority
- [ ] **class_management_service** - Core data service
- [ ] **essay_lifecycle_service** - Core processing service

### Processing Services  
- [ ] **file_service** - File operations
- [ ] **spellchecker_service** - Phase 1 processor
- [ ] **cj_assessment_service** - Phase 2 processor
- [ ] **nlp_service** - Phase 2 processor
- [ ] **result_aggregator_service** - Results collector

### Supporting Services
- [ ] **identity_service** - Auth/identity
- [ ] **content_service** - Content management
- [ ] **batch_conductor_service** - Batch coordination
- [ ] **websocket_service** - Real-time updates
- [ ] **email_service** - Notifications
- [ ] **llm_provider_service** - LLM integration

### Completed
- [x] **entitlements_service** - Reference implementation

## Per-Service Migration Steps

### 1. App Setup
```python
# app.py
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware,
)

# Add after app creation, before routes
setup_correlation_middleware(app)
```

### 2. DI Provider
```python
# di.py
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)

class ImplementationProviders(Provider):
    scope = Scope.REQUEST
    
    @provide
    def provide_correlation_context(self) -> CorrelationContext:
        from quart import g, request
        
        ctx = getattr(g, "correlation_context", None)
        if isinstance(ctx, CorrelationContext):
            return ctx
        return extract_correlation_context_from_request(request)
```

### 3. Route Updates
Replace all instances of:
```python
# OLD
correlation_header = request.headers.get("X-Correlation-ID")
correlation_id = UUID(correlation_header) if correlation_header else uuid4()
```

With:
```python
# NEW
async def endpoint(corr: FromDishka[CorrelationContext]):
    # Use corr.uuid for internal operations
    # Use corr.original for client responses
```

### 4. Error Factory Updates
```python
# Update error calls
raise_validation_error(
    service="service_name",
    operation="operation",
    correlation_id=corr.uuid,  # Use UUID form
    details={"original_correlation_id": corr.original}
)
```

### 5. Event Publishing Updates
```python
# Update event envelopes
envelope = EventEnvelope(
    correlation_id=corr.uuid,  # Canonical UUID
    metadata={"original_correlation_id": corr.original}  # Optional
)
```

### 6. Test Updates
```python
# Mock CorrelationContext in tests
mock_corr = CorrelationContext(
    original="test-correlation-123",
    uuid=UUID("12345678-1234-5678-1234-567812345678"),
    source="header"
)
```

## Verification
Per service:
1. `pdm run pytest-root services/<service>/tests/unit -q`
2. `pdm run pytest-root services/<service>/tests/integration -q`
3. Check logs show correlation threading
4. Verify events use canonical UUID

## Notes
- Entitlements service is reference implementation
- `g.correlation_id` remains for backwards compatibility
- No database migrations required
- No event contract changes (already use UUID)