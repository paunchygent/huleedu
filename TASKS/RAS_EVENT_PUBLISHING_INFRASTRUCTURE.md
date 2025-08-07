# Result Aggregator Service (RAS) Event Publishing Infrastructure

## Executive Summary

Complete RAS transformation from pure consumer to full event-driven service with publishing capabilities. This unblocks teacher result notifications in the WebSocket layer and enables downstream services (AI Feedback) to consume batch completion events.

**Status**: 🔴 BLOCKED - Required for WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md Phase 3B

**Dependencies**: 
- Blocks: `/TASKS/WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md` - Result completion notifications
- Enables: Future AI Feedback Service consumption of results

## Current State Analysis

### What RAS Has ✅
```python
# Consumer Infrastructure (WORKING)
- Kafka consumer with idempotency (Redis)
- PostgreSQL persistence (batch_results, essay_results)
- Query API endpoints (internal/v1)
- Processes: SpellcheckCompleted, CJAssessmentCompleted, BatchPhaseOutcome
```

### What RAS Lacks ❌
```python
# Publishing Infrastructure (MISSING)
- No EventPublisher implementation
- No OutboxManager for reliable delivery
- No EventOutbox database table
- No notification projector
- No Kafka producer configuration
```

## Implementation Phases

### PHASE 1: Transactional Outbox Pattern (2 sessions)

**Rule References**:
- `.cursor/rules/042.1-transactional-outbox-pattern.mdc` - Pattern specification
- `.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling
- `.cursor/rules/085-database-migration-standards.mdc` - Migration standards

#### Session 1.1: Core Outbox Implementation
```python
# Files to create (follow existing patterns):
services/result_aggregator_service/
├── implementations/
│   ├── outbox_manager.py          # Copy pattern from file_service
│   └── event_publisher_impl.py    # Copy pattern from class_management_service
├── models_db.py                   # Add EventOutbox model
└── alembic/versions/
    └── YYYYMMDD_add_event_outbox.py

# Reference implementations:
- /services/file_service/implementations/outbox_manager.py
- /services/class_management_service/implementations/outbox_manager.py
- /services/file_service/models_db.py (EventOutbox table)
```

#### Session 1.2: Outbox Testing
**Rule**: `.cursor/rules/075-test-creation-methodology.mdc`

```python
# Test files to create:
tests/
├── unit/
│   ├── test_outbox_manager.py
│   └── test_event_publisher.py
└── integration/
    └── test_outbox_pattern_integration.py

# Test scenarios:
1. Transactional guarantee (event + business data)
2. Retry mechanism on Kafka failures
3. Idempotency with duplicate processing
4. Outbox processor background task
```

### PHASE 2: Event Publishing Infrastructure (3 sessions)

**Rule References**:
- `.cursor/rules/050-python-coding-standards.mdc` - Coding standards
- `.cursor/rules/071-observability-core-patterns.mdc` - Observability
- `.cursor/rules/081-pdm-dependency-management.mdc` - Dependencies

#### Session 2.1: Publisher Implementation
```python
# DI Provider updates:
services/result_aggregator_service/di.py:
  + provide_kafka_publisher() -> KafkaPublisherProtocol
  + provide_outbox_manager() -> OutboxManager
  + provide_event_publisher() -> EventPublisherProtocol

# Protocol additions:
services/result_aggregator_service/protocols.py:
  + EventPublisherProtocol
  + OutboxManagerProtocol
```

#### Session 2.2: Event Contracts
```python
# New events in common_core:
libs/common_core/src/common_core/events/result_events.py:
  + BatchResultsReadyV1          # All phases complete
  + BatchAssessmentCompletedV1   # CJ assessment done
  + BatchPartialResultsV1        # Progressive updates

# Event registration:
libs/common_core/src/common_core/event_enums.py:
  + BATCH_RESULTS_READY = "batch_results_ready"
  + BATCH_ASSESSMENT_COMPLETED = "batch_assessment_completed"
  + BATCH_PARTIAL_RESULTS = "batch_partial_results"
```

#### Session 2.3: Publishing Tests
```python
# Integration tests:
tests/integration/test_event_publishing.py:
  - test_batch_completion_publishes_event()
  - test_assessment_completion_publishes_event()
  - test_partial_results_publishing()
  - test_event_envelope_structure()
```

### PHASE 3: Notification Projection Pattern (1 session)

**Rule Reference**: `.cursor/rules/030-event-driven-architecture-eda-standards.mdc`

#### Session 3.1: Notification Projector
```python
# Create notification projector:
services/result_aggregator_service/notification_projector.py

class NotificationProjector:
    """Projects result events to teacher notifications."""
    
    async def handle_batch_results_ready(self, event: BatchResultsReadyV1):
        # Project to TeacherNotificationRequestedV1
        # Priority: HIGH (important completion)
        # Category: PROCESSING_RESULTS
        
    async def handle_batch_assessment_completed(self, event: BatchAssessmentCompletedV1):
        # Project to TeacherNotificationRequestedV1
        # Priority: STANDARD
        # Category: PROCESSING_RESULTS

# Reference implementations:
- /services/class_management_service/notification_projector.py
- /services/batch_orchestrator_service/notification_projector.py
```

### PHASE 4: CJ Assessment Service Enhancements (2 sessions)

**Rule Reference**: `.cursor/rules/052-phase2-processing-flow.mdc`

#### Session 4.1: Structured Result Storage
```python
# CJ Assessment Service updates:
services/cj_assessment_service/
├── models_db.py          # Add structured result tables
│   + AssessmentResult    # Detailed assessment data
│   + ComparisonMatrix    # Pairwise comparisons
│   + JudgeDecision       # Individual judge decisions
└── implementations/
    └── result_repository.py  # Result storage/retrieval

# Store rich data locally, publish thin events
```

#### Session 4.2: Result Query API
```python
# New endpoints for RAS to query:
services/cj_assessment_service/api/result_routes.py:
  GET /internal/v1/assessments/{job_id}/detailed
  GET /internal/v1/assessments/{batch_id}/summary

# RAS can fetch detailed data when needed
```

### PHASE 5: Event Enrichment Strategy (1 session)

#### Session 5.1: Determine Enrichment Point
```python
# Options to evaluate:

1. Enrich at CJ Assessment (NOT RECOMMENDED):
   - Would create fat events
   - Violates thin event principle
   
2. Enrich at RAS (RECOMMENDED):
   - RAS queries CJ Assessment API for details
   - Stores enriched data locally
   - Publishes thin completion events
   
3. Create new DetailedResultRequestedV1 event:
   - Only if absolutely necessary
   - Allows on-demand detail fetching
```

## Implementation Patterns

### Pattern 1: Outbox with Dishka DI
```python
# From file_service/di.py:
@provide(scope=Scope.APP)
async def provide_outbox_manager(
    engine: AsyncEngine,
    kafka_publisher: KafkaPublisherProtocol,
) -> OutboxManager:
    return OutboxManager(engine, kafka_publisher)
```

### Pattern 2: Event Publishing
```python
# From class_management_service/implementations/event_publisher_impl.py:
async def publish_result_event(self, event: BatchResultsReadyV1):
    envelope = EventEnvelope(
        event_type=topic_name(ProcessingEvent.BATCH_RESULTS_READY),
        data=event,
        source_service="result_aggregator_service",
    )
    await self.outbox_manager.publish_to_outbox(
        aggregate_id=event.batch_id,
        event_data=envelope,
    )
```

### Pattern 3: Notification Projection
```python
# Direct invocation pattern (no Kafka round-trip):
if event_type == "batch_results_ready":
    await self.notification_projector.handle_batch_results_ready(event)
    # Internally publishes TeacherNotificationRequestedV1
```

## Testing Strategy

**Rule**: `.cursor/rules/075-test-creation-methodology.mdc`

### Unit Tests (80% coverage minimum)
- Mock all external dependencies
- Test each component in isolation
- Use pytest fixtures for DI

### Integration Tests
- TestContainers for PostgreSQL, Kafka, Redis
- Full event flow validation
- Outbox pattern transactional guarantees

### E2E Tests
- Complete pipeline: Event → RAS → Notification → WebSocket
- Use existing test patterns from file_service, class_management_service

## Success Criteria

1. **Outbox Pattern**: Transactional guarantee for all published events
2. **Event Publishing**: 3 event types published reliably
3. **Notification Projection**: 2+ teacher notifications implemented
4. **CJ Assessment**: Structured storage with query API
5. **Testing**: >80% coverage, all integration tests passing
6. **Documentation**: Updated service README and rule files

## Development Workflow

**Rule**: `.cursor/rules/080-repository-workflow-and-tooling.mdc`

```bash
# For each session:
1. Create feature branch
2. Implement with TDD approach
3. Run: pdm run lint-fix
4. Run: pdm run typecheck-all
5. Run: pdm run test-unit
6. Run: pdm run test-integration
7. Update documentation
8. Create PR with session results
```

## Dependencies & Configuration

**Rule**: `.cursor/rules/081-pdm-dependency-management.mdc`

```toml
# pyproject.toml additions:
[tool.pdm.dependencies]
aiokafka = "^0.8.0"       # Already present
sqlalchemy = "^2.0.0"     # Already present
dishka = "^1.0.0"         # Already present

# New environment variables:
RESULT_AGGREGATOR_SERVICE_KAFKA_PRODUCER_CLIENT_ID=ras-producer
RESULT_AGGREGATOR_SERVICE_OUTBOX_POLL_INTERVAL=5
RESULT_AGGREGATOR_SERVICE_OUTBOX_BATCH_SIZE=100
```

## Migration Path

**Rule**: `.cursor/rules/085-database-migration-standards.mdc`

```bash
# Session 1.1: Add EventOutbox table
cd services/result_aggregator_service
pdm run alembic revision -m "Add event outbox table"
# Edit migration file
pdm run alembic upgrade head

# Session 4.1: Add CJ Assessment result tables
cd services/cj_assessment_service
pdm run alembic revision -m "Add structured result storage"
pdm run alembic upgrade head
```

## Error Handling

**Rule**: `.cursor/rules/048-structured-error-handling-standards.mdc`

```python
# Use structured error handling from libs:
from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_validation_error,
    ServiceError,
)

# Consistent error patterns across all new code
```

## Observability

**Rule**: `.cursor/rules/071-observability-core-patterns.mdc`

```python
# Add metrics for:
- Events published count
- Outbox processing latency
- Notification projection success/failure
- CJ Assessment query response times

# Use existing patterns from other services
```

## Timeline Estimate

- **Phase 1**: 2 sessions (Outbox implementation + testing)
- **Phase 2**: 3 sessions (Publishing infrastructure + contracts + testing)
- **Phase 3**: 1 session (Notification projection)
- **Phase 4**: 2 sessions (CJ Assessment enhancements)
- **Phase 5**: 1 session (Event enrichment)

**Total**: ~9 sessions to complete RAS event publishing infrastructure

## Next Session Focus

**Session 1.1: Implement Transactional Outbox Pattern**
1. Copy outbox pattern from file_service
2. Add EventOutbox model to models_db.py
3. Create database migration
4. Implement OutboxManager
5. Add DI providers
6. Basic unit tests

## Related Documentation

- **Blocked Task**: `/TASKS/WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md#phase-3b`
- **Architecture Rules**: See rule references in each phase
- **Reference Services**: 
  - `/services/file_service/` (outbox pattern)
  - `/services/class_management_service/` (event publishing)
  - `/services/batch_orchestrator_service/` (notification projection)