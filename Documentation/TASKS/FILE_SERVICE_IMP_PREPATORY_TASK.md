# Task Ticket: Implement Batch Coordination Walking Skeleton (Common Core, ELS & BOS Updates - Preparatory Phase)

Ticket ID: HULEDU-PREP-001
Assignee: Junior Developer Team
Reporter: System Architect
Priority: Critical

**Goal**:
Implement the foundational **preparatory steps** for the batch processing coordination "Walking Skeleton." This involves critical updates to `common_core`, substantial changes to the Essay Lifecycle Service (ELS) including its containerization, and modifications to the Batch Orchestrator Service (BOS) to enable an end-to-end event flow. This phase ensures these components are ready *before* the File Service is implemented. The initial pipeline focus remains spellcheck-only.

**Context/Background**:
This implementation follows the agreed-upon architectural vision, which refines the "Batch Coordination Implementation Roadmap" and PRD. The core principle is event-driven communication with clear service responsibilities.

**Key Architectural Decisions to Adhere To (for these preparatory steps)**:

* **Overall Event Flow (relevant to these parts)**:
    1. **Client** → **BOS API** (new endpoint): Registers a batch, providing `course_code`, `class_designation`, `essay_instructions`, `expected_essay_count`, `essay_ids`.
    2. **BOS** stores this full context and emits a *lightweight* `BatchEssaysRegistered` event (NO `course_code`, etc.) to ELS.
    3. (File Service will later emit `EssayContentReady` to ELS).
    4. **ELS** consumes `BatchEssaysRegistered` (and later `EssayContentReady`) for readiness aggregation.
    5. **ELS** → **BOS**: Emits `BatchEssaysReady` when a batch is complete.
    6. **BOS** → **ELS**: Sends pipeline commands (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`) which **now include the necessary processing context** like `language` (inferred by BOS from its stored `course_code`).
* **ELS Containerization**: ELS will run as two separate processes/services (API and Worker) in Docker Compose using the same Docker image.
* **BOS API Request Models**: Pydantic models for BOS API request bodies will be local to the BOS service.
* **`course_code` Propagation**: Handled via BOS storing it and then passing `language` (inferred from `course_code`) in commands to ELS.
* **Adherence to Rules**: All implementations must follow existing project rules regarding DI, protocols, Pydantic settings, logging, file sizes (LoC < 400, line length <= 100), and project structure.

## Implementation Tasks (Preparatory Phase)

### A. Common Core Changes (`common_core/`)

1. **Update Enums (`src/common_core/enums.py`)**:
    * In the `ProcessingEvent` enum, add the following members:
        * `BATCH_ESSAYS_REGISTERED = "batch.essays.registered"`
        * `ESSAY_CONTENT_READY = "essay.content.ready"`
    * In the `_TOPIC_MAPPING` dictionary, add the following explicit mappings for the new events:
        * `ProcessingEvent.BATCH_ESSAYS_REGISTERED: "huleedu.batch.essays.registered.v1"`
        * `ProcessingEvent.ESSAY_CONTENT_READY: "huleedu.file.essay.content.ready.v1"`
    * **Verification**: After these changes, the `kafka_topic_bootstrap.py` script should be able to create these new topics by design, as it iterates over `_TOPIC_MAPPING`.

2. **Update Event Models (`src/common_core/events/batch_coordination_events.py`)**:
    * **`BatchEssaysRegistered`**:
        * **Action**: Verify the existing model is lightweight and strictly contains only `batch_id: str`, `expected_essay_count: int`, `essay_ids: list[str]`, `event: str` (defaulted), and `metadata: SystemProcessingMetadata`.
        * **Crucial**: Ensure no business-specific context like `course_code` is added here; this context remains within BOS's domain.
    * **`EssayContentReady`**:
        * **Action**: Confirm the existing model includes all necessary fields: `event: str` (defaulted), `essay_id: str`, `batch_id: str`, `content_storage_reference: StorageReferenceMetadata`, `entity: EntityReference`, `metadata: SystemProcessingMetadata`.
        * **Action**: Confirm it also includes the optional, stubbed student information fields as specified:

            ```python
            student_name: Optional[str] = Field(default=None, description="Parsed student name, if available (stubbed for walking skeleton)")
            student_email: Optional[str] = Field(default=None, description="Parsed student email, if available (stubbed for walking skeleton)")
            ```

        * Ensure `Field` from `pydantic` is correctly imported and used.

3. **Update `src/common_core/__init__.py`**:
    * **Action**: Add any new or newly confirmed Pydantic models from `batch_coordination_events.py` (i.e., `BatchEssaysRegistered`, `EssayContentReady`, and `BatchReadinessTimeout` if it's confirmed as used/new for this phase) to the `__all__` list for proper export.
    * **Action**: Add `model_rebuild(raise_errors=True)` calls at the end of the file for these models to ensure forward references are correctly resolved. For example:

        ```python
        # common_core/src/common_core/__init__.py
        # ... existing imports and __all__ ...
        from .events.batch_coordination_events import ( # Ensure these are imported
            BatchEssaysRegistered,
            EssayContentReady,
            BatchEssaysReady, # Already present
            BatchReadinessTimeout
        )

        # ... existing model_rebuild calls ...
        BatchEssaysRegistered.model_rebuild(raise_errors=True)
        EssayContentReady.model_rebuild(raise_errors=True)
        BatchReadinessTimeout.model_rebuild(raise_errors=True) # If confirmed new/used
        ```

---

### B. Kafka Topic Bootstrap Script (`scripts/kafka_topic_bootstrap.py`)

1. **Verification**:
    * No direct code changes should be needed in `kafka_topic_bootstrap.py` itself, as its logic to discover topics from `common_core.enums._TOPIC_MAPPING` is generic.
2. **Test (Post `common_core` update)**:
    * **Action**: Run the `kafka_topic_bootstrap.py` script (either locally via `pdm run kafka-setup-topics` or observe its execution when `docker-compose up` is run).
    * **Expected**: The script should now attempt to create the new topics: `huleedu.batch.essays.registered.v1` and `huleedu.file.essay.content.ready.v1`. Verify its logs for success or "topic already exists" messages.

---

### C. ELS Containerization & Updates (`services/essay_lifecycle_service/`)

1. **Review and Update `Dockerfile`** (`services/essay_lifecycle_service/Dockerfile`):
    * **Action**: Confirm the existing Dockerfile adheres to project patterns (Python 3.11-slim, PDM global install, correct copying of `common_core`, `services/libs`, and ELS service code, `pdm install --prod`, non-root `appuser`).
    * **Action**: Add `settings.PROMETHEUS_PORT` (which is 9090) to the `EXPOSE` instruction alongside the existing `HTTP_PORT`. Example: `EXPOSE ${HTTP_PORT} ${PROMETHEUS_PORT_ENV_VAR}` (ensure you define `PROMETHEUS_PORT_ENV_VAR` in the ENV section or use the direct value). The ELS `config.py` defines `PROMETHEUS_PORT: int = 9090`.
    * The default `CMD ["pdm", "run", "start"]` is suitable for the API service. The worker will use a command override in Docker Compose.

2. **Update `docker-compose.yml`**:
    * **Action**: Remove the existing single `essay_lifecycle_service` entry.
    * **Action**: Add two new service definitions for ELS:
        * `essay_lifecycle_api`:
            * `build`: Context `.` and Dockerfile `services/essay_lifecycle_service/Dockerfile`.
            * `container_name: huleedu_essay_lifecycle_api`.
            * `command: ["pdm", "run", "start"]` (This PDM script should execute `python app.py` or `hypercorn app:app ...` as defined in ELS `pyproject.toml`).
            * `ports`: Map a host port (e.g., `6001`) to container `ESSAY_LIFECYCLE_SERVICE_HTTP_PORT` (e.g., `6000`). Map a host port (e.g., `9091`) to container `ESSAY_LIFECYCLE_SERVICE_PROMETHEUS_PORT` (e.g., `9090`).
            * `environment`:
                * `ESSAY_LIFECYCLE_SERVICE_HTTP_PORT=6000` (or the port `app.py` listens on).
                * `ESSAY_LIFECYCLE_SERVICE_PROMETHEUS_PORT=9090`.
                * Other necessary env vars like `KAFKA_BOOTSTRAP_SERVERS`, `CONTENT_SERVICE_URL`, `DATABASE_PATH` (ensure this path is appropriate for a container, possibly a volume).
            * `depends_on`: `kafka_topic_setup: condition: service_completed_successfully`, `content_service: condition: service_started`.
        * `essay_lifecycle_worker`:
            * `build`: Same as `essay_lifecycle_api`.
            * `container_name: huleedu_essay_lifecycle_worker`.
            * `command: ["pdm", "run", "start_worker"]` (This PDM script executes `python worker_main.py`).
            * `ports`: No ports need to be exposed for the worker unless it has a specific metrics endpoint different from the API (the task ticket implies one metrics port for ELS, likely served by the API).
            * `environment`: Necessary env vars like `KAFKA_BOOTSTRAP_SERVERS`, `CONTENT_SERVICE_URL`, `DATABASE_PATH`.
            * `depends_on`: `kafka_topic_setup: condition: service_completed_successfully`, `content_service: condition: service_started`.
    * **Action**: Update `batch_orchestrator_service` `depends_on` to include `essay_lifecycle_api: condition: service_started`. (Worker dependency is less common for an API-first interaction but consider if BOS immediately needs the ELS worker operational).

3. **Update ELS Kafka Consumer (`services/essay_lifecycle_service/worker_main.py`)**:
    * **Action**: In the `kafka_consumer_context` function (or wherever `AIOKafkaConsumer` is initialized), add the following topics to the subscription list by resolving them with `topic_name()` from `common_core.enums`:
        * `topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED)`
        * `topic_name(ProcessingEvent.ESSAY_CONTENT_READY)`
    * **Configuration Consistency**: Ensure topic names are not hardcoded but derived using `common_core.enums.topic_name()`.

4. **Update ELS Event Routing (e.g., `services/essay_lifecycle_service/batch_command_handlers.py` or logic within `worker_main.py`)**:
    * **Action**: Modify the event deserialization and routing logic (e.g., in `_deserialize_message` and `_route_event` within `batch_command_handlers.py`) to handle the new event types.
    * If `envelope.event_type == topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED)`:
        * Deserialize `envelope.data` into `common_core.events.batch_coordination_events.BatchEssaysRegistered`.
        * Route the deserialized event data to `BatchEssayTracker.register_batch()`. Ensure `BatchEssayTracker` instance is correctly injected/accessed.
    * If `envelope.event_type == topic_name(ProcessingEvent.ESSAY_CONTENT_READY)`:
        * Deserialize `envelope.data` into `common_core.events.batch_coordination_events.EssayContentReady`.
        * Route the deserialized event data to `BatchEssayTracker.mark_essay_ready()`.
        * Log any received `student_name` / `student_email` from the event data.
        * **Idempotency**: When this event potentially triggers an update to the main `EssayState` (e.g., in `SQLiteEssayStateStore` to `READY_FOR_PROCESSING`), ensure this state update is idempotent. The logic should:
            1. Fetch the current `EssayState`.
            2. Use `StateTransitionValidator` to check if the transition from the *current* status to `READY_FOR_PROCESSING` (or other relevant status) is valid.
            3. Only apply the update if valid. Log skipped updates for duplicate/stale events that don't result in a valid state change.
    * **Error Handling**: Implement `try-except` blocks around deserialization and event processing logic. Log errors clearly, including correlation IDs and event details. Decide on a strategy for messages that fail deserialization (e.g., log and skip, or move to a DLQ if configured).

---

### D. Batch Orchestrator Service (BOS) Modifications (`services/batch_orchestrator_service/`)

1. **Create API Request Model (`services/batch_orchestrator_service/api_models.py`)**:
    * **Action**: Create this new file.
    * **Action**: Define `BatchRegistrationRequestV1(BaseModel)` with fields: `expected_essay_count: int`, `essay_ids: List[str]`, `course_code: str`, `class_designation: str`, `essay_instructions: str`. Use `pydantic.Field` for descriptions.

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
    * **Action**: Implement the `POST /register` endpoint within the existing `batch_bp`.

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

    * **Note on Request Handling**: Ensure `BatchRegistrationRequestV1` is used for validating the request body.
    * **Error Handling**: Implement `try-except` for request validation, repository operations, and event publishing. Log errors and return appropriate HTTP status codes.

3. **Update BOS `app.py`**:
    * It already imports and registers `batch_bp`. The `/trigger-spellcheck-test` route is already in `batch_routes.py`. No changes likely needed here if `batch_routes.py` is correctly updated.

4. **Update `BatchRepositoryProtocol` (in `protocols.py`) and `MockBatchRepository` (in `di.py`)**:
    * **Action (`protocols.py`)**:
        * Add a new method like `async def store_batch_context(self, batch_id: str, registration_data: BatchRegistrationRequestV1, pipeline_state: ProcessingPipelineState) -> None;` or modify `create_batch` and `save_processing_pipeline_state` to handle the storage of `course_code`, `class_designation`, `essay_instructions` along with the `batch_id`.
        * Add a method like `async def get_batch_context(self, batch_id: str) -> Optional[BatchRegistrationRequestV1];` (or a model that combines all stored context).
    * **Action (`di.py`)**:
        * Update `MockBatchRepository` to implement these new/modified methods. For the mock, this can involve extending its internal dictionary to store this additional context per `batch_id`.

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
    * **Action**: Implement a Kafka consumer in BOS to listen for `BatchEssaysReady` events from ELS.
        * **Consumer Implementation**: For the walking skeleton, this consumer can be an `asyncio` background task managed by the Quart application lifecycle (`app.before_serving` to start, `app.after_serving` to stop).
            * Reference ELS `worker_main.py` or Spell Checker `worker_main.py` for patterns on creating an `AIOKafkaConsumer` and processing messages in a loop.
            * The consumer should subscribe to the topic where ELS publishes `BatchEssaysReady` (this topic needs to be defined, e.g., `huleedu.els.batch.essays.ready.v1`). **Ensure this topic is added to `common_core.enums` and `_TOPIC_MAPPING`.**
        * **Event Handler Logic (for `BatchEssaysReady`)**:
            1. Deserialize the `EventEnvelope[BatchEssaysReady]`.
            2. Extract `batch_id`.
            3. **Idempotency Check**: Fetch the current `ProcessingPipelineState` for the `batch_id` from `BatchRepositoryProtocol`. If the spellcheck pipeline (or the relevant pipeline for future tasks) is already `DISPATCH_INITIATED`, `IN_PROGRESS`, or in a terminal state, log the (potentially duplicate) event and skip further processing for this phase.
            4. Retrieve the stored full batch context (especially `course_code`) for the `batch_id` using the updated `BatchRepositoryProtocol`.
            5. Implement a helper function: `_infer_language_from_course_code(course_code: str) -> str` (e.g., "SV1" -> "sv"; "ENG5" -> "en"). This can be a simple dict lookup or conditional logic.
            6. Construct `BatchServiceSpellcheckInitiateCommandDataV1` (from `common_core.batch_service_models`). Populate its `language` field using the inferred language. Ensure `entity_ref` points to the batch.
            7. Create an `EventEnvelope` for this command. The `event_type` should be the topic ELS listens to for spellcheck commands (e.g., `huleedu.els.spellcheck.initiate.command.v1` - **this topic also needs definition in `common_core.enums` and `_TOPIC_MAPPING`, and ELS worker needs to subscribe to it**).
            8. Publish this command envelope using `BatchEventPublisherProtocol`.
            9. Update the `ProcessingPipelineState` for the batch in BOS's repository to reflect that the spellcheck phase has been initiated (e.g., status to `DISPATCH_INITIATED`).
        * **Error Handling**: Implement `try-except` for deserialization, repository access, language inference, and event publishing. Log errors.
        * **Configuration Consistency**: Ensure the consumer group ID for BOS and any new topic names are managed via BOS's `config.py` and environment variables.
        * **`TODO` Comment**: Add a `TODO` in the BOS consumer: `TODO: Evaluate moving this Kafka consumer to a separate worker process if event volume or processing complexity increases, or for better resource isolation.`

---

**General Considerations for All Tasks:**

* **Error Handling & Resilience**:
  * In all new event publishing and consumption logic, include `try-except` blocks to catch potential errors (e.g., `KafkaTimeoutError`, `KafkaConnectionError`, deserialization errors, errors calling other services). Log these errors with relevant context (like `correlation_id`).
  * For API endpoints, ensure appropriate HTTP error responses are returned.
* **Configuration Consistency**:
  * All new Kafka topic names must be defined in `common_core.enums.ProcessingEvent` and mapped in `_TOPIC_MAPPING`. Services must use `topic_name(ProcessingEvent.EVENT_NAME)` to get topic strings.
  * Ensure new environment variables are prefixed correctly for each service in their respective `config.py` files and consistently used in `Dockerfile` and `docker-compose.yml`.
* **Logging**: Implement structured logging using `create_service_logger` and `log_event_processing` from `huleedu_service_libs.logging_utils` for all new major operations, event consumptions, and publications, including `correlation_id`.

## Linking Summary to Subsequent File Service Implementation

Upon successful completion and verification of all tasks (A, B, C, D) outlined in this preparatory ticket (HULEDU-PREP-001), the HuleEdu system will be ready for the next crucial phase: the implementation of the File Service.

The File Service (to be detailed in task HULEDU-FILESVC-001) will act as the primary HTTP interface for batch file uploads. Its core responsibilities will include:

Accepting multiple file uploads associated with a batch_id.
Performing basic text extraction (initially for .txt files).
Stubbing student information parsing.
Coordinating with the Content Service to store extracted text.
Producing EssayContentReady Kafka events for each successfully processed file, signaling its readiness to the Essay Lifecycle Service (ELS).
The detailed architectural blueprint and implementation plan for the File Service are specified in Part E of the main project task document and will form the basis of task HULEDU-FILESVC-001. The successful completion of the current preparatory tasks is a strict prerequisite for commencing work on the File Service.
