# TASK TICKET: PIPELINE_HARDENING_V1.1 — Event Idempotency (Tasks 3.1-3.5)

Status: REFINED & READY FOR IMPLEMENTATION
Epic: Event Idempotency (PIPELINE_HARDENING_V1.1)
Owner: @LeadDeveloper
Labels: architecture, reliability, idempotency, redis, data-integrity, observability

Objective: Transition the platform from at-least-once event delivery to effectively-once processing. This is a non-negotiable requirement for data integrity, preventing duplicate operations and state corruption in our distributed system.

---

## ✅ **COMPLETED TASKS**

### Task 3.1: Add Redis to Infrastructure ✅ COMPLETED

**Implementation**: Redis infrastructure fully deployed with service library integration following KafkaBus patterns. All 4 consumer services (BOS, ELS, CJ Assessment, Spell Checker) configured with RedisClientProtocol and DI providers. 15 Redis integration tests passing.

**Technical Details**:

- Redis 7-alpine in docker-compose.yml with persistence (AOF) and memory management
- `huleedu_service_libs/redis_client.py` wrapper with lifecycle management
- Protocol-based DI injection with APP scope across all services
- Environment variable configuration: `REDIS_URL: str = "redis://localhost:6379"`

### Task 3.2: Generate Deterministic Event ID ✅ COMPLETED

**Implementation**: Created `common_core/src/common_core/events/utils.py` with `generate_deterministic_event_id()` function for stable, content-based event hashing critical to idempotency guarantees.

**Technical Details**:

```python
def generate_deterministic_event_id(msg_value: bytes) -> str:
    # Hash stable 'data' payload only, ignoring transient envelope metadata
    # Handles JSON key order independence via sort_keys=True
    # Fallback to raw message hash for malformed/non-UTF8 content
    return hashlib.sha256(stable_string.encode('utf-8')).hexdigest()
```

**Validation**: 12 comprehensive unit tests covering edge cases (malformed JSON, non-UTF8 bytes, missing data field, key order independence). All tests passing with full exception handling for `UnicodeDecodeError`, `JSONDecodeError`, and `TypeError`.

### Task 3.3: Create Idempotency Decorator ✅ COMPLETED

**Implementation**: Successfully created `services/libs/huleedu_service_libs/idempotency.py` with production-ready idempotency decorator following established service library patterns.

**Technical Features**:

- DRY decorator pattern using `@idempotent_consumer(redis_client, ttl_seconds=86400)`
- Redis SETNX operations with configurable TTL for duplicate detection
- Deterministic event ID generation using existing `common_core.events.utils`
- Fail-open approach: processes without idempotency protection if Redis fails
- Proper error handling with automatic key cleanup on processing failures
- Structured logging for duplicate detection and debugging
- Type-safe integration with central RedisClientProtocol

**Unit Tests**: Created comprehensive test suite `services/libs/huleedu_service_libs/tests/test_idempotency.py` with 8 test scenarios:

- ✅ First-time event processing with real handlers (not mocks)
- ✅ Duplicate event detection and skipping
- ✅ Processing failure recovery with key cleanup
- ✅ Redis failure fallback behavior
- ✅ Default TTL application (24 hours)
- ✅ Deterministic key generation validation
- ✅ Call tracking verification without mocking business logic

**Validation**: All 8 unit tests passing, follows testing best practices (real handler functions, only external dependencies mocked).

### 🏗️ **ARCHITECTURAL REFINEMENT COMPLETED**

**Lead Architect Feedback Implementation**: Successfully implemented the recommended architectural refinement to centralize `RedisClientProtocol` and eliminate technical debt.

**Changes Made**:

1. **Central Protocol Creation**: Created `services/libs/huleedu_service_libs/protocols.py` with canonical `RedisClientProtocol`
2. **Type Safety Enhancement**: Updated idempotency decorator to use `RedisClientProtocol` instead of `Any` type workaround
3. **DRY Compliance**: Removed 4 duplicate protocol definitions across services → 1 authoritative source
4. **Service Migration**: Updated all 4 services (BOS, ELS, CJ Assessment, Spell Checker) to import from central location:
   - Updated `di.py` files to import from `huleedu_service_libs.protocols`
   - Updated `protocols.py` files to remove duplicate definitions
   - Updated test files to use central protocol

**Quality Assurance**:
- ✅ All 23 tests passing (8 idempotency + 15 Redis integration)
- ✅ Zero linting errors across all modified files
- ✅ MyPy type checking passes with full type safety
- ✅ No breaking changes to existing functionality

**Benefits Achieved**:
- **Type Safety**: Eliminated `Any` workaround, achieved full type safety
- **Maintainability**: Single source of truth for Redis protocol interface
- **Consistency**: All services use identical protocol definition
- **Encapsulation**: Protocol belongs with its implementation in service libs

---

## ⏳ **PENDING TASKS**

## ⏳ **Task 3.4: Apply Decorator to All Consumers - PENDING**

**Ready for Implementation**: Decorator infrastructure complete, tested, and architecturally refined.

### Implementation Pattern

```python
# Example: services/essay_lifecycle_service/worker_main.py

from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.protocols import RedisClientProtocol

async def main():
    container = make_async_container(CoreInfrastructureProvider())
    
    async with container() as request_container:
        # Get dependencies from DI
        redis_client = await request_container.get(RedisClientProtocol)
        batch_coordination_handler = await request_container.get(BatchCoordinationHandlerProtocol)

        # Apply decorator to message handler
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: ConsumerRecord) -> Any:
            return await process_single_message(msg, batch_coordination_handler)

        # Consumer loop with idempotency
        async for msg in consumer:
            try:
                result = await handle_message_idempotently(msg)
                if result is not None:  # Only commit if not a skipped duplicate
                    await consumer.commit()
            except Exception:
                logger.warning(f"Message processing failed for offset {msg.offset}, not committing.")
```

### Services to Update:
1. **Batch Orchestrator Service** - `services/batch_orchestrator_service/kafka_consumer.py`
2. **Essay Lifecycle Service** - `services/essay_lifecycle_service/worker_main.py`
3. **CJ Assessment Service** - `services/cj_assessment_service/worker_main.py`
4. **Spell Checker Service** - `services/spell_checker_service/worker_main.py`

---

## Task 3.5: Test Implementation

**Motivation**: We must prove that the idempotency layer works as designed under adversarial conditions.

- **File to Create**: 📂 `tests/functional/test_e2e_idempotency.py`
- **Action**: Create an E2E test that intentionally publishes a duplicate event and asserts that the core business logic is executed only once.

```python
# tests/functional/test_e2e_idempotency.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from aiokafka import AIOKafkaProducer
import json
import uuid
import logging

# Ensure necessary imports for mocking if not already present in your test setup
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import DefaultBatchCoordinationHandler # Example import, adjust as needed
from common_core.events.envelope import EventEnvelope # Assuming EventEnvelope is used for Kafka messages
from common_core.events.file_events import EssayBatchRegisteredV1 # Example event, adjust as needed

logger = logging.getLogger(__name__)

# Mock KafkaManager and TOPICS for test
class MockKafkaManager:
    def __init__(self):
        self.producer = AsyncMock(spec=AIOKafkaProducer)
        self.producer.start = AsyncMock()
        self.producer.stop = AsyncMock()

    async def publish_event(self, topic: str, event: Any):
        logger.info(f"MockKafkaManager: Publishing to {topic}: {event.model_dump_json()}")
        await self.producer.send_and_wait(topic, event.model_dump_json().encode('utf-8'))

# Example helper function to create an event
def create_batch_registered_event(batch_id: str, correlation_id: uuid.UUID) -> EventEnvelope:
    data = EssayBatchRegisteredV1(
        batch_id=batch_id,
        essay_count=1,
        # Add other necessary fields for the event data
        # Ensure these fields make the event 'deterministic' for hashing
    )
    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="huleedu.essay.batch.registered.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="batch_orchestrator_service",
        correlation_id=correlation_id,
        data=data
    )

# Mock TOPICS dictionary
TOPICS = {
    "batch_registered": "huleedu.test.batch.registered",
    # Add other topics as needed for the test environment
}

@pytest.fixture(scope="module")
async def kafka_manager():
    manager = MockKafkaManager()
    await manager.producer.start()
    yield manager
    await manager.producer.stop()

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_idempotent_consumer_skips_duplicate_event(mocker, kafka_manager):
    # ... setup test data (batch_id, correlation_id, etc.) ...
    batch_id = str(uuid.uuid4())
    correlation_id = uuid.uuid4()
    
    # 1. Spy on a downstream dependency that should only be called once.
    # Example: The database call to create an essay record in ELS.
    # Adjust this import path and method name to the actual method that would be called
    # by the business logic *after* the idempotency check passes.
    
    # Ensure DefaultBatchCoordinationHandler is properly mocked or if it's a real class,
    # that its dependencies are handled for testing.
    # For a true E2E, this would involve observing the actual side effect (e.g., a DB entry).
    # For functional, spying on a mocked dependency is more common.
    
    # Assuming DefaultBatchCoordinationHandler is instantiated somewhere in the ELS worker_main.py
    # and has a method like handle_batch_essays_registered that performs the critical side-effect.
    
    # If DefaultBatchCoordinationHandler is a concrete class that gets instantiated,
    # you might need to patch its method on the class itself or mock the instance.
    
    # Using patch.object to mock the method of the class (if it's a static/class method or if you control instantiation)
    # or a spy on the method of an *instance* if it's passed via DI.
    
    # For this example, we'll assume it's a method on a concrete class that the worker uses.
    # Adjust 'target_path_to_mock' to the actual module path where DefaultBatchCoordinationHandler is defined.
    # e.g., 'services.essay_lifecycle_service.implementations.batch_coordination_handler_impl.DefaultBatchCoordinationHandler'
    
    # You might need to adjust the patch target if your DI setup makes it more complex.
    # Simplest for functional test is to mock the method that performs the unique action.
    
    # Example using mocker.patch:
    # Ensure this path correctly points to where the method is looked up/called
    mock_handle_batch_essays_registered = mocker.patch(
        'services.essay_lifecycle_service.implementations.batch_coordination_handler_impl.DefaultBatchCoordinationHandler.handle_batch_essays_registered',
        new_callable=AsyncMock # Assuming it's an async method
    )

    # 2. Construct a specific, deterministic event payload.
    event_to_publish = create_batch_registered_event(batch_id, correlation_id)

    # 3. Publish the event for the first time.
    logger.info(f"Publishing first event for batch: {batch_id}")
    await kafka_manager.publish_event(TOPICS["batch_registered"], event_to_publish)

    # Give the consumer a moment to process it. Adjust sleep duration based on service processing time.
    await asyncio.sleep(5) 

    # 4. Assert that the business logic was called exactly once so far.
    logger.info("Asserting first call...")
    mock_handle_batch_essays_registered.assert_called_once()
    logger.info("First call asserted.")

    # 5. Publish the exact same event again.
    logger.info(f"Publishing duplicate event for batch: {batch_id}")
    await kafka_manager.publish_event(TOPICS["batch_registered"], event_to_publish)

    # Give the consumer time to see the duplicate.
    await asyncio.sleep(5)

    # 6. Assert that the business logic was *still* only called once.
    # The spy's call count should not have increased.
    logger.info("Asserting duplicate call...")
    mock_handle_batch_essays_registered.assert_called_once() # Should still be 1 call
    logger.info("Duplicate call asserted (skipped).")

    print("✅ Idempotency test passed: Duplicate event was correctly identified and skipped.")

```
