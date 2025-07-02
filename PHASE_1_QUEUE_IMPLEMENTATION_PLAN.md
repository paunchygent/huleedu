# Phase 1: Queue Infrastructure Implementation Plan

## Overview
Transform Redis from storing responses to storing requests, creating a queue-based resilience system.

## Simplified Architecture

```
Production Flow:
├─ LLM Available → Fresh call → Return result
└─ LLM Unavailable → Queue request
    ├─ Redis up → Persistent queue → 202 + queue_id
    └─ Redis down → Local queue (with limits) → 202 + queue_id

Development Flow:
├─ Mock Provider (default) → Instant responses
└─ Real Provider Testing → Optional response recorder
```

## Implementation Steps

### Step 1: Add Queue Status Enum (15 mins)
**File**: `common_core/src/common_core/status_enums.py`
```python
class QueueStatus(str, Enum):
    """Status codes for queued LLM requests."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"
```

### Step 2: Create Queue Models (30 mins)
**File**: `services/llm_provider_service/queue_models.py`
- `QueuedRequest`: Core request model with TTL, priority, status
- `QueueStats`: Statistics for monitoring

### Step 3: Add Queue Protocols (20 mins)
**File**: `services/llm_provider_service/protocols.py`
- `QueueManagerProtocol`: High-level queue operations
- `QueueRepositoryProtocol`: Storage operations

### Step 4: Redis Queue Implementation (1 hour)
**File**: `services/llm_provider_service/implementations/redis_queue_repository_impl.py`
- Sorted sets for priority queue
- Hash storage for request data
- Native TTL support
- Atomic operations

### Step 5: Local Queue Implementation (1 hour)
**File**: `services/llm_provider_service/implementations/local_queue_manager_impl.py`
- Min-heap priority queue
- Strict capacity limits (no eviction)
- Watermark circuit breaker
- Memory tracking

### Step 6: Resilient Queue Manager (45 mins)
**File**: `services/llm_provider_service/implementations/resilient_queue_manager_impl.py`
- Redis primary, local fallback
- Automatic failover
- Combined statistics

### Step 7: Configuration Updates (20 mins)
**File**: `services/llm_provider_service/config.py`
```python
# Queue settings
QUEUE_MAX_SIZE: int = 1000
QUEUE_MAX_MEMORY_MB: int = 100
QUEUE_HIGH_WATERMARK: float = 0.8
QUEUE_LOW_WATERMARK: float = 0.6
QUEUE_REQUEST_TTL_HOURS: int = 4

# Development settings
RECORD_LLM_RESPONSES: bool = False  # For API validation only
```

### Step 8: Wire DI (30 mins)
**File**: `services/llm_provider_service/di.py`
- Add queue providers
- Keep cache temporarily for migration

### Step 9: Development Response Recorder (30 mins)
**File**: `services/llm_provider_service/implementations/response_recorder_impl.py`
```python
class DevelopmentResponseRecorder:
    """Simple file-based recorder for API validation."""
    
    def __init__(self, settings: Settings):
        self.enabled = (
            settings.ENVIRONMENT == "development" 
            and settings.RECORD_LLM_RESPONSES
        )
        self.output_dir = Path("./llm_response_logs")
    
    async def record(self, provider: str, request: Any, response: Any):
        # Save to JSON for human inspection
        # Track API versions
        # Git-ignored directory
```

## Testing Requirements

### Unit Tests
- Queue operations (enqueue, dequeue, priority)
- Capacity management
- TTL expiration
- Watermark behavior

### Integration Tests
- Redis failover
- Recovery scenarios
- Concurrent access
- Memory limits

### Load Tests
- 1000+ queued items
- Memory usage accuracy
- Rejection behavior

## Migration Safety
- Deploy alongside existing cache
- No changes to request flow yet
- Feature flags ready for Phase 2
- Comprehensive logging

## What We're NOT Doing
- No complex cache infrastructure for development
- No response caching anywhere
- No silent request dropping
- No unnecessary abstractions

## Success Criteria
1. Queue infrastructure deployed and tested
2. Redis successfully stores requests (not responses)
3. Local queue enforces capacity limits
4. Response recorder works for API validation
5. Zero impact on current service operation

## Time Estimate
- Total: ~6 hours implementation
- Testing: ~3 hours
- Deploy alongside existing code
- Safe rollback possible