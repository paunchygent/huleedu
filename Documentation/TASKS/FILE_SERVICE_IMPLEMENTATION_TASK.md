Okay, this is a great, focused approach! Here's a comprehensive task ticket designed for a junior developer, incorporating the architectural decisions we've made. It aims to be explicit about implementation details where necessary, guiding them while leveraging their existing knowledge.

## Task Ticket: Implement Batch Coordination Walking Skeleton (File Service, BOS & ELS Updates)

**Goal**:
Implement the foundational "Walking Skeleton" for batch processing coordination. This involves creating a new File Service, modifying the Batch Orchestrator Service (BOS) and Essay Lifecycle Service (ELS) to enable an end-to-end flow where batches are registered, files are uploaded and processed, and ELS signals batch readiness to BOS, all using our event-driven architecture. The initial pipeline will be spellcheck-only.

**Context/Background**:
This implementation follows the agreed-upon architectural vision, which refines the "Batch Coordination Implementation Roadmap" and PRD. The core principle is event-driven communication with clear service responsibilities.

**Key Architectural Decisions to Adhere To**:

* **Overall Event Flow**:
    1. **Client** → **BOS API** (new endpoint): Registers a batch, providing `course_code`, `class_designation`, `essay_instructions`, `expected_essay_count`, `essay_ids`.
    2. **BOS** stores this full context and emits a *lightweight* `BatchEssaysRegistered` event (NO `course_code`, etc. (bounded to BOS SRP)) to ELS.
    3. **Client** → **File Service API**: Uploads files for the `batch_id`.
    4. **File Service** processes each file, stores content (via Content Service), (stubs student info parsing), and emits `EssayContentReady` (with `essay_id`, `batch_id`, `storage_id`, and optional stubbed `student_name`/`student_email`) to ELS.
    5. **ELS** consumes `BatchEssaysRegistered` and `EssayContentReady` for readiness aggregation.
    6. **ELS** → **BOS**: Emits `BatchEssaysReady` when a batch is complete.
    7. **BOS** → **ELS**: Sends pipeline commands (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`) which **now include the necessary processing context** like `language` (inferred by BOS from its stored `course_code`).
* **ELS Containerization**: ELS will run as two separate processes/services in Docker Compose (API and Worker) using the same Docker image.
* **BOS API Request Models**: Pydantic models for BOS API request bodies will be local to the BOS service (not in `common_core`).
* **File Service**: Will be an HTTP service that produces Kafka events. No Kafka consumer is needed for the walking skeleton.
* **`course_code` Propagation**: Handled via BOS storing it and then passing `language` (inferred from `course_code`) in commands to ELS.
* **Student Info Parsing (File Service)**: This is a future feature. For the walking skeleton, implement a stub that returns `None` for `student_name` and `student_email`.
* **Adherence to Rules**: All implementations must follow existing project rules regarding DI, protocols, Pydantic settings, logging, file sizes (LoC < 400, line length <= 100), and project structure.

---

## Implementation Tasks

### A. Common Core Changes (`common_core/`)

1. **Update Enums (`src/common_core/enums.py`)**:
    * Add `BATCH_ESSAYS_REGISTERED = "batch.essays.registered"` to the `ProcessingEvent` enum.
    * Add `ESSAY_CONTENT_READY = "essay.content.ready"` to the `ProcessingEvent` enum (confirm it doesn't already exist with a different name/purpose).
    * In `_TOPIC_MAPPING`, add:
        * `ProcessingEvent.BATCH_ESSAYS_REGISTERED: "huleedu.batch.essays.registered.v1"`
        * `ProcessingEvent.ESSAY_CONTENT_READY: "huleedu.file.essay.content.ready.v1"`
    * **Action**: Verify these additions allow `kafka_topic_bootstrap.py` to create these topics.

2. **Update Event Models (`src/common_core/events/batch_coordination_events.py`)**:
    * **`BatchEssaysRegistered`**: Confirm this model remains lightweight. It should *only* contain `batch_id: str`, `expected_essay_count: int`, `essay_ids: list[str]`, and `metadata: SystemProcessingMetadata`. Do **not** add `course_code` etc., here.
    * **`EssayContentReady`**: Modify this model to include the optional, stubbed student information:

        ```python
        from typing import Optional
        from pydantic import BaseModel, Field # Ensure Field is imported
        # ... other imports from the file
        
        class EssayContentReady(BaseModel): # Or ensure it inherits from a suitable base like BaseEventData
            # ... existing fields: essay_id, batch_id, content_storage_reference, entity, metadata ...
            # Ensure these existing fields are present and correctly typed.
            # For example, it should have:
            # event: str = Field(default="essay.content.ready", description="Event type identifier")
            # essay_id: str
            # batch_id: str
            # content_storage_reference: StorageReferenceMetadata # from common_core.metadata_models
            # entity: EntityReference # from common_core.metadata_models
            # metadata: SystemProcessingMetadata # from common_core.metadata_models
            
            student_name: Optional[str] = Field(default=None, description="Parsed student name, if available (stubbed for walking skeleton)")
            student_email: Optional[str] = Field(default=None, description="Parsed student email, if available (stubbed for walking skeleton)")
        ```

3. **Update `src/common_core/__init__.py`**:
    * Ensure any new or modified enums and Pydantic models (like the updated `EssayContentReady`) are added to `__all__`.
    * Add `model_rebuild()` calls for any new/modified Pydantic models that have forward references resolved within this file.

---

### B. Kafka Topic Bootstrap Script (`scripts/kafka_topic_bootstrap.py`)

1. **Verification**: No direct code changes should be needed in `kafka_topic_bootstrap.py` *if* it correctly iterates over `_TOPIC_MAPPING` from `common_core.enums`.
2. **Test**: After `common_core` changes, run this script locally (or via Docker Compose) to ensure the new topics (`huleedu.batch.essays.registered.v1` and `huleedu.file.essay.content.ready.v1`) are created in Kafka.

---

### C. ELS Containerization & Updates (`services/essay_lifecycle_service/`)

1. **Create `Dockerfile`**:
    * Path: `services/essay_lifecycle_service/Dockerfile`
    * Follow the structure of existing Dockerfiles (e.g., `services/content_service/Dockerfile` or `services/batch_orchestrator_service/Dockerfile`).
    * Key steps: `python:3.11-slim` base, install PDM, copy `common_core` & `services/libs`, copy ELS service code, `pdm install --prod`, create non-root `appuser`, `EXPOSE` ports defined in `settings.HTTP_PORT` (6000) and `settings.PROMETHEUS_PORT` (9090).
    * The `CMD` should be flexible or you will define it in `docker-compose.yml`.

2. **Update `docker-compose.yml`**:
    * Remove the single existing `essay_lifecycle_service` entry.
    * Add two new service definitions:
        * `essay_lifecycle_api`:
            * Uses the ELS Dockerfile.
            * `container_name: huleedu_essay_lifecycle_api`.
            * `command: ["pdm", "run", "start"]` (to run `app.py` via PDM script defined in ELS `pyproject.toml`).
            * Ports: Map host port (e.g., 6001) to container port `settings.HTTP_PORT` (6000) and host port (e.g., 9091) to container `settings.PROMETHEUS_PORT` (9090).
            * Environment: Set necessary ELS env vars, e.g., `ESSAY_LIFECYCLE_SERVICE_HTTP_PORT`, `KAFKA_BOOTSTRAP_SERVERS`.
            * `depends_on: [kafka_topic_setup, content_service]`.
        * `essay_lifecycle_worker`:
            * Uses the same ELS Dockerfile.
            * `container_name: huleedu_essay_lifecycle_worker`.
            * `command: ["pdm", "run", "start_worker"]` (to run `worker_main.py` via PDM script).
            * Environment: Set necessary ELS env vars.
            * `depends_on: [kafka_topic_setup, content_service]`.
    * Update `batch_orchestrator_service` to `depend_on: [essay_lifecycle_api]` (and `essay_lifecycle_worker` if BOS needs worker to be up before it can function, though less likely).

3. **Update ELS Kafka Consumer (`worker_main.py`)**:
    * Add the new topic `topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED)` to the list of topics the `AIOKafkaConsumer` subscribes to.
    * (The existing ELS `worker_main.py` consumes `essay.upload.events`, etc. Ensure it is updated to consume topics relevant for batch coordination as per `batch_tracker.py` and PRD, like the one for `BatchEssaysRegistered` and `EssayContentReady`). **Correction**: ELS worker should listen for `BatchEssaysRegistered` (from BOS) and `EssayContentReady` (from File Service).

4. **Update ELS Event Routing (`batch_command_handlers.py` or equivalent logic called by worker)**:
    * Ensure that incoming `EventEnvelope[BatchEssaysRegistered]` messages are routed to `BatchEssayTracker.register_batch()`.
    * Ensure that incoming `EventEnvelope[EssayContentReady]` messages are routed to `BatchEssayTracker.mark_essay_ready()`.
    * When processing `EssayContentReady`, log any received `student_name` / `student_email` (for now, no further processing/storage of these in ELS for walking skeleton).

---

### D. Batch Orchestrator Service (BOS) Modifications (`services/batch_orchestrator_service/`)

1. **Create API Request Model (`api_models.py`)**:
    * Path: `services/batch_orchestrator_service/api_models.py`
    * Define `BatchRegistrationRequestV1(BaseModel)` with fields: `expected_essay_count: int`, `essay_ids: List[str]`, `course_code: str`, `class_designation: str`, `essay_instructions: str`. Use `pydantic.Field` for descriptions and validation if needed.

2. **Create API Route Module (`api/batch_routes.py`)**:
    * Path: `services/batch_orchestrator_service/api/batch_routes.py`
    * Define a `Blueprint`: `batch_bp = Blueprint('batch_routes', __name__, url_prefix='/v1/batches')`.
    * Implement the `POST /register` endpoint (`async def register_batch(...)`):
        * Use `@inject` for dependencies: validated `BatchRegistrationRequestV1` (see note below), `BatchEventPublisherProtocol`, `BatchRepositoryProtocol`.
        * **Request Handling**: Quart typically requires you to get JSON from `request.get_json()` and then validate with Pydantic, e.g., `validated_data = BatchRegistrationRequestV1(**await request.get_json())`.
        * **Logic**:
            1. Generate `batch_id` (UUID). Generate `correlation_id`.
            2. **Persist Full Batch Context**:
                * Use `BatchRepositoryProtocol.save_processing_pipeline_state()` to store an initial `ProcessingPipelineState` for the `batch_id`.
                * **Crucial**: Also persist `course_code`, `class_designation`, `essay_instructions` associated with this `batch_id`. Your `BatchRepositoryProtocol` and its mock/real implementation will need to support storing/retrieving this extended context. This might mean adding a method like `store_batch_registration_details(batch_id: str, details: BatchRegistrationRequestV1)` or enhancing existing methods. For the mock, you can extend its internal dictionary.
            3. Construct the **lightweight** `BatchEssaysRegistered` Pydantic model (from `common_core.events.batch_coordination_events`) using `batch_id`, `expected_essay_count`, `essay_ids` from the request, and `SystemProcessingMetadata`.
            4. Create an `EventEnvelope` for this `BatchEssaysRegistered` data. Set `event_type` to `topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED)`.
            5. Publish the envelope using `BatchEventPublisherProtocol.publish_batch_event()`.
            6. Return `202 Accepted` with `batch_id` and `correlation_id`.
        * Ensure proper logging and error handling.

3. **Update BOS `app.py`**:
    * Import and register `batch_bp` with the Quart app instance.
    * Move the existing `/v1/batches/trigger-spellcheck-test` endpoint to `batch_routes.py` as well, to keep `app.py` lean.

4. **Update `BatchRepositoryProtocol` (in `protocols.py`) and `MockBatchRepository` (in `di.py`)**:
    * Add methods or modify existing ones (like `create_batch` in the mock) to allow storing and retrieving the full batch registration context including `course_code`, `class_designation`, `essay_instructions` alongside the `batch_id` and `ProcessingPipelineState`.

5. **Update BOS Logic for Pipeline Initiation**:
    * When BOS consumes `BatchEssaysReady` from ELS (this consumption logic needs to be implemented in BOS, likely in a worker or an event handler if BOS has a consumer loop):
        1. It needs to retrieve the stored `course_code` for the given `batch_id` using its `BatchRepositoryProtocol`.
        2. Implement a helper function, e.g., `_infer_language_from_course_code(course_code: str) -> str` (e.g., "SV1"/"SV2"/"SV3" -> "sv"; "ENG5"/"ENG6"/"ENG7" -> "en").
        3. When BOS is ready to command ELS to start spellchecking for essays in the batch, it will construct `BatchServiceSpellcheckInitiateCommandDataV1` instances. Populate the `language` field in this command with the language inferred from `course_code`.
        4. Publish this command to ELS (this publishing mechanism to ELS for commands also needs to be clearly defined and implemented in BOS, likely via its `BatchEventPublisherProtocol` to a specific ELS command topic).

---

### E. File Service Implementation (Skeleton - `services/file_service/`)

1. **Create Service Directory and Core Files**:
    * `services/file_service/`
    * `__init__.py`
    * `config.py`: Standard Pydantic `Settings` (Kafka details, Content Service URL, `ESSAY_CONTENT_READY_TOPIC` name, `FILE_SERVICE_` prefix).
    * `protocols.py`:
        * `ContentServiceClientProtocol`: `async def store_content(self, content_bytes: bytes, content_type: ContentType, file_name: str) -> str` (returns `storage_id`).
        * `EventPublisherProtocol`: `async def publish_essay_content_ready(self, event_data: EssayContentReady, correlation_id: Optional[uuid.UUID]) -> None`.
        * `TextExtractorProtocol`: `async def extract_text(self, file_content: bytes, file_name: str) -> str`.
    * `di.py`: `FileServiceProvider(Provider)` with provides for settings, `AIOKafkaProducer`, `aiohttp.ClientSession`, and concrete implementations of the above protocols.
        * `DefaultContentServiceClient`: Uses `aiohttp.ClientSession` to `POST` to Content Service.
        * `DefaultEventPublisher`: Uses `AIOKafkaProducer` to send `EventEnvelope[EssayContentReady]` to the topic from settings.
        * `DefaultTextExtractor`: Initial simple impl for `.txt` files.
    * `text_processing.py` (or part of `core_logic.py`):
        * `async def extract_text_from_file(...)`: Implements basic `.txt` extraction.
        * `async def parse_student_info(text_content: str) -> tuple[Optional[str], Optional[str]]`:
            * **Stub**: `logger.info("Student info parsing stub called."); return None, None`. Add `TODO` for future regex.
    * `core_logic.py`:
        * `async def process_single_file_upload(batch_id: str, file_content: bytes, file_name: str, correlation_id: uuid.UUID, /* injected dependencies: text_extractor, content_client, event_publisher */) -> dict`:
            1. `essay_id = str(uuid.uuid4())`
            2. `text = await text_extractor.extract_text(file_content, file_name)`
            3. `student_name, student_email = await parse_student_info(text)` (from `text_processing.py`)
            4. `storage_id = await content_client.store_content(text.encode('utf-8'), ContentType.ORIGINAL_ESSAY, file_name)`
            5. Construct `EssayContentReady` data (from `common_core`) including `essay_id`, `batch_id`, `storage_id` for `content_storage_reference`, `entity` ref, `SystemProcessingMetadata`, and the (stubbed `None`) `student_name`, `student_email`.
            6. `await event_publisher.publish_essay_content_ready(event_data, correlation_id)`
            7. Return `{"essay_id": essay_id, "file_name": file_name, "status": "processing_initiated"}`.
    * `api/file_routes.py`:
        * `file_bp = Blueprint('file_routes', __name__, url_prefix='/v1/files')`
        * `@file_bp.route("/batch", methods=["POST"])`:
            * Inject `core_logic_module_or_specific_function_via_protocol`.
            * Expect `batch_id` from form data (`request.form.get("batch_id")`).
            * Handle multiple file uploads from `request.files`.
            * Generate a main `correlation_id` for the whole batch upload operation.
            * For each file: `asyncio.create_task(core_logic.process_single_file_upload(batch_id, await file.read(), file.filename, correlation_id, ...dependencies...))`.
            * Return `202 Accepted` with a summary (e.g., number of files received for batch).
    * `app.py`: Basic Quart app setup, registers `file_bp`, Dishka setup.
    * `Dockerfile`, `pyproject.toml` (Quart, Hypercorn, aiokafka, aiohttp, common_core, service_libs, pydantic-settings, Dishka), `hypercorn_config.py`, `README.md`.

---
**Definition of Done**:

1. All `common_core` changes are implemented and pass type checking.
2. `kafka_topic_bootstrap.py` successfully creates all required topics, including new ones.
3. ELS is fully containerized with separate API and Worker services in `docker-compose.yml`, and its worker consumes `BatchEssaysRegistered` and `EssayContentReady` correctly.
4. BOS has a new API endpoint `/v1/batches/register` which stores full batch context (including `course_code` etc.) and publishes a lightweight `BatchEssaysRegistered` event.
5. BOS, when initiating spellcheck, correctly infers language from `course_code` and includes it in the `BatchServiceSpellcheckInitiateCommandDataV1` sent to ELS.
6. File Service skeleton is created with the `POST /v1/files/batch` API endpoint that accepts files + `batch_id`, extracts text (basic `.txt`), stubs student info parsing, stores content via Content Service, and publishes `EssayContentReady` events (with optional `student_name`/`student_email` fields stubbed to `None`).
7. All new/modified code adheres to project standards (linting, typing, file size, SRP).
8. Services start and run in Docker Compose without errors related to these changes.
9. Basic manual test of the flow: Register batch via BOS API -> Upload files via File Service API -> Check ELS logs for readiness aggregation -> Check BOS logs for pipeline command -> Check ELS logs for dispatch -> Check Spell Checker logs for processing.

**Important Considerations**:

* **Error Handling**: Implement basic error handling (try/except blocks, logging errors) in new API endpoints and processing logic. More sophisticated error handling can be a follow-up.
* **Testing**: While writing full unit/integration tests might be a separate ticket, ensure the code is structured to be testable (e.g., dependencies injected, core logic in separate functions).
* **Logging**: Implement structured logging with correlation IDs throughout the new flows.
* **Idempotency**: Consider idempotency for event handlers where applicable (though less critical for ELS readiness aggregation if `BatchEssayTracker` handles duplicates gracefully).
* Refer to existing services (`content_service`, `spell_checker_service`, `batch_orchestrator_service`, `essay_lifecycle_service`) for patterns on DI, config, Kafka producers, Quart app setup, and Dockerfiles.

This ticket should provide your junior developers with a clear and structured path to implement the walking skeleton components.
