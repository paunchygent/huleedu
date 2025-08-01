# Priority 1 Critical Refactoring Guide

**STATUS**: ✅ PARTIALLY COMPLETED  
**ENTITY REFERENCE ELIMINATION**: ✅ COMPLETED (2025-08-01)  
**REMAINING TASK**: Batch Orchestrator backwards compatibility removal

## Executive Summary

This guide provides a complete analysis and step-by-step refactoring plan for eliminating backwards compatibility patterns and legacy code from the HuleEdu platform. The refactoring follows a CLEAN BREAK approach with NO backwards compatibility as per project mandates.

**UPDATE**: EntityReference elimination has been completed via commit `6d29985 refactor: remove EntityReference model in favor of primitive parameters`. All EntityReference usage has been replaced with primitive parameters across the codebase.

## 1. Remove All Backwards Compatibility in Batch Orchestrator

### 1.1 Current State Analysis

The Batch Orchestrator's `DefaultPipelinePhaseCoordinator` contains dictionary-based fallbacks in 5 critical locations:

1. **Line 169-174**: Pipeline state type checking
2. **Line 221-249**: Idempotency check with dual logic
3. **Line 297-318**: Error handling with dual state updates
4. **Line 323-345**: Phase status updates
5. **Line 391-416**: Resolved pipeline initiation

**Pattern Found**:
```python
# Current anti-pattern repeated throughout
if hasattr(current_pipeline_state, "requested_pipelines"):  # Pydantic object
    requested_pipelines = current_pipeline_state.requested_pipelines
else:  # Dictionary - backwards compatibility
    requested_pipelines = current_pipeline_state.get("requested_pipelines")
```

### 1.2 Root Cause

The `BatchRepositoryProtocol.get_processing_pipeline_state()` is returning either:
- A proper `ProcessingPipelineState` Pydantic model
- A raw dictionary (legacy pattern)

This violates the architectural mandate that all inter-service data MUST be Pydantic models.

### 1.3 Refactoring Plan

#### Step 1: Fix Repository Implementation

```python
# services/batch_orchestrator_service/implementations/batch_repository_impl.py

async def get_processing_pipeline_state(self, batch_id: str) -> ProcessingPipelineState | None:
    """Get processing pipeline state - ALWAYS returns Pydantic model."""
    pipeline_key = f"pipeline:state:{batch_id}"
    
    state_json = await self.redis_client.get_key(pipeline_key)
    if not state_json:
        return None
    
    # ALWAYS deserialize to Pydantic model
    return ProcessingPipelineState.model_validate_json(state_json)

async def save_processing_pipeline_state(
    self, 
    batch_id: str, 
    state: ProcessingPipelineState  # ONLY accept Pydantic model
) -> None:
    """Save processing pipeline state - ONLY accepts Pydantic model."""
    if not isinstance(state, ProcessingPipelineState):
        raise_validation_error(
            service="batch_orchestrator_service",
            operation="save_processing_pipeline_state",
            field="state",
            message="State must be ProcessingPipelineState instance, not dict",
        )
    
    pipeline_key = f"pipeline:state:{batch_id}"
    await self.redis_client.set_key(
        pipeline_key,
        state.model_dump_json(),
        ttl_seconds=86400
    )
```

#### Step 2: Simplify Coordinator Logic

```python
# services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py

async def _initiate_next_phase(
    self,
    batch_id: str,
    completed_phase: PhaseName,
    correlation_id: UUID,
    processed_essays_from_previous_phase: list[Any] | None = None,
) -> None:
    """Determine and initiate the next pipeline phase."""
    try:
        # Get batch context and pipeline state
        batch_context = await self.batch_repo.get_batch_context(batch_id)
        if not batch_context:
            logger.error(f"Missing batch context for batch {batch_id}")
            return

        current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if not current_pipeline_state:
            logger.error(f"No pipeline state found for batch {batch_id}")
            return

        # Direct access - no type checking needed
        requested_pipelines = current_pipeline_state.requested_pipelines
        
        if not requested_pipelines:
            raise_validation_error(
                service="batch_orchestrator_service",
                operation="handle_phase_concluded",
                field="requested_pipelines",
                message=f"No requested pipelines found for batch {batch_id}",
                correlation_id=correlation_id,
                batch_id=batch_id,
            )

        # Find current and next phase
        try:
            current_index = requested_pipelines.index(completed_phase.value)
        except ValueError:
            logger.error(
                f"Completed phase '{completed_phase.value}' not found in requested_pipelines"
            )
            return

        # Check if pipeline is complete
        if current_index + 1 >= len(requested_pipelines):
            logger.info(f"Pipeline completed for batch {batch_id}")
            return

        # Get next phase
        next_phase_str = requested_pipelines[current_index + 1]
        next_phase_name = PhaseName(next_phase_str)

        # Idempotency check - direct Pydantic access
        pipeline_detail = current_pipeline_state.get_pipeline(next_phase_name.value)
        if pipeline_detail and pipeline_detail.status in [
            PipelineExecutionStatus.DISPATCH_INITIATED,
            PipelineExecutionStatus.IN_PROGRESS,
            PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
            PipelineExecutionStatus.FAILED,
        ]:
            logger.info(
                f"Phase {next_phase_name.value} already initiated, skipping",
                extra={"current_status": pipeline_detail.status.value},
            )
            return

        # Continue with phase initiation...
```

#### Step 3: Update All Dictionary References

Replace all 5 locations with direct Pydantic model access:

```python
# BEFORE (lines 169-174)
if hasattr(current_pipeline_state, "requested_pipelines"):
    requested_pipelines = current_pipeline_state.requested_pipelines
else:
    requested_pipelines = current_pipeline_state.get("requested_pipelines")

# AFTER
requested_pipelines = current_pipeline_state.requested_pipelines
```

### 1.4 Testing Strategy

1. **Unit Tests**: Update all mocks to return ProcessingPipelineState objects
2. **Integration Tests**: Verify Redis serialization/deserialization
3. **Migration**: One-time script to convert any existing Redis dict entries

```python
# scripts/migrate_pipeline_states.py
async def migrate_pipeline_states(redis_client: AtomicRedisClientProtocol):
    """One-time migration of dictionary states to Pydantic models."""
    cursor = "0"
    migrated = 0
    
    while cursor != 0:
        cursor, keys = await redis_client._client.scan(
            cursor, match="pipeline:state:*", count=100
        )
        
        for key in keys:
            state_json = await redis_client.get_key(key.decode())
            if state_json:
                try:
                    # Try to load as dict first
                    state_dict = json.loads(state_json)
                    if isinstance(state_dict, dict) and "batch_id" in state_dict:
                        # Convert to Pydantic model
                        state_model = ProcessingPipelineState(**state_dict)
                        await redis_client.set_key(
                            key.decode(),
                            state_model.model_dump_json()
                        )
                        migrated += 1
                except Exception as e:
                    logger.error(f"Failed to migrate {key}: {e}")
    
    logger.info(f"Migrated {migrated} pipeline states")
```

## 2. Remove Legacy Validation Failure Support in Common Core

### 2.1 Current State Analysis

**CRITICAL LEGACY PATTERN IDENTIFIED**: The `BatchEssaysReady` event contains anti-pattern legacy fields that violate modern error handling principles:

- `validation_failures: list[EssayValidationFailedV1] | None` (line 81)
- `total_files_processed: int | None` (line 85)

**Impact Assessment**:
- **45+ files** reference `BatchEssaysReady` across the codebase
- **22+ files** specifically use the `validation_failures` field
- **7+ files** use the `total_files_processed` field
- **Critical business logic** depends on mixed success/error event pattern

**Architecture Violation**: These fields represent an **OLD ANTI-PATTERN** where validation failures were bundled with success events, violating:
- **Single Responsibility Principle**: Events handle both success AND error cases
- **Structured Error Handling**: Errors are embedded in success events instead of separate error events
- **Observability Standards**: Mixed success/error data complicates metrics and alerting

### 2.2 Modern Structured Error Handling Alternative

**NEW PATTERN**: Use separate success and error events following HuleEdu structured error handling standards:

```python
# Modern pattern - clean separation of success and error flows
class BatchEssaysReadyV2(BaseModel):
    """Clean event for successful batch readiness - NO legacy fields."""
    event: str = Field(default="batch.essays.ready.v2")
    batch_id: str
    ready_essays: list[EssayProcessingInputRefV1]
    batch_id: str
    entity_type: str = "batch"
    metadata: SystemProcessingMetadata
    
    # Educational context (no legacy error fields)
    course_code: CourseCode
    course_language: str
    essay_instructions: str
    class_type: str
    teacher_first_name: str | None = None
    teacher_last_name: str | None = None
    
    # REMOVED: validation_failures, total_files_processed

class BatchValidationErrorsV1(BaseModel):
    """Separate event for validation failures using structured error handling."""
    event: str = Field(default="batch.validation.errors.v1")
    batch_id: str
    failed_essays: list[EssayValidationError]
    error_summary: BatchErrorSummary
    correlation_id: UUID = Field(default_factory=uuid4)
    metadata: SystemProcessingMetadata
```

### 2.3 Test Architecture Refactoring Strategy

#### 2.3.1 Current Test Anti-Patterns (TO BE ELIMINATED)

**🔴 CRITICAL ISSUE**: Current tests exhibit **Docker-heavy infrastructure anti-patterns**:

**Problematic Tests**:
- `test_pending_validation_failures_integration.py` - **Docker + Redis + Complex setup**
- `test_validation_coordination_complete_failures.py` - **E2E with multiple services**  
- `test_validation_coordination_partial_failures.py` - **Full infrastructure stack**
- `test_batch_tracker_validation.py` - **Heavy integration dependencies**

**Anti-Pattern Problems**:
- **Slow feedback loops**: 2-5 minutes per test run (Docker startup overhead)
- **Infrastructure coupling**: Tests fail due to Docker/Redis issues, not business logic
- **Complex setup/teardown**: Brittle test environments prone to flaking
- **Hard to debug**: Business logic failures buried in infrastructure noise
- **Maintenance burden**: Tests break when infrastructure changes, not business changes

#### 2.3.2 Modern Test Architecture (REPLACEMENT STRATEGY)

**🟢 NEW PATTERN**: **REPLACE** (not refactor) with fast, focused unit tests:

**Fast Unit Tests with Clean Dependencies**:
```python
# NEW: services/essay_lifecycle_service/tests/unit/test_dual_event_publishing.py
class TestDualEventPublishing:
    """Test dual-event publishing pattern for batch coordination."""
    
    async def test_successful_batch_publishes_clean_success_event(self):
        """Success path: clean event with no error fields."""
        # Arrange: Mock dependencies (no Docker)
        mock_publisher = AsyncMock()
        handler = BatchCoordinationHandler(mock_publisher, ...)
        
        ready_essays = [create_mock_essay("essay1")]
        failed_essays = []  # No failures
        
        # Act: Trigger batch ready
        await handler.publish_batch_ready(batch_id, ready_essays, failed_essays)
        
        # Assert: Only success event published
        assert mock_publisher.publish_batch_ready.call_count == 1
        assert mock_publisher.publish_validation_errors.call_count == 0
        
        # Verify clean success event has NO legacy fields
        success_event = mock_publisher.publish_batch_ready.call_args[0][0]
        assert not hasattr(success_event, 'validation_failures')
        assert not hasattr(success_event, 'total_files_processed')
    
    async def test_validation_failures_publish_separate_error_event(self):
        """Error path: separate error event with structured details."""
        # Arrange
        mock_publisher = AsyncMock()
        handler = BatchCoordinationHandler(mock_publisher, ...)
        
        ready_essays = []
        failed_essays = [create_mock_validation_error("essay2")]
        
        # Act
        await handler.publish_batch_ready(batch_id, ready_essays, failed_essays)
        
        # Assert: Only error event published
        assert mock_publisher.publish_batch_ready.call_count == 0
        assert mock_publisher.publish_validation_errors.call_count == 1
        
        # Verify structured error event
        error_event = mock_publisher.publish_validation_errors.call_args[0][0]
        assert isinstance(error_event.error_summary, BatchErrorSummary)
        assert error_event.failed_essays[0].error_detail.error_code
    
    async def test_mixed_results_publish_both_events(self):
        """Mixed path: both success and error events published."""
        # Test dual-event publishing for mixed scenarios
```

**Contract Tests for Event Schemas**:
```python
# NEW: libs/common_core/tests/unit/test_event_contracts_v2.py
class TestEventContractsV2:
    """Test clean event contracts without legacy fields."""
    
    def test_batch_essays_ready_v2_has_no_legacy_fields(self):
        """Ensure clean event model has no legacy fields."""
        event = BatchEssaysReadyV2(
            batch_id="test",
            ready_essays=[],
            batch_id="test",
            entity_type="batch",
            metadata=SystemProcessingMetadata(...),
            course_code=CourseCode.EN_101,
            course_language="english",
            essay_instructions="Test instructions",
            class_type="GUEST"
        )
        
        # Verify legacy fields don't exist
        with pytest.raises(AttributeError):
            _ = event.validation_failures
        with pytest.raises(AttributeError):
            _ = event.total_files_processed
    
    def test_batch_validation_errors_event_follows_structured_error_handling(self):
        """Test separate error event follows structured error handling standards."""
        error_event = BatchValidationErrorsV1(
            batch_id="test",
            failed_essays=[create_validation_error()],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=True
            ),
            metadata=SystemProcessingMetadata(...)
        )
        
        # Verify structured error handling compliance
        assert isinstance(error_event.error_summary, BatchErrorSummary)
        assert error_event.failed_essays[0].error_detail.error_code
        assert error_event.error_summary.error_categories
```

### 2.4 Implementation Strategy

#### Step 1: Create New Event Models (Week 1)

```python
# libs/common_core/src/common_core/events/batch_coordination_events.py

from huleedu_service_libs.error_handling import ErrorDetail

class EssayValidationError(BaseModel):
    """Structured validation error for an essay following HuleEdu error standards."""
    essay_id: str
    file_name: str
    error_detail: ErrorDetail  # Uses structured error handling
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class BatchErrorSummary(BaseModel):
    """Summary of batch processing errors for observability."""
    total_errors: int
    error_categories: dict[str, int]  # e.g., {"validation": 3, "extraction": 2}
    critical_failure: bool = False  # True if no essays succeeded

class BatchValidationErrorsV1(BaseModel):
    """Event for batch validation failures - replaces legacy inline errors."""
    event: str = Field(default="batch.validation.errors.v1")
    batch_id: str
    failed_essays: list[EssayValidationError]
    error_summary: BatchErrorSummary
    correlation_id: UUID = Field(default_factory=uuid4)
    metadata: SystemProcessingMetadata

# Clean V2 event with NO legacy fields
class BatchEssaysReadyV2(BaseModel):
    """Clean event for successful batch readiness - NO legacy validation fields."""
    event: str = Field(default="batch.essays.ready.v2")
    batch_id: str
    ready_essays: list[EssayProcessingInputRefV1]
    batch_id: str
    entity_type: str = "batch"
    metadata: SystemProcessingMetadata
    
    # Educational context (clean)
    course_code: CourseCode
    course_language: str
    essay_instructions: str
    class_type: str
    teacher_first_name: str | None = None
    teacher_last_name: str | None = None
    
    # REMOVED: validation_failures, total_files_processed
```

#### Step 2: Replace Test Architecture (Week 2)

**COMPLETE TEST REPLACEMENT - NO REFACTORING**:

**🔴 DELETE These Docker-Heavy Tests**:
1. `services/essay_lifecycle_service/tests/integration/test_pending_validation_failures_integration.py`
2. `tests/functional/test_validation_coordination_complete_failures.py`
3. `tests/functional/test_validation_coordination_partial_failures.py`
4. `services/essay_lifecycle_service/tests/unit/test_batch_tracker_validation.py`
5. `services/essay_lifecycle_service/tests/unit/test_batch_tracker_validation_fix.py`

**🟢 CREATE These Fast Unit Tests**:
1. `services/essay_lifecycle_service/tests/unit/test_dual_event_publishing.py`
2. `services/essay_lifecycle_service/tests/unit/test_clean_batch_coordination.py`
3. `libs/common_core/tests/unit/test_event_contracts_v2.py`
4. `services/batch_orchestrator_service/tests/unit/test_dual_event_handling.py`

**Performance Improvement**:
- **Before**: 5-10 minute test suite (Docker overhead)
- **After**: 30 second test suite (pure unit tests)

#### Step 3: Update ELS Implementation (Week 2-3)

```python
# services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py

async def _publish_batch_ready_events(
    self,
    batch_id: str,
    ready_essays: list[EssayProcessingInputRefV1],
    failed_essays: list[EssayValidationError],
    batch_context: dict[str, Any],
) -> None:
    """Publish dual events: clean success + separate errors."""
    
    # Publish clean success event (NO legacy fields)
    if ready_essays:
        ready_event = BatchEssaysReadyV2(
            batch_id=batch_id,
            ready_essays=ready_essays,
            batch_id=batch_id,
            entity_type="batch",
            metadata=SystemProcessingMetadata(
                correlation_id=self.correlation_id,
                causation_id=str(uuid4()),
                timestamp=datetime.now(UTC)
            ),
            course_code=batch_context["course_code"],
            course_language=batch_context["course_language"],
            essay_instructions=batch_context["essay_instructions"],
            class_type=batch_context.get("class_type", "GUEST"),
            teacher_first_name=batch_context.get("teacher_first_name"),
            teacher_last_name=batch_context.get("teacher_last_name"),
        )
        
        await self.event_publisher.publish_batch_essays_ready(ready_event)
    
    # Publish separate structured error event
    if failed_essays:
        error_categories = self._categorize_errors(failed_essays)
        error_event = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=failed_essays,
            error_summary=BatchErrorSummary(
                total_errors=len(failed_essays),
                error_categories=error_categories,
                critical_failure=len(ready_essays) == 0
            ),
            metadata=SystemProcessingMetadata(
                correlation_id=self.correlation_id,
                causation_id=str(uuid4()),
                timestamp=datetime.now(UTC)
            )
        )
        
        await self.event_publisher.publish_batch_validation_errors(error_event)

def _categorize_errors(self, failed_essays: list[EssayValidationError]) -> dict[str, int]:
    """Categorize errors for observability metrics."""
    categories = {}
    for error in failed_essays:
        category = error.error_detail.error_code.split("_")[0].lower()
        categories[category] = categories.get(category, 0) + 1
    return categories
```

#### Step 4: Update BOS Consumer (Week 3)

```python
# services/batch_orchestrator_service/implementations/

# REMOVE legacy field handling
# BEFORE (DELETE):
# if event_data.validation_failures:
#     for failure in event_data.validation_failures:
#         # Handle legacy failure

# ADD new dual-event handling
@event_handler(ProcessingEvent.BATCH_VALIDATION_ERRORS)
async def handle_batch_validation_errors(
    self,
    event: EventEnvelope[BatchValidationErrorsV1]
) -> None:
    """Handle batch validation errors separately from success flow."""
    error_data = event.data
    
    # Structured error handling
    if error_data.error_summary.critical_failure:
        # Handle critical failure - no essays succeeded
        await self._handle_batch_critical_failure(
            error_data.batch_id,
            error_data.error_summary,
            str(event.correlation_id)
        )
    else:
        # Log errors but batch can still proceed with successful essays
        await self._log_batch_partial_failures(
            error_data.batch_id,
            error_data.failed_essays,
            error_data.error_summary
        )
    
    # Update observability metrics
    self._update_validation_error_metrics(error_data.error_summary)
```

### 2.5 Files Requiring Changes

#### 2.5.1 Core Implementation Changes (8 files)

**COMPLETE REWRITE Required**:
1. `libs/common_core/src/common_core/events/batch_coordination_events.py` - **Add new events, mark old fields deprecated**
2. `services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py` - **Dual event publishing**
3. `services/essay_lifecycle_service/implementations/batch_essay_tracker_impl.py` - **Remove legacy field population**
4. `services/batch_orchestrator_service/implementations/batch_essays_ready_handler.py` - **Add error event handler**

#### 2.5.2 Test Replacement (12 files)

**DELETE and REPLACE** (no refactoring):
- **DELETE**: All Docker-heavy integration tests (5 files)
- **DELETE**: All functional coordination tests (3 files)
- **CREATE**: Fast unit tests for dual-event patterns (4 files)

#### 2.5.3 Minor Field Removal (6 files)

**Simple field removal**:
1. `services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py` - Remove `"validation_failures": []`
2. `services/batch_orchestrator_service/tests/unit/test_idempotency_outage.py` - Remove `"validation_failures": []`
3. Other minor test updates

### 2.6 Success Metrics

#### 2.6.1 Code Quality Metrics
- ✅ **Zero `validation_failures` references** in production code
- ✅ **Zero `total_files_processed` references** in events
- ✅ **All new events use structured error handling** (ErrorDetail, BatchErrorSummary)
- ✅ **Clean separation** of success and error event flows

#### 2.6.2 Test Architecture Metrics
- ✅ **Test suite runtime**: <1 minute (down from 5-10 minutes)
- ✅ **Test maintainability**: Zero Docker dependencies for unit tests
- ✅ **Test clarity**: Each test validates single business concern
- ✅ **Test reliability**: No infrastructure flaking

#### 2.6.3 Observability Metrics
- ✅ **Error categorization**: Structured error categories for metrics
- ✅ **Critical failure detection**: Boolean flag for alerting
- ✅ **Correlation tracking**: Proper correlation IDs across events
- ✅ **Business impact measurement**: Success/failure ratio tracking

### 2.7 Migration Timeline

#### Week 1: Foundation & New Events
- **Day 1-2**: Create new event models in common_core
- **Day 3-4**: Update ELS to publish dual events (backward compatible)
- **Day 5**: Add BOS handlers for new error events

#### Week 2: Test Architecture Replacement
- **Day 1-2**: DELETE old Docker-heavy tests, CREATE fast unit tests
- **Day 3-4**: CREATE contract tests for new event schemas  
- **Day 5**: Verify 100% business logic coverage with new tests

#### Week 3: Legacy Removal & Cleanup
- **Day 1-2**: Remove legacy fields from BatchEssaysReady
- **Day 3-4**: Remove all legacy field handling code
- **Day 5**: Full regression testing with new fast test suite

This refactoring eliminates **critical architectural anti-patterns** in both **event design** and **test architecture**, establishing modern structured error handling and fast, maintainable testing practices across the HuleEdu platform.

## 3. NLP Service Architecture Decision

### 3.1 Analysis of Current Dual Responsibility

The NLP Service currently handles:
- **Phase 1**: Student matching (pre-readiness) - Pattern extraction and fuzzy matching
- **Phase 2**: NLP analysis (post-readiness) - Linguistic analysis

**Key Differences**:
- Different triggers: `ESSAY_STUDENT_MATCHING_REQUESTED` vs `BATCH_NLP_INITIATE_COMMAND`
- Different outputs: Match suggestions vs Analysis results
- Different consumers: Class Management vs Result Aggregator
- Different business purposes: Identity resolution vs Content analysis

### 3.2 Recommendation: Defer Split

While architecturally cleaner to split, I recommend **DEFERRING** the service split for now:

**Reasons**:
1. **YAGNI Principle**: Current implementation works and meets requirements
2. **Shared Infrastructure**: Both phases benefit from same caching, error handling, DI setup
3. **Code Reuse**: Extraction pipeline is used by both phases
4. **Maintenance Overhead**: Two services = double the deployment, monitoring, configuration

**Future Split Criteria**:
- Different scaling requirements emerge
- Teams need independent deployment cycles
- Business logic diverges significantly
- Performance profiles differ substantially

### 3.3 Immediate Improvements (Without Split)

Instead of splitting, improve internal organization:

```python
# services/nlp_service/event_processor.py

# Clear separation of concerns
PHASE_1_HANDLERS = {
    ProcessingEvent.ESSAY_STUDENT_MATCHING_REQUESTED: "student_matching_handler"
}

PHASE_2_HANDLERS = {
    ProcessingEvent.BATCH_NLP_INITIATE_COMMAND: "nlp_analysis_handler"
}

async def process_single_message(...):
    """Route to appropriate phase handler."""
    event_type = envelope.event_type
    
    # Clear phase separation
    if event_type in PHASE_1_HANDLERS:
        handler_name = PHASE_1_HANDLERS[event_type]
    elif event_type in PHASE_2_HANDLERS:
        handler_name = PHASE_2_HANDLERS[event_type]
    else:
        logger.error(f"Unknown event type: {event_type}")
        return
```

## 4. Implementation Timeline

### Week 1: Batch Orchestrator
- Day 1-2: Update repository implementation
- Day 3-4: Refactor coordinator logic
- Day 5: Run migration script, deploy

### Week 2: Common Core Events
- Day 1-2: Create new event models
- Day 3-4: Update ELS implementation
- Day 5: Update downstream consumers

### Week 3: Testing & Validation
- Day 1-2: Update all unit tests
- Day 3-4: Integration testing
- Day 5: Performance validation

## 5. Rollback Plan

Each refactoring has a safe rollback:

1. **Batch Orchestrator**: Revert repository changes, coordinator continues working
2. **Common Core**: Keep v1 events while migrating to v2
3. **NLP Service**: No changes needed if split is deferred

## 6. Success Metrics

- Zero `hasattr()` checks in Batch Orchestrator
- Zero dictionary fallbacks in pipeline handling
- All events use structured error handling
- No legacy fields in production events
- All tests pass without mocking dictionaries

## Conclusion

This refactoring eliminates critical technical debt while maintaining system stability. The CLEAN BREAK approach ensures no lingering backwards compatibility code. The deferred NLP Service split follows YAGNI principles while keeping the option open for future architectural evolution.