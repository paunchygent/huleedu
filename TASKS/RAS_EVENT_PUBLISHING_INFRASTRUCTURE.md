# Result Aggregator Service (RAS) Event Publishing Infrastructure

## Executive Summary

Complete RAS transformation from pure consumer to full event-driven service with publishing capabilities. This unblocks teacher result notifications in the WebSocket layer and enables downstream services (AI Feedback) to consume batch completion events.

**Status**: 🟡 IN PROGRESS - Phase 1 (Outbox) Complete, Phase 2 (Publishing) Ready

**Dependencies**: 
- Blocks: `/TASKS/WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md` - Result completion notifications
- Enables: Future AI Feedback Service consumption of results

**Session 1.1 Completed**: ✅ Transactional outbox pattern implemented with 7/7 tests passing

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

### PHASE 1: Transactional Outbox Pattern ✅ COMPLETED

**Implementation**: Session 1.1 completed successfully with full transactional outbox pattern.

```python
# Implemented files:
services/result_aggregator_service/
├── implementations/
│   └── outbox_manager.py          # ✅ Direct copy from file_service pattern
├── models_db.py                   # ✅ EventOutbox model added (11 columns, 3 indexes)
├── alembic/versions/
│   └── 20250807_1411_dd059078c9c5_add_event_outbox_table_for_reliable_.py  # ✅
└── protocols.py                   # ✅ OutboxManagerProtocol added

# DI Integration (di.py):
- PostgreSQLOutboxRepository provided in DatabaseProvider
- OutboxManager provided in ServiceProvider with Redis + OutboxRepo dependencies

# Database verification:
Table: event_outbox (result_aggregator DB, port 5436)
Indexes: ix_event_outbox_unpublished, ix_event_outbox_aggregate_id
```

**Tests**: 7/7 unit tests passing for OutboxManager covering all scenarios including error handling, Redis notifications, and transactional guarantees.

### PHASE 2: Event Publishing Infrastructure ✅ PARTIALLY COMPLETED

#### Session 2.1 & 2.2 ✅ COMPLETED

**Implemented**: ResultEventPublisher with TRUE OUTBOX PATTERN, event contracts in common_core.

```python
# services/result_aggregator_service/implementations/event_publisher_impl.py
class ResultEventPublisher:
    async def publish_batch_results_ready(self, event_data: BatchResultsReadyV1, correlation_id: UUID):
        envelope = EventEnvelope[BatchResultsReadyV1](...)
        await self.outbox_manager.publish_to_outbox(...)  # TRUE OUTBOX
        if self.notification_projector:
            await self.notification_projector.handle_batch_results_ready(event_data)  # CANONICAL

# libs/common_core/src/common_core/events/result_events.py
class BatchResultsReadyV1(ProcessingUpdate):  # Inherits system_metadata
    batch_id: str; user_id: str; total_essays: int; completed_essays: int
    phase_results: dict[str, PhaseResultSummary]; overall_status: BatchStatus

# DI wiring in di.py:
provide_kafka_bus() -> KafkaBus with lifecycle
provide_circuit_breaker() -> CircuitBreaker(failure_threshold=5, recovery_timeout=30s)
provide_kafka_publisher() -> ResilientKafkaPublisher(delegate=kafka_bus, circuit_breaker)
provide_event_publisher() -> ResultEventPublisher(outbox_manager, settings, None)

# 12 unit tests passing: test_event_publisher.py
```

#### Session 2.3: Publishing Integration

**Implementation Requirements**: Wire EventPublisher into EventProcessorImpl at two critical integration points.

##### Integration Point 1: Batch Phase Outcome Handler (Line 130-184)

**File**: `services/result_aggregator_service/implementations/event_processor_impl.py`

```python
# Add after line 14 (imports):
from services.result_aggregator_service.protocols import EventPublisherProtocol

# Update __init__ to inject EventPublisher:
def __init__(
    self,
    batch_repository: BatchRepositoryProtocol,
    state_store: StateStoreProtocol,
    cache_manager: CacheManagerProtocol,
    event_publisher: EventPublisherProtocol,  # NEW
):
    self.event_publisher = event_publisher  # NEW

# Add after line 177 (after cache invalidation):
# Check if all phases complete for batch
batch = await self.batch_repository.get_batch(data.batch_id)
if batch and await self._check_batch_completion(batch):
    # Calculate phase summaries from batch data
    phase_results = self._calculate_phase_results(batch)
    
    # Create BatchResultsReadyV1 event
    from common_core.events.result_events import BatchResultsReadyV1
    from common_core.metadata_models import SystemProcessingMetadata
    
    system_metadata = SystemProcessingMetadata(
        entity_id=batch.batch_id,
        entity_type="batch",
        processing_stage=ProcessingStage.COMPLETED,
    )
    
    event = BatchResultsReadyV1(
        event_name=ProcessingEvent.BATCH_RESULTS_READY,
        status=BatchStatus.COMPLETED_SUCCESSFULLY,
        system_metadata=system_metadata,
        batch_id=batch.batch_id,
        user_id=batch.user_id,
        total_essays=batch.total_essay_count,
        completed_essays=batch.processed_essay_count,
        phase_results=phase_results,
        overall_status=self._determine_overall_status(batch),
        processing_duration_seconds=self._calculate_duration(batch),
    )
    
    await self.event_publisher.publish_batch_results_ready(
        event, envelope.correlation_id
    )
    
    logger.info(
        "Published BatchResultsReadyV1 event",
        batch_id=batch.batch_id,
        user_id=batch.user_id,
    )

# Helper methods to add:
async def _check_batch_completion(self, batch: BatchResult) -> bool:
    """Check if all configured phases are complete."""
    # Implementation: Check batch.phase_statuses against expected phases
    pass

def _calculate_phase_results(self, batch: BatchResult) -> dict:
    """Calculate phase result summaries from batch data."""
    # Implementation: Transform batch.phase_statuses to PhaseResultSummary dict
    pass

def _determine_overall_status(self, batch: BatchResult) -> BatchStatus:
    """Determine overall batch status from phase results."""
    # Implementation: Logic to determine COMPLETED_SUCCESSFULLY vs COMPLETED_WITH_FAILURES
    pass

def _calculate_duration(self, batch: BatchResult) -> float:
    """Calculate total processing duration."""
    # Implementation: batch.completed_at - batch.created_at in seconds
    pass
```

##### Integration Point 2: CJ Assessment Completed Handler (Line 288-347)

```python
# Add after line 331 (after cache invalidation):
# Get batch info for user_id
batch = await self.batch_repository.get_batch(batch_id)
if batch:
    # Create BatchAssessmentCompletedV1 event
    from common_core.events.result_events import BatchAssessmentCompletedV1
    from common_core.metadata_models import SystemProcessingMetadata
    
    system_metadata = SystemProcessingMetadata(
        entity_id=batch_id,
        entity_type="batch",
        processing_stage=ProcessingStage.COMPLETED,
    )
    
    event = BatchAssessmentCompletedV1(
        event_name=ProcessingEvent.BATCH_ASSESSMENT_COMPLETED,
        status=BatchStatus.COMPLETED_SUCCESSFULLY,
        system_metadata=system_metadata,
        batch_id=batch_id,
        user_id=batch.user_id,
        assessment_job_id=data.cj_assessment_job_id,
        rankings_summary=data.rankings,  # Thin event - just summary
    )
    
    await self.event_publisher.publish_batch_assessment_completed(
        event, envelope.correlation_id
    )
    
    logger.info(
        "Published BatchAssessmentCompletedV1 event",
        batch_id=batch_id,
        assessment_job_id=data.cj_assessment_job_id,
        rankings_count=len(data.rankings),
    )
```

##### DI Container Update

```python
# In services/result_aggregator_service/di.py:
# Update provide_event_processor to inject EventPublisher:
@provide
def provide_event_processor(
    self,
    batch_repository: BatchRepositoryProtocol,
    state_store: StateStoreProtocol,
    cache_manager: CacheManagerProtocol,
    event_publisher: EventPublisherProtocol,  # NEW
) -> EventProcessorProtocol:
    return EventProcessorImpl(
        batch_repository, 
        state_store, 
        cache_manager,
        event_publisher,  # NEW
    )
```

##### Test Requirements

```python
# tests/unit/result_aggregator_service/test_event_processor_integration.py
# Test batch completion detection logic
# Test event creation with correct data mapping
# Test publisher invocation with proper correlation_id
# Mock EventPublisher to verify correct method calls
```

### PHASE 3: Notification Projection Pattern (1 session)

**CANONICAL PATTERN**: Direct notification projector invocation after domain event (NO Kafka round-trip)

#### Session 3.1: Notification Projector

```python
# Implementation pattern from file_service:
services/result_aggregator_service/notification_projector.py

from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

class ResultNotificationProjector:
    """Projects result events to teacher notifications."""
    
    def __init__(self, kafka_publisher: KafkaPublisherProtocol):
        self.kafka_publisher = kafka_publisher
    
    async def handle_batch_results_ready(self, event: BatchResultsReadyV1) -> None:
        """Project batch completion to high-priority teacher notification."""
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="batch_results_ready",
            category=WebSocketEventCategory.PROCESSING_RESULTS,
            priority=NotificationPriority.IMMEDIATE,  # Important completion
            payload={
                "batch_id": event.batch_id,
                "total_essays": event.total_essays,
                "completed_essays": event.completed_essays,
                "overall_status": event.overall_status.value,
                "message": f"Batch {event.batch_id} processing complete. {event.completed_essays}/{event.total_essays} essays processed successfully.",
                "phase_summaries": self._summarize_phases(event.phase_results)
            },
            action_required=True,  # Teacher should review results
            correlation_id=str(event.correlation_id),
            batch_id=event.batch_id
        )
        
        # Publish directly to WebSocket service via Kafka
        envelope = EventEnvelope[TeacherNotificationRequestedV1](
            event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
            source_service="result_aggregator_service",
            correlation_id=UUID(notification.correlation_id),
            data=notification
        )
        
        await self.kafka_publisher.publish(
            topic=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
            envelope=envelope,
            key=event.user_id  # Partition by teacher
        )
    
    async def handle_batch_assessment_completed(self, event: BatchAssessmentCompletedV1) -> None:
        """Project CJ assessment completion to teacher notification."""
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="batch_assessment_completed",
            category=WebSocketEventCategory.PROCESSING_RESULTS,
            priority=NotificationPriority.STANDARD,
            payload={
                "batch_id": event.batch_id,
                "assessment_job_id": event.assessment_job_id,
                "message": f"Comparative judgment assessment completed for batch {event.batch_id}",
                "rankings_available": len(event.rankings_summary) > 0
            },
            action_required=False,
            correlation_id=str(event.correlation_id),
            batch_id=event.batch_id
        )
        
        await self._publish_notification(notification)
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

## Critical Implementation Patterns

### TRUE OUTBOX PATTERN (Mandatory)

```python
# ALWAYS store in DB first, relay worker publishes asynchronously
await self.outbox_manager.publish_to_outbox(
    aggregate_type="batch",
    aggregate_id=event.batch_id,
    event_type=envelope.event_type,
    event_data=envelope,  # Pass original Pydantic envelope
    topic=topic_name(ProcessingEvent.BATCH_RESULTS_READY)
)
# NEVER direct Kafka publishing from business logic
```

### CANONICAL NOTIFICATION PATTERN

```python
# Direct projector invocation after domain event (NO Kafka round-trip)
async def publish_batch_results_ready(self, event_data, correlation_id):
    # 1. Store domain event in outbox
    await self.outbox_manager.publish_to_outbox(...)
    
    # 2. Directly invoke notification projector 
    if self.notification_projector:
        await self.notification_projector.handle_batch_results_ready(event_data)
```

### DI WIRING PATTERN

```python
# From working services - exact pattern to copy:
@provide(scope=Scope.APP)
def provide_outbox_repository(self, engine: AsyncEngine) -> OutboxRepositoryProtocol:
    return PostgreSQLOutboxRepository(engine)

@provide(scope=Scope.APP) 
def provide_kafka_publisher(self, ...) -> KafkaPublisherProtocol:
    return ResilientKafkaPublisher(kafka_bus, circuit_breaker)

@provide(scope=Scope.APP)
def provide_event_publisher(self, outbox_manager, settings, notification_projector):
    return ResultEventPublisher(outbox_manager, settings, notification_projector)
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

**Session 2.1: Implement Event Publisher** (Ready to start)

1. **Create ResultEventPublisher**:
   - Copy pattern from `file_service/implementations/event_publisher_impl.py`
   - Implement `publish_batch_results_ready()` and `publish_batch_assessment_completed()`
   - Use OutboxManager for TRUE OUTBOX PATTERN

2. **Wire Kafka Publisher in DI**:
   - Add `provide_kafka_publisher()` using `ResilientKafkaPublisher`
   - Add `provide_event_publisher()` with dependencies
   - Update imports for `huleedu_service_libs.kafka.resilient_kafka_bus`

3. **Create Basic Event Contracts** (temporary):
   - Stub out `BatchResultsReadyV1` and `BatchAssessmentCompletedV1` locally
   - Full common_core implementation in Session 2.2

4. **Unit Tests**:
   - Test event envelope structure
   - Test outbox integration
   - Mock notification projector

## Related Documentation

- **Blocked Task**: `/TASKS/WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md#phase-3b`
- **Architecture Rules**: See rule references in each phase
- **Reference Services**:
  - `/services/file_service/` (outbox pattern ✅ STUDIED)
  - `/services/class_management_service/` (event publishing pattern)
  - `/services/essay_lifecycle_service/` (batch lifecycle publisher pattern)
- **Shared Libraries**:
  - `huleedu_service_libs.kafka` - ResilientKafkaPublisher
  - `huleedu_service_libs.outbox` - PostgreSQLOutboxRepository ✅ USED
  - `huleedu_service_libs.protocols` - KafkaPublisherProtocol
