# TASK-CJ-04: CJ Assessment Service Production Readiness & Integration Testing

**Status**: Not Started  
**Estimated Duration**: 3-4 days  
**Dependencies**: TASK-LLM-02 completed ✅  
**Risk Level**: Medium (Critical bugs blocking service operation)  
**Architectural Impact**: Low (Bug fixes and testing only)  
**Follow-up Required**: TASK-CJ-05 for error handling phase 6 (when unblocked)

## 📋 Executive Summary

Complete production readiness for the CJ Assessment Service by fixing critical diagnostic errors, implementing comprehensive integration tests, and verifying architectural compliance. This task addresses blocking bugs discovered during TASK-LLM-02 implementation and establishes robust testing for the event-driven callback workflow.

## 🎯 Business Objectives

1. **Ensure Service Stability**: Fix all blocking bugs preventing service from running
2. **Validate Event-Driven Architecture**: Comprehensive testing of callback-based workflow
3. **Production Confidence**: 95%+ test coverage for critical paths
4. **Type Safety**: Complete HuleEduApp integration for infrastructure access
5. **Operational Excellence**: Proper error handling and observability

## 🚨 Critical Issues Identified

### Blocking Bugs from Diagnostic Analysis
- **correlation_id Access Error**: `CJBatchState` has no `correlation_id` attribute
- **Method Name Mismatches**: `publish_cj_assessment_failed` doesn't exist
- **Field Name Errors**: Using `content` instead of `text_content` for essays
- **Parameter Mismatches**: Incorrect parameters to `publish_assessment_completed`

### Architectural Clarifications
- **Cache Already Removed**: Comment confirms removal for methodology integrity
- **Rate Limiting**: Belongs in LLM Provider Service, not CJ Assessment

## ✅ Architecture Prerequisites

**From TASK-LLM-02**:
- ✅ Event-driven callback processing implemented
- ✅ Batch monitoring and recovery system
- ✅ Bradley-Terry scoring integration
- ✅ Health check endpoints

**Current Infrastructure**:
- ✅ Kafka consumer with dual-topic subscription
- ✅ PostgreSQL with batch state tracking
- ✅ Prometheus metrics integration
- ✅ Structured error handling framework

## 📚 Required Architecture Rules

**MUST READ** before implementation:
- `.cursor/rules/055-import-resolution-patterns.mdc` - Full module path imports
- `.cursor/rules/050-python-coding-standards.mdc` - Code formatting and typing
- `.cursor/rules/070-testing-and-quality-assurance.mdc` - Testing strategies
- `.cursor/rules/048-structured-error-handling-standards.mdc` - Error patterns
- `.cursor/rules/052-event-contract-standards.mdc` - Event envelope structure

## 🎨 Implementation Design

### Phase 1: Critical Diagnostic Fixes ❌ NOT STARTED

**Estimated Duration**: 2-3 hours  
**Priority**: BLOCKING - Must complete before any other work

#### 1.1 Fix correlation_id Access Pattern

**File**: `services/cj_assessment_service/batch_monitor.py`

```python
# Current (BROKEN) - Lines 225, 270
correlation_id=batch_state.correlation_id  # AttributeError

# Fixed implementation
# Option 1: Join with batch_upload table when querying
stmt = select(CJBatchState).where(
    CJBatchState.batch_id == batch_id
).options(
    selectinload(CJBatchState.batch_upload)  # Eager load relationship
)

# Then access via relationship
correlation_id = UUID(batch_state.batch_upload.event_correlation_id)

# Option 2: Store correlation_id earlier in the method
# At the beginning of _handle_stuck_batch method:
batch_upload = await session.get(CJBatchUpload, batch_state.batch_id)
correlation_id = UUID(batch_upload.event_correlation_id)
```

#### 1.2 Fix Method Name for Failed Event Publishing

**File**: `services/cj_assessment_service/batch_monitor.py`

```python
# Current (BROKEN) - Line 263
await self._event_publisher.publish_cj_assessment_failed(

# Fixed implementation
await self._event_publisher.publish_assessment_failed(
    failure_data=failure_envelope,  # Must be EventEnvelope[CJAssessmentFailedV1]
    correlation_id=correlation_id,
)
```

#### 1.3 Fix EssayForComparison Field Names

**Files**: 
- `services/cj_assessment_service/batch_monitor.py` (Line 332)
- `services/cj_assessment_service/cj_core_logic/batch_callback_handler.py` (Line 367)

```python
# Current (BROKEN)
essay_data = EssayForComparison(
    essay_id=essay.id,
    content=essay.content,  # Wrong field name
)

# Fixed implementation
essay_data = EssayForComparison(
    essay_id=essay.id,
    text_content=essay.content,  # Correct field name
)
```

#### 1.4 Create EventEnvelope for publish_assessment_completed

**Files**: 
- `services/cj_assessment_service/batch_monitor.py` (Lines 365-371)
- `services/cj_assessment_service/cj_core_logic/batch_callback_handler.py` (Lines 400-405)

```python
# Current (BROKEN)
await self._event_publisher.publish_assessment_completed(
    cj_batch_id=batch_id,      # Wrong - these are not parameters
    rankings=rankings,          # of publish_assessment_completed
    final_scores=final_scores,
    status="COMPLETED",
    correlation_id=correlation_id,
)

# Fixed implementation
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.models.batch_models import BatchStatus
from common_core.models.system_models import SystemProcessingMetadata
from common_core.status_enums import ProcessingEvent

# Create the event data
event_data = CJAssessmentCompletedV1(
    event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
    entity_ref=batch_upload.bos_batch_id,  # BOS batch ID, not CJ batch ID
    status=BatchStatus.COMPLETED_SUCCESSFULLY,
    system_metadata=SystemProcessingMetadata(
        source_service="cj_assessment_service",
        processed_at=datetime.now(UTC),
        processing_duration_seconds=processing_duration,
        resource_usage={
            "total_comparisons": total_comparisons,
            "completed_comparisons": completed_comparisons,
        }
    ),
    cj_assessment_job_id=batch_id,  # Internal CJ batch ID
    rankings=rankings,  # List of dicts with essay_id, rank, score
)

# Wrap in EventEnvelope
completion_envelope = EventEnvelope[CJAssessmentCompletedV1](
    event_type="cj_assessment.completed.v1",
    event_timestamp=datetime.now(UTC),
    source_service="cj_assessment_service",
    correlation_id=correlation_id,
    data=event_data
)

# Publish with correct parameters
await self._event_publisher.publish_assessment_completed(
    completion_data=completion_envelope,
    correlation_id=correlation_id,
)
```

### Phase 2: Code Quality & Type Annotations ❌ NOT STARTED

**Estimated Duration**: 30 minutes  
**Priority**: Low - Not blocking functionality

#### 2.1 Fix Import Ordering and Formatting

**File**: `services/cj_assessment_service/cj_core_logic/batch_callback_handler.py`

```bash
# Run formatting command
pdm run format-all

# Or specifically for the affected files
pdm run ruff format --force-exclude services/cj_assessment_service/
```

#### 2.2 Add Type Annotations

Run `pdm run typecheck-all` from root directory to check for type errors. Fix any type errors that are found: no ignores or casts allowed.

**Files**: Multiple locations

```python
# Current (Missing type annotation)
comparisons = []

# Fixed implementation
from typing import List
from services.cj_assessment_service.models_api import ComparisonResult

comparisons: List[ComparisonResult] = []
```

### Phase 3: Comprehensive Integration Testing ❌ NOT STARTED

**Estimated Duration**: 1-2 days  
**Priority**: High - Critical for production confidence

#### 3.1 Create Integration Test Framework

**File**: `services/cj_assessment_service/tests/integration/test_batch_workflow_integration.py`

```python
"""
End-to-end integration tests for CJ Assessment batch workflow.
Tests the complete lifecycle from request to callback to completion.
"""
import asyncio
from datetime import datetime, UTC
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from common_core.events.cj_assessment_events import CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.implementations.kafka_event_publisher_impl import (
    KafkaEventPublisherImpl,
)
from services.cj_assessment_service.implementations.postgresql_repository_impl import (
    PostgreSQLCJRepositoryImpl,
)
from services.cj_assessment_service.worker_main import process_messages


@pytest.mark.integration
class TestBatchWorkflowIntegration:
    """Test complete batch processing workflow with callbacks."""

    async def test_full_batch_lifecycle(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
        kafka_test_consumer,
    ):
        """Test batch from creation through callbacks to completion."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()
        
        # Create assessment request event
        request_event = self._create_assessment_request(
            batch_id=batch_id,
            correlation_id=correlation_id,
            essay_count=10,
        )
        
        # Act - Process the request
        await process_assessment_request(
            request_event,
            test_database,
            test_publisher,
        )
        
        # Assert - Verify batch created with correct state
        async with test_database.session() as session:
            batch = await self._get_batch_by_bos_id(session, batch_id)
            assert batch is not None
            assert batch.batch_state.state == CJBatchStateEnum.GENERATING_PAIRS
            
            # Verify comparison pairs created
            pairs = await self._get_comparison_pairs(session, batch.id)
            assert len(pairs) == 45  # C(10,2) = 45 pairs
        
        # Act - Simulate LLM callbacks for all pairs
        for i, pair in enumerate(pairs):
            callback_event = self._create_callback_event(
                request_id=str(pair.id),
                correlation_id=pair.request_correlation_id,
                winner="essay_a" if i % 2 == 0 else "essay_b",
            )
            
            await process_llm_callback(
                callback_event,
                test_database,
                test_publisher,
            )
        
        # Assert - Verify batch completed
        async with test_database.session() as session:
            batch = await self._get_batch_by_bos_id(session, batch_id)
            assert batch.batch_state.state == CJBatchStateEnum.COMPLETED
            assert batch.batch_state.completed_comparisons == 45
            
            # Verify completion event published
            completion_events = await kafka_test_consumer.get_events(
                topic="huleedu.cj_assessment.completed.v1"
            )
            assert len(completion_events) == 1
            assert completion_events[0].data.cj_assessment_job_id == batch.id

    async def test_batch_monitoring_recovery(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
        test_monitor: BatchMonitor,
    ):
        """Test stuck batch detection and recovery."""
        # Arrange - Create a stuck batch
        batch = await self._create_stuck_batch(
            test_database,
            state=CJBatchStateEnum.WAITING_CALLBACKS,
            progress_percentage=85,  # Above recovery threshold
            hours_old=5,  # Past timeout threshold
        )
        
        # Act - Run batch monitor
        await test_monitor.check_stuck_batches()
        
        # Assert - Verify batch recovered
        async with test_database.session() as session:
            updated_batch = await session.get(CJBatchState, batch.batch_id)
            assert updated_batch.state == CJBatchStateEnum.SCORING
            
            # Verify completion event published
            events = await self._get_published_events(test_publisher)
            assert any(e.event_type == "cj_assessment.completed.v1" for e in events)

    async def test_concurrent_callback_processing(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
    ):
        """Test race conditions with concurrent callbacks."""
        # Arrange
        batch = await self._create_test_batch(test_database, pair_count=100)
        
        # Act - Process callbacks concurrently
        tasks = []
        for pair in batch.comparison_pairs:
            callback = self._create_callback_event(
                request_id=str(pair.id),
                correlation_id=pair.request_correlation_id,
                winner="essay_a",
            )
            task = asyncio.create_task(
                process_llm_callback(callback, test_database, test_publisher)
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Assert - Verify no duplicate processing
        async with test_database.session() as session:
            updated_batch = await session.get(CJBatchState, batch.id)
            assert updated_batch.completed_comparisons == 100
            assert updated_batch.state == CJBatchStateEnum.COMPLETED

    async def test_partial_batch_completion(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
        test_settings,
    ):
        """Test partial completion threshold triggering."""
        # Arrange
        test_settings.COMPLETION_THRESHOLD_PCT = 80
        batch = await self._create_test_batch(test_database, pair_count=100)
        
        # Act - Complete 80% of comparisons
        for i in range(80):
            callback = self._create_callback_event(
                request_id=str(batch.comparison_pairs[i].id),
                correlation_id=batch.comparison_pairs[i].request_correlation_id,
                winner="essay_a",
            )
            await process_llm_callback(callback, test_database, test_publisher)
        
        # Assert - Verify partial scoring triggered
        async with test_database.session() as session:
            updated_batch = await session.get(CJBatchState, batch.id)
            assert updated_batch.partial_scoring_triggered is True
            assert updated_batch.state == CJBatchStateEnum.SCORING
```

#### 3.2 Test Error Scenarios

**File**: `services/cj_assessment_service/tests/integration/test_error_handling_integration.py`

```python
"""Integration tests for error handling and recovery scenarios."""

@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Test error scenarios and recovery mechanisms."""

    async def test_callback_for_unknown_correlation_id(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
    ):
        """Test handling of orphaned callbacks."""
        # Arrange
        unknown_correlation_id = uuid4()
        callback = self._create_callback_event(
            request_id=str(uuid4()),
            correlation_id=unknown_correlation_id,
            winner="essay_a",
        )
        
        # Act - Should handle gracefully
        result = await process_llm_callback(
            callback, test_database, test_publisher
        )
        
        # Assert
        assert result is True  # Acknowledged but not processed
        # Verify no database changes
        async with test_database.session() as session:
            pairs = await self._get_all_comparison_pairs(session)
            assert all(p.request_correlation_id != unknown_correlation_id for p in pairs)

    async def test_duplicate_callback_idempotency(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
    ):
        """Test idempotent handling of duplicate callbacks."""
        # Arrange
        batch = await self._create_test_batch(test_database, pair_count=1)
        pair = batch.comparison_pairs[0]
        
        callback = self._create_callback_event(
            request_id=str(pair.id),
            correlation_id=pair.request_correlation_id,
            winner="essay_a",
        )
        
        # Act - Process same callback twice
        await process_llm_callback(callback, test_database, test_publisher)
        await process_llm_callback(callback, test_database, test_publisher)
        
        # Assert - Only processed once
        async with test_database.session() as session:
            updated_pair = await session.get(ComparisonPair, pair.id)
            assert updated_pair.winner == "essay_a"
            assert updated_pair.completed_at is not None
            
            batch_state = await session.get(CJBatchState, batch.id)
            assert batch_state.completed_comparisons == 1  # Not 2

    async def test_high_failure_rate_batch_termination(
        self,
        test_database: PostgreSQLCJRepositoryImpl,
        test_publisher: KafkaEventPublisherImpl,
        test_settings,
    ):
        """Test batch failure when error rate exceeds threshold."""
        # Arrange
        test_settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8
        batch = await self._create_test_batch(test_database, pair_count=20)
        
        # Act - Make 50% of callbacks fail (exceeds 20% failure threshold)
        for i, pair in enumerate(batch.comparison_pairs[:10]):
            if i < 5:
                # Success callbacks
                callback = self._create_callback_event(
                    request_id=str(pair.id),
                    correlation_id=pair.request_correlation_id,
                    winner="essay_a",
                )
            else:
                # Error callbacks
                callback = self._create_error_callback(
                    request_id=str(pair.id),
                    correlation_id=pair.request_correlation_id,
                    error_code="PROVIDER_ERROR",
                )
            
            await process_llm_callback(callback, test_database, test_publisher)
        
        # Assert - Batch marked as failed
        async with test_database.session() as session:
            batch_state = await session.get(CJBatchState, batch.id)
            assert batch_state.state == CJBatchStateEnum.FAILED
            assert batch_state.completed_comparisons == 5
            assert batch_state.failed_comparisons == 5
            
            # Verify failure event published
            failure_events = await self._get_failure_events(test_publisher)
            assert len(failure_events) == 1
```

### Phase 4: HuleEduApp Integration Verification ✅ COMPLETED

**Estimated Duration**: 1-2 hours  
**Priority**: Medium - Type safety improvement  
**Actual Duration**: 45 minutes  
**Completion Date**: 2025-07-16

#### 4.1 Verify Current Integration ✅

**Status**: VERIFIED - Service properly uses HuleEduApp with guaranteed infrastructure

**Findings**:
- **app.py**: Correctly initializes HuleEduApp with guaranteed infrastructure
- **Database Engine**: Created in app.py and passed to DI container
- **Container**: Properly initialized before Blueprint registration
- **No Legacy Patterns**: No setattr/getattr usage found
- **Proper App Attributes**: Uses app.database_engine and app.container correctly

**Current Implementation**:
```python
# app.py - Correct HuleEduApp usage
app = HuleEduApp(__name__)
app.database_engine = create_async_engine(settings.database_url, ...)
app.container = make_async_container(CJAssessmentServiceProvider(engine=app.database_engine))
QuartDishka(app=app, container=app.container)
```

#### 4.2 Complete Type Safety ✅

**Status**: VERIFIED - All DI providers use proper protocol types

**Findings**:
- **DI Container**: All providers return protocol types (CJRepositoryProtocol, CJEventPublisherProtocol)
- **API Routes**: Properly use @inject with FromDishka[ProtocolType]
- **Type Checking**: No type errors found in CJ Assessment Service
- **Protocol Definitions**: All protocols properly defined in protocols.py

**Current Implementation**:
```python
# di.py - Proper protocol typing
@provide(scope=Scope.APP)
def provide_database_handler(
    self, settings: Settings, database_metrics: DatabaseMetrics, engine: AsyncEngine
) -> CJRepositoryProtocol:
    return PostgreSQLCJRepositoryImpl(settings, database_metrics, engine)

# health_routes.py - Proper DI usage
@inject
async def readiness_probe(
    repository: FromDishka[CJRepositoryProtocol],
) -> tuple[Response, int]:
```

#### 4.3 Infrastructure Access Verification ✅

**Status**: VERIFIED - All infrastructure access via DI

**Findings**:
- **No Direct Access**: No direct infrastructure access outside DI container
- **Engine Usage**: Database engine properly injected into repository implementation
- **Health Routes**: Use guaranteed infrastructure (app.database_engine) only for health checks
- **Proper Scoping**: All infrastructure uses Scope.APP for singleton behavior

### Phase 5: Error Handling Phase 6 ❌ BLOCKED

**Status**: Blocked by LLM Provider Service refactor  
**Estimated Duration**: 6-8 hours (when unblocked)  
**Priority**: Medium - Service functional without it

**Scope When Unblocked**:
1. Remove all `error_message` fields in favor of `error_detail`
2. Update database schemas and create migration
3. Align with new LLM Provider error patterns
4. Update all error handling to use structured format

## ✅ Success Criteria

### Functional Requirements
- ✅ All diagnostic errors fixed and service runs without errors
- ✅ Event envelope structure properly implemented
- ✅ Integration tests cover full batch lifecycle
- ✅ Error scenarios handled gracefully
- ✅ Type safety verified throughout

### Performance Requirements
- ✅ Concurrent callback processing without race conditions
- ✅ Batch monitoring completes within 30 seconds for 1000 batches
- ✅ No memory leaks during extended operation
- ✅ Database queries optimized with proper indexes

### Operational Requirements
- ✅ All code formatted according to standards
- ✅ Type hints complete and mypy passing
- ✅ Integration tests can run in CI/CD pipeline
- ✅ Comprehensive logging for debugging
- ✅ Metrics track all critical operations

## 🚀 Deployment Strategy

### Prerequisites
1. [x] TASK-LLM-02 implementation complete
2. [ ] All diagnostic fixes applied and tested
3. [ ] Integration tests passing
4. [ ] Code review completed

### Deployment Steps
1. **Run tests locally** - Ensure all fixes work
2. **Deploy to staging** - Validate in staging environment
3. **Run integration tests** - Full test suite in staging
4. **Monitor metrics** - Watch for any anomalies
5. **Deploy to production** - With careful monitoring

### Rollback Plan
1. Service is already deployed with bugs
2. Fixes are backwards compatible
3. Can rollback individual fixes if needed
4. No data migration required

## ⚠️ Anti-Patterns to Avoid

1. **DO NOT** access `correlation_id` directly from `CJBatchState`
2. **DO NOT** pass raw parameters to event publisher methods
3. **DO NOT** skip EventEnvelope wrapping
4. **DO NOT** use relative imports in service code
5. **DO NOT** ignore type hints and mypy errors

## 📊 Expected Impact

### Service Stability
- **Bug Fixes**: Service operational without runtime errors
- **Type Safety**: Compile-time error detection improved
- **Test Coverage**: 95%+ coverage for critical paths
- **Error Handling**: Graceful degradation for all scenarios

### Development Velocity
- **Confidence**: Changes can be made without breaking workflow
- **Documentation**: Clear examples for future development
- **Debugging**: Comprehensive logging and error messages
- **Maintenance**: Clean, well-tested codebase

## 🔗 Related Tasks

- **Prerequisite**: TASK-LLM-02 (Event-driven implementation) ✅
- **Blocked By**: LLM Provider Service refactor (for Phase 5)
- **Follow-up**: TASK-CJ-05 - Error handling phase 6 (when unblocked)
- **Related**: TASK-CJ-03 - Proper batch LLM integration

## 📋 Implementation Checklist

### Phase 1: Critical Fixes ❌
- [ ] Fix correlation_id access pattern
- [ ] Fix publish_assessment_failed method name
- [ ] Fix text_content field name
- [ ] Create EventEnvelope wrappers
- [ ] Test all fixes work together

### Phase 2: Code Quality ❌
- [ ] Run pdm run format-all
- [ ] Add type annotations for lists
- [ ] Fix import ordering
- [ ] Remove whitespace issues
- [ ] Verify mypy passes

### Phase 3: Integration Tests ❌
- [ ] Create test framework
- [ ] Test full batch lifecycle
- [ ] Test concurrent callbacks
- [ ] Test error scenarios
- [ ] Test batch monitoring
- [ ] Test partial completion
- [ ] Add to CI/CD pipeline

### Phase 4: HuleEduApp Verification ❌
- [ ] Verify current usage
- [ ] Remove any legacy patterns
- [ ] Ensure DI used throughout
- [ ] Add type safety
- [ ] Document patterns

### Phase 5: Error Handling ❌ BLOCKED
- [ ] Wait for LLM Provider refactor
- [ ] Plan database migration
- [ ] Update error structures
- [ ] Test compatibility

**Service Status**: ~85% Production Ready - Critical fixes needed for operation