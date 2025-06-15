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

---

## ⏳ **PENDING TASKS**

## Task 3.3 & 3.4: Create and Apply Idempotency Decorator

**Motivation**: The logic for checking and setting the idempotency key is identical for every consumer. A decorator is the perfect pattern to apply this cross-cutting concern in a clean, DRY (Don't Repeat Yourself), and non-invasive manner.

- **File to Create**: 📂 `services/libs/huleedu_service_libs/idempotency.py`
- **Action**: Implement the decorator and then apply it to the message handlers in all consumer services.

### Step 1: Create the Decorator

```python
# services/libs/huleedu_service_libs/idempotency.py

import functools
from typing import Awaitable, Callable, Any
import redis.asyncio as redis
from aiokafka import ConsumerRecord
from .logging_utils import create_service_logger # Assuming this exists or is created
from common_core.events.utils import generate_deterministic_event_id

logger = create_service_logger("idempotency_decorator") # ➕ Ensure create_service_logger is available

def idempotent_consumer(
    redis_client: redis.Redis,
    ttl_seconds: int = 86400  # 24 hours
) -> Callable:
    """
    Decorator to make a Kafka message handler idempotent using Redis.

    Args:
        redis_client: An active async Redis client instance.
        ttl_seconds: The time-to-live for the idempotency key in Redis.
    """
    def decorator(func: Callable[[ConsumerRecord, ...], Awaitable[Any]]) -> Callable:
        @functools.wraps(func)
        async def wrapper(msg: ConsumerRecord, *args, **kwargs) -> Any:
            deterministic_id = generate_deterministic_event_id(msg.value)
            key = f"huleedu:events:seen:{deterministic_id}"

            # Atomically set the key if it does not exist.
            # If set returns 0, the key already existed, so this is a duplicate.
            if await redis_client.set(key, "1", ex=ttl_seconds, nx=True) == 0:
                logger.warning(f"Duplicate event skipped: {key}")
                return None # Return None to signal the caller to just commit the offset.

            try:
                # Execute the actual business logic.
                return await func(msg, *args, **kwargs)
            except Exception as e:
                # If processing fails, release the lock so the event can be retried.
                logger.error(f"Processing failed for event {key}. Unlocking for retry.", exc_info=True)
                await redis_client.delete(key)
                raise # Re-raise the exception so the caller knows it failed.
        return wrapper
    return decorator
```

### Step 2: Apply the Decorator (Example from ELS)

```python
# services/essay_lifecycle_service/worker_main.py
# ... imports, including the new decorator and Redis client ...

import asyncio # ➕ Ensure asyncio is imported
from aiokafka import AIOKafkaConsumer # ➕ Ensure AIOKafkaConsumer is imported
from dishka import make_async_container # ➕ Ensure make_async_container is imported
from .di import CoreInfrastructureProvider # ➕ Ensure CoreInfrastructureProvider is imported
from .protocols import RedisClientProtocol # ➕ Ensure RedisClientProtocol is imported
from services.libs.huleedu_service_libs.idempotency import idempotent_consumer # ➕ Import the decorator
import logging # ➕ Ensure logging is imported

logger = logging.getLogger(__name__) # ➕ Get logger instance

# Define or import TOPICS if not already defined
TOPICS = {"batch_registered": "huleedu.test.batch.registered"} # Example, replace with actual topics

# Mock implementations for demonstration if not in actual code
class BatchCoordinationHandler:
    async def handle_batch_essays_registered(self, *args, **kwargs):
        logger.info("BatchCoordinationHandler: handle_batch_essays_registered called.")

async def process_single_message(msg, batch_coordination_handler):
    logger.info(f"Processing message: {msg.offset}")
    # Simulate some processing
    await batch_coordination_handler.handle_batch_essays_registered()
    return True


async def main(): # Assuming main function exists for consumer loop
    container = make_async_container(CoreInfrastructureProvider())
    
    # 🔄 UPDATE THE CONSUMER SETUP
    consumer = AIOKafkaConsumer(
        TOPICS["batch_registered"],
        bootstrap_servers='localhost:9092', # Replace with actual Kafka brokers
        group_id="els_consumer_group",
        auto_offset_reset="earliest"
    )
    await consumer.start()

    try:
        async with container() as request_container:
            # Get dependencies from DI
            redis_client = await request_container.get(RedisClientProtocol)
            batch_coordination_handler = BatchCoordinationHandler() # Replace with actual DI resolution
            # ... other handlers ...

            # 🔄 WRAP THE CORE LOGIC with the decorator
            @idempotent_consumer(redis_client=redis_client)
            async def handle_message_idempotently(msg: ConsumerRecord) -> Any: # Changed return to Any to match decorator
                return await process_single_message(
                    msg, 
                    batch_coordination_handler=batch_coordination_handler,
                    # ... pass other handlers ...
                )

            # 🔄 UPDATE THE CONSUMER LOOP
            async for msg in consumer:
                try:
                    # The handle_message_idempotently function now contains the check.
                    # It will return None for duplicates, or raise an exception on failure.
                    result = await handle_message_idempotently(msg)

                    # If no exception was raised, commit the offset.
                    # This covers both successful processing and skipped duplicates.
                    if result is not None: # Only commit if not a skipped duplicate
                        await consumer.commit()
                except Exception:
                    # The decorator already logged the error and unlocked the key.
                    # The consumer loop should NOT commit the offset, allowing Kafka to redeliver.
                    logger.warning(f"Message processing failed for offset {msg.offset}, not committing.")
                    # Optional: Add a small delay or advanced retry/DLQ logic here.
    finally:
        await consumer.stop()

# Example of how to run main, usually from worker_main.py
# if __name__ == "__main__":
#    asyncio.run(main())
```

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
