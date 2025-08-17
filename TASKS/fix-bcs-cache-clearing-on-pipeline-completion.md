# Task: Fix BCS Cache Clearing on Pipeline Completion

## Problem Statement
BCS currently **clears Redis cache when pipeline completes**, defeating cross-pipeline phase pruning optimization. The cache should persist for 7 days to enable phase pruning across multiple pipeline executions.

## Current Incorrect Behavior
```
Pipeline 1: NLP completes → Cache cleared ❌
Pipeline 2: CJ Assessment → Must query PostgreSQL (slow) → Can't benefit from cached state
```

## Desired Correct Behavior  
```
Pipeline 1: NLP completes → Cache remains (7-day TTL) ✅
Pipeline 2: CJ Assessment → Reads from Redis cache (fast) → Prunes spellcheck efficiently
```

## Implementation Changes Required

### 1. Remove Pipeline Completion Handler
**File**: `services/batch_conductor_service/kafka_consumer.py`
- **DELETE** entire `_handle_batch_pipeline_completed()` method (lines ~437-474)
- **REMOVE** topic subscription: `"huleedu.batch.pipeline.completed.v1"` (line ~126)
- **REMOVE** message routing for this topic in `_handle_message()` (lines ~223-225)

### 2. Remove Clear Method from Repositories
**Files to modify**:
- `services/batch_conductor_service/protocols.py` - Remove `clear_batch_pipeline_state()` from protocol
- `services/batch_conductor_service/implementations/redis_batch_state_repository.py` - Delete method
- `services/batch_conductor_service/implementations/postgres_batch_state_repository.py` - Delete method  
- `services/batch_conductor_service/implementations/mock_batch_state_repository.py` - Delete method

### 3. Fix Tests
**Remove/update tests** that expect cache clearing on pipeline completion:
- `tests/integration/test_postgres_phase_persistence.py` - Remove cache clearing test
- `tests/integration/test_pipeline_transitions.py` - Remove clear method from mock
- Update any tests that verify cache is cleared after pipeline completion

## Validation Criteria
1. **Redis cache persists** after pipeline completion
2. **7-day TTL** naturally expires unused cache entries
3. **Cross-pipeline pruning** works: Second pipeline reads from Redis, not PostgreSQL
4. **Test scenario**: Run NLP → wait → run CJ Assessment → verify Redis hit, not PostgreSQL query

## Why This Matters
- **Performance**: Avoid PostgreSQL queries for every pipeline resolution
- **Efficiency**: Enable true cross-pipeline optimization
- **Simplicity**: Let TTL handle expiration, not explicit clearing

## Notes
- PostgreSQL records remain permanent (correct behavior)
- Redis TTL of 7 days is already configured correctly
- This fix makes phase pruning work as originally intended