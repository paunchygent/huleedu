# CJ Assessment Batch LLM Processing Implementation Plan

## Document Status

- **Created**: 2025-01-15
- **Author**: Claude Code Assistant
- **Status**: In Planning
- **Target Implementation**: Phase 1 (Q1 2025)
- **Last Updated**: 2025-01-15 (Added failed comparison pool mechanism)

## Executive Summary

This document outlines the implementation plan for integrating batch LLM processing into the CJ Assessment Service. The plan builds upon existing infrastructure (callback processing, batch state management, async support) to create a robust batch processing system that minimizes changes to proven logic while enabling efficient processing of up to 200 comparisons per batch.

### Key Goals

1. **Minimal Disruption**: Integrate with existing workflow without replacing proven components
2. **Scalability**: Support batch sizes up to 200 comparisons with efficient async processing
3. **Reliability**: Handle failures gracefully with partial completion support and failed comparison pooling
4. **Future-Ready**: Architecture supports future stability-based stopping features
5. **Admin Control**: Enable dynamic batch size configuration and overrides
6. **Fairness**: Ensure all essays receive equal comparison counts through retry mechanism

## Current State Analysis

### Existing Infrastructure

The CJ Assessment Service already has significant infrastructure in place:

#### 1. Database Schema

- **CJBatchState** table with comprehensive tracking:
  - `submitted_comparisons`: Tracks comparisons sent to LLM
  - `completed_comparisons`: Successfully completed comparisons
  - `failed_comparisons`: Failed comparison attempts
  - `state`: Enum-based state machine (INITIALIZING, GENERATING_PAIRS, WAITING_CALLBACKS, SCORING, COMPLETED, FAILED, CANCELLED)
  - `processing_metadata`: JSON field for flexible metadata storage

#### 2. Async Processing Support

- **LLMProviderServiceClient** already handles:
  - 202 responses for queued requests
  - Returns `None` for async processing
  - Callback topic configuration

#### 3. Callback Processing

- **workflow_logic.py** implements:
  - `continue_cj_assessment_workflow()` for callback processing
  - State machine with optimistic locking
  - Progress tracking and failure rate monitoring

#### 4. Batch Monitoring

- **batch_monitor.py** provides:
  - Stuck batch detection
  - Automatic recovery strategies
  - Configurable timeout thresholds

### Current Workflow

1. **Synchronous Processing**: Comparisons are generated and processed sequentially
2. **Blocking Calls**: Each iteration waits for all LLM responses before proceeding
3. **Limited Concurrency**: Semaphore limits concurrent requests but within synchronous batch

### Identified Gaps

1. **Batch Submission**: No mechanism to submit large batches to LLM provider
2. **State Persistence**: Limited tracking of individual comparison states
3. **Partial Processing**: No support for continuing with partial results
4. **Dynamic Configuration**: Batch size configuration not exposed to admins

## Target Architecture

### High-Level Design

```text
┌─────────────────────┐     ┌─────────────────────┐
│ Workflow            │     │ Batch Processor     │
│ Orchestrator        │────▶│ (New Component)     │
└─────────────────────┘     └─────────────────────┘
           │                           │
           │                           ▼
           │                ┌─────────────────────┐
           │                │ LLM Provider        │
           │                │ Service (Async)     │
           │                └─────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ CJBatchState        │◀────│ Kafka Callbacks     │
│ (State Machine)     │     │ Topic               │
└─────────────────────┘     └─────────────────────┘
```

### Key Components

#### 1. Enhanced Batch Processor

- **Location**: `cj_core_logic/batch_processor.py`
- **Responsibilities**:
  - Submit comparison batches to LLM provider
  - Track submission state in database
  - Handle partial batch submissions
  - Implement retry logic for failed submissions

#### 2. State Management Enhancements

- **ComparisonPair** tracking:
  - Already has `request_correlation_id` for callback linkage
  - Already has `submitted_at` and `completed_at` timestamps
  - No schema changes needed!

#### 3. Configuration System

- **Dynamic Batch Size Control**:

  ```python
  # In config.py
  BATCH_SIZE_DEFAULT: int = 50
  BATCH_SIZE_MAX: int = 200
  BATCH_SIZE_MIN: int = 10
  
  # In request_data (admin override)
  batch_config_overrides: {
    "batch_size": 100,
    "max_concurrent_batches": 2,
    "partial_completion_threshold": 0.85
  }
  ```

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

#### 1.1 Create Batch Processor Module

```python
# cj_core_logic/batch_processor.py
class BatchProcessor:
    def __init__(
        self,
        llm_interaction: LLMInteractionProtocol,
        database: CJRepositoryProtocol,
        settings: Settings,
    ):
        self.llm_interaction = llm_interaction
        self.database = database
        self.settings = settings
        
    async def submit_comparison_batch(
        self,
        comparison_tasks: list[ComparisonTask],
        cj_batch_id: int,
        correlation_id: UUID,
        batch_config: dict[str, Any] | None = None,
    ) -> BatchSubmissionResult:
        """Submit comparisons in configurable batches."""
        # Implementation details below
```

#### 1.2 Integrate with Existing Workflow

- Modify `comparison_processing.py` to use BatchProcessor
- Replace synchronous `perform_comparisons` with batch submission
- Update state to WAITING_CALLBACKS after submission

#### 1.3 Enhance Callback Processing

- Update `workflow_logic.py` to handle batch completion logic
- Implement "continue or complete" decision making
- Add support for partial batch completion

### Phase 2: State Management (Week 3)

#### 2.1 Batch State Transitions

```python
# State machine transitions
INITIALIZING → GENERATING_PAIRS → WAITING_CALLBACKS → SCORING → COMPLETED
                                          ↓
                                       FAILED
```

#### 2.2 Progress Tracking

- Implement real-time progress updates
- Use existing `CJBatchState` counters
- Add batch submission metadata to `processing_metadata`

#### 2.3 Failure Handling

- Track individual comparison failures in a dedicated pool
- Implement configurable failure thresholds before triggering retries
- Support retry of failed comparisons while preserving original pairs
- Maintain failure counts per comparison for limiting retry attempts
- Ensure failed comparisons are collected and retried as complete batches

##### Failed Comparison Pool Mechanism

The system maintains a pool of failed comparisons that preserves:

- Original comparison pair IDs (essay_1_id, essay_2_id)
- Original pairing context (why these essays were paired)
- Failure reason and timestamp
- Retry attempt count

When failures exceed a threshold (e.g., 20 comparisons), the system:

1. Forms a retry batch from the failed pool
2. Submits the retry batch with same size constraints (up to 200)
3. Marks comparisons as retry attempts in metadata
4. Continues normal processing for successful comparisons

This ensures all essays receive equal comparison counts, which is critical for Bradley-Terry scoring fairness.

#### 2.4 Failed Comparison Pool Management

##### Pool Data Structure

```python
# In processing_metadata
{
    "failed_comparison_pool": [
        {
            "essay_a_id": "123",
            "essay_b_id": "456",
            "comparison_task": {...},  # Original task data
            "failure_reason": "timeout",
            "failed_at": "2024-01-15T10:30:00Z",
            "retry_count": 0,
            "batch_id": "batch_001"  # Original batch
        }
    ],
    "pool_statistics": {
        "total_failed": 23,
        "retry_attempts": 1,
        "last_retry_batch": "retry_batch_001"
    }
}
```

##### Retry Batch Formation

```python
async def form_retry_batch(self, session: AsyncSession, batch_id: int):
    """Form a retry batch from failed comparison pool."""
    
    # Get current failed pool
    batch_state = await self.get_batch_state(session, batch_id)
    failed_pool = batch_state.processing_metadata.get("failed_comparison_pool", [])
    
    # Check if we have enough failures to warrant a batch
    retry_threshold = self.settings.FAILED_COMPARISON_RETRY_THRESHOLD  # e.g., 20
    if len(failed_pool) < retry_threshold and not batch_state.all_submitted:
        return None  # Wait for more failures or completion
    
    # Form retry batch (up to max batch size)
    retry_batch = failed_pool[:self.settings.BATCH_SIZE_MAX]
    
    # Submit as special retry batch
    retry_result = await self.submit_batch(
        comparisons=retry_batch,
        is_retry=True,
        parent_batch_id=batch_id
    )
    
    # Update pool and statistics
    remaining_pool = failed_pool[len(retry_batch):]
    batch_state.processing_metadata["failed_comparison_pool"] = remaining_pool
    batch_state.processing_metadata["pool_statistics"]["retry_attempts"] += 1
    
    return retry_result
```

##### Integration with Workflow

1. **On Callback Failure**: Add comparison to failed pool
2. **On Batch Progress Check**: Check if retry batch needed
3. **On Retry Success**: Remove from pool, update counts
4. **On Max Retries**: Mark comparison as permanently failed

### Phase 3: Configuration & Control (Week 4)

#### 3.1 Admin Override System

```python
# models_api.py enhancement
class CJAssessmentRequest(BaseModel):
    # ... existing fields ...
    batch_config_overrides: BatchConfigOverrides | None = None

class BatchConfigOverrides(BaseModel):
    batch_size: int | None = Field(None, ge=10, le=200)
    max_concurrent_batches: int | None = Field(None, ge=1, le=5)
    partial_completion_threshold: float | None = Field(None, ge=0.5, le=1.0)
    enable_stability_checking: bool | None = None
```

#### 3.2 Dynamic Configuration

- Read batch size from request or settings
- Validate against min/max constraints
- Log configuration for audit trail

### Phase 4: Stability Support Preparation (Week 5)

#### 4.1 Score Tracking Infrastructure

```python
# Enhanced processing_metadata structure
{
    "iterations": [
        {
            "iteration_number": 1,
            "comparisons_submitted": 50,
            "comparisons_completed": 48,
            "score_snapshot": {...},
            "max_score_change": 0.15
        }
    ],
    "stability_metrics": {
        "consecutive_stable_iterations": 0,
        "stability_threshold": 0.05
    }
}
```

#### 4.2 Iteration Management

- Track scores between iterations
- Calculate stability metrics
- Prepare for future early stopping

## Integration Points

### 1. Minimal Changes to Existing Code

#### comparison_processing.py

```python
# OLD CODE (lines 199-207)
llm_comparison_results: list[ComparisonResult] = await perform_comparisons_coro(
    comparison_tasks_for_llm,
    model_override=model_override,
    # ...
)

# NEW CODE
batch_processor = BatchProcessor(llm_interaction, database, settings)
submission_result = await batch_processor.submit_comparison_batch(
    comparison_tasks_for_llm,
    cj_batch_id=cj_batch_id,
    correlation_id=correlation_id,
    batch_config=request_data.get("batch_config_overrides"),
)

# Update state and return - let callbacks handle results
if submission_result.all_submitted:
    await database.update_batch_state(
        session, cj_batch_id, 
        state=CJBatchStateEnum.WAITING_CALLBACKS
    )
    return None  # Workflow continues via callbacks
```

### 2. Callback Integration

The existing `continue_cj_assessment_workflow` already handles:

- Individual comparison result updates
- Progress tracking
- State transitions
- Completion detection

No changes needed to callback processing!

### 3. Monitoring Integration

Enhance `batch_monitor.py` to:

- Track batches in WAITING_CALLBACKS state
- Detect submission failures
- Trigger resubmission if needed

## State Management Design

### Batch Lifecycle States

1. **INITIALIZING**
   - Essays being prepared
   - Initial setup

2. **GENERATING_PAIRS**
   - Creating comparison pairs
   - Preparing batches

3. **WAITING_CALLBACKS** (New primary state)
   - Comparisons submitted to LLM
   - Awaiting async results
   - May have multiple submission batches in flight

4. **SCORING**
   - All comparisons complete
   - Calculating final scores

5. **COMPLETED**
   - Final scores published
   - Success state

6. **FAILED**
   - Unrecoverable error
   - Too many failures

### Comparison Tracking

Each ComparisonPair already has:

- `request_correlation_id`: Links to LLM callback
- `submitted_at`: When sent to LLM
- `completed_at`: When result received
- `winner`: Result or "error"

This existing schema perfectly supports batch processing!

## Configuration System

### Settings Hierarchy

1. **Default Settings** (config.py)
2. **Environment Overrides** (ENV vars)
3. **Request Overrides** (Admin API)

### Key Configuration Parameters

```python
# Batch Processing
BATCH_SIZE_DEFAULT: int = 50
BATCH_SIZE_MAX: int = 200
BATCH_SIZE_MIN: int = 10
MAX_CONCURRENT_BATCHES: int = 3

# Completion Thresholds
PARTIAL_COMPLETION_THRESHOLD: float = 0.85
MIN_SUCCESS_RATE: float = 0.80

# Timeouts
BATCH_SUBMISSION_TIMEOUT: int = 30  # seconds
CALLBACK_WAIT_TIMEOUT: int = 300   # 5 minutes

# Failed Comparison Pool
FAILED_COMPARISON_RETRY_THRESHOLD: int = 20  # Min failures before retry batch
MAX_RETRY_ATTEMPTS: int = 3  # Max retries per comparison
RETRY_BATCH_PRIORITY: str = "high"  # Priority for retry batches

# Stability (Future)
ENABLE_STABILITY_CHECKING: bool = False
STABILITY_CHECK_INTERVAL: int = 10
STABILITY_THRESHOLD: float = 0.05
```

## Future Stability Threshold Support

### Architecture Preparation

1. **Score Snapshots**
   - Store BT scores after each batch
   - Track in `processing_metadata`

2. **Stability Calculation**
   - Already implemented in `workflow_logic._check_score_stability`
   - Just needs score calculation implementation

3. **Early Stopping Logic**

   ```python
   if (stability_enabled and 
       consecutive_stable_iterations >= required_stable_iterations):
       # Complete early with stable scores
       batch_state.state = CJBatchStateEnum.COMPLETED
   ```

### Migration Path

1. **Phase 1**: Batch processing without stability
2. **Phase 2**: Add score tracking between batches
3. **Phase 3**: Enable stability-based stopping
4. **Phase 4**: Admin controls for stability thresholds

## Risk Mitigation

### 1. Performance Risks

- **Risk**: Large batches overwhelm LLM provider
- **Mitigation**:
  - Configurable batch sizes
  - Rate limiting at submission
  - Circuit breaker protection

### 2. Reliability Risks

- **Risk**: Network failures during batch submission
- **Mitigation**:
  - Retry logic with exponential backoff
  - Partial batch recovery
  - Comprehensive error tracking

### 3. Data Consistency Risks

- **Risk**: Callbacks arrive out of order
- **Mitigation**:
  - Idempotent callback processing
  - Request correlation IDs
  - Optimistic locking on state updates

### 4. Operational Risks

- **Risk**: Stuck batches in WAITING_CALLBACKS
- **Mitigation**:
  - Batch monitor enhancements
  - Configurable timeouts
  - Manual intervention tools

## Success Criteria

### Functional Requirements

1. ✓ Support batch sizes up to 200 comparisons
2. ✓ Process callbacks asynchronously
3. ✓ Handle partial batch completion (≥85% threshold)
4. ✓ Maintain backward compatibility
5. ✓ Enable admin configuration overrides

### Performance Requirements

1. ✓ Reduce total processing time by 50%+
2. ✓ Support 3+ concurrent batches per assessment
3. ✓ Handle 1000+ comparisons per minute (system-wide)
4. ✓ Maintain <5% failure rate under normal conditions

### Operational Requirements

1. ✓ Comprehensive progress tracking
2. ✓ Automatic failure recovery
3. ✓ Detailed audit logging
4. ✓ Prometheus metrics for monitoring
5. ✓ Clear error messages for debugging

## Implementation Timeline

### Week 1-2: Foundation

- [ ] Create BatchProcessor module
- [ ] Update comparison_processing.py
- [ ] Write unit tests for batch submission
- [ ] Integration test with mock LLM provider

### Week 3: State Management

- [ ] Enhance state transitions
- [ ] Implement progress tracking
- [ ] Add failure handling logic
- [ ] Test partial completion scenarios

### Week 4: Configuration

- [ ] Add batch config to API models
- [ ] Implement override validation
- [ ] Create admin documentation
- [ ] End-to-end testing

### Week 5: Stability Preparation

- [ ] Add score tracking infrastructure
- [ ] Implement iteration metadata
- [ ] Prepare stability calculations
- [ ] Performance testing

### Week 6: Production Readiness

- [ ] Load testing with real workloads
- [ ] Monitor integration
- [ ] Deployment procedures
- [ ] Rollback plan

## Conclusion

This implementation plan provides a clear path to integrate batch LLM processing into the CJ Assessment Service while:

- Minimizing changes to proven logic
- Leveraging existing infrastructure
- Preparing for future enhancements
- Maintaining system reliability

The phased approach ensures each component is thoroughly tested before moving to the next phase, reducing risk and ensuring a smooth transition to batch processing.
