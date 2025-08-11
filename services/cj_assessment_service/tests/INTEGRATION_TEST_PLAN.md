# Comprehensive Integration Test Plan for CJ Assessment Service

## Overview
This document outlines the implementation plan for critical integration tests that validate the complete CJ Assessment workflow, including incremental scoring, anchor essay integration, workflow continuation, and retry mechanisms.

---

## 1. Incremental Scoring Tests - Score Evolution Through Callback Lifecycle

### Test File: `test_incremental_scoring_integration.py`

### Purpose
Track and validate how Bradley-Terry scores evolve as LLM callbacks arrive incrementally throughout the batch processing lifecycle.

### Test Scenarios
1. **Progressive Score Refinement**
   - Submit batch with 50 essays (1225 comparison pairs)
   - Process callbacks in increments: 10%, 25%, 50%, 75%, 90%, 100%
   - Track score changes, stability metrics, and ranking shifts
   - Validate monotonic improvement in score confidence

2. **Early Stopping Detection**
   - Test score stability threshold triggering
   - Validate that processing stops when scores converge
   - Ensure partial completion triggers at 80% threshold

3. **Score Consistency Across Iterations**
   - Verify that final rankings remain stable
   - Test that score differences are preserved
   - Validate mean-centering after each update

### Implementation Files to Test
```
services/cj_assessment_service/
├── cj_core_logic/
│   ├── scoring_ranking.py              # record_comparisons_and_update_scores, check_score_stability
│   ├── batch_callback_handler.py       # process_callback_and_continue_workflow
│   ├── callback_state_manager.py       # update_comparison_result, check_batch_completion_conditions
│   └── batch_completion_checker.py     # should_trigger_completion
├── implementations/
│   └── db_access_impl.py              # get_batch_comparison_stats
└── event_processor.py                 # process_llm_result
```

### Data Models & Events
```
common_core/
├── events/
│   ├── llm_provider_events.py         # LLMComparisonResultV1, TokenUsage
│   └── cj_assessment_events.py        # CJAssessmentCompletedV1, ELS_CJAssessmentRequestV1
├── status_enums.py                    # CJBatchStateEnum, BatchStatus
└── domain_enums.py                    # EssayComparisonWinner

services/cj_assessment_service/
├── models_db.py                       # CJBatchState, ComparisonPair, ProcessedEssay
├── models_api.py                      # ComparisonResult, EssayForComparison
└── enums_db.py                        # CJBatchStatusEnum, CJIterationEnum
```

---

## 2. Anchor Essay Integration Test - Full Workflow with Grade Projection

### Test File: `test_anchor_essay_workflow_integration.py`

### Purpose
Validate the complete anchor essay workflow from initial batch creation through grade projection and final grade assignment.

### Test Scenarios
1. **Full Anchor Workflow**
   - Create batch with 30 student essays + 24 anchor essays (3 per grade: A, B, C, D, E, F)
   - Process all comparisons including student-anchor pairs
   - Validate grade calibration from anchor BT scores
   - Test grade probability distributions and confidence scores

2. **Sparse Anchor Handling**
   - Test with only 2-3 anchor grades present
   - Validate fallback to expected grade positions
   - Test variance inflation for uncertain grades

3. **Grade Boundary Calculation**
   - Test isotonic regression for monotonic boundaries
   - Validate smooth grade transitions
   - Test entropy-based confidence calculation

### Implementation Files to Test
```
services/cj_assessment_service/
├── cj_core_logic/
│   ├── grade_projector.py             # GradeProjector class, project_grades_from_rankings
│   ├── grade_utils.py                 # Grade conversion utilities, Swedish grade system
│   ├── anchor_essay_manager.py        # fetch_anchor_essays, prepare_anchor_context
│   └── batch_preparation.py           # prepare_batch_with_anchors
├── implementations/
│   └── content_client_impl.py         # fetch_content for anchor essays
└── protocols.py                       # AnchorEssayContext protocol
```

### Data Models & Events
```
common_core/
├── events/
│   └── cj_assessment_events.py        # RAS_CJGradeProjectionV1, AnchorGradeDistribution
├── metadata_models.py                 # AnchorEssayRef, GradeProjection
└── domain_enums.py                    # CourseCode, Grade

services/cj_assessment_service/
├── models_db.py                       # ProcessedEssay (is_anchor flag)
└── cj_core_logic/
    └── grade_calibration.py           # GradeCalibrationData, AnchorStatistics
```

---

## 3. Workflow Continuation Test - Real Async Workflow

### Test File: `test_async_workflow_continuation_integration.py`

### Purpose
Test the real asynchronous workflow continuation without mocks, validating the complete async processing chain.

### Test Scenarios
1. **Async Workflow Chain**
   - Remove all mocks for continue_workflow_async
   - Test real async task spawning and completion
   - Validate workflow state transitions
   - Test concurrent comparison processing

2. **Iteration Management**
   - Test iteration transitions (INITIAL → REFINEMENT → FINAL)
   - Validate comparison pair generation per iteration
   - Test iteration-based scoring updates
   - Validate iteration completion criteria

3. **Workflow State Recovery**
   - Test workflow resumption after interruption
   - Validate state consistency across restarts
   - Test idempotent workflow operations

### Implementation Files to Test
```
services/cj_assessment_service/
├── cj_core_logic/
│   ├── comparison_processing.py       # continue_workflow_async, process_iteration_async
│   ├── batch_processor.py             # submit_batch_for_comparisons
│   ├── batch_submission.py            # update_batch_status, get_batch_state
│   └── workflow_coordinator.py        # coordinate_batch_workflow
├── implementations/
│   └── llm_interaction_impl.py        # submit_comparisons_async
└── event_processor.py                 # process_single_message (Kafka consumer)
```

### Data Models & Events
```
common_core/
├── events/
│   ├── envelope.py                    # EventEnvelope
│   └── llm_provider_events.py         # LLMComparisonRequestV1
├── status_enums.py                    # ProcessingStage
└── event_enums.py                     # ProcessingEvent, topic_name

services/cj_assessment_service/
├── models_db.py                       # CJBatchState, CJIteration
└── enums_db.py                        # CJIterationEnum, WorkflowStateEnum
```

---

## 4. Retry Mechanism Tests - Resilience to Failures

### Test File: `test_retry_mechanisms_integration.py`

### Purpose
Validate retry mechanisms and error recovery strategies for failed comparisons and stuck batches.

### Test Scenarios
1. **Failed Comparison Retry**
   - Simulate LLM provider failures (timeout, rate limit, invalid response)
   - Test exponential backoff retry logic
   - Validate retry pool management
   - Test maximum retry limit enforcement

2. **Batch Recovery**
   - Test stuck batch detection (>6 hours in WAITING_CALLBACKS)
   - Validate batch monitor recovery workflow
   - Test partial batch completion with failed comparisons
   - Validate graceful degradation strategies

3. **Circuit Breaker Testing**
   - Test circuit breaker activation after repeated failures
   - Validate fallback to alternative LLM providers
   - Test circuit breaker reset logic
   - Validate health check mechanisms

4. **Transactional Integrity**
   - Test database transaction rollback on failures
   - Validate no partial updates or orphaned data
   - Test concurrent failure handling
   - Validate event publishing atomicity

### Implementation Files to Test
```
services/cj_assessment_service/
├── cj_core_logic/
│   ├── batch_retry_processor.py       # BatchRetryProcessor, retry_failed_comparisons
│   ├── callback_error_handler.py      # handle_callback_error, should_retry
│   └── circuit_breaker.py             # CircuitBreaker implementation
├── batch_monitor.py                   # BatchMonitor, check_and_recover_stuck_batches
├── implementations/
│   └── retry_policy_impl.py           # Exponential backoff, jitter
└── metrics.py                         # failure_counter, retry_counter metrics
```

### Data Models & Events
```
common_core/
├── error_enums.py                     # ErrorCode, CJAssessmentErrorCode
├── models/
│   └── error_models.py                # ErrorDetail, ServiceError
└── events/
    └── system_events.py               # SystemHealthEvent, RecoveryEvent

services/cj_assessment_service/
├── models_api.py                      # FailedComparisonEntry, FailedComparisonPoolStatistics
├── models_db.py                       # ComparisonPair (error fields), RetryHistory
└── enums_db.py                        # RetryStatusEnum, FailureTypeEnum

libs/huleedu_service_libs/
└── src/huleedu_service_libs/
    └── error_handling/
        ├── cj_assessment_factories.py # CJ-specific error factories
        └── huleedu_error.py           # HuleEduError base class
```

---

## 5. Test Implementation Priority & Dependencies

### Phase 1: Foundation (Week 1)
1. **Incremental Scoring Tests** - Critical for understanding score evolution
2. **Async Workflow Continuation** - Remove mocks, establish real workflow

### Phase 2: Advanced Features (Week 2)
3. **Anchor Essay Integration** - Complex grade projection workflow
4. **Retry Mechanisms** - Error handling and resilience

### Test Infrastructure Requirements
```
services/cj_assessment_service/tests/
├── fixtures/
│   ├── test_data_generator.py         # Generate realistic essay/comparison data
│   ├── kafka_test_utils.py            # Kafka test consumer/producer utilities
│   └── llm_response_factory.py        # Create mock LLM responses
└── integration/
    ├── conftest.py                     # Shared pytest fixtures
    └── test_helpers.py                 # Common test utilities
```

---

## 6. Validation Criteria

### All Tests Must Validate:
1. **Functional Correctness**
   - Business logic works as designed
   - Mathematical properties are preserved
   - State transitions are valid

2. **Performance Characteristics**
   - Processing time scales linearly
   - Memory usage remains bounded
   - Database queries are optimized

3. **Error Handling**
   - Graceful degradation on failures
   - No data corruption or loss
   - Clear error messages and logging

4. **Observability**
   - Metrics are correctly recorded
   - Traces span the full workflow
   - Logs provide debugging context

---

## 7. Test Execution Strategy

### Local Development
```bash
# Run individual test suites
pdm run pytest tests/integration/test_incremental_scoring_integration.py -xvs
pdm run pytest tests/integration/test_anchor_essay_workflow_integration.py -xvs
pdm run pytest tests/integration/test_async_workflow_continuation_integration.py -xvs
pdm run pytest tests/integration/test_retry_mechanisms_integration.py -xvs

# Run all integration tests
pdm run pytest tests/integration/ -m integration --tb=short

# Run with coverage
pdm run pytest tests/integration/ --cov=services/cj_assessment_service --cov-report=html
```

### CI/CD Pipeline
```yaml
# GitHub Actions workflow
- name: Run CJ Assessment Integration Tests
  run: |
    docker-compose up -d postgres kafka
    pdm run pytest services/cj_assessment_service/tests/integration/ \
      -m integration \
      --junit-xml=test-results.xml \
      --cov-report=xml
```

---

## 8. Success Metrics

### Test Coverage Goals
- **Line Coverage**: >80% for critical paths
- **Branch Coverage**: >75% for decision points
- **Integration Coverage**: 100% of external service interactions

### Quality Metrics
- **Test Execution Time**: <30 seconds per test file
- **Test Stability**: 0% flakiness over 100 runs
- **Memory Usage**: <500MB per test execution
- **Database Connections**: <10 concurrent connections

---

## Notes

### Key Principles
1. **No Mocks for Core Logic** - Test real implementations
2. **Real Database Operations** - Use testcontainers for PostgreSQL
3. **Real Event Processing** - Use embedded Kafka for event testing
4. **Realistic Data Volumes** - Test with production-like data sizes
5. **Error Injection** - Systematically test failure scenarios

### References
- Testing Methodology: `.cursor/rules/075-test-creation-methodology.mdc`
- Architecture Rules: `.cursor/rules/020-architectural-mandates.mdc`
- Event Standards: `.cursor/rules/030-event-driven-architecture-eda-standards.mdc`
- Error Handling: `.cursor/rules/048-structured-error-handling-standards.mdc`