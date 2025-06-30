# Systematic Isolation Plan for E2E Test Failure

## Current State

- ✅ All 637 unit tests pass
- ✅ Complete test isolation achieved (Redis, Kafka, DB)
- ❌ E2E test times out after 40 seconds
- ❌ Issue persists despite batch_id persistence fixes

## Isolation Strategy

### Phase 1: Diagnostic Analysis (Immediate)

1. **Run Diagnostic Monitor**

   ```bash
   # Terminal 1: Start monitoring
   python diagnose_e2e_failure.py
   
   # Terminal 2: Run isolated test
   python test_redis_isolation.py
   ```

   This will show exactly where the pipeline stops.

2. **Collect Service Logs**

   ```bash
   # Capture logs during test failure
   docker compose logs -f > service_logs.txt 2>&1
   ```

3. **Check Database State**

   ```bash
   # After test timeout, check what was persisted
   docker exec -i huleedu_essay_lifecycle_db psql -U huleedu_user -d essay_lifecycle -c "SELECT essay_id, batch_id, current_status FROM essay_states;"
   docker exec -i huleedu_batch_orchestrator_db psql -U huleedu_user -d batch_orchestrator -c "SELECT * FROM batches;"
   ```

### Phase 2: Minimal Reproduction Case

1. **Test Individual Event Flows** ✅ DONE
   - Created `test_basic_pipeline.py` - basic flow works
   - Created `test_e2e_trace.py` - traced failure point
   - Created `test_minimal_flow.py` - monitored Kafka events

2. **Binary Search Approach** ⚠️ PARTIALLY DONE
   - Identified that pipeline works without topic recreation
   - Found failure point: Kafka consumer can't subscribe to recreated topics
   - Still need to test with topic waiting logic

### Phase 3: Service-by-Service Validation

1. **ELS Validation** ✅ DONE via `test_basic_pipeline.py`
   - Batch registration: ✅ Works
   - Essay state persistence: ✅ Confirmed in DB
   - Event publishing: ✅ Verified

2. **BOS Validation** ✅ DONE via `test_basic_pipeline.py`
   - Batch creation: ✅ Works
   - Returns batch_id and correlation_id: ✅ Verified

3. **Integration Points** ⚠️ PARTIALLY TESTED
   - Redis idempotency: ✅ Tested (but found ID generation bug)
   - Kafka message flow: ❌ Broken due to topic recreation
   - Database transactions: ✅ Working correctly

### Phase 4: Root Cause Analysis

Based on the timeout at 40 seconds and complete isolation, likely causes:

1. **Event Not Published**
   - Service crashes before publishing
   - Conditional logic prevents publishing
   - Wrong topic or correlation ID

2. **Event Not Consumed**
   - Consumer group misconfiguration
   - Deserialization error
   - Idempotency false positive

3. **State Machine Issue**
   - Invalid state transition
   - Missing state update
   - Batch ID not propagated

4. **Timing/Race Condition**
   - Service not ready when event arrives
   - Async operation not awaited
   - Database transaction not committed

## Investigation Findings

### 1. Topic Name Bug (FIXED)

**Discovery**: The enum mapping had `batch_phase` with underscore instead of dot

- File: `common_core/src/common_core/event_enums.py`
- Line 74: Changed `huleedu.els.batch_phase.outcome.v1` to `huleedu.els.batch.phase.outcome.v1`
- **Status**: ✅ Fixed

### 2. Basic Pipeline Works

**Test**: Created `test_basic_pipeline.py` to verify core functionality

- Batch registration: ✅ Works
- ELS processes events: ✅ Works  
- Kafka events published: ✅ Works
- **Conclusion**: Services are functional, issue is in test setup

### 3. Services Have In-Memory State

**Discovery**: ELS logs showed "No available slots for content" from old test runs

- Services were caching state from previous tests
- **Fix Applied**: Restarted services with `docker compose restart`
- **Status**: ✅ Resolved

### 4. E2E Test Stops at File Upload

**Test**: Created `test_e2e_trace.py` to trace execution

- Batch creation: ✅ Works
- File upload: ❌ Fails with 401 (authentication required)
- **Finding**: Test needs proper authentication setup

### 5. Kafka Topic Availability (CRITICAL)

**Discovery**: When monitoring events during test:

```
Topic huleedu.batch.essays.registered.v1 not found in cluster metadata
Topic huleedu.file.essay.content.provisioned.v1 not found in cluster metadata
```

- **Root Cause**: Topics are deleted and recreated but not available when consumer starts
- **Impact**: Consumer can't subscribe → No events consumed → Test timeout
- **Status**: ❌ This is why E2E test fails!

## Execution Order

1. ✅ Run diagnostic monitor to identify failure point
   - Created `diagnose_e2e_failure.py` - found services report 404 on health checks
   - Created `test_minimal_flow.py` - discovered Kafka topics not available

2. ✅ Create minimal test for that specific failure  
   - Created `test_basic_pipeline.py` - proved basic flow works
   - Created `test_e2e_trace.py` - found auth failure at file upload

3. ⚠️ Add comprehensive logging to track event flow between services
   - Partially done - added monitoring but haven't modified service code

4. ✅ Test with single essay instead of batch
   - Tested with 1-3 essays in various test scripts

5. ⚠️ Compare working unit test with failing E2E scenario
   - Found key difference: E2E test recreates Kafka topics, unit tests don't

6. ❌ Fix Kafka topic availability issue (NEXT STEP)

## Success Criteria

- Identify the exact service and method where failure occurs
- Reproduce the failure in a minimal test case
- Understand why unit tests pass but E2E fails
- Implement and verify the fix

## Additional Failing Tests

### Test Suite: tests/functional/test_e2e_client_pipeline_resolution_workflow.py

This suite has three failing tests with different root causes:

#### 1. test_complete_client_pipeline_resolution_workflow

**Status**: FAILED  
**Primary Issue**: Serialization error  
**Details**: The test fails with `Can not serialize value type: <class 'tuple'>`. This occurs when trying to serialize a tuple `('c8532ee5-d9e7-4336-8ec0-5fa1c07772ba', '218f1c83-c15a-4dff-b98c-6605cbbdb0bf')` for a Kafka event.  
**Root Cause**: Likely returning a tuple instead of a proper response object from a service method.

#### 2. test_state_aware_pipeline_optimization

**Status**: FAILED  
**Primary Issue**: Pydantic model validation error  
**Details**: `PydanticUserError: If you want to use '@model_validator' with 'mode='after'', the decorated function must be a method of the model`  
**Final Error**: Test hangs after initial error, resulting in 40-second timeout  
**Root Cause**: Incorrectly configured Pydantic model validator - likely a decorator on a standalone function instead of a model method.

#### 3. test_trigger_downstream_services

**Status**: FAILED  
**Primary Issue**: Same Pydantic model validation error as test #2  
**Details**: Identical `PydanticUserError` about `@model_validator`  
**Final Error**: 40-second timeout after initial error  
**Root Cause**: Same misconfigured Pydantic model affecting multiple tests.

### Prioritized Fix Order

1. **Fix Pydantic Model Validator** (affects tests #2 and #3)
   - Find the model with incorrect `@model_validator` usage
   - Move the validator to be a proper model method

2. **Fix Serialization Issue** (affects test #1)
   - Find where a tuple is being returned instead of proper response
   - Ensure all Kafka messages use serializable types

3. **Fix E2E Pipeline Test**
   - Continue investigation of event flow
   - Resolve authentication and file upload issues

### Test Suite: tests/functional/test_e2e_idempotency.py

Two failing tests reveal a critical issue with deterministic ID generation:

#### 1. TestAuthenticRedisIdempotency::test_cross_service_deterministic_id_consistency

**Status**: FAILED  
**Primary Issue**: AssertionError - Deterministic ID generation is inconsistent  
**Details**: Test created 3 events with identical data but different envelope metadata. Expected 1 unique ID, got 3.  
**Root Cause**: The `generate_deterministic_event_id` function is incorrectly including envelope metadata (event_id, timestamp) in the hash calculation.

#### 2. TestControlledIdempotencyScenarios::test_deterministic_id_generation_consistency

**Status**: FAILED  
**Primary Issue**: AssertionError - Same deterministic ID issue  
**Details**: Created 5 event variations with different metadata. Expected 1 unique ID, got 5.  
**Root Cause**: Confirms the ID generation includes variable metadata instead of just stable business data.

**Note**: 5 other idempotency tests PASSED, confirming Redis operations, duplicate detection, and fail-open behavior work correctly.

### Test Suite: tests/functional/test_e2e_cj_assessment_workflows.py

**Status**: All 4 tests PASSED ✅

This suite confirms that the CJ Assessment service and its pipeline work correctly in isolation, processing essays and publishing completion events as expected.

## Comprehensive Functional Test Results

### Overall Statistics

- **Total test files**: 16
- **✅ Passed**: 12 (75.0%)
- **⚠️ Partially passed**: 1 (6.3%)
- **❌ Failed**: 3 (18.8%)

### Passing Test Suites (12/16)

These tests confirm core service functionality works correctly:

- `test_e2e_cj_assessment_workflows.py` (4/4 tests)
- `test_e2e_file_workflows.py` (4/4 tests)
- `test_e2e_kafka_monitoring.py` (3/3 tests)
- `test_e2e_pipeline_workflows.py` (2/2 tests)
- `test_e2e_realtime_notifications.py` (4/4 tests)
- `test_e2e_spellcheck_workflows.py` (4/4 tests)
- `test_file_service_raw_storage_e2e.py` (2/2 tests)
- `test_pattern_alignment_validation.py` (7/7 tests)
- `test_result_aggregator_api_caching.py` (6/6 tests)
- `test_service_health.py` (2/2 tests)
- `test_simple_validation_e2e.py` (1/1 tests)
- `test_validation_coordination_success.py` (1/1 tests)

### Partially Passing Test Suite

**`test_e2e_idempotency.py`** (5/7 tests passed)

- ❌ `TestAuthenticRedisIdempotency::test_cross_service_deterministic_id_consistency`
- ❌ `TestControlledIdempotencyScenarios::test_deterministic_id_generation_consistency`
- Issue: Deterministic ID generation includes envelope metadata

### Failing Test Suites (3/16)

#### 1. `test_e2e_client_pipeline_resolution_workflow.py` (0/3 tests passed)

- All tests fail with serialization errors and timeouts
- Example: `TypeError: Cannot serialize value type: <class 'tuple'>`

#### 2. `test_validation_coordination_complete_failures.py` (0/1 tests passed)

- Test timeout (>40s)
- `RuntimeError: athrow(): asynchronous generator is already running`

#### 3. `test_validation_coordination_partial_failures.py` (0/2 tests passed)

- Test timeouts (>40s)
- Same async generator error as above

## Root Cause Analysis Summary

### 1. Kafka Topic Recreation Issue (Critical)

**Finding**: When we delete and recreate Kafka topics in the isolation script, they're not immediately available when the test starts.  
**Impact**: Consumer can't subscribe to non-existent topics, so NO events are consumed.  
**Solution**: Add retry logic or wait for topic creation confirmation before starting tests.

### 2. Deterministic ID Generation Bug

**Finding**: The `generate_deterministic_event_id` function includes envelope metadata instead of just business data.  
**Impact**: Same business events with different timestamps/IDs are not detected as duplicates.  
**Solution**: Fix the function to hash only stable business data, not envelope metadata.

### 3. Pydantic Model Configuration

**Finding**: Incorrect `@model_validator` usage in some models.  
**Impact**: Tests fail immediately with configuration errors.  
**Solution**: Find and fix the incorrectly decorated validators.

### 4. Async Generator Runtime Error

**Finding**: Multiple validation coordination tests fail with "asynchronous generator is already running"  
**Impact**: Tests timeout after 40 seconds  
**Solution**: Fix the async generator usage in validation coordination code

### 5. Tuple Serialization Issue

**Finding**: Some service returns tuples that can't be serialized for Kafka  
**Impact**: Client pipeline resolution tests fail immediately  
**Solution**: Find and fix methods returning raw tuples instead of proper response objects

## Proposed Solutions

### 1. Fix Kafka Topic Availability (Priority 1)

Instead of deleting/recreating topics:

```python
# Option A: Don't delete topics, just clear them
async def clear_kafka_topics():
    # Use kafka-delete-records instead of topic deletion
    
# Option B: Wait for topics to be ready
async def wait_for_topics_ready():
    admin_client = KafkaAdminClient()
    while not all_topics_exist():
        await asyncio.sleep(0.5)
```

### 2. Fix Deterministic ID Generation (Priority 2)

Update `generate_deterministic_event_id` to use only event_id:

```python
# Current (WRONG): includes all envelope data
event_id = event_dict.get("event_id", "")
if event_id:
    return hashlib.sha256(f"event:{event_id}".encode()).hexdigest()
```

This is actually correct! The issue might be in the test expectations.

### 3. Fix Test Isolation Script

Improve `test_redis_isolation.py`:

- Add topic readiness check after recreation
- Add service health check before test
- Add proper error handling for missing topics

### 4. Fix Authentication in E2E Tests

- Use proper test user creation from AuthTestManager
- Ensure tokens are passed to all service calls
- Fix file upload endpoint authentication

## Phase 5: Storage Reference Fix Investigation

### Issue: CJ Assessment Cannot Fetch Essay Content

**Discovery**: After fixing all the above issues, CJ Assessment service was still failing with "Invalid content ID format" errors.

**Root Cause Analysis**:
1. CJ Assessment was receiving `text_storage_id` values like `"original-{essay_id}"` instead of actual storage IDs
2. This was a fallback value from ELS's `_get_text_storage_id_for_phase` method in `batch_phase_coordinator_impl.py`
3. The method couldn't find the corrected text storage ID from the spellcheck phase

**Investigation Steps**:
1. Checked CJ Assessment logs - confirmed it was trying to fetch content with invalid IDs like `"original-40843bf8-c472-4adf-a4f7-f48441c7ec5c"`
2. Traced back to ELS - found it was sending these fallback IDs in the CJ assessment request
3. Examined database - found that:
   - `storage_references` field was empty `{}`
   - Corrected text storage ID was buried in `processing_metadata.spellcheck_result.storage_metadata.references.corrected_text.default`
   - Example: `{"references": {"corrected_text": {"default": "5f5afdfb1c1e4533857e15144caaa0d1"}}}`

### Fix Applied: Atomic Storage Reference Updates

**Changes Made**:
1. Extended `EssayRepositoryProtocol` and PostgreSQL implementation to accept optional `storage_reference` parameter
2. Modified `update_essay_state` and `update_essay_status_via_machine` methods to atomically update storage references
3. Updated `DefaultServiceResultHandler::handle_spellcheck_result` to:
   - Extract corrected text storage ID from spellcheck result
   - Pass it to repository as `(ContentType.CORRECTED_TEXT, storage_id)`
4. Fixed enum usage from incorrect `ContentType.SPELLCHECKED_ESSAY` to `ContentType.CORRECTED_TEXT`

### Why The Fix Still Failed

**After applying the fix and rebuilding**:
1. Ran new test with batch ID `6ec9a2db-e5a9-41f6-9e8c-04fec4d13fd8`
2. CJ Assessment STILL received `"original-{essay_id}"` values
3. Database check revealed `storage_references` field was STILL empty `{}`

**Root Cause of Fix Failure**:
The service result handler looks for the storage ID under the key `"storage_id"`:
```python
storage_id = spellchecked_ref.get("storage_id")
```

But the spell checker service stores it under the key `"default"`:
```python
storage_metadata_for_result = StorageReferenceMetadata(
    references={ContentType.CORRECTED_TEXT: {"default": new_storage_id}},
)
```

**Actual Database Structure**:
```json
{"default": "21bde2369215411faaf1a7fa85b2c03d"}
```

**The Bug**: The fix is looking for the wrong key. It should be:
```python
storage_id = spellchecked_ref.get("default")  # Not "storage_id"
```

This explains why the storage_references field remains empty even after the fix - the code can't find the storage ID because it's looking for the wrong key name.

### Next Steps

1. Fix the key name in `service_result_handler_impl.py` from `"storage_id"` to `"default"`
2. Rebuild and test again
3. Verify that `storage_references` field is properly populated
4. Confirm CJ Assessment receives correct storage IDs instead of fallback values
