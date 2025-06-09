# **TASK TICKET: `PIPELINE_HARDENING_V1.1`**

* **Status:** `REVISED & READY FOR IMPLEMENTATION`
* **Epic:** Pipeline Reliability & Robustness
* **Owner:** `@LeadDeveloper`
* **Labels:** `architecture`, `reliability`, `idempotency`, `redis`, `data-integrity`

## **1. Change Summary & Motivation**

This revised plan (`v1.1`) supersedes the previous document. It incorporates two critical architectural improvements to enhance data integrity and processing reliability:

1. **Pre-emptive Raw File Storage:** The `File Service` will now persist the raw, unmodified file blob to the `Content Service` *before* any extraction or validation occurs. This establishes an immutable source of truth, enabling robust reprocessing and decoupling storage from interpretation.
2. **Redis-backed Idempotency:** All Kafka consumers will implement a Redis-backed, check-and-set mechanism to guarantee that each event is processed exactly once. This prevents data corruption from inevitable event re-deliveries in a distributed system and is vastly more performant and scalable than using PostgreSQL for this purpose.

## **2. Revised Solution Architecture Canvas**

### **Canvas 1: New File Ingestion Flow (`File Service`)**

This diagram illustrates the updated, more robust data flow for handling file uploads.

```text
                                            +-----------------------------+
                                      ------> | 2. Extract Text from Bytes  |
                                      |     |                             |
+-----------------+   +---------------+     +-----------------------------+
| Client Uploads  |-->| 1. Store Raw  |     | 3. Validate Extracted Text  |--> [FAIL?]-> 5b. Publish ValidationFailed
| (Batch of Files)|   | Blob to CS    |     +-----------------------------+            Event (includes raw_id)
+-----------------+   | (Get raw_id)  |     | 4. Store Extracted Text     |
                      +---------------+     |    to CS (Get text_id)      |
                                      |     +-----------------------------+
                                      |     | 5a. Publish Content         |
                                      ------> | Provisioned Event (with   |
                                            |  raw_id and text_id)        |
                                            +-----------------------------+
```

#### **Canvas 2: New Idempotent Consumer Logic (All Kafka Workers)**

This diagram shows the new processing loop inside every Kafka consumer.

```text
+-------------------+   +----------------------------+   +----------------------+   +-------------------+
| Message received  |-->| 1. Generate Deterministic  |-->| 2. Check & Set Key in  |-->| 3a. Is it a Dup?  |
| from Kafka Topic  |   |    Event ID (SHA256)       |   |    Redis (SETNX)       |   |      (Key Exists) |
+-------------------+   +----------------------------+   +----------------------+   +-------------------+
                                                                 |                         |
                                                        [ Is Key New? ]                  |
                                                                 |                         v
                                +--------------------------------+       +-------------------+
                                | 3b. Process Message (Biz Logic)|------>| 5. Skip & Commit  |
                                +--------------------------------+       |    Offset         |
                                |  try...except...finally        |       +-------------------+
                                +--------------------------------+
                                       |            |
                                 [ SUCCESS ]    [ FAILURE ]
                                       |            |
     +-----------------------------------+            +------------------------------------+
     |                                                  |
     v                                                  v
+----+-------------------+                     +--------+----------+
| 4a. Commit Offset      |                     | 4b. Unlock Key in |
|    (Message Done)      |                     |      Redis        |
+------------------------+                     +-------------------+
```

### **3. Revised Phased Implementation Plan**

#### **Epic 1: Foundational Changes (Contracts & Infrastructure)**

* **Sub-Task 1.1: Update `common_core` Event Contracts**
  * **TDD (Write these tests first):**
    * `test_essay_content_provisioned_v1_includes_raw_storage_id`: Verify the model contains the new field.
    * `test_essay_validation_failed_v1_includes_raw_storage_id`: Verify the failure event also contains the raw ID for traceability.
  * **Implementation Details:**
    * **File:** 📂 `common_core/src/common_core/events/file_events.py`
    * **Action:** Add the `raw_file_storage_id` field to the `EssayContentProvisionedV1` and `EssayValidationFailedV1` models. This ensures downstream services know where the original, untouched file is stored.

        ```python
        # common_core/src/common_core/events/file_events.py
        class EssayContentProvisionedV1(BaseModel):
            # ... existing fields
            raw_file_storage_id: str = Field(description="Storage ID of the original, unmodified raw file blob.") # 
            text_storage_id: str
            # ...

        class EssayValidationFailedV1(BaseModel):
            # ... existing fields
            raw_storage_id: str = Field(description="Storage ID of the raw file that failed validation.") # 
            # ...
        ```

  * **Definition of DONE:**
    * Both Pydantic models in `common_core` are updated with the new field.
    * Unit tests for the models pass.
    * The `common_core` package version is incremented, and `pdm.lock` is updated.

* **Sub-Task 1.2: Add Redis to Infrastructure**
  * **TDD (Write these tests first):**
    * `test_redis_fixture_provides_running_client`: An integration test fixture that spins up a Redis container using Testcontainers and yields a connected client.
  * **Implementation Details:**
    * **File:** 📂 `docker-compose.yml`
    * **Action:** Add a Redis service.

    ```yaml
    # docker-compose.yml
    services:
      # ... other services
      redis:
        image: redis:7-alpine
        container_name: huleedu_redis
        restart: unless-stopped
        networks:
          - huleedu_internal_network
        ports:
          - "6379:6379"
        healthcheck:
          test: ["CMD", "redis-cli", "ping"]
          interval: 10s
          timeout: 5s
          retries: 5
    ```

    * **File:** 📂 `pyproject.toml` (root)
    * **Action:** Add `redis` to the `dev` dependency group.
    * **File:** 📂 `services/essay_lifecycle_service/di.py` (and other consumer DIs)
    * **Action:** Create a provider that yields a Redis client.

    ```python
    # In a provider class within di.py
    import redis.asyncio as redis

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> redis.Redis:
        client = redis.from_url(settings.REDIS_URL)
        await client.ping() # Verify connection on startup
        return client
    ```

  * **Definition of DONE:**
    * Redis service is defined in `docker-compose.yml` and starts successfully.
    * A `RedisClientProtocol` and DI provider are created and available to consumer services.
    * The Testcontainers fixture for Redis is implemented and passing.

---

#### **Epic 2: Service Implementation**

* **Sub-Task 2.1: Refactor `File Service` for Pre-emptive Blob Storage**
  * **TDD (Write these tests first):**
    * `test_process_single_file_stores_raw_blob_first`: A unit test for the core logic function ensuring `content_client.store_content` is called with the raw bytes *before* text extraction.
    * `test_content_provisioned_event_contains_both_storage_ids`: An integration test verifying the final Kafka event includes both `raw_file_storage_id` and `text_storage_id`.
  * **Implementation (`services/file_service/core_logic.py`):**
    Refactor `process_single_file_upload` to implement the new flow.

    ```python
    # services/file_service/core_logic.py
    
    async def process_single_file_upload(
        # ... function signature ...
    ) -> Dict[str, Any]:
        # ...
        try:
            # Store the raw, unmodified file first.
            raw_storage_id = await content_client.store_content(file_content, content_type="raw_upload")

            # Extract text from the same bytes.
            text = await text_extractor.extract_text(file_content, file_name)

            # Validate extracted text.
            validation_result = await content_validator.validate_content(text, file_name)
            if not validation_result.is_valid:
                # Publish failure event, now including raw_storage_id
                validation_failure_event = EssayValidationFailedV1(
                    raw_storage_id=raw_storage_id,
                    # ... other fields
                    )
                await event_publisher.publish_essay_validation_failed(...)
                return { "status": "validation_failed", "raw_storage_id": raw_storage_id }

            # Store the processed (extracted) text.
            text_storage_id = await content_client.store_content(text.encode("utf-8"), content_type="extracted_text")

            # Publish success event with BOTH storage IDs.
            content_provisioned_event = EssayContentProvisionedV1(
                # ...
                raw_file_storage_id=raw_storage_id,
                text_storage_id=text_storage_id,
                # ...
                )
                await event_publisher.publish_essay_content_provisioned(...)

                return { "status": "processing_success", "raw_storage_id": raw_storage_id, "text_storage_id": text_storage_id }
        ```

    **Definition of DONE:**
    * `ContentServiceClientProtocol` is updated to accept an optional `content_type`.
    * The `process_single_file_upload` function implements the new "store raw first" logic.
    * The `EssayContentProvisionedV1` and `EssayValidationFailedV1` events are published with the `raw_storage_id`.
    * All new and existing tests for the File Service pass.

## Sub-Task 2.2: Implement Redis-backed Idempotent Consumer

* **TDD (Write these tests first):**
  * `test_consumer_skips_known_event_id`: Using a Redis test fixture, assert that publishing an event with the same deterministic ID twice results in the core logic being called only once.
* **Implementation (`services/essay_lifecycle_service/worker_main.py`):**
    Apply this pattern to all worker services.

    ```python
    # services/essay_lifecycle_service/worker_main.py
    # ... inside run_consumer_loop, after deserializing the message
    
    async for msg in consumer:
        # ... deserialize message into `envelope` ...
    
        # KEY CHANGE: Idempotency Check
        # Assumes a deterministic key (e.g., from a hash of key fields or a unique event ID)
        event_key = f"huleedu:events:{envelope.event_id}" 
        
        # Use SETNX to atomically check and set. If it returns 0, the key already existed.
        if await redis_client.set(event_key, "1", ex=7200, nx=True) == 0:
            logger.warning(f"Duplicate event skipped: {event_key}")
            await consumer.commit() # Commit to advance past the duplicate
            continue

        try:
            # This is your existing business logic call
            success = await process_single_message(msg, ...)
            if success:
                await consumer.commit() # Commit on success
        except Exception as e:
            logger.error(f"Processing failed for event {event_key}. Unlocking for retry.", exc_info=True)
            # Release the lock so the event can be retried later
            await redis_client.delete(event_key)
            # DO NOT commit, so Kafka will redeliver for another attempt
        ```

    **Definition of DONE:**
    * A deterministic event key strategy is established.
    * The Redis `SETNX` check is implemented in the consumer loop of ELS.
    * The key is deleted from Redis on processing failure to allow retries.
    * The offset is committed for both successfully processed messages and skipped duplicates.

### **5. Architectural Rationale**

Event-driven systems like yours (Kafka) guarantee **at-least-once** delivery. Without idempotency, duplicate events can trigger redundant operations—for example:

* **EssayLifecycleService (ELS):** multiple state transitions or duplicate CJ assessment commands  
* **BatchOrchestratorService (BOS):** repeated batch initiation commands causing cascades of work  
* **SpellCheckerService:** duplicate spell-check runs and redundant content storage  

By standardizing a Redis-backed decorator, you enforce **exactly-once** processing, eliminate boilerplate across services, and dramatically improve system resilience.

### **6. Practical Implementation Strategy**

Since the logic is identical in every consumer, abstract it into your shared libs:

#### 6.1 Decorator Implementation

```python
# services/libs/huleedu_service_libs/kafka_consumer_utils.py
from __future__ import annotations
import functools
from typing import Any, Awaitable, Callable

import redis.asyncio as redis
from aiokafka import ConsumerRecord
from huleedu_service_libs.logging_utils import create_service_logger
from common_core.events.utils import generate_deterministic_event_id

logger = create_service_logger("kafka.idempotency")

def idempotent_consumer(
    redis_client: redis.Redis,
    ttl_seconds: int = 7200  # 2 hours
) -> Callable:
    """Decorator to make a Kafka message handler idempotent using Redis."""
    def decorator(func: Callable[[ConsumerRecord, ...], Awaitable[Any]]) -> Callable:
        @functools.wraps(func)
        async def wrapper(msg: ConsumerRecord, *args, **kwargs) -> Any:
            key = f"huleedu:events:seen:{generate_deterministic_event_id(msg.value)}"
            if not await redis_client.set(key, "1", ex=ttl_seconds, nx=True):
                logger.warning(f"Duplicate event skipped: {key}")
                return None
            try:
                return await func(msg, *args, **kwargs)
            except Exception:
                logger.error(f"Processing failed for event {key}; unlocking for retry.", exc_info=True)
                await redis_client.delete(key)
                raise
        return wrapper
    return decorator

#### **6.2 Usage in Consumer Workers**

```python
# services/spell_checker_service/worker_main.py
from aiokafka import ConsumerRecord
from huleedu_service_libs.kafka_consumer_utils import idempotent_consumer

# Obtain Redis client via DI
redis_client = await container.get(redis.Redis)

@idempotent_consumer(redis_client=redis_client)
async def handle_spellcheck(msg: ConsumerRecord):
    return await process_single_message(msg)

async for msg in consumer:
    try:
        await handle_spellcheck(msg)
        await consumer.commit()
    except Exception:
        # Retry or DLQ logic
        ...
```

#### **7. Codebase Validation Findings**
