# Task: Fix Idempotency Test Shortcuts and Improve Test Quality

## Overview

This task addresses critical shortcuts and unrealistic mocking in the idempotency tests that could mask real issues in production. Each issue must be fixed individually and tested before proceeding to the next one.

**CRITICAL RULE**: Fix ONE issue at a time. After implementing each fix, run the affected tests to ensure they still pass and actually test the intended behavior. DO NOT edit multiple files and test later.

## Issue Priority

1. **Critical**: Issues that could hide production failures
2. **High**: Issues that test implementation details rather than behavior
3. **Medium**: Issues that reduce test maintainability

## Issues to Fix

### Issue 1: Synchronous Confirmation Pattern [CRITICAL]

**Affected Files**:
- ✅ `services/batch_conductor_service/tests/unit/test_bcs_idempotency_basic.py` - COMPLETED
  - Added `test_async_confirmation_pattern` 
  - Added `test_crash_before_confirmation`
  - Created shared `AsyncConfirmationTestHelper` in `libs/huleedu_service_libs/tests/idempotency_test_utils.py`
- `services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py`
- `services/cj_assessment_service/tests/unit/test_cj_idempotency_basic.py`
- `services/essay_lifecycle_service/tests/unit/test_els_idempotency_integration.py`
- `services/spellchecker_service/tests/unit/test_spell_idempotency_basic.py`
- `services/result_aggregator_service/tests/integration/test_kafka_consumer_idempotency.py`

**Current Pattern**:
```python
@idempotent_consumer(redis_client=redis_client, config=config)
async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> bool:
    result = await process_single_message(msg, ...)
    await confirm_idempotency()  # Called immediately after processing
    return result
```

**Problem**: 
This pattern doesn't test the real-world scenario where:
1. Message processing starts (sets "processing" status)
2. Business logic executes and database transaction commits
3. Confirmation happens AFTER transaction commit
4. A crash between steps 2 and 3 should allow retry

**Solution**:
Create a test that simulates async confirmation with potential failure:
```python
@idempotent_consumer(redis_client=redis_client, config=config)
async def handle_message_with_delayed_confirmation(msg: ConsumerRecord, *, confirm_idempotency):
    # Simulate transaction processing
    processing_complete = asyncio.Event()
    confirmation_allowed = asyncio.Event()
    
    async def process_with_transaction():
        # Business logic
        result = await process_single_message(msg, ...)
        processing_complete.set()
        # Wait for test to allow confirmation
        await confirmation_allowed.wait()
        await confirm_idempotency()
        return result
    
    task = asyncio.create_task(process_with_transaction())
    await processing_complete.wait()
    # Now test can verify "processing" state before confirmation
    return task, confirmation_allowed
```

**Verification**: Add test cases for:
- Crash before confirmation (should see "processing" status)
- Successful confirmation (should see "completed" status)
- Another worker attempting during "processing" state

### Issue 2: Unrealistic MockRedisClient [CRITICAL]

**Affected Files**:
- `libs/huleedu_service_libs/tests/test_idempotency.py` (MockRedisClient class)
- All service test files that duplicate MockRedisClient

**Current Implementation**:
```python
class MockRedisClient:
    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        self.set_calls.append((key, value, ttl_seconds or 0))
        if key in self.keys:
            return False
        self.keys[key] = value
        return True
```

**Problems**:
1. No TTL expiration simulation
2. No concurrent access protection
3. No simulation of Redis latency or partial failures
4. TTL is stored but never used

**Solution**:
Create a realistic Redis test double:
```python
import asyncio
import time
from typing import Dict, Optional, Tuple

class RealisticRedisTestDouble:
    def __init__(self, latency_ms: float = 1.0):
        self.data: Dict[str, Tuple[str, float]] = {}  # key -> (value, expiry_time)
        self.lock = asyncio.Lock()
        self.latency_ms = latency_ms
        self.operation_log = []
        
    async def _simulate_latency(self):
        await asyncio.sleep(self.latency_ms / 1000)
    
    def _clean_expired(self):
        """Remove expired keys"""
        current_time = time.time()
        expired_keys = [k for k, (_, exp) in self.data.items() if exp <= current_time]
        for key in expired_keys:
            del self.data[key]
    
    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> bool:
        await self._simulate_latency()
        async with self.lock:
            self._clean_expired()
            self.operation_log.append(('SETNX', key, value, ttl_seconds))
            
            if key in self.data:
                return False
                
            expiry = time.time() + (ttl_seconds or 86400)
            self.data[key] = (value, expiry)
            return True
    
    async def get(self, key: str) -> Optional[str]:
        await self._simulate_latency()
        async with self.lock:
            self._clean_expired()
            self.operation_log.append(('GET', key))
            
            if key in self.data:
                value, _ = self.data[key]
                return value
            return None
    
    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        await self._simulate_latency()
        async with self.lock:
            self.operation_log.append(('SETEX', key, ttl_seconds, value))
            expiry = time.time() + ttl_seconds
            self.data[key] = (value, expiry)
            return True
```

**Verification**: Update one test file at a time and verify:
- TTL expiration works correctly
- Concurrent access is properly serialized
- Operation log can be inspected for debugging

### Issue 3: TTL Testing Only Checks Initial Value [CRITICAL]

**Affected Files**: All service test files with TTL assertions

**Current Pattern**:
```python
assert len(mock_redis_client.set_calls) == 1
set_call = mock_redis_client.set_calls[0]
assert set_call[2] == 300  # Processing state TTL
```

**Problem**: 
Tests only verify the initial "processing" TTL (300s) but never verify that the configured TTL (e.g., 86400s) is applied after confirmation via SETEX.

**Solution**:
Create comprehensive TTL verification:
```python
async def test_ttl_lifecycle(self):
    """Test that TTLs are correctly applied during the two-phase commit"""
    redis_client = RealisticRedisTestDouble()
    config = IdempotencyConfig(
        service_name="test-service",
        default_ttl=86400,  # 24 hours
    )
    
    confirmation_called = False
    
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handler(msg: ConsumerRecord, *, confirm_idempotency):
        # Check processing state TTL
        operations = [op for op in redis_client.operation_log if op[0] == 'SETNX']
        assert len(operations) == 1
        assert operations[0][3] == 300  # Processing TTL
        
        # Simulate work
        await asyncio.sleep(0.1)
        
        # Confirm
        await confirm_idempotency()
        nonlocal confirmation_called
        confirmation_called = True
        return "success"
    
    result = await handler(create_test_message())
    
    # Verify SETEX was called with configured TTL
    setex_ops = [op for op in redis_client.operation_log if op[0] == 'SETEX']
    assert len(setex_ops) == 1
    assert setex_ops[0][2] == 86400  # Configured TTL
    assert confirmation_called
```

### Issue 4: Fail-Open Tests Don't Verify Processing [CRITICAL]

**Affected Files**:
- All `test_redis_failure_fallback` and similar tests

**Current Pattern**:
```python
failing_redis.get.side_effect = Exception("Redis connection failed")
result = await handle_message_idempotently(kafka_msg)
assert result is True
assert len(redis_client.set_calls) == 0  # No SET attempted during outage
```

**Problem**: 
Tests only verify Redis wasn't called and function returned True. They don't verify the message was actually processed correctly during the outage.

**Solution**:
Add verification of actual processing:
```python
async def test_redis_failure_processes_message_correctly(self):
    """Test that messages are processed correctly during Redis outage"""
    # Track actual processing
    processed_messages = []
    
    async def mock_process_single_message(msg, **kwargs):
        event_data = json.loads(msg.value)
        processed_messages.append({
            'event_id': event_data['event_id'],
            'event_type': event_data['event_type'],
            'timestamp': time.time()
        })
        # Simulate actual work
        await asyncio.sleep(0.05)
        return True
    
    # Configure failing Redis
    failing_redis = AsyncMock(spec=RedisClientProtocol)
    failing_redis.get.side_effect = Exception("Redis connection failed")
    failing_redis.set_if_not_exists.side_effect = Exception("Redis connection failed")
    
    @idempotent_consumer(redis_client=failing_redis, config=config)
    async def handler(msg: ConsumerRecord, *, confirm_idempotency):
        return await mock_process_single_message(msg)
    
    # Process message during outage
    msg = create_test_message(event_id="test-123")
    result = await handler(msg)
    
    # Verify processing occurred despite Redis failure
    assert result is True
    assert len(processed_messages) == 1
    assert processed_messages[0]['event_id'] == "test-123"
    
    # Verify no Redis operations attempted after initial failure
    assert failing_redis.get.call_count == 1
    assert failing_redis.set_if_not_exists.call_count == 0
```

### Issue 5: Manual Redis Key Construction [HIGH]

**Affected Files**: All tests with `test_duplicate_event_skipped`

**Current Pattern**:
```python
# Manually construct key and data
v2_key = f"huleedu:idempotency:v2:service-name:event_type:{deterministic_id}"
redis_client.keys[v2_key] = json.dumps({
    "status": "completed",
    "processed_at": 1640995200,  # Hardcoded timestamp
    "processed_by": "service-name"
})
```

**Problem**: 
Bypasses actual decorator logic and uses hardcoded values that may not match real implementation.

**Solution**:
Use actual decorator to set up duplicate state:
```python
async def test_duplicate_detection_with_real_decorator(self):
    """Test duplicate detection using actual decorator logic"""
    redis_client = RealisticRedisTestDouble()
    config = IdempotencyConfig(service_name="test-service")
    
    # First, process a message normally to establish state
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handler(msg: ConsumerRecord, *, confirm_idempotency):
        await asyncio.sleep(0.01)  # Simulate work
        await confirm_idempotency()
        return "processed"
    
    msg = create_test_message(event_id="dup-test-123")
    
    # Process once
    result1 = await handler(msg)
    assert result1 == "processed"
    
    # Attempt duplicate
    result2 = await handler(msg)
    assert result2 is None  # Duplicate detected
    
    # Verify only one processing attempt
    setnx_ops = [op for op in redis_client.operation_log if op[0] == 'SETNX']
    assert len(setnx_ops) == 1  # Only first attempt
```

### Issue 6: No Concurrent Worker Simulation [CRITICAL - NEW TEST]

**New Test File**: Create `test_idempotency_concurrency.py` in libs/huleedu_service_libs/tests/

**Problem**: 
No tests simulate multiple workers attempting to process the same message simultaneously.

**Solution**:
```python
async def test_concurrent_workers_race_condition(self):
    """Test that only one worker processes a message when racing"""
    redis_client = RealisticRedisTestDouble(latency_ms=5)
    config = IdempotencyConfig(service_name="test-service")
    
    processing_count = 0
    processing_lock = asyncio.Lock()
    
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handler(msg: ConsumerRecord, *, confirm_idempotency):
        nonlocal processing_count
        async with processing_lock:
            processing_count += 1
        
        # Simulate processing time
        await asyncio.sleep(0.1)
        await confirm_idempotency()
        return f"processed_by_worker_{processing_count}"
    
    msg = create_test_message(event_id="concurrent-test")
    
    # Launch multiple workers simultaneously
    workers = [
        asyncio.create_task(handler(msg))
        for _ in range(5)
    ]
    
    results = await asyncio.gather(*workers)
    
    # Verify only one succeeded
    successful_results = [r for r in results if r is not None]
    assert len(successful_results) == 1
    assert processing_count == 1
    
    # Verify others detected duplicate
    none_results = [r for r in results if r is None]
    assert len(none_results) == 4
```

### Issue 7: No Stale Lock Recovery Test [CRITICAL - NEW TEST]

**New Test**: Add to existing test files

**Problem**: 
No test verifies that stale "processing" locks are detected and retried after timeout.

**Solution**:
```python
async def test_stale_processing_lock_recovery(self):
    """Test that stale processing locks can be recovered"""
    redis_client = RealisticRedisTestDouble()
    config = IdempotencyConfig(service_name="test-service")
    
    # Simulate a crashed worker by setting processing state directly
    test_key = "huleedu:idempotency:v2:test-service:test_event:abc123"
    stale_data = {
        "status": "processing",
        "started_at": time.time() - 400,  # 400 seconds ago (stale)
        "processed_by": "crashed-worker"
    }
    await redis_client.setex(test_key, 300, json.dumps(stale_data))
    
    # New worker attempts same message
    processed = False
    
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handler(msg: ConsumerRecord, *, confirm_idempotency):
        nonlocal processed
        processed = True
        await confirm_idempotency()
        return "recovered"
    
    # Create message that would generate same key
    msg = create_test_message_with_deterministic_id("abc123")
    result = await handler(msg)
    
    # Should process despite stale lock
    assert result == "recovered"
    assert processed is True
```

### Issue 8: Exception Lock Release Verification [HIGH]

**Affected Files**: All `test_exception_failure_releases_lock` tests

**Current Pattern**:
```python
with pytest.raises(Exception):
    await handle_message_idempotently(kafka_msg)
assert len(mock_redis_client.delete_calls) == 1
```

**Problem**: 
Only verifies delete was called, not that another worker can process immediately after.

**Solution**:
```python
async def test_exception_releases_lock_for_retry(self):
    """Test that exceptions properly release locks for immediate retry"""
    redis_client = RealisticRedisTestDouble()
    config = IdempotencyConfig(service_name="test-service")
    
    attempt_count = 0
    
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handler(msg: ConsumerRecord, *, confirm_idempotency):
        nonlocal attempt_count
        attempt_count += 1
        
        if attempt_count == 1:
            raise Exception("First attempt fails")
        
        await confirm_idempotency()
        return f"success_attempt_{attempt_count}"
    
    msg = create_test_message(event_id="retry-test")
    
    # First attempt should fail
    with pytest.raises(Exception, match="First attempt fails"):
        await handler(msg)
    
    # Verify lock was acquired then released
    ops = redis_client.operation_log
    setnx_ops = [op for op in ops if op[0] == 'SETNX']
    assert len(setnx_ops) == 1
    
    # Second attempt should succeed immediately
    result = await handler(msg)
    assert result == "success_attempt_2"
    assert attempt_count == 2
```

## Implementation Workflow

**MANDATORY PROCESS - DO NOT SKIP STEPS**:

1. **Select Issue**: Start with Issue 1 (most critical)
2. **Create Test Double**: If the issue requires RealisticRedisTestDouble, implement it first in a shared location
3. **Fix ONE Test File**: 
   - Select the first file from the issue's affected files list
   - Implement the suggested solution
   - Keep other tests in the file unchanged
4. **Run Tests**: 
   - Run ONLY the modified test file
   - Verify all tests pass
   - Verify the new test actually tests the intended behavior
5. **Commit**: Create a commit with message like "fix(tests): Issue 1 - Add async confirmation test for batch_conductor_service"
6. **Next File**: Repeat steps 3-5 for the next file in the issue
7. **Next Issue**: Only after ALL files for an issue are complete, move to the next issue

## Success Criteria

Each fixed test must:
1. Still pass (no regressions)
2. Actually test the behavior, not the mock
3. Be resilient to implementation changes that preserve behavior
4. Catch the failure modes it's designed to detect
5. Use realistic test doubles that simulate actual Redis/system behavior

## Notes

- The RealisticRedisTestDouble should be created once and shared across all tests
- Each issue fix should be independently testable and committable
- If a test reveals an actual bug in the implementation, stop and fix the bug first
- Document any discovered implementation issues as separate tasks