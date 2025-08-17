# BCS Cache Fix - Implementation Checklist

## Quick Reference
**Goal**: Stop clearing Redis cache on pipeline completion. Let 7-day TTL handle expiration.

## Step-by-Step Implementation

### [ ] Step 1: Remove Kafka Topic Subscription
```python
# kafka_consumer.py line ~126
# DELETE this line:
"huleedu.batch.pipeline.completed.v1",  # ← REMOVE
```

### [ ] Step 2: Remove Message Handler
```python
# kafka_consumer.py lines ~223-225
# DELETE these lines:
elif msg.topic == "huleedu.batch.pipeline.completed.v1":
    await self._handle_batch_pipeline_completed(msg)
    await self._track_event_success("batch_pipeline_completed")
```

### [ ] Step 3: Delete Handler Method
```python
# kafka_consumer.py lines ~437-474
# DELETE entire method:
async def _handle_batch_pipeline_completed(self, msg: ConsumerRecord) -> None:
    # DELETE ALL OF THIS
```

### [ ] Step 4: Remove from Protocol
```python
# protocols.py
# DELETE this method from BatchStateRepositoryProtocol:
async def clear_batch_pipeline_state(self, batch_id: str) -> bool:
    ...
```

### [ ] Step 5: Remove from Implementations
Delete `clear_batch_pipeline_state()` method from:
- [ ] `redis_batch_state_repository.py` (lines ~605-643)
- [ ] `postgres_batch_state_repository.py` 
- [ ] `mock_batch_state_repository.py`

### [ ] Step 6: Fix Tests
- [ ] Remove cache clearing assertions from tests
- [ ] Update mocks to not have the method

### [ ] Step 7: Verify Fix
```bash
# Run test to confirm cache persists across pipelines
pdm run pytest tests/functional/test_e2e_cj_after_nlp_with_pruning.py -xvs

# Check logs - should NOT see "Cleared pipeline state"
# Should see Redis cache hits on second pipeline
```

## Expected Result
```
✅ First pipeline: Stores phase completions in Redis (7-day TTL)
✅ Second pipeline: Reads from Redis cache (fast)
✅ No "Cleared pipeline state" logs
✅ Phase pruning works across multiple pipelines
```