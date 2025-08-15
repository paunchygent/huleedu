# Multi-Pipeline Support Implementation Task

**Created**: 2025-01-15  
**Status**: IN PROGRESS  
**Reference**: `documentation/processing-flow-map-and-pipeline-state-management-implementation-plan.md`

## Overview

Implementing multi-pipeline support to enable sequential pipeline execution where subsequent pipelines can skip already-completed phases. This is critical for enabling NLP Pipeline integration alongside existing CJ Assessment Pipeline.

## Session 1: Core Infrastructure (COMPLETED - 2025-01-15)

### What We Implemented

1. **BatchPipelineCompletedV1 Event Model** (`libs/common_core/src/common_core/events/batch_coordination_events.py`)
   - Created event model with pipeline completion metrics
   - Added to event enums and topic mappings
   - Integrated with EventEnvelope pattern

2. **Pipeline Completion Detection & Publishing** (`services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`)
   - Added `_publish_pipeline_completion_event()` method
   - Detects when all requested phases complete
   - Publishes BatchPipelineCompletedV1 with completion metrics
   - Conservative essay success/failure counting (TODO: improve with actual counts from ELSBatchPhaseOutcomeV1)

3. **BOS→BCS Phase Reporting (TO BE REMOVED)** (`services/batch_orchestrator_service/implementations/batch_conductor_client_impl.py`)
   - Added `report_phase_completion()` method
   - Integrated into pipeline coordinator
   - **Note**: Will be removed in Session 2 for pure event-driven approach

4. **BCS Phase Completion Endpoint** (`services/batch_conductor_service/api/pipeline_routes.py`)
   - Added `/internal/v1/phases/complete` endpoint
   - Batch-level phase tracking (not essay-level)
   - Will remain for operational/manual use only

### Architectural Decision Made

After analysis, we determined:
- **Batch-level completion tracking is correct** (not essay-level)
- **Failed essays should go to DLQ** (not automatic retry)
- **Pure event-driven is the right approach** (not API calls)

## Session 2: Event-Driven Refactoring (NEXT)

### What We Need to Do

1. **Remove BOS→BCS API Coupling**
   - Remove `bcs_client` parameter from `DefaultPipelinePhaseCoordinator`
   - Remove `report_phase_completion()` calls from pipeline coordinator
   - Update DI configuration to remove BCS client injection
   - Simplify pipeline coordinator to only publish events

2. **Implement BCS Event Consumption**
   - Update `services/batch_conductor_service/kafka_consumer.py`:
     - Add handler for `ELSBatchPhaseOutcomeV1` events
     - Add handler for `BatchPipelineCompletedV1` events
     - Record phase completions from events (not API calls)
   - Ensure BCS consumer subscribes to required topics:
     - `huleedu.els.batch.phase.outcome.v1`
     - `huleedu.batch.pipeline.completed.v1`

3. **Fix Test Files**
   - Update test files that create `DefaultPipelinePhaseCoordinator`:
     - `tests/integration/test_pipeline_state_management_scenarios.py`
     - `tests/integration/test_pipeline_state_management_progression.py`
     - `tests/integration/test_pipeline_state_management_failures.py`
     - `tests/integration/test_pipeline_state_management_edge_cases.py`
   - Remove `bcs_client` parameter from test instantiations

4. **Update Pipeline Rules Implementation**
   - Verify `services/batch_conductor_service/implementations/pipeline_rules_impl.py:111-120`
   - Ensure `prune_completed_steps()` correctly queries Redis state
   - Test that completed phases are properly skipped

## Session 3: Testing & Quality Control

### Integration Testing

1. **Test Multi-Pipeline Flow**
   - Run CJ Assessment Pipeline (spellcheck + cj_assessment)
   - Run NLP Pipeline on same batch
   - Verify NLP skips spellcheck (already completed)
   - Verify only NLP phase executes

2. **Test Pipeline Completion Event**
   - Verify BatchPipelineCompletedV1 publishes when pipeline completes
   - Verify event contains correct completion metrics
   - Verify BCS receives and processes the event
   - Verify pipeline state is cleared for next pipeline

3. **Test Failure Scenarios**
   - Test batch with some failed essays
   - Verify status is COMPLETED_WITH_FAILURES
   - Verify failed essays don't block completion
   - Verify failed essays are tracked for DLQ

4. **End-to-End Test**
   - Full flow from ClientBatchPipelineRequestV1 to BatchPipelineCompletedV1
   - Verify all events publish correctly
   - Verify state management works across services

### Quality Control

1. **Run Full Test Suite**
   ```bash
   pdm run typecheck-all
   pdm run test-all
   pdm run lint
   ```

2. **Verify Event Flow**
   - Trace correlation IDs through full pipeline
   - Ensure no events are lost
   - Verify idempotency at each step

3. **Performance Testing**
   - Measure latency of pipeline completion detection
   - Verify Redis state updates are performant
   - Check for any memory leaks in long-running services

## Session 4: NLP Pipeline Implementation

### What This Enables

With multi-pipeline support complete, we can:

1. **Implement NLP Pipeline**
   - Create NLP-specific pipeline configuration in BCS
   - NLP Pipeline = [spellcheck, nlp]
   - When run after CJ Assessment, spellcheck will be skipped

2. **Test Pipeline Combinations**
   - CJ Assessment Pipeline → NLP Pipeline (skip spellcheck)
   - NLP Pipeline → CJ Assessment Pipeline (skip spellcheck, nlp)
   - AI Feedback Pipeline (when implemented) with all dependencies

3. **Enable Teacher Workflows**
   - Teachers can run initial assessment (CJ)
   - Then run deeper analysis (NLP) without reprocessing
   - Finally get AI feedback without redundant work

### Success Criteria

- [ ] Multiple pipelines can be run on same batch
- [ ] Completed phases are skipped in subsequent pipelines
- [ ] Pipeline completion events publish correctly
- [ ] BCS tracks state via event consumption (not API calls)
- [ ] No redundant processing occurs
- [ ] Failed essays don't block pipeline completion

## Architecture Alignment

This implementation follows the architecture defined in the processing flow map by:

1. **Solving Gap 1**: Pipeline Completion Event (Section 5, Gap 1)
   - BatchPipelineCompletedV1 now publishes when pipeline completes

2. **Solving Gap 2**: BCS State Population (Section 5, Gap 2)
   - BCS will consume events to track phase completions

3. **Solving Gap 3**: Pipeline State Management (Section 5, Gap 3)
   - Pipeline completion clears active state for next pipeline

4. **Enabling Solution 1**: Pipeline Completion Implementation (Section 6, Solution 1)
   - Completion event publishing is implemented

5. **Enabling Solution 2**: BCS Completion Tracking (Section 6, Solution 2)
   - Event-driven tracking will be implemented in Session 2

## Notes

- We chose event-driven over API calls for better service autonomy
- Batch-level tracking is sufficient (essay-level not needed for completion)
- Failed essays should go to DLQ, not trigger retries
- The architecture is now ready for true multi-pipeline workflows