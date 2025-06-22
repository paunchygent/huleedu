# Client-Initiated Retry Framework Implementation Task

## Executive Summary

**What**: Add manual retry capabilities for failed batches and essays via API/UI  
**Why**: Allow teachers to retry transient failures without re-uploading  
**How**: New retry commands, error categorization, and retry tracking  
**Special Case**: CJ Assessment must retry entire batches (no single essays)  

## Overview

Implement a client-side retry system that allows users to manually retry failed batches and essays through the UI/API. This is NOT an automatic retry system - users explicitly choose what to retry based on error information.

**Key Distinction**: CJ Assessment Service requires full batch retries only (no individual essay retries) due to comparative ranking requirements.

## Architecture Context

### Current State

1. **Idempotency**: Services use `@idempotent_consumer` decorator (`services/libs/huleedu_service_libs/idempotency.py`)
2. **Error Handling**: Services publish failure events with `SystemProcessingMetadata.error_info`
3. **State Management**:
   - BOS tracks pipeline state in `ProcessingPipelineState`
   - ELS owns essay state through state machine
4. **No Retry Infrastructure**: No retry commands, retry tracking, or DLQ handling exists

### Key Services and Their Error Patterns

#### Spell Checker Service (`services/spell_checker_service/`)

- **Current**: Publishes `SpellcheckResultDataV1` with `status=EssayStatus.SPELLCHECK_FAILED`
- **Error Types**: Content fetch failures, storage failures, algorithm errors
- **Location**: `event_processor.py:117-293`

#### CJ Assessment Service (`services/cj_assessment_service/`)

- **Current**: Uses internal tenacity retry for LLM calls (`implementations/retry_manager_impl.py`)
- **Publishes**: `CJAssessmentFailedV1` on final failure
- **Special**: Batch-level processing only - no single essay retries

#### File Service (`services/file_service/`)

- **Current**: Distinguishes validation vs storage failures
- **Error Codes**: Uses `FileValidationErrorCode` enum
- **Location**: `core_logic.py:87-276`

## Implementation Phases

### Phase A: Common Core Foundations

#### A.1 Extend Error Tracking Models

**File**: `common_core/src/common_core/metadata_models.py`

Add retry metadata to complement existing `SystemProcessingMetadata`:

```python
class RetryMetadata(BaseModel):
    """Metadata for tracking retry attempts across services."""
    retry_count: int = 0
    first_attempt_at: datetime
    last_attempt_at: datetime | None = None
    is_retryable: bool = True
    retry_reason: str | None = None
    max_retries_exceeded: bool = False
```

**File**: `common_core/src/common_core/enums.py`

Extend error categorization:

```python
# After existing ErrorCode enum (line 273)
class RetryableErrorCategory(str, Enum):
    """Categories of errors for retry decision making."""
    TRANSIENT_NETWORK = "transient_network"  # Retry recommended
    EXTERNAL_SERVICE = "external_service"     # Retry may help
    VALIDATION_ERROR = "validation_error"     # No retry needed
    PROCESSING_ERROR = "processing_error"     # Retry unlikely to help
    UNKNOWN = "unknown"                       # Retry at user discretion
```

#### A.2 Add Retry Helper Functions

**File**: `services/libs/huleedu_service_libs/retry_utils.py` (NEW)

```python
"""Retry utilities for categorizing and handling retryable errors."""

from common_core.enums import ErrorCode, RetryableErrorCategory

# Map existing error codes to retry categories
RETRY_CATEGORY_MAP = {
    ErrorCode.EXTERNAL_SERVICE_ERROR: RetryableErrorCategory.TRANSIENT_NETWORK,
    ErrorCode.CONTENT_SERVICE_ERROR: RetryableErrorCategory.EXTERNAL_SERVICE,
    ErrorCode.KAFKA_PUBLISH_ERROR: RetryableErrorCategory.TRANSIENT_NETWORK,
    ErrorCode.VALIDATION_ERROR: RetryableErrorCategory.VALIDATION_ERROR,
    # ... complete mapping
}

def get_retry_category(error_code: ErrorCode) -> RetryableErrorCategory:
    """Determine retry category for an error code."""
    return RETRY_CATEGORY_MAP.get(error_code, RetryableErrorCategory.UNKNOWN)

def is_likely_retryable(error_code: ErrorCode) -> bool:
    """Quick check if an error is likely retryable."""
    category = get_retry_category(error_code)
    return category in {
        RetryableErrorCategory.TRANSIENT_NETWORK,
        RetryableErrorCategory.EXTERNAL_SERVICE
    }
```

### Phase B: Service Event Updates

#### B.1 Update Service Result Events

Each service needs to include retry metadata in their result events. Example for Spell Checker:

**File**: `common_core/src/common_core/events/spellcheck_models.py`

```python
class SpellcheckResultDataV2(ProcessingUpdate):
    """V2 adds retry tracking metadata."""
    # ... existing fields ...
    retry_metadata: RetryMetadata | None = None
```

#### B.2 Service Implementation Updates

**Spell Checker Service** - Update `event_processor.py`:

```python
# Line 127 - Content fetch failure
retry_metadata = RetryMetadata(
    retry_count=0,  # Will be incremented by BOS/ELS
    first_attempt_at=datetime.now(UTC),
    is_retryable=is_likely_retryable(ErrorCode.CONTENT_SERVICE_ERROR),
    retry_reason=None
)
```

**File Service** - Already distinguishes error types well:

- `FileValidationErrorCode.EMPTY_CONTENT` → not retryable
- `FileValidationErrorCode.RAW_STORAGE_FAILED` → retryable

### Phase C: Orchestration Commands

#### C.1 Define Retry Commands

**File**: `common_core/src/common_core/batch_service_models.py`

Add after existing command models (line 56):

```python
class RetryPhaseCommandV1(BaseEventData):
    """Command to retry a specific phase for selected essays."""
    batch_id: str
    phase_name: str  # Must match PhaseName enum values
    essay_ids: list[str]  # Empty = retry all essays in batch
    retry_reason: str  # User-provided reason
    retry_attempt: int  # Current retry count
    initiated_by: str  # User ID who initiated retry

class RetryPipelineCommandV1(BaseEventData):
    """Command to retry entire pipeline from failure point."""
    batch_id: str
    retry_from_phase: str  # Phase to restart from
    retry_reason: str
    retry_attempt: int
    initiated_by: str
```

#### C.2 BOS Retry Command Handlers

**File**: `services/batch_orchestrator_service/implementations/retry_command_handler.py` (NEW)

```python
"""Handler for client-initiated retry commands."""

from huleedu_service_libs.logging_utils import create_service_logger
from common_core.batch_service_models import RetryPhaseCommandV1
from common_core.pipeline_models import PhaseName

logger = create_service_logger("bos.retry_handler")

class RetryCommandHandler:
    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ):
        self.batch_repo = batch_repo
        self.phase_coordinator = phase_coordinator

    async def handle_retry_phase_command(self, command: RetryPhaseCommandV1) -> None:
        """Handle client-initiated phase retry."""
        logger.info(
            f"Processing retry command for batch {command.batch_id}, "
            f"phase {command.phase_name}, attempt {command.retry_attempt}"
        )
        
        # Special handling for CJ Assessment - always retry full batch
        if command.phase_name == PhaseName.CJ_ASSESSMENT.value:
            if command.essay_ids:
                logger.warning(
                    "CJ Assessment retry requested with specific essays, "
                    "but will retry entire batch for ranking consistency"
                )
            essays_to_retry = await self.batch_repo.get_batch_essays(command.batch_id)
        else:
            # Other phases can retry specific essays
            if command.essay_ids:
                all_essays = await self.batch_repo.get_batch_essays(command.batch_id)
                essays_to_retry = [e for e in all_essays if e.essay_id in command.essay_ids]
            else:
                essays_to_retry = await self.batch_repo.get_batch_essays(command.batch_id)
        
        # Update retry metadata in pipeline state
        await self._update_retry_metadata(command)
        
        # Reuse existing phase coordination
        # Note: Current implementation doesn't have is_retry param
        # Either extend the interface or track retry state separately
        await self.phase_coordinator.initiate_phase(
            batch_id=command.batch_id,
            phase_name=command.phase_name,
            essays=essays_to_retry,
            correlation_id=command.correlation_id
            # is_retry=True  # Add this parameter to interface
        )
```

#### C.3 BOS Kafka Consumer Update

**File**: `services/batch_orchestrator_service/kafka_consumer.py`

Add retry command topics to consumer (around line 56):

```python
# In __init__, add retry topics to the list
self.topics = [
    # ... existing topics ...
    topic_name(ProcessingEvent.RETRY_PHASE_COMMAND),
    topic_name(ProcessingEvent.RETRY_PIPELINE_COMMAND),
]
```

Add handlers in `_handle_message` method:

```python
elif msg.topic == topic_name(ProcessingEvent.RETRY_PHASE_COMMAND):
    await self.retry_handler.handle_retry_phase_command(msg)
elif msg.topic == topic_name(ProcessingEvent.RETRY_PIPELINE_COMMAND):
    await self.retry_handler.handle_retry_pipeline_command(msg)
```

#### C.4 Kafka Topic Registration

**File**: `common_core/src/common_core/enums.py`

Add to ProcessingEvent enum (around line 64):

```python
# Retry commands
RETRY_PHASE_COMMAND = "retry.phase.command"
RETRY_PIPELINE_COMMAND = "retry.pipeline.command"
```

Add to _TOPIC_MAPPING (around line 100):

```python
ProcessingEvent.RETRY_PHASE_COMMAND: "huleedu.batch.retry.phase.command.v1",
ProcessingEvent.RETRY_PIPELINE_COMMAND: "huleedu.batch.retry.pipeline.command.v1",
```

### Phase D: DLQ Implementation

#### D.1 Extend KafkaBus for DLQ

**File**: `services/libs/huleedu_service_libs/kafka_client.py`

Add DLQ publishing method after line 96:

```python
async def publish_to_dlq(
    self,
    original_topic: str,
    envelope: EventEnvelope[T_EventPayload],
    error_info: dict[str, Any],
    key: str | None = None,
) -> None:
    """Publish failed message to DLQ after max retries."""
    dlq_topic = f"{original_topic}.dlq"
    
    # Enhance envelope with DLQ metadata
    dlq_envelope = envelope.model_copy(update={
        "data": {
            **envelope.data.model_dump(),
            "dlq_metadata": {
                "original_topic": original_topic,
                "failed_at": datetime.now(UTC).isoformat(),
                "error_info": error_info
            }
        }
    })
    
    await self.publish(dlq_topic, dlq_envelope, key)
    logger.warning(
        f"Message sent to DLQ: {dlq_topic}, event_id: {envelope.event_id}"
    )
```

#### D.2 DLQ Replay CLI Tool

**File**: `scripts/replay_dlq.py` (NEW) - or create `scripts/operations/` subdirectory first

```python
#!/usr/bin/env python
"""CLI tool to replay messages from Dead Letter Queue."""

import asyncio
import argparse
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

async def replay_dlq_messages(
    dlq_topic: str,
    target_topic: str,
    bootstrap_servers: str,
    message_filter: dict | None = None
):
    """Replay messages from DLQ to original topic."""
    # Implementation following existing Kafka patterns
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dlq-topic", required=True)
    parser.add_argument("--target-topic", required=True)
    # ... parse and run
```

### Phase E: HTTP Endpoints

#### E.1 BOS Retry Endpoints

**File**: `services/batch_orchestrator_service/api/retry_routes.py` (NEW)

Following existing Blueprint pattern from `batch_routes.py`:

```python
"""API routes for client-initiated retry operations."""

from quart import Blueprint, request, current_app
from dishka.integrations.quart import inject

retry_bp = Blueprint("retry", __name__)

@retry_bp.route("/v1/batches/<batch_id>/retry", methods=["POST"])
@inject
async def retry_batch_pipeline(
    batch_id: str,
    retry_handler: RetryCommandHandler,
) -> dict[str, Any]:
    """Retry entire pipeline or specific phase for a batch."""
    data = await request.get_json()
    
    # Validate request
    phase = data.get("phase")  # Optional - if not provided, retry from failure point
    reason = data.get("reason", "User initiated retry")
    
    # Get current retry count from pipeline state
    pipeline_state = await retry_handler.batch_repo.get_processing_pipeline_state(batch_id)
    current_retry_count = pipeline_state.get("retry_count", 0)
    
    # Check retry limits
    if current_retry_count >= 3:  # Configurable max retries
        return {"error": "Maximum retry attempts exceeded"}, 429
    
    # Special validation for CJ Assessment
    if phase == "CJ_ASSESSMENT" and data.get("essay_ids"):
        return {
            "error": "CJ Assessment requires full batch retry for ranking consistency"
        }, 400
    
    # Create and publish retry command
    # ... implementation
    
    return {"status": "retry_initiated", "retry_attempt": current_retry_count + 1}
```

**File**: `services/batch_orchestrator_service/app.py`

Register retry blueprint (add after line 65):

```python
from api.retry_routes import retry_bp
app.register_blueprint(retry_bp)
```

### Phase F: Observability

#### F.1 Prometheus Metrics

**File**: `services/batch_orchestrator_service/metrics.py`

Add retry-specific metrics in `_create_metrics()` function:

```python
"retry_attempts_total": Counter(
    "bos_retry_attempts_total",
    "Total number of client-initiated retries",
    ["batch_id", "phase", "retry_reason"],
    registry=REGISTRY,
),
"dlq_messages_total": Counter(
    "bos_dlq_messages_total", 
    "Total messages sent to DLQ",
    ["original_topic", "error_category"],
    registry=REGISTRY,
),
```

### Phase G: Testing

#### G.1 Retry Command Tests

**File**: `services/batch_orchestrator_service/tests/test_retry_command_handler.py` (NEW)

```python
"""Tests for client-initiated retry functionality."""

@pytest.mark.asyncio
async def test_cj_assessment_ignores_specific_essays():
    """Test that CJ Assessment always retries full batch."""
    # Setup mock repository with 5 essays
    # Send retry command with only 2 essay IDs
    # Verify all 5 essays are retried
    pass

@pytest.mark.asyncio
async def test_retry_count_increments():
    """Test retry count tracking in pipeline state."""
    pass
```

## Special Considerations

### CJ Assessment Batch-Only Retry

1. **API Layer**: Validate and reject individual essay retry requests
2. **UI Layer**: Disable essay selection for CJ Assessment retry
3. **Cost Display**: Show full batch processing cost before retry confirmation
4. **Documentation**: Clear explanation of why batch-only is required

### Integration with Existing Idempotency

The `@idempotent_consumer` decorator currently deletes Redis keys on failure (`idempotency.py:82-99`). For retry support:

1. **Modify idempotency decorator** to distinguish retry-eligible failures:

   ```python
   # In idempotency.py, replace current failure handling
   except Exception as processing_error:
       # Check if error is retryable
       if is_retryable_error(processing_error):
           # Keep the key but add retry count
           await redis_client.hincrby(f"{key}:meta", "retry_count", 1)
           logger.info(f"Retryable failure for {deterministic_id}, keeping lock")
       else:
           # Non-retryable, delete key as before
           await redis_client.delete_key(key)
       raise processing_error
   ```

2. **Check retry count** before processing in decorator
3. **Delete key** only after max retries exceeded or non-retryable error

## Migration Notes

1. Start with read-only retry metadata (don't break existing flows)
2. Deploy retry command handlers before UI changes
3. Monitor retry patterns before enforcing limits
4. Consider backfilling retry_count=0 for existing pipeline states

## Success Criteria

1. Users can retry failed batches/phases via API
2. CJ Assessment enforces batch-only retry
3. Retry history visible in pipeline state
4. DLQ captures permanently failed messages
5. Metrics show retry patterns
6. No disruption to existing pipeline flows

## Implementation Priority

1. **Phase A & C first**: Core retry infrastructure without breaking changes
2. **Phase B gradually**: Update services to emit retry metadata  
3. **Phase E next**: API endpoints for user interaction
4. **Phase D later**: DLQ can be added after retry patterns are understood
5. **Phase F & G**: Observability and testing throughout

**Critical**: Maintain backwards compatibility - old events without retry metadata must still process correctly.
