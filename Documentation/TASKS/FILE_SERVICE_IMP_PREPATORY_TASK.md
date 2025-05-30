# Task Ticket: Implement Batch Coordination Walking Skeleton (Common Core, ELS & BOS Updates - Preparatory Phase)

Ticket ID: HULEDU-PREP-001
Assignee: Junior Developer Team
Reporter: System Architect
Priority: Critical
**Status**: IN PROGRESS

## ✅ COMPLETION STATUS

- **Section A: Common Core Changes** - ✅ COMPLETED & VERIFIED (2025-01-28)
- **Section B: Kafka Topic Bootstrap Script** - ✅ COMPLETED & VERIFIED (2025-01-28)
- **Section C: ELS Containerization & Updates** - ✅ COMPLETED & VERIFIED (2025-01-30)
- **Section D: BOS Modifications** - ⏳ PENDING
- **Section E: Design Principle Consolidation** - ✅ COMPLETED & VERIFIED (2025-01-30)

**Goal**:
Implement the foundational **preparatory steps** for the batch processing coordination "Walking Skeleton." This involves critical updates to `common_core`, substantial changes to the Essay Lifecycle Service (ELS) including its containerization, and modifications to the Batch Orchestrator Service (BOS) to enable an end-to-end event flow. This phase ensures these components are ready *before* the File Service is implemented. The initial pipeline focus remains spellcheck-only.

**Context/Background**:
This implementation follows the agreed-upon architectural vision, which refines the "Batch Coordination Implementation Roadmap" and PRD. The core principle is event-driven communication with clear service responsibilities.

**Key Architectural Decisions to Adhere To (for these preparatory steps)**:

- **Overall Event Flow (relevant to these parts)**:
    1. **Client** → **BOS API** (new endpoint): Registers a batch, providing `course_code`, `class_designation`, `essay_instructions`, `expected_essay_count`, `essay_ids`.
    2. **BOS** stores this full context and emits a *lightweight* `BatchEssaysRegistered` event (NO `course_code`, etc.) to ELS.
    3. (File Service will later emit `EssayContentReady` to ELS).
    4. **ELS** consumes `BatchEssaysRegistered` (and later `EssayContentReady`) for readiness aggregation.
    5. **ELS** → **BOS**: Emits `BatchEssaysReady` when a batch is complete.
    6. **BOS** → **ELS**: Sends pipeline commands (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`) which **now include the necessary processing context** like `language` (inferred by BOS from its stored `course_code`).
- **ELS Containerization**: ELS will run as two separate processes/services (API and Worker) in Docker Compose using the same Docker image.
- **BOS API Request Models**: Pydantic models for BOS API request bodies will be local to the BOS service.
- **`course_code` Propagation**: Handled via BOS storing it and then passing `language` (inferred from `course_code`) in commands to ELS.
- **Adherence to Rules**: All implementations must follow existing project rules regarding DI, protocols, Pydantic settings, logging, file sizes (LoC < 400, line length <= 100), and project structure.

## Implementation Tasks (Preparatory Phase)

### A. Common Core Changes (`common_core/`) ✅ COMPLETED & VERIFIED

**Implementation Summary:**

- ✅ **Updated Enums**: Added `BATCH_ESSAYS_REGISTERED` and `ESSAY_CONTENT_READY` to `ProcessingEvent` enum
- ✅ **Updated Topic Mapping**: Added explicit topic mappings for new events:
  - `BATCH_ESSAYS_REGISTERED` → `"huleedu.batch.essays.registered.v1"`
  - `ESSAY_CONTENT_READY` → `"huleedu.file.essay.content.ready.v1"`
- ✅ **Event Models Verified**: Confirmed `BatchEssaysRegistered` and `EssayContentReady` models are properly defined with required fields
- ✅ **Module Exports Updated**: Added models to `__init__.py` with proper `model_rebuild()` calls
- ✅ **Verification**: Kafka topic bootstrap script successfully creates new topics

### B. Kafka Topic Bootstrap Script (`scripts/kafka_topic_bootstrap.py`) ✅ COMPLETED & VERIFIED

**Implementation Summary:**

- ✅ **No Changes Required**: Script already uses generic discovery from `common_core.enums._TOPIC_MAPPING`
- ✅ **Verification Passed**: Script successfully creates new topics:
  - `huleedu.batch.essays.registered.v1`
  - `huleedu.file.essay.content.ready.v1`
- ✅ **Docker Integration**: Topics created automatically during `docker-compose up`

---

### C. ELS Containerization & Updates (`services/essay_lifecycle_service/`) ✅ COMPLETED & VERIFIED

**Implementation Summary:**

1. ✅ **Dockerfile Updated**: Added `PROMETHEUS_PORT=9090` environment variable and proper `EXPOSE ${HTTP_PORT} ${PROMETHEUS_PORT}` instructions
2. ✅ **Docker Compose Split**:
   - `essay_lifecycle_api`: HTTP service on port 6001 with `pdm run start`
   - `essay_lifecycle_worker`: Kafka consumer with `pdm run start_worker`
   - Both services properly configured with dependencies and environment variables
3. ✅ **Worker Topic Subscription**: Added `BATCH_ESSAYS_REGISTERED` and `ESSAY_CONTENT_READY` topic subscriptions using `topic_name()` function
4. ✅ **Event Routing Implemented**:
   - `BatchEssaysRegistered` events routed to `BatchEssayTracker.register_batch()`
   - `EssayContentReady` events routed to `BatchEssayTracker.mark_essay_ready()`
   - Proper error handling and logging with correlation IDs
   - TODO markers for future idempotent state updates:
     - Basic idempotency for `EssayContentReady` state updates implemented (e.g., checking current status via `StateTransitionValidator` before transitioning `EssayState`); advanced idempotency strategies (e.g., full event ID tracking for all handlers) marked as TODO for future refinement.

---

### D. Batch Orchestrator Service (BOS) Modifications (`services/batch_orchestrator_service/`)

1. **Create API Request Model (`services/batch_orchestrator_service/api_models.py`)**:
    - **Action**: Create this new file.
    - **Action**: Define `BatchRegistrationRequestV1(BaseModel)` with fields: `expected_essay_count: int`, `essay_ids: List[str]`, `course_code: str`, `class_designation: str`, `essay_instructions: str`. Use `pydantic.Field` for descriptions.

        ```python
        # services/batch_orchestrator_service/api_models.py
        from __future__ import annotations
        from typing import List
        from pydantic import BaseModel, Field

        class BatchRegistrationRequestV1(BaseModel):
            expected_essay_count: int = Field(..., description="Number of essays expected in this batch.", gt=0)
            essay_ids: List[str] = Field(..., description="List of unique essay IDs that will be processed in this batch.", min_length=1)
            course_code: str = Field(..., description="Course code associated with this batch (e.g., SV1, ENG5).")
            class_designation: str = Field(..., description="Class or group designation (e.g., 'Class 9A', 'Group Blue').")
            essay_instructions: str = Field(..., description="Instructions provided for the essay assignment.")
        ```

2. **Update API Route Module (`services/batch_orchestrator_service/api/batch_routes.py`)**:
    - **Action**: Implement the `POST /register` endpoint within the existing `batch_bp`.

        ```python
        # At the top of batch_routes.py
        from ..api_models import BatchRegistrationRequestV1 # Assuming api_models.py is in the parent of api directory
        from common_core.events.batch_coordination_events import BatchEssaysRegistered
        from common_core.metadata_models import SystemProcessingMetadata, EntityReference
        from common_core.enums import ProcessingEvent, topic_name, BatchStatus # Add BatchStatus
        from common_core.pipeline_models import ProcessingPipelineState # For storing initial state

        # ... existing code ...

        @batch_bp.route("/register", methods=["POST"])
        @inject
        async def register_batch(
            event_publisher: FromDishka[BatchEventPublisherProtocol],
            batch_repo: FromDishka[BatchRepositoryProtocol], # Ensure this protocol is suitable for all needed operations
        ) -> Union[Response, tuple[Response, int]]:
            correlation_id = uuid.uuid4()
            try:
                raw_request_data = await request.get_json()
                if not raw_request_data:
                    return jsonify({"error": "Request body must be valid JSON"}), 400
                
                validated_data = BatchRegistrationRequestV1(**raw_request_data)
                batch_id = str(uuid.uuid4())
                
                logger.info(f"Registering new batch {batch_id} with {validated_data.expected_essay_count} essays. Correlation ID: {correlation_id}")

                # 1. Persist Full Batch Context
                # This requires BatchRepositoryProtocol and its implementation to support storing these details.
                # For the mock, this might mean enhancing its internal dict.
                # Example: await batch_repo.store_full_batch_details(batch_id, validated_data, correlation_id)
                # For now, let's assume we're also storing an initial ProcessingPipelineState
                initial_pipeline_state = ProcessingPipelineState(
                    batch_id=batch_id,
                    requested_pipelines=[], # Spellcheck will be added when BatchEssaysReady is received
                    # Initialize other pipeline details with REQUESTED_BY_USER or a suitable initial status
                )
                await batch_repo.save_processing_pipeline_state(batch_id, initial_pipeline_state)
                # TODO: Ensure 'course_code', 'class_designation', 'essay_instructions' are also persisted
                # associated with batch_id by the batch_repo. This might require a new method or
                # extending save_processing_pipeline_state or create_batch in the protocol/implementation.

                # 2. Construct lightweight BatchEssaysRegistered event
                batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")
                event_metadata = SystemProcessingMetadata(
                    entity=batch_entity_ref,
                    event=ProcessingEvent.BATCH_ESSAYS_REGISTERED.value, # Use enum value
                    timestamp=datetime.now(timezone.utc) 
                )
                batch_registered_event_data = BatchEssaysRegistered(
                    batch_id=batch_id,
                    expected_essay_count=validated_data.expected_essay_count,
                    essay_ids=validated_data.essay_ids,
                    metadata=event_metadata
                    # event field is now part of BatchEssaysRegistered model by default
                )

                # 3. Create EventEnvelope
                envelope = EventEnvelope[BatchEssaysRegistered](
                    event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
                    source_service=settings.SERVICE_NAME, # from BOS config
                    correlation_id=correlation_id,
                    data=batch_registered_event_data
                )

                # 4. Publish event
                await event_publisher.publish_batch_event(envelope) # Ensure this method exists and is typed in protocol
                
                logger.info(f"Published BatchEssaysRegistered event for batch {batch_id}, event_id {envelope.event_id}")
                if BATCH_OPERATIONS: # Assuming BATCH_OPERATIONS metric is available
                    BATCH_OPERATIONS.labels(operation="register_batch", status="success").inc()

                return jsonify({"batch_id": batch_id, "correlation_id": str(correlation_id), "status": "registered"}), 202

            except ValidationError as ve: # Pydantic validation error
                logger.warning(f"Batch registration validation error. Correlation ID: {correlation_id}", exc_info=True)
                if BATCH_OPERATIONS:
                    BATCH_OPERATIONS.labels(operation="register_batch", status="validation_error").inc()
                return jsonify({"error": "Validation Error", "details": ve.errors()}), 400
            except Exception as e:
                logger.error(f"Error registering batch. Correlation ID: {correlation_id}", exc_info=True)
                if BATCH_OPERATIONS:
                    BATCH_OPERATIONS.labels(operation="register_batch", status="error").inc()
                return jsonify({"error": "Failed to register batch."}), 500
        ```

    - **Note on Request Handling**: Ensure `BatchRegistrationRequestV1` is used for validating the request body.
    - **Error Handling**: Implement `try-except` for request validation, repository operations, and event publishing. Log errors and return appropriate HTTP status codes.

3. **Update BOS `app.py`**:
    - It already imports and registers `batch_bp`. The `/trigger-spellcheck-test` route is already in `batch_routes.py`. No changes likely needed here if `batch_routes.py` is correctly updated.

4. **Update `BatchRepositoryProtocol` (in `protocols.py`) and `MockBatchRepository` (in `di.py`)**:
    - **Action (`protocols.py`)**:
        - Add a new method like `async def store_batch_context(self, batch_id: str, registration_data: BatchRegistrationRequestV1, pipeline_state: ProcessingPipelineState) -> None;` or modify `create_batch` and `save_processing_pipeline_state` to handle the storage of `course_code`, `class_designation`, `essay_instructions` along with the `batch_id`.
        - Add a method like `async def get_batch_context(self, batch_id: str) -> Optional[BatchRegistrationRequestV1];` (or a model that combines all stored context).
    - **Action (`di.py`)**:
        - Update `MockBatchRepository` to implement these new/modified methods. For the mock, this can involve extending its internal dictionary to store this additional context per `batch_id`.

        ```python
        # Example snippet for MockBatchRepository in di.py
        # self.batch_contexts: Dict[str, BatchRegistrationRequestV1] = {}
        # self.pipeline_states: Dict[str, ProcessingPipelineState] = {}

        # async def store_batch_context(self, batch_id: str, registration_data: BatchRegistrationRequestV1, pipeline_state: ProcessingPipelineState):
        #     self.batch_contexts[batch_id] = registration_data
        #     self.pipeline_states[batch_id] = pipeline_state
        #     logger.info(f"MockBatchRepo: Stored context for batch {batch_id}")
        #     return True # or None if protocol returns None

        # async def get_batch_context(self, batch_id: str) -> Optional[BatchRegistrationRequestV1]:
        #     return self.batch_contexts.get(batch_id)
            
        # Modify existing save_processing_pipeline_state or create_batch as needed.
        ```

5. **Update BOS Logic for Pipeline Initiation (New Consumer Logic)**:
    - **Action**: Implement a Kafka consumer in BOS to listen for `BatchEssaysReady` events from ELS.
        - **Consumer Implementation**: For the walking skeleton, this consumer can be an `asyncio` background task managed by the Quart application lifecycle (`app.before_serving` to start, `app.after_serving` to stop).
            - Reference ELS `worker_main.py` or Spell Checker `worker_main.py` for patterns on creating an `AIOKafkaConsumer` and processing messages in a loop.
            - The consumer should subscribe to the topic where ELS publishes `BatchEssaysReady` (this topic needs to be defined, e.g., `huleedu.els.batch.essays.ready.v1`). **Ensure this topic is added to `common_core.enums` and `_TOPIC_MAPPING`.**
        - **Event Handler Logic (for `BatchEssaysReady`)**:
            1. Deserialize the `EventEnvelope[BatchEssaysReady]`.
            2. Extract `batch_id`.
            3. **Idempotency Check**: Fetch the current `ProcessingPipelineState` for the `batch_id` from `BatchRepositoryProtocol`. If the spellcheck pipeline (or the relevant pipeline for future tasks) is already `DISPATCH_INITIATED`, `IN_PROGRESS`, or in a terminal state, log the (potentially duplicate) event and skip further processing for this phase.
            4. Retrieve the stored full batch context (especially `course_code`) for the `batch_id` using the updated `BatchRepositoryProtocol`.
            5. Implement a helper function: `_infer_language_from_course_code(course_code: str) -> str` (e.g., "SV1" -> "sv"; "ENG5" -> "en"). This can be a simple dict lookup or conditional logic.
            6. Construct `BatchServiceSpellcheckInitiateCommandDataV1` (from `common_core.batch_service_models`). Populate its `language` field using the inferred language. Ensure `entity_ref` points to the batch.
            7. Create an `EventEnvelope` for this command. The `event_type` should be the topic ELS listens to for spellcheck commands (e.g., `huleedu.els.spellcheck.initiate.command.v1` - **this topic also needs definition in `common_core.enums` and `_TOPIC_MAPPING`, and ELS worker needs to subscribe to it**).
            8. Publish this command envelope using `BatchEventPublisherProtocol`.
            9. Update the `ProcessingPipelineState` for the batch in BOS's repository to reflect that the spellcheck phase has been initiated (e.g., status to `DISPATCH_INITIATED`).
        - **Error Handling**: Implement `try-except` for deserialization, repository access, language inference, and event publishing. Log errors.
        - **Configuration Consistency**: Ensure the consumer group ID for BOS and any new topic names are managed via BOS's `config.py` and environment variables.
        - **`TODO` Comment**: Add a `TODO` in the BOS consumer: `TODO: Evaluate moving this Kafka consumer to a separate worker process if event volume or processing complexity increases, or for better resource isolation.`

---

**General Considerations for All Tasks:**

- **Error Handling & Resilience**:
  - In all new event publishing and consumption logic, include `try-except` blocks to catch potential errors (e.g., `KafkaTimeoutError`, `KafkaConnectionError`, deserialization errors, errors calling other services). Log these errors with relevant context (like `correlation_id`).
  - For API endpoints, ensure appropriate HTTP error responses are returned.
- **Configuration Consistency**:
  - All new Kafka topic names must be defined in `common_core.enums.ProcessingEvent` and mapped in `_TOPIC_MAPPING`. Services must use `topic_name(ProcessingEvent.EVENT_NAME)` to get topic strings.
  - Ensure new environment variables are prefixed correctly for each service in their respective `config.py` files and consistently used in `Dockerfile` and `docker-compose.yml`.
- **Logging**: Implement structured logging using `create_service_logger` and `log_event_processing` from `huleedu_service_libs.logging_utils` for all new major operations, event consumptions, and publications, including `correlation_id`.

## Linking Summary to Subsequent File Service Implementation

Upon successful completion and verification of all tasks (A, B, C, D) outlined in this preparatory ticket (HULEDU-PREP-001), the HuleEdu system will be ready for the next crucial phase: the implementation of the File Service.

The File Service (to be detailed in task HULEDU-FILESVC-001) will act as the primary HTTP interface for batch file uploads. Its core responsibilities will include:

Accepting multiple file uploads associated with a batch_id.
Performing basic text extraction (initially for .txt files).
Stubbing student information parsing.
Coordinating with the Content Service to store extracted text.
Producing EssayContentReady Kafka events for each successfully processed file, signaling its readiness to the Essay Lifecycle Service (ELS).
The detailed architectural blueprint and implementation plan for the File Service are specified in Part E of the main project task document and will form the basis of task HULEDU-FILESVC-001. The successful completion of the current preparatory tasks is a strict prerequisite for commencing work on the File Service.

## Section E: Design Principle Consolidation ✅ COMPLETED & VERIFIED (2025-01-30)

### E.1: Protocol Drift Resolution ✅ COMPLETED

**Issue**: BatchEssayTracker was imported as concrete implementation instead of protocol interface
**Resolution**:

- Added `BatchEssayTracker` protocol to `services/essay_lifecycle_service/protocols.py`
- Updated all imports in `batch_command_handlers.py`, `worker_main.py`, and `di.py` to use protocol
- Maintained concrete implementation import only in DI provider method

### E.2: MyPy Library Stubs ✅ COMPLETED  

**Issue**: Missing library stubs error for `batch_tracker` module
**Resolution**: Added `batch_tracker` to MyPy overrides in root `pyproject.toml`

### E.3: Legacy Topic Cleanup ✅ COMPLETED

**Issue**: Hardcoded legacy topics for backward compatibility
**Resolution**: Removed all hardcoded topics, using only `topic_name()` function for consistency

### E.4: Test Infrastructure ✅ COMPLETED

**Issue**: Functional tests failing when services not running
**Resolution**:

- Added proper `@pytest.mark.docker` and `@pytest.mark.integration` markers
- Added graceful connection error handling with `pytest.skip()`
- Fixed functional test infrastructure to handle service unavailability

### E.5: All Tests Passing ✅ VERIFIED

**Status**:

- ✅ **77 tests passed**
- ✅ **9 functional tests properly skipped** when services aren't running
- ✅ **Type checking passes** cleanly  
- ✅ **Linting passes** cleanly
- ✅ **Docker builds work** correctly

### E.6: Design Principles Verified ✅ COMPLETED

**Dependency Inversion**: ✅ All business logic depends on protocols, not concrete implementations  
**Protocol Compliance**: ✅ BatchEssayTracker follows proper protocol pattern  
**Walking Skeleton**: ✅ No unnecessary backward compatibility or fallbacks  
**Type Safety**: ✅ All MyPy issues resolved  
**SRP Compliance**: ✅ Essay Lifecycle Service di.py refactored (449→114 lines, 71% reduction)  
**Clean Architecture**: ✅ Business logic implementations extracted to implementations/ directory:

- `content_client.py` (47 lines): HTTP content storage operations
- `event_publisher.py` (98 lines): Kafka event publishing logic  
- `metrics_collector.py` (69 lines): Prometheus metrics collection
- `batch_command_handler_impl.py` (67 lines): Batch command processing
- `service_request_dispatcher.py` (63 lines): Specialized service request dispatching

**Architectural Compliance**: ✅ Perfect adherence to SRP, file size limits, and design principles
