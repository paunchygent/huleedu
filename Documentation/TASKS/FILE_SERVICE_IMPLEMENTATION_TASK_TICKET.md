# Task Ticket: Implement File Service Skeleton (Batch Coordination Walking Skeleton - Part E)

Ticket ID: HULEDU-FILESVC-001
Assignee: Junior Developer Team
Reporter: System Architect
Priority: High
Depends On: HULEDU-PREP-001 (Preparatory tasks for Common Core, ELS, BOS)

Summary: This ticket details the implementation of the new File Service skeleton. This service is a critical component of the "Batch Coordination Walking Skeleton." It will act as an HTTP service for batch file uploads, perform basic text extraction, coordinate content storage with the Content Service, and produce EssayContentReady Kafka events.

## Context/Background

The File Service is a new microservice in the HuleEdu ecosystem. Its creation and integration are the final major steps in establishing the walking skeleton for batch processing. This implementation must adhere strictly to the architectural decisions, project rules, and established patterns from existing services.

## Key Architectural Decisions to Adhere To

* **File Service is an HTTP service that produces Kafka events. No Kafka consumer is needed for this walking skeleton.**

* **Student Info Parsing: For this walking skeleton, student name/email parsing will be a stub returning None.**

* **All code must comply with DI patterns (Dishka), protocol-based abstractions, Pydantic settings, structured logging, file size/line length limits, and Blueprint-based API structure for Quart services.**

* **Interaction with Content Service must align with its current API.**

* **All imports must be absolute as per Rule 050-python-coding-standards.mdc.**

### E. File Service Implementation (Skeleton - `services/file_service/`)

This section outlines the creation of the new **File Service**. It will be an HTTP service responsible for receiving file uploads, performing basic text extraction, coordinating with the Content Service for storage, and producing `EssayContentReady` Kafka events. For this walking skeleton, it will not include a Kafka consumer. Strict adherence to existing project rules and patterns observed in services like `content_service` and `batch_orchestrator_service` is required.

1. **Create Service Directory and Initial Structure**:
    * **Action**: Create the main service directory: `services/file_service/`.
    * **Action**: Inside `services/file_service/`, create an empty `__init__.py` file to mark it as a Python package.

2. **Implement Configuration (`services/file_service/config.py`)**:
    * **Action**: Create `config.py`.
    * **Instruction**: Define a Pydantic `Settings` class inheriting from `pydantic_settings.BaseSettings`.
        * Include necessary settings:
            * `LOG_LEVEL: str` (default to "INFO").
            * `SERVICE_NAME: str` (default to "file-service").
            * `KAFKA_BOOTSTRAP_SERVERS: str` (e.g., "kafka:9092").
            * `CONTENT_SERVICE_URL: str` (e.g., "http://content_service:8000/v1/content").
            * `ESSAY_CONTENT_READY_TOPIC: str`.
                * **Critical**: This topic name **must** be derived from `common_core.enums` to ensure central management and consistency. Example:

                    ```python
                    from common_core.enums import ProcessingEvent, topic_name
                    # ...
                    ESSAY_CONTENT_READY_TOPIC: str = topic_name(ProcessingEvent.ESSAY_CONTENT_READY)
                    ```

            * `HTTP_PORT: int` (e.g., a suitable port like 7001, ensure it's unique).
            * `PROMETHEUS_PORT: int` (e.g., 9092, ensure it's unique).
        * Configure `SettingsConfigDict` with `env_prefix="FILE_SERVICE_"` and allow `.env` file loading.
        * Refer to `services/content_service/config.py` or `services/batch_orchestrator_service/config.py` for the standard structure.

3. **Define Protocols (`services/file_service/protocols.py`)**:
    * **Action**: Create `protocols.py`.
    * **Instruction**: Define the following `typing.Protocol` interfaces:
        * `ContentServiceClientProtocol`:

            ```python
            from common_core.enums import ContentType # Add this import
            # ... other imports ...
            class ContentServiceClientProtocol(Protocol):
                async def store_content(self, content_bytes: bytes) -> str: # Returns storage_id
                    # Note: Aligned with current Content Service API (POST /v1/content)
                    # which accepts raw binary data. file_name and content_type, if needed
                    # by File Service internally (e.g., for logging or decisions before this call),
                    # should be handled by the caller of this protocol method and not passed here
                    # unless the Content Service API itself is extended to accept them.
                    ...
            ```

        * `EventPublisherProtocol`:

            ```python
            import uuid # Add this import
            from common_core.events.batch_coordination_events import EssayContentReady # Add this import
            # ... other imports ...
            class EventPublisherProtocol(Protocol):
                async def publish_essay_content_ready(self, event_data: EssayContentReady, correlation_id: Optional[uuid.UUID]) -> None:
                    ...
            ```

        * `TextExtractorProtocol`:

            ```python
            class TextExtractorProtocol(Protocol):
                async def extract_text(self, file_content: bytes, file_name: str) -> str: # file_name can be used for context or simple type dispatch
                    ...
            ```

    * Ensure `from __future__ import annotations` is used.

4. **Implement Dependency Injection (`services/file_service/di.py`)**:
    * **Action**: Create `di.py`.
    * **Instruction**: Define a `FileServiceProvider(Provider)` class from `dishka`.
        * Provide `Settings` from `./config.py`.
        * Provide an `AIOKafkaProducer` instance (configured with `settings.KAFKA_BOOTSTRAP_SERVERS`). Remember to `await producer.start()` if creating it in an async provider method.
        * Provide an `aiohttp.ClientSession` instance.
        * Provide concrete implementations for the protocols defined in `protocols.py`:
            * `DefaultContentServiceClient(ContentServiceClientProtocol)`:
                * Inject `aiohttp.ClientSession` and `Settings`.
                * Implement `store_content`: POST `content_bytes` to `settings.CONTENT_SERVICE_URL`. It should interact with the Content Service's `POST /v1/content` endpoint which expects raw binary data.
            * `DefaultEventPublisher(EventPublisherProtocol)`:
                * Inject `AIOKafkaProducer` and `Settings`.
                * Implement `publish_essay_content_ready`: Construct an `EventEnvelope[EssayContentReady]` and publish it to `settings.ESSAY_CONTENT_READY_TOPIC` using the producer.
            * `DefaultTextExtractor(TextExtractorProtocol)`:
                * Implement `extract_text`: For the walking skeleton, provide a simple implementation that decodes `.txt` files (e.g., `file_content.decode('utf-8', errors='ignore')`). If `file_name` suggests a non-txt file, it can log a warning and return empty string or raise a specific exception to be handled by `core_logic`.

5. **Implement Text Processing Logic (`services/file_service/text_processing.py`)**:
    * **Action**: Create `text_processing.py`.
    * **Instruction**:
        * Implement `async def extract_text_from_file(file_content: bytes, file_name: str) -> str`:
            * This function will contain the basic `.txt` file content extraction logic (decode bytes to string).
            * For non `.txt` files (identified by `file_name` extension), log a warning and return an empty string or handle as an error.
        * Implement `async def parse_student_info(text_content: str) -> tuple[Optional[str], Optional[str]]`:
            * **Stub Implementation**:

                ```python
                from typing import Optional, Tuple
                from huleedu_service_libs.logging_utils import create_service_logger # Or get logger from core_logic

                logger = create_service_logger("file_service.text_processing") # Adjust as needed

                async def parse_student_info(text_content: str) -> Tuple[Optional[str], Optional[str]]:
                    logger.info("Student info parsing stub called. Returning None, None.")
                    # TODO: Implement actual student name/email parsing from text_content (e.g., using regex) in a future phase.
                    return None, None
                ```

6. **Implement Core Logic (`services/file_service/core_logic.py`)**:
    * **Action**: Create `core_logic.py`.
    * **Instruction**: Implement the main file processing workflow:

        ```python
        import uuid
        from typing import Optional, Dict, Any # Add Any for return type clarity
        from .protocols import TextExtractorProtocol, ContentServiceClientProtocol, EventPublisherProtocol
        from .text_processing import parse_student_info # Ensure direct import
        from common_core.enums import ContentType
        from common_core.events.batch_coordination_events import EssayContentReady
        from common_core.metadata_models import EntityReference, StorageReferenceMetadata, SystemProcessingMetadata
        from datetime import datetime, timezone # For SystemProcessingMetadata
        from common_core.enums import ProcessingEvent # For SystemProcessingMetadata

        async def process_single_file_upload(
            batch_id: str,
            file_content: bytes,
            file_name: str,
            main_correlation_id: uuid.UUID, # Correlation ID for the whole batch upload operation
            text_extractor: TextExtractorProtocol,
            content_client: ContentServiceClientProtocol,
            event_publisher: EventPublisherProtocol,
            # Service specific logger can also be passed or created here
        ) -> Dict[str, Any]: # Return a dict for clear API response
            essay_id = str(uuid.uuid4())
            # Ensure logger is available, e.g., by creating it here or passing it.
            # from huleedu_service_libs.logging_utils import create_service_logger
            # logger = create_service_logger("file_service.core_logic")
            # logger.info(f"Processing file {file_name} for batch {batch_id}, essay {essay_id}, correlation {main_correlation_id}")
            
            try:
                text = await text_extractor.extract_text(file_content, file_name)
                if not text: # Handle case where text extraction fails or returns empty for non-txt
                    # logger.warning(f"Text extraction failed or returned empty for {file_name}, essay {essay_id}")
                    # Decide on error handling: e.g., publish a failure event or just skip?
                    # For walking skeleton, skipping might be acceptable if logged.
                    return {"essay_id": essay_id, "file_name": file_name, "status": "extraction_failed_or_empty"}


                student_name, student_email = await parse_student_info(text) # Uses stub from text_processing.py

                # Store the extracted text using ContentServiceClientProtocol
                storage_id = await content_client.store_content(text.encode('utf-8'))
                # logger.info(f"Stored content for essay {essay_id}, storage_id: {storage_id}")

                # Construct StorageReferenceMetadata
                content_storage_ref = StorageReferenceMetadata()
                content_storage_ref.add_reference(ContentType.ORIGINAL_ESSAY, storage_id)
                
                # Construct EntityReference and SystemProcessingMetadata
                essay_entity_ref = EntityReference(entity_id=essay_id, entity_type="essay", parent_id=batch_id)
                event_sys_metadata = SystemProcessingMetadata(
                    entity=essay_entity_ref,
                    event=ProcessingEvent.ESSAY_CONTENT_READY.value, # Use enum value
                    timestamp=datetime.now(timezone.utc)
                )

                # Construct EssayContentReady event data
                essay_ready_event_data = EssayContentReady(
                    # event field is defaulted in Pydantic model
                    essay_id=essay_id,
                    batch_id=batch_id,
                    content_storage_reference=content_storage_ref,
                    entity=essay_entity_ref,
                    metadata=event_sys_metadata,
                    student_name=student_name, # Will be None from stub
                    student_email=student_email  # Will be None from stub
                )
                
                # Publish the event
                await event_publisher.publish_essay_content_ready(essay_ready_event_data, main_correlation_id)
                # logger.info(f"Published EssayContentReady for essay {essay_id}")

                return {"essay_id": essay_id, "file_name": file_name, "status": "processing_initiated"}
            except Exception as e:
                # logger.error(f"Error processing file {file_name} for essay {essay_id}: {e}", exc_info=True)
                # Optionally publish a failure event for this specific essay
                return {"essay_id": essay_id, "file_name": file_name, "status": "processing_error", "detail": str(e)}
        ```

    * **Error Handling**: Implement `try-except` blocks within this function for robustness, especially around external calls (text extraction, content storage, event publishing). Log errors with `essay_id`, `file_name`, and `correlation_id`.

7. **Implement API Routes (`services/file_service/api/`)**:
    * **Action**: Create directory `services/file_service/api/`.
    * **Action**: Create `services/file_service/api/__init__.py`.
    * **Action**: Create `services/file_service/api/health_routes.py`:
        * **Instruction**: Implement this following the exact pattern of `services/content_service/api/health_routes.py` or `services/batch_orchestrator_service/api/health_routes.py`.
        * Define `health_bp = Blueprint('health_routes', __name__)`.
        * Include `/healthz` (returning service status) and `/metrics` (using `generate_latest` from `prometheus_client` and `CollectorRegistry` injected via Dishka) endpoints.
        * Ensure it can accept the `CollectorRegistry` via a `set_..._dependencies` function or relies on app-level DI setup for Blueprints.
    * **Action**: Create `services/file_service/api/file_routes.py`:
        * **Instruction**:

            ```python
            from quart import Blueprint, request, jsonify, Response # Add Response
            from quart_dishka import inject
            from dishka import FromDishka
            import asyncio
            import uuid # For generating main_correlation_id
            # Assuming core_logic.py has process_single_file_upload
            # and DI is set up to inject it or its containing class/module
            from ..core_logic import process_single_file_upload 
            from ..protocols import TextExtractorProtocol, ContentServiceClientProtocol, EventPublisherProtocol
            # from huleedu_service_libs.logging_utils import create_service_logger
            # logger = create_service_logger("file_service.api.routes")

            file_bp = Blueprint('file_routes', __name__, url_prefix='/v1/files')

            # Placeholder for metric injection if needed at blueprint level
            # FILE_OPERATIONS: Optional[Counter] = None
            # def set_file_operations_metric(metric: Counter) -> None:
            #     global FILE_OPERATIONS
            #     FILE_OPERATIONS = metric

            @file_bp.route("/batch", methods=["POST"])
            @inject
            async def upload_batch_files(
                # Inject dependencies needed by process_single_file_upload
                text_extractor: FromDishka[TextExtractorProtocol],
                content_client: FromDishka[ContentServiceClientProtocol],
                event_publisher: FromDishka[EventPublisherProtocol]
            ) -> tuple[Response, int]:
                form_data = await request.form
                batch_id = form_data.get("batch_id")
                files = await request.files
                
                if not batch_id:
                    # logger.warning("Batch upload attempt without batch_id.")
                    return jsonify({"error": "batch_id is required in form data."}), 400
                
                uploaded_files = files.getlist('files') # Assuming form field name is 'files'
                if not uploaded_files:
                    # logger.warning(f"No files provided for batch {batch_id}.")
                    return jsonify({"error": "No files provided in 'files' field."}), 400

                main_correlation_id = uuid.uuid4()
                # logger.info(f"Received {len(uploaded_files)} files for batch {batch_id}. Correlation ID: {main_correlation_id}")

                tasks = []
                for file_storage in uploaded_files:
                    if file_storage and file_storage.filename:
                        file_content = await file_storage.read()
                        # Pass all required injected dependencies to process_single_file_upload
                        task = asyncio.create_task(
                            process_single_file_upload(
                                batch_id=batch_id,
                                file_content=file_content,
                                file_name=file_storage.filename,
                                main_correlation_id=main_correlation_id,
                                text_extractor=text_extractor,
                                content_client=content_client,
                                event_publisher=event_publisher
                            )
                        )
                        tasks.append(task)
                
                # For a 202 Accepted, we don't typically wait for all tasks.
                # However, error logging from tasks is important.
                # Consider adding a done_callback to tasks for logging/handling exceptions
                # if not handled within process_single_file_upload itself.
                # For example:
                # def _handle_task_result(task: asyncio.Task) -> None:
                #    if task.exception():
                #        logger.error(f"Error processing uploaded file: {task.exception()}", exc_info=task.exception())
                # for task in tasks:
                #    task.add_done_callback(_handle_task_result)
                
                # if FILE_OPERATIONS:
                #    FILE_OPERATIONS.labels(operation="batch_upload", status="initiated").inc(len(uploaded_files))

                return jsonify({
                    "message": f"{len(uploaded_files)} files received for batch {batch_id} and are being processed.",
                    "batch_id": batch_id,
                    "correlation_id": str(main_correlation_id)
                }), 202
            ```

        * **Import Style**: Ensure all intra-service imports (e.g., to `core_logic`) are absolute: `from core_logic import process_single_file_upload`.
        * **Error Handling**: Log exceptions from the `asyncio.create_task` calls, as these run in the background.

8. **Implement Application Setup (`services/file_service/app.py`)**:
    * **Action**: Create `app.py`.
    * **Instruction**:
        * Create a Quart app instance.
        * Configure logging using `configure_service_logging` from `huleedu_service_libs`.
        * Set up Dishka using `QuartDishka` and the `FileServiceProvider`.
        * Register the `file_bp` from `api.file_routes`.
        * **Crucial**: Register the `health_bp` from `api.health_routes`.
        * Implement standard `before_request` and `after_request` hooks for metrics (REQUEST_COUNT, REQUEST_DURATION), similar to other services. Ensure metrics are initialized with the Dishka-provided `CollectorRegistry`.
        * Ensure `app.py` remains lean (< 150 LoC).

9. **Create `Dockerfile` (`services/file_service/Dockerfile`)**:
    * **Action**: Create this file.
    * **Instruction**: Model it closely on `services/content_service/Dockerfile` or `services/batch_orchestrator_service/Dockerfile`.
        * Use `python:3.11-slim` base image.
        * Set `ENV` vars (Python defaults, `ENV_TYPE=docker`, `QUART_APP=app:app`, service-specific vars like `FILE_SERVICE_HTTP_PORT`, `FILE_SERVICE_PROMETHEUS_PORT`).
        * Install PDM globally.
        * Correctly copy `common_core/`, `services/libs/`, then `services/file_service/`.
        * Run `pdm install --prod` from within the `services/file_service/` workdir.
        * Create and use a non-root `appuser`.
        * `EXPOSE ${HTTP_PORT}` and `EXPOSE ${PROMETHEUS_PORT}` (using the env vars defined for these).
        * `CMD ["pdm", "run", "start"]`.

10. **Create `pyproject.toml` (`services/file_service/pyproject.toml`)**:
    * **Action**: Create this file.
    * **Instruction**:
        * Define `[project]` section with `name = "huleedu-file-service"`, version, description, authors, `requires-python = ">=3.11"`.
        * `dependencies`: List all required libraries such as `quart`, `hypercorn`, `aiokafka`, `aiohttp`, `python-dotenv`, `pydantic`, `pydantic-settings`, `prometheus-client`, `dishka`, `quart-dishka`.
        * **Local Development Dependencies**: For local development using PDM directly, include local path dependencies for shared packages:

            ```toml
            huleedu-common-core = {path = "../../common_core", editable = true}
            huleedu-service-libs = {path = "../libs", editable = true}
            ```

        * `[tool.pdm.scripts]`:
            * `start = "hypercorn app:app --config python:hypercorn_config"`
            * `dev = "quart --app app:app --debug run -p {FILE_SERVICE_HTTP_PORT_VALUE_HERE}"` (e.g., use the value from your File Service `config.py`, like 7001).
        * **Docker Build Overrides**: For building the Docker image, where `common_core` and `libs` are copied to specific locations (e.g., under `/app/`), PDM needs hints to find them during `pdm install --prod` inside the container. Add these to `[tool.pdm.resolution.overrides]`, mirroring other services like `content_service`:

            ```toml
            [tool.pdm.resolution.overrides]
            huleedu-common-core = "file:///app/common_core"
            huleedu-service-libs = "file:///app/services/libs"
            ```

            *(Ensure these override paths match where your File Service `Dockerfile` copies these shared dependencies relative to its `/app` WORKDIR before running `pdm install`)*.
        * Include MyPy configuration, similar to other services, potentially ignoring missing imports for third-party libraries like `dishka.*`, `quart_dishka.*` if official stubs are unavailable.

11. **Create `hypercorn_config.py` (`services/file_service/hypercorn_config.py`)**:
    * **Action**: Create this file.
    * **Instruction**: Model it on `services/content_service/hypercorn_config.py`, ensuring it sources `HOST` and `PORT` from `config.settings` (or environment variables that `config.settings` would load).

12. **Create `README.md` (`services/file_service/README.md`)**:
    * **Action**: Create this file.
    * **Instruction**: Document the File Service's purpose, API endpoints (`POST /v1/files/batch`, `/healthz`, `/metrics`), required environment variables (from its `config.py`), and local development setup instructions. Follow Rule `090-documentation-standards.mdc`.

13. **Add File Service to `docker-compose.yml`**:
    * **Action**: Edit the root `docker-compose.yml` file.
    * **Instruction**: Add a new service definition for `file_service`.
        * `build`: context `.` and Dockerfile `services/file_service/Dockerfile`.
        * `container_name: huleedu_file_service`.
        * `ports`: Map host port (e.g., 7001) to container `FILE_SERVICE_HTTP_PORT`. Map host port (e.g., 9092) to container `FILE_SERVICE_PROMETHEUS_PORT`.
        * `environment`: Pass necessary environment variables (Kafka, Content Service URL, etc.).
        * `depends_on`: `kafka_topic_setup: condition: service_completed_successfully`, `content_service: condition: service_started`.
        * Update `essay_lifecycle_api` and `essay_lifecycle_worker` to also `depend_on` `file_service: condition: service_started` if ELS directly consumes events from File Service at startup (which it will for `EssayContentReady`).

## Definition of Done (File Service Implementation - HULEDU-FILESVC-001)

### A. Service Structure and Core Files Created

The services/file_service/ directory and all specified core files (**init**.py, config.py, protocols.py, di.py, text_processing.py, core_logic.py, api/**init**.py, api/health_routes.py, api/file_routes.py, app.py) are created and populated according to the detailed instructions.
File Service README.md is created and populated with essential service information.
File Service hypercorn_config.py is created and correctly configured.
Configuration and DI Implemented:

config.py defines Pydantic Settings with a FILE_SERVICE_ prefix, and ESSAY_CONTENT_READY_TOPIC is correctly derived using topic_name(ProcessingEvent.ESSAY_CONTENT_READY) from common_core.enums.
protocols.py defines ContentServiceClientProtocol, EventPublisherProtocol, and TextExtractorProtocol.
di.py implements FileServiceProvider with concrete, working implementations for all defined protocols, including DefaultContentServiceClient that correctly calls the Content Service API (raw binary POST).
Core Logic and API Endpoints Functional:

text_processing.py contains the basic .txt text extraction and the stubbed parse_student_info function.
core_logic.py implements process_single_file_upload which:
Generates a unique essay_id.
Calls text_extractor.extract_text.
Calls the stubbed parse_student_info.
Correctly calls content_client.store_content (sending only raw bytes to Content Service).
Constructs the EssayContentReady event data (from common_core.events.batch_coordination_events) with all required fields, including stubbed student_name and student_email as None.
Publishes the event via event_publisher.publish_essay_content_ready.
api/health_routes.py provides functional /healthz and /metrics endpoints.
api/file_routes.py implements the POST /v1/files/batch endpoint which:
Accepts batch_id via form data and multiple file uploads.
Uses asyncio.create_task to call process_single_file_upload for each file concurrently.
Handles cases with no batch_id or no files.
Returns a 202 Accepted response.
Includes basic error logging for background tasks.
app.py is lean, correctly sets up Dishka, registers file_bp and health_bp, and includes Prometheus metrics hooks.
Containerization and Orchestration:

File Service Dockerfile is created, builds successfully, and follows project patterns (slim image, PDM, non-root user, correct CMD).
File Service pyproject.toml is correctly configured with all dependencies (including local path dependencies for common_core and libs for dev, and Docker overrides if necessary) and PDM scripts (start, dev).
File Service is added to the root docker-compose.yml with correct build context, ports, environment variables, and depends_on conditions.
Adherence to Standards:

All new code (Python, Dockerfile, PDM scripts) adheres to project standards: absolute imports for Python, Ruff linting compliance, MyPy type checking success, file size limits (LoC < 400, line length <= 100), and SRP.
Structured logging with correlation IDs is implemented for key operations.
End-to-End Flow Verification (Manual):

The complete walking skeleton flow can be manually tested:
Register a batch via BOS API (POST /v1/batches/register).
Upload files for that batch_id via File Service API (POST /v1/files/batch).
Observe ELS logs for consumption of EssayContentReady events and readiness aggregation (leading to BatchEssaysReady event emission).
Observe BOS logs for consumption of BatchEssaysReady and subsequent emission of a pipeline command (e.g., BatchServiceSpellcheckInitiateCommandDataV1) to ELS.
(If applicable and ELS command handling for spellcheck is stubbed/implemented) Observe ELS logs for dispatching requests to Spell Checker.
Observe Spell Checker logs for processing initiation (if it consumes the ELS command).
All services involved in this flow (common_core updates reflected, BOS, ELS API & Worker, File Service, Content Service, Kafka) start and run in Docker Compose without errors attributable to the File Service implementation or related preparatory changes.
