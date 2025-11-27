# Dual-Event Pattern

Architectural pattern for separating state tracking from business data in event-driven systems.

## Pattern Overview

Publish TWO events when completing processing:

1. **Thin Event**: State tracking only → Orchestrator (ELS, BOS)
2. **Rich Event**: Full business data → Aggregator/Consumer (RAS, Analytics)

This separates concerns: orchestration logic doesn't couple to business data structures.

## Base Classes

### Thin Events: ProcessingUpdate

```python
from common_core.events.base_event_models import ProcessingUpdate

class ProcessingUpdate(BaseEventData):
    """Base for thin state-tracking events."""

    status: ProcessingStage  # COMPLETED, FAILED, etc.
    system_metadata: SystemProcessingMetadata  # Timestamps, errors
```

Thin events extend `ProcessingUpdate`, contain ONLY:
- Processing status (success/failure)
- Entity reference (batch_id, essay_id)
- Error information (if failed)
- Processing summary (counts, not data)

### Rich Events: BaseEventData

```python
from common_core.events.base_event_models import BaseEventData

class BaseEventData(BaseModel):
    """Base for all event data models."""

    event_name: ProcessingEvent
    entity_ref: str  # Business entity ID
```

Rich events extend `BaseEventData`, contain:
- Full business results
- Detailed metrics
- Typed data structures
- Large payloads (or StorageReferences)

## CJ Assessment Example (Canonical)

File: `common_core/events/cj_assessment_events.py`

### Thin Event: CJAssessmentCompletedV1

```python
class CJAssessmentCompletedV1(ProcessingUpdate):
    """State tracking event to ELS.

    CRITICAL: Thin event following clean architecture.
    Contains ONLY state information - NO business data.
    Business data goes to RAS via AssessmentResultV1.

    Producer: CJ Assessment Service
    Consumer: Essay Lifecycle Service
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    # entity_ref inherited from BaseEventData - BOS Batch ID
    # status inherited from ProcessingUpdate - COMPLETED/FAILED
    # system_metadata inherited from ProcessingUpdate - timestamps, errors

    cj_assessment_job_id: str  # Internal CJ job ID for tracing

    # State summary - NO business data
    processing_summary: dict[str, Any] = Field(
        description="Summary for state management",
        default_factory=lambda: {
            "total_essays": 0,
            "successful": 0,
            "failed": 0,
            "successful_essay_ids": [],  # IDs only, not results
            "failed_essay_ids": [],
            "processing_time_seconds": 0.0,
        },
    )
```

**Contains**: Success/failure status, essay counts, timing
**Does NOT contain**: Scores, grades, rankings, Bradley-Terry values

### Rich Event: AssessmentResultV1

```python
class AssessmentResultV1(BaseEventData):
    """Rich business data event to Result Aggregator Service.

    Contains full CJ assessment results including scores, grades, rankings.
    Published alongside thin CJAssessmentCompletedV1.

    Producer: CJ Assessment Service
    Consumer: Result Aggregator Service
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED)

    # Batch identification
    batch_id: str
    cj_assessment_job_id: str
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
        description="Assignment identifier for this assessment batch, if available",
    )

    # Assessment method tracking
    assessment_method: str  # "cj_assessment"
    model_used: str  # "claude-3-opus"
    model_provider: str  # "anthropic"
    model_version: str | None

    # TYPED business results
    essay_results: list[EssayResultV1] = Field(
        description="Student essay assessment results with typed validation"
    )

    # Assessment metadata
    assessment_metadata: dict[str, Any] = Field(
        default_factory=dict,
        # Contains: anchor_essays_used, calibration_method, comparison_count,
        # processing_duration_seconds, llm_temperature,
        # assignment_id (legacy location; prefer top-level field)
    )

    assessed_at: datetime
```

**Contains**: Full typed results, scores, grades, confidence, BT stats, calibration data

## Event Flow

```
CJ Assessment Service completes processing
         |
         ├──> Thin Event (CJAssessmentCompletedV1)
         |    └──> Essay Lifecycle Service
         |         └──> Updates batch state to COMPLETED
         |         └──> Triggers next pipeline phase
         |
         └──> Rich Event (AssessmentResultV1)
              └──> Result Aggregator Service
                   └──> Stores full results
                   └──> Publishes to WebSocket
                   └──> Updates analytics
```

## When to Use Dual-Event Pattern

Use dual-event when service produces results consumed by DIFFERENT downstream services with DIFFERENT concerns:

| Consumer Type | Event Type | Contains |
|---------------|-----------|----------|
| Orchestrator (ELS, BOS) | Thin | Status, success/failure, entity refs, timing |
| Aggregator/Analytics | Rich | Full business data, typed results, metrics |

### Examples Where Dual-Event Applies

**CJ Assessment Service**:
- Thin → ELS (batch processing state)
- Rich → RAS (scores, grades, rankings)

**Spellcheck Service**:
- Thin → ELS (`SPELLCHECK_PHASE_COMPLETED`)
- Rich → Content Service (`SPELLCHECK_RESULTS` with corrections)

**NLP Service** (future):
- Thin → ELS (analysis completion status)
- Rich → RAS (linguistic metrics, complexity scores)

### When NOT to Use Dual-Event

Don't use dual-event when:

1. **Single Consumer**: Only one service needs the event
   - Example: `BATCH_ESSAYS_REGISTERED` only consumed by ELS
   - Use single event with necessary fields

2. **State-Only Events**: No significant business data
   - Example: `BATCH_PHASE_SKIPPED` is already thin
   - Use single `ProcessingUpdate`-based event

3. **Small Business Data**: Business data fits comfortably in single event
   - Threshold: <10KB event payload
   - Use single rich event, orchestrator ignores extra fields

## Implementation Pattern

### Producer Service

```python
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name

async def publish_completion_events(
    self,
    batch_id: str,
    job_id: str,
    results: list[ResultData],
    correlation_id: UUID
) -> None:
    """Publish both thin and rich events."""

    # 1. Create thin event for orchestrator
    thin_event = CJAssessmentCompletedV1(
        entity_ref=batch_id,
        status=ProcessingStage.COMPLETED,
        system_metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            processing_stage=ProcessingStage.COMPLETED,
            completed_at=datetime.now(UTC)
        ),
        cj_assessment_job_id=job_id,
        processing_summary={
            "successful": len(results),
            "successful_essay_ids": [r.essay_id for r in results],
            "processing_time_seconds": duration
        }
    )

    thin_envelope = EventEnvelope[CJAssessmentCompletedV1](
        event_type=topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
        source_service="cj_assessment_service",
        correlation_id=correlation_id,
        data=thin_event
    )

    # 2. Create rich event for aggregator
    rich_event = AssessmentResultV1(
        batch_id=batch_id,
        cj_assessment_job_id=job_id,
        assessment_method="cj_assessment",
        model_used="claude-3-opus",
        model_provider="anthropic",
        essay_results=[
            EssayResultV1(
                essay_id=r.essay_id,
                normalized_score=r.score,
                letter_grade=r.grade,
                confidence_score=r.confidence,
                bt_score=r.bt_value,
                rank=r.rank
            ) for r in results
        ],
        assessment_metadata={
            "anchor_essays_used": anchor_count,
            "comparison_count": comparison_count
        }
    )

    rich_envelope = EventEnvelope[AssessmentResultV1](
        event_type=topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
        source_service="cj_assessment_service",
        correlation_id=correlation_id,  # Same correlation_id
        data=rich_event
    )

    # 3. Publish both (order doesn't matter, consumers are independent)
    await self.kafka_bus.publish(
        topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
        thin_envelope.model_dump_json().encode('utf-8')
    )

    await self.kafka_bus.publish(
        topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
        rich_envelope.model_dump_json().encode('utf-8')
    )
```

### Consumer: Orchestrator (Thin Event)

```python
# Essay Lifecycle Service
async def handle_cj_completion(self, message: bytes) -> None:
    """Handle thin event - state tracking only."""

    envelope = EventEnvelope[Any].model_validate_json(message)
    completion = CJAssessmentCompletedV1.model_validate(envelope.data)

    # Extract state information
    batch_id = completion.entity_ref
    status = completion.status
    summary = completion.processing_summary

    if status == ProcessingStage.COMPLETED:
        # Update batch state
        await self.update_batch_status(
            batch_id=batch_id,
            status=BatchStatus.CJ_ASSESSMENT_COMPLETED,
            successful_count=summary["successful"],
            failed_count=summary["failed"]
        )

        # Trigger next phase (orchestration logic)
        await self.initiate_next_pipeline_phase(batch_id)

    elif status == ProcessingStage.FAILED:
        # Handle failure
        error_info = completion.system_metadata.error_info
        await self.handle_phase_failure(batch_id, error_info)

    # No business data processing - that's RAS's job
```

### Consumer: Aggregator (Rich Event)

```python
# Result Aggregator Service
async def handle_assessment_result(self, message: bytes) -> None:
    """Handle rich event - store and distribute business data."""

    envelope = EventEnvelope[Any].model_validate_json(message)
    result = AssessmentResultV1.model_validate(envelope.data)

    # Store full typed results in database
    for essay_result in result.essay_results:
        await self.store_essay_result(
            essay_id=essay_result.essay_id,
            score=essay_result.normalized_score,
            grade=essay_result.letter_grade,
            confidence=essay_result.confidence_score,
            bt_score=essay_result.bt_score,
            rank=essay_result.rank
        )

    # Store batch-level metadata
    await self.store_assessment_metadata(
        batch_id=result.batch_id,
        method=result.assessment_method,
        model=result.model_used,
        metadata=result.assessment_metadata
    )

    # Publish to WebSocket for real-time updates
    await self.websocket_service.notify_results_ready(result.batch_id)

    # No orchestration decisions - that's ELS's job
```

## Error Handling in Dual-Event

When processing fails, ONLY send thin event:

```python
async def publish_failure_event(
    self,
    batch_id: str,
    job_id: str,
    error: Exception,
    correlation_id: UUID
) -> None:
    """Publish only thin event on failure - no rich event."""

    failure_event = CJAssessmentFailedV1(
        entity_ref=batch_id,
        status=ProcessingStage.FAILED,
        system_metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            processing_stage=ProcessingStage.FAILED,
            error_info={
                "error_code": ErrorCode.CJ_ASSESSMENT_SERVICE_ERROR,
                "error_message": str(error),
                "error_type": type(error).__name__
            }
        ),
        cj_assessment_job_id=job_id
    )

    envelope = EventEnvelope[CJAssessmentFailedV1](
        event_type=topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED),
        source_service="cj_assessment_service",
        correlation_id=correlation_id,
        data=failure_event
    )

    await self.kafka_bus.publish(
        topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED),
        envelope.model_dump_json().encode('utf-8')
    )

    # NO rich event published - no results to aggregate
```

## Benefits

1. **Separation of Concerns**: Orchestrators don't couple to business data schemas
2. **Independent Evolution**: Rich events can change without affecting orchestration
3. **Performance**: Orchestrators process lightweight events quickly
4. **Scalability**: Aggregators can be scaled independently from orchestrators
5. **Clear Contracts**: Each consumer gets exactly what it needs

## Anti-Pattern: Mixing Concerns

```python
# WRONG - Single event with both state and business data
class CJAssessmentCompletedV1(BaseEventData):  # ❌
    # State tracking
    status: ProcessingStage
    system_metadata: SystemProcessingMetadata

    # Business data (WRONG - couples ELS to result structure)
    essay_results: list[EssayResultV1]  # ❌ ELS doesn't need this
    assessment_metadata: dict[str, Any]  # ❌ ELS doesn't need this

# Problem: ELS must deserialize/ignore large business data it doesn't use
# Problem: Rich event schema changes break ELS
# Problem: Aggregator depends on ELS's event contract
```

## Related Documentation

- [Event Envelope](event-envelope.md) - EventEnvelope structure
- [Event Registry](event-registry.md) - ProcessingEvent enum
- `common_core/events/cj_assessment_events.py` - Canonical example implementation
- `.claude/rules/020-architectural-mandates.md` - Separation of concerns
