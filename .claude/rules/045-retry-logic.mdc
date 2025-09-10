---
description: 
globs: 
alwaysApply: false
---
# 045: Retry Logic Standards

## 1. Current Approach: Natural Retry via Idempotency

### 1.1. Existing Retry Capabilities
HuleEdu implements **natural retry** through the idempotency system:

- **`@idempotent_consumer` decorator** deletes Redis keys on processing failure
- **Kafka message reprocessing** provides automatic retry mechanism
- **`PipelinePhaseCoordinatorProtocol`** handles phase transition failures
- **`ProcessingPipelineState`** includes comprehensive error tracking

### 1.2. User-Initiated Retry Pattern
For client-initiated retries, use **existing pipeline request pattern**:

```python
# Extend ClientBatchPipelineRequestV1 with retry context
class ClientBatchPipelineRequestV1(BaseModel):
    batch_id: str
    requested_pipeline: str  # e.g., "spellcheck" for phase retry
    user_id: str
    is_retry: bool = False  # Simple flag for retry context
    retry_reason: str | None = None  # Optional user reason
```

### 1.3. Implementation Guidelines
- **Phase Retry = Single-Phase Pipeline**: Treat phase retries as pipeline requests
- **User Authorization**: Leverage existing user_id propagation for ownership checks
- **CJ Assessment Constraint**: Handle batch-only requirement through API validation
- **Error Context**: Use existing `PipelineStateDetail.error_info` for failure tracking

## 2. API-Level Retry Implementation

### 2.1. BOS Retry Endpoint Pattern
```python
@retry_bp.route("/v1/batches/<batch_id>/retry-phase", methods=["POST"])
async def retry_phase(batch_id: str):
    # Validate ownership via existing user_id propagation
    # Reset phase status to REQUESTED_BY_USER
    # Use existing phase coordination logic
```

### 2.2. CJ Assessment Validation
```python
# Handle batch-only constraint at API level
if phase_name == "cj_assessment" and specific_essay_ids:
    return {"error": "CJ Assessment requires full batch retry"}, 400
```

## 3. Future Enhancements (TODO)

### 3.1. Idempotency Enhancement
If explicit retry tracking becomes necessary, extend the decorator minimally:

```python
# In idempotency.py - potential future enhancement
except Exception as processing_error:
    error_category = get_error_category(processing_error)
    if error_category == "PERMANENT_FAILURE":
        # Keep key, prevent further retries
        await redis_client.set(f"{key}:permanent_failure", "1")
    else:
        # Current behavior - delete key, allow retry
        await redis_client.delete_key(key)
```

### 3.2. Retry Metadata
Only add if business requirements demand explicit retry count tracking:
- Extend `PipelineStateDetail.error_info` with retry context
- Maintain backwards compatibility with existing state management
- Avoid redundant retry metadata in event payloads

## 4. Architectural Principles
- **Leverage Existing Infrastructure**: Extend proven patterns vs. creating new ones
- **Simplicity Over Complexity**: Natural retry via idempotency is often sufficient
- **User Authorization**: Use established user_id propagation patterns
- **Event-Driven Consistency**: Maintain thin event patterns and existing contracts

---
**Current implementation provides robust retry capabilities through existing architectural patterns.**
