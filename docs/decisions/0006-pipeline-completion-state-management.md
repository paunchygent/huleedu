---
type: decision
id: ADR-0006
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0006: Pipeline Completion State Management

## Status
Proposed

## Implementation Status
- **BatchPipelineCompletedV1 event**: NOT YET IMPLEMENTED - event type defined but not published
- **_complete_pipeline method**: PROPOSED - does not exist yet
- **BCS phase completion endpoint**: NOT YET IMPLEMENTED
- **Pipeline session archival**: NOT YET IMPLEMENTED
- **prune_completed_steps**: EXISTS at `pipeline_rules_impl.py:128` but lacks BOS reporting integration

## Context
The HuleEdu assessment platform orchestrates multi-phase processing pipelines (Spellcheck → CJ Assessment → NLP Analysis → AI Feedback) across microservices. The current implementation has critical gaps:

### Current Architecture
- **BOS** (Batch Orchestrator Service): Coordinates pipeline execution, tracks state in PostgreSQL
- **BCS** (Batch Conductor Service): Resolves pipeline dependencies, maintains Redis state cache
- **ELS** (Essay Lifecycle Service): Manages essay state transitions and phase dispatching
- **Processing Services**: Spellcheck, CJ Assessment, NLP, etc.

### Critical Gaps
1. **Missing Completion Event**: BOS logs "Pipeline completed" but never publishes `BatchPipelineCompletedV1` event
2. **Incomplete State Reporting**: BOS never reports phase completions to BCS, causing `prune_completed_steps()` to fail
3. **Persistent Active Flags**: Completed pipelines remain marked as "active" indefinitely, blocking new pipeline requests
4. **No Deduplication**: Running "NLP Pipeline" after "CJ Assessment Pipeline" re-executes Spellcheck unnecessarily

### Business Impact
- **Multi-Pipeline Support Blocked**: Cannot run sequential pipelines (e.g., CJ Assessment → NLP → AI Feedback)
- **Testing Failures**: Integration tests timeout waiting for completion events that never arrive
- **Resource Waste**: Redundant processing due to missing dependency resolution
- **Operational Blindness**: No way to query pipeline completion status or history

The platform urgently needs pipeline completion tracking to support the imminent NLP integration and future AI Feedback pipeline.

## Decision
Implement **hybrid event-driven and REST state management** with explicit completion signaling:

### 1. Pipeline Completion Event Publishing
**Location**: `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py:193-199`

**New Behavior**:
```python
async def _complete_pipeline(
    self,
    batch_id: str,
    correlation_id: UUID,
    pipeline_state: ProcessingPipelineState
):
    """Complete pipeline execution and publish completion event."""

    # 1. Publish completion event to Kafka
    completion_event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        correlation_id=correlation_id,
        completed_phases=[phase.value for phase in pipeline_state.requested_pipelines],
        pipeline_status="completed",
        timestamp=datetime.now(UTC)
    )
    await self.event_publisher.publish(
        topic=topic_name(EventType.BATCH_PIPELINE_COMPLETED),
        event=completion_event
    )

    # 2. Report to BCS for state tracking
    await self._report_pipeline_completion_to_bcs(batch_id, pipeline_state)

    # 3. Archive pipeline session (clear active flags, preserve history)
    await self.batch_repository.archive_pipeline_session(batch_id, correlation_id)
```

### 2. BOS → BCS Phase Completion Reporting
**New HTTP Endpoint in BCS**: `POST /internal/v1/phases/complete`

**BCS Handler**:
```python
@pipeline_bp.route("/internal/v1/phases/complete", methods=["POST"])
@inject
async def record_phase_completion(
    batch_state_repo: FromDishka[BatchStateRepositoryProtocol]
):
    """Record phase completion for dependency resolution."""
    data = await request.get_json()

    # Update Redis state for each essay in batch
    essay_ids = await _get_batch_essay_ids(data["batch_id"])
    for essay_id in essay_ids:
        await batch_state_repo.record_essay_step_completion(
            batch_id=data["batch_id"],
            essay_id=essay_id,
            step_name=data["phase_name"],
            metadata={
                "completed_at": data["completed_at"],
                "essays_processed": data["essays_processed"]
            }
        )

    return jsonify({"status": "recorded"}), 200
```

**BOS Client Extension**:
Add `report_phase_completion()` method to `BatchConductorClientImpl`:
```python
async def report_phase_completion(
    self,
    batch_id: str,
    phase_name: PhaseName,
    essays_processed: int,
    metadata: dict | None = None
) -> bool:
    """Report phase completion to BCS for state tracking."""
    # HTTP POST to BCS /phases/complete endpoint
```

### 3. Pipeline Session Archival
**New Method**: `BatchRepositoryProtocol.archive_pipeline_session()`

**Behavior**:
- Move completed pipeline state to `pipeline_history` JSON array (new DB field)
- Clear active pipeline flags (`IN_PROGRESS`, `DISPATCH_INITIATED` → `None`)
- Preserve `COMPLETED` and `FAILED` states for BCS dependency resolution
- Allow new pipeline requests after archival

**Database Migration**:
```sql
ALTER TABLE batches ADD COLUMN pipeline_history JSONB DEFAULT '[]';
```

### 4. BCS State Repository Enhancement
**Fix**: `prune_completed_steps()` in `pipeline_rules_impl.py:128`

**New Behavior**:
```python
async def prune_completed_steps(
    self,
    pipeline_steps: list[str],
    batch_id: str
) -> list[str]:
    """Remove already-completed steps from pipeline."""
    remaining_steps = []
    for step in pipeline_steps:
        is_complete = await self.batch_state_repository.is_batch_step_complete(
            batch_id, step
        )
        if not is_complete:
            remaining_steps.append(step)
        else:
            logger.info(f"Skipping completed step: {step} for batch {batch_id}")
    return remaining_steps
```

### 5. Event Flow Summary
```
BOS receives final ELSBatchPhaseOutcomeV1
  ↓
BOS publishes BatchPipelineCompletedV1 (Kafka)
  ↓
BOS calls BCS POST /phases/complete (HTTP)
  ↓
BCS updates Redis state (batch:essay:completed_steps)
  ↓
BOS archives pipeline session (DB update)
  ↓
Clients/tests consume BatchPipelineCompletedV1
  ↓
Next pipeline request → BCS prunes completed steps
```

## Consequences

### Positive
- **Multi-Pipeline Support**: Sequential pipeline requests work correctly with deduplication
- **Operational Visibility**: Completion events enable monitoring, alerting, and client notifications
- **Resource Efficiency**: Avoid redundant processing via completed step pruning
- **State Consistency**: BCS state repository accurately reflects system reality
- **Testing Reliability**: Integration tests can deterministically wait for completion
- **History Tracking**: Pipeline execution history preserved for debugging and auditing

### Negative
- **Dual State Storage**: Pipeline state in both BOS PostgreSQL and BCS Redis (consistency risk)
- **Network Dependency**: BCS reporting adds HTTP call that can fail (requires retry logic)
- **Migration Required**: Database schema change for pipeline_history field
- **Complexity Increase**: Three-step completion process (event + HTTP + DB update) vs simple log
- **BCS Coupling**: BOS now makes synchronous HTTP calls to BCS (mitigated by non-blocking reporting)

## Alternatives Considered

1. **Event-Only State Management**: BCS consumes completion events instead of HTTP reporting
   - Rejected: Eventual consistency makes dependency resolution unreliable
   - BCS might prune steps before state update arrives, causing race conditions
   - HTTP provides synchronous confirmation needed for correctness

2. **Polling-Based Completion**: Clients poll BOS for pipeline status instead of consuming events
   - Rejected: Adds load, increases latency, anti-pattern for event-driven architecture
   - Events enable real-time notifications and loose coupling

3. **BCS as Single Source of Truth**: Move all pipeline state to BCS, remove BOS tracking
   - Rejected: Violates service boundaries; BOS owns pipeline orchestration
   - Would require BCS to understand business logic (pipeline composition rules)

4. **No Archival, Keep Active Flags Forever**: Allow multiple concurrent pipelines per batch
   - Rejected: Risk of resource exhaustion, unclear completion semantics
   - Need to prevent conflicting pipeline requests (e.g., two CJ Assessments)

5. **Synchronous Pipeline Execution**: Block until pipeline completes before returning to client
   - Rejected: Unacceptable latency (minutes to hours), defeats async architecture benefits
   - Would require long-lived HTTP connections or WebSockets

## Related ADRs
- ADR-0004: LLM Provider Batching Mode Selection (pipeline phase timing considerations)
- ADR-0005: Event Schema Versioning Strategy (BatchPipelineCompletedV1 schema governance)

## References
- docs/architecture/processing-flow-map-and-pipeline-state-management-implementation-plan.md
- services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py:193-199
- services/batch_conductor_service/implementations/pipeline_rules_impl.py:128
- .agent/rules/020-architectural-mandates.md (event-driven patterns)
- .agent/rules/042-async-patterns-and-di.md (async coordination)
