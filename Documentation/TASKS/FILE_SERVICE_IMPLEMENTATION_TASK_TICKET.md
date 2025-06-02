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

* **Make sure that imports are from protocols, not concrete implementations.**

* **importing protocols will lead to mypy issues (missing library stubs). Those are handled in by adding the import to root pyproject.toml exclusion list**

* **Ensure that you do not mix concerns, add implementation classes to implementations/**

* **No unit tests are written for the services yet, test by command line tests and scripts + live testing using root tests/**

* **Make sure to clean up orphaned containers after Docker rebuilds and always run docker compose up -d --build, never restart (as it will just restart the old build)**

### E. File Service Implementation (Skeleton - `services/file_service/`) - ✅ COMPLETED

This section outlines the creation of the new **File Service**. It will be an HTTP service responsible for receiving file uploads, performing basic text extraction, coordinating with the Content Service for storage, and producing `EssayContentReady` Kafka events. For this walking skeleton, it will not include a Kafka consumer. Strict adherence to existing project rules and patterns observed in services like `content_service` and `batch_orchestrator_service` is required.

1. **Create Service Directory and Initial Structure** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created the main service directory: `services/file_service/`.
    * **✅ IMPLEMENTED**: Created empty `__init__.py` file to mark it as a Python package.

2. **Implement Configuration (`services/file_service/config.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created `config.py` with Pydantic `Settings` class inheriting from `pydantic_settings.BaseSettings`.
    * **✅ IMPLEMENTED**: All required settings included:
        * `LOG_LEVEL: str = "INFO"`
        * `SERVICE_NAME: str = "file-service"`
        * `KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"`
        * `CONTENT_SERVICE_URL: str = "http://content_service:8000/v1/content"`
        * `ESSAY_CONTENT_READY_TOPIC: str` - **✅ CORRECTLY DERIVED** using `topic_name(ProcessingEvent.ESSAY_CONTENT_READY)`
        * `HTTP_PORT: int = 7001`
        * `PROMETHEUS_PORT: int = 9094`
        * **📝 DEVIATION**: Changed Prometheus port from suggested 9092 to 9094 to avoid conflict with Kafka in docker-compose.yml
    * **✅ IMPLEMENTED**: `SettingsConfigDict` with `env_prefix="FILE_SERVICE_"` and `.env` file loading.
    * **✅ IMPLEMENTED**: Followed standard structure from existing services.

3. **Define Protocols (`services/file_service/protocols.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created `protocols.py` with all required `typing.Protocol` interfaces.
    * **✅ IMPLEMENTED**: `ContentServiceClientProtocol` with `store_content` method returning `storage_id: str`
    * **✅ IMPLEMENTED**: `EventPublisherProtocol` with `publish_essay_content_ready` method accepting `EssayContentReady` and `correlation_id`
    * **✅ IMPLEMENTED**: `TextExtractorProtocol` with `extract_text` method for file processing
    * **✅ IMPLEMENTED**: All required imports including `uuid`, `EssayContentReady`, and proper typing annotations
    * **✅ IMPLEMENTED**: Used `from __future__ import annotations` for forward references

4. **Implement Dependency Injection (`services/file_service/di.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created `di.py` with `FileServiceProvider(Provider)` class from `dishka`.
    * **✅ IMPLEMENTED**: All required providers:
        * `Settings` provider from `config.py`
        * `AIOKafkaProducer` with proper async startup and configuration
        * `aiohttp.ClientSession` provider
        * `CollectorRegistry` for Prometheus metrics
    * **✅ IMPLEMENTED**: All concrete protocol implementations:
        * `DefaultContentServiceClient`: POST binary data to Content Service `/v1/content` endpoint
        * `DefaultEventPublisher`: Constructs `EventEnvelope[EssayContentReady]` and publishes to Kafka
        * `DefaultTextExtractor`: Delegates to `text_processing.py` functions
    * **📝 CRITICAL DEVIATION FIXED**: Event publishing initially used `json.dumps(envelope.model_dump())` which failed with UUID serialization. **FIXED** to use `json.dumps(envelope.model_dump(mode="json"))` to properly handle UUID serialization to strings.
    * **✅ IMPLEMENTED**: Proper error handling and logging throughout all implementations

5. **Implement Text Processing Logic (`services/file_service/text_processing.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created `text_processing.py` with all required functions.
    * **✅ IMPLEMENTED**: `extract_text_from_file(file_content: bytes, file_name: str) -> str`:
        * Basic `.txt` file content extraction using UTF-8 decoding with error handling
        * Proper warning logging for non-`.txt` files
        * Returns empty string for unsupported file types
    * **✅ IMPLEMENTED**: `parse_student_info(text_content: str) -> tuple[Optional[str], Optional[str]]`:
        * **Correctly implemented as stub** returning `(None, None)`
        * Includes proper logging indicating stub status
        * Ready for future implementation of actual student name/email parsing

6. **Implement Core Logic (`services/file_service/core_logic.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created `core_logic.py` with complete file processing workflow.
    * **✅ IMPLEMENTED**: `process_single_file_upload` function with all required parameters and logic:

        * **✅ FULLY IMPLEMENTED**: Complete end-to-end workflow including:
            * Essay ID generation with `uuid.uuid4()`
            * Text extraction via injected `TextExtractorProtocol`
            * Stubbed student info parsing (returns `None, None`)
            * Content storage via injected `ContentServiceClientProtocol`
            * Proper `StorageReferenceMetadata` and `EntityReference` construction
            * Complete `EssayContentReady` event data assembly
            * Event publishing via injected `EventPublisherProtocol`
        * **✅ IMPLEMENTED**: Comprehensive error handling with try-catch blocks
        * **✅ IMPLEMENTED**: Structured logging with correlation IDs using `extra={'correlation_id': str(main_correlation_id)}`
        * **✅ IMPLEMENTED**: Proper handling of empty text extraction (non-txt files)
        * **✅ IMPLEMENTED**: All imports use absolute paths as required by project standards

7. **Implement API Routes (`services/file_service/api/`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Created directory `services/file_service/api/` with `__init__.py`.
    * **✅ IMPLEMENTED**: `health_routes.py` following exact pattern from existing services:
        * `health_bp = Blueprint('health_routes', __name__)`
        * `/healthz` endpoint returning service status JSON
        * `/metrics` endpoint using `generate_latest` from `prometheus_client`
        * Proper integration with Dishka dependency injection
    * **✅ IMPLEMENTED**: `file_routes.py` with complete batch upload functionality:
        * **✅ FULLY IMPLEMENTED**: `POST /v1/files/batch` endpoint with complete functionality:
            * Proper form data validation for `batch_id` and `files`
            * Correlation ID generation for batch tracking
            * Concurrent file processing using `asyncio.create_task`
            * Error handling for missing batch_id or files
            * **📝 CRITICAL DEVIATION FIXED**: Initially used `await file_storage.read()` but Quart's file storage read is synchronous. **FIXED** to use `file_storage.read()`
            * Task result callback for background error logging
            * Proper 202 Accepted response with batch tracking information
        * **✅ IMPLEMENTED**: All imports using absolute paths as required
        * **✅ IMPLEMENTED**: Proper integration with Dishka dependency injection
        * **✅ IMPLEMENTED**: Comprehensive error logging and exception handling

8. **Implement Application Setup (`services/file_service/app.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Complete Quart application setup with all required components:
        * Quart app instance creation and configuration
        * Service logging configuration using `configure_service_logging`
        * Dishka dependency injection setup with `QuartDishka` and `FileServiceProvider`
        * Blueprint registration for both `file_bp` and `health_bp`
        * **📝 DEVIATION FIXED**: Initial metrics implementation used incorrect Prometheus pattern. **FIXED** to match existing services using `time.time()` for duration measurement
        * Proper startup/shutdown hooks for Kafka producer lifecycle
        * **✅ CONSTRAINT MET**: File remains under 150 LoC as required

9. **Create `Dockerfile` (`services/file_service/Dockerfile`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Complete Dockerfile following project patterns:
        * `python:3.11-slim` base image
        * Proper environment variables and Python configuration
        * PDM global installation
        * Correct copy sequence: `common_core/`, `services/libs/`, then `services/file_service/`
        * Production dependency installation with `pdm install --prod`
        * Non-root `appuser` security setup
        * Proper port exposure and CMD configuration

10. **Create `pyproject.toml` (`services/file_service/pyproject.toml`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Complete project configuration:
        * Project metadata with `huleedu-file-service` name and proper versioning
        * All required dependencies without version pinning (matching other services)
        * **📝 DEVIATION FIXED**: Initially used pinned dependency versions. **FIXED** to remove version constraints to match existing service patterns and resolve PDM resolution conflicts
        * Local development path dependencies for `common_core` and `service_libs`
        * Docker build overrides for container paths
        * PDM scripts for `start` and `dev` commands
        * MyPy configuration with proper third-party library exclusions

11. **Create `hypercorn_config.py` (`services/file_service/hypercorn_config.py`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Hypercorn configuration following project patterns
    * **📝 DEVIATION FIXED**: Initial implementation had line length violation. **FIXED** by breaking long bind configuration into multiple variables

12. **Create `README.md` (`services/file_service/README.md`)** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Complete service documentation including:
        * Service purpose and functionality description
        * API endpoint documentation (`/v1/files/batch`, `/healthz`, `/metrics`)
        * Environment variable requirements
        * Local development setup instructions
        * Docker deployment guidance

13. **Add File Service to `docker-compose.yml`** - ✅ COMPLETED:
    * **✅ IMPLEMENTED**: Complete service integration:
        * Service definition with proper build context and Dockerfile
        * Container naming following project conventions
        * **📝 DEVIATION FIXED**: Initial port mapping used 9092 which conflicts with Kafka. **FIXED** to use 9094 for Prometheus port
        * All required environment variables for service operation
        * Proper dependency chain: `kafka_topic_setup` → `content_service` → `file_service`
        * Updated ELS services to depend on File Service for event consumption

## Testing Results and Verification

### Linting and Type Checking - ✅ PASSED

* **Command**: `pdm run lint-all` and `pdm run typecheck-all`
* **Result**: All linting and type checking issues resolved
* **Issues Fixed**:
  * Line length violations in `hypercorn_config.py`
  * MyPy type annotation issues in `di.py` for JSON response handling
  * Missing Response import and type annotation in `app.py`

### Docker Container Build and Deployment - ✅ PASSED

* **Commands**:
  * `docker-compose build file_service --no-cache`
  * `docker-compose up -d`
* **Result**: Service builds and starts successfully
* **Issues Fixed**:
  * Port conflict resolution (changed Prometheus port from 9092 to 9094)
  * PDM dependency resolution conflicts resolved

### API Endpoint Testing - ✅ PASSED

#### Health Endpoints

* **`GET /healthz`**: ✅ Returns `{"message": "File Service is healthy", "status": "ok"}`
* **`GET /metrics`**: ✅ Returns Prometheus metrics (empty initially, as expected)

#### Batch Upload Endpoint Testing

* **Valid Upload Test**: ✅ PASSED
  * **Command**: `curl -X POST http://localhost:7001/v1/files/batch -F "batch_id=test-batch-final-001" -F "files=@test_uploads/essay1.txt" -F "files=@test_uploads/essay2.txt"`
  * **Result**: HTTP 202 Accepted with proper JSON response including batch_id and correlation_id
  * **Verification**: Service logs show successful text extraction, Content Service storage, and Kafka event publishing

* **Error Handling Tests**: ✅ PASSED
  * **Missing batch_id**: ✅ Returns HTTP 400 with `{"error": "batch_id is required in form data."}`
  * **No files provided**: ✅ Returns HTTP 400 with `{"error": "No files provided in 'files' field."}`
  * **Mixed file types**: ✅ Processes .txt files, logs warnings for non-.txt files

#### End-to-End Processing Verification

* **Text Extraction**: ✅ Successfully extracts text from .txt files (207 and 204 characters logged)
* **Content Storage**: ✅ Successfully stores content in Content Service (storage_ids received)
* **Event Publishing**: ✅ Successfully publishes `EssayContentReady` events to Kafka topic `huleedu.file.essay.content.ready.v1`
* **Correlation Tracking**: ✅ Proper correlation ID propagation through all processing steps

### Critical Issues Discovered and Fixed During Testing

1. **📝 CRITICAL**: `await file_storage.read()` → `file_storage.read()` (Quart's synchronous file reading)
2. **📝 CRITICAL**: `json.dumps(envelope.model_dump())` → `json.dumps(envelope.model_dump(mode="json"))` (UUID serialization)
3. **📝 DEPLOYMENT**: Port conflict resolution in docker-compose.yml

## Definition of Done (File Service Implementation - HULEDU-FILESVC-001) - ✅ COMPLETED

### F. Service Structure and Core Files Created

### File Service Implementation Requirements

#### 1. File Structure and Core Files

Create `services/file_service/` directory with all specified core files:

* `__init__.py`
* `config.py`
* `protocols.py`
* `di.py`
* `text_processing.py`
* `core_logic.py`
* `api/__init__.py`
* `api/health_routes.py`
* `api/file_routes.py`
* `app.py`
* Create `README.md` with essential service information
* Create properly configured `hypercorn_config.py`

#### 2. Configuration and Dependency Injection

##### `config.py`

* Define Pydantic Settings with `FILE_SERVICE_` prefix

* Derive `ESSAY_CONTENT_READY_TOPIC` using `topic_name(ProcessingEvent.ESSAY_CONTENT_READY)` from `common_core.enums`

##### `protocols.py`

* Define:
  * `ContentServiceClientProtocol`
  * `EventPublisherProtocol`
  * `TextExtractorProtocol`

##### `di.py`

* Implement `FileServiceProvider` with:
  * Concrete implementations for all protocols
  * `DefaultContentServiceClient` that correctly calls Content Service API (raw binary POST)

#### 3. Core Logic and API Endpoints

##### `text_processing.py`

* Implement basic `.txt` text extraction

* Include stubbed `parse_student_info` function

##### `core_logic.py`

* Implement `process_single_file_upload` that:
  1. Generates unique `essay_id`
  2. Calls `text_extractor.extract_text`
  3. Calls stubbed `parse_student_info`
  4. Calls `content_client.store_content` (sending raw bytes)
  5. Constructs `EssayContentReady` event data (from `common_core.events.batch_coordination_events`) with required fields (stubbed `student_name` and `student_email` as `None`)
  6. Publishes event via `event_publisher.publish_essay_content_ready`

##### API Endpoints

###### `api/health_routes.py`

* Functional `/healthz` endpoint

* Functional `/metrics` endpoint

###### `api/file_routes.py`

* Implement `POST /v1/files/batch` that:
  * Accepts `batch_id` via form data and multiple file uploads
  * Uses `asyncio.create_task` for concurrent processing
  * Handles cases with no `batch_id` or no files
  * Returns `202 Accepted` response
  * Includes basic error logging for background tasks

###### `app.py`

* Lean implementation

* Correctly sets up Dishka
* Registers `file_bp` and `health_bp`
* Includes Prometheus metrics hooks

#### 4. Containerization and Orchestration

* Create `Dockerfile` that:
  * Builds successfully
  * Follows project patterns (slim image, PDM, non-root user, correct CMD)

* Configure `pyproject.toml` with:
  * All dependencies (including local path dependencies for dev)
  * Docker overrides if necessary
  * PDM scripts (`start`, `dev`)
* Add File Service to root `docker-compose.yml` with:
  * Correct build context
  * Proper port mappings
  * Required environment variables
  * Correct `depends_on` conditions

#### 5. Adherence to Standards

* All new code must:
  * Use absolute imports
  * Pass Ruff linting
  * Pass MyPy type checking
  * Follow file size limits (<400 LoC, line length ≤100)
  * Follow Single Responsibility Principle

* Implement structured logging with correlation IDs for key operations

#### 6. End-to-End Flow Verification - 🔄 NEXT PHASE

**✅ COMPLETED - File Service Integration**:
* File Service successfully receives batch uploads
* Text extraction and content storage working end-to-end
* Kafka event publishing confirmed with proper event structure
* All services start and run in Docker Compose without File Service-related errors

**🔄 REMAINING - Full Walking Skeleton Flow** (Next Phase Testing):

1. Register batch via BOS API (`POST /v1/batches/register`)
2. Upload files via File Service API (`POST /v1/files/batch`) ✅ COMPLETED
3. Verify ELS logs for:
   * Consumption of `EssayContentReady` events ⏳ NEXT
   * `BatchEssaysReady` event emission ⏳ NEXT
4. Verify BOS logs for:
   * Consumption of `BatchEssaysReady` ⏳ NEXT
   * Emission of pipeline command (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`) ⏳ NEXT
5. (If applicable) Verify ELS logs for spellcheck request dispatching ⏳ NEXT
6. (If applicable) Verify Spell Checker logs for processing initiation ⏳ NEXT

## Next Steps and Recommendations

### Immediate Next Steps (Walking Skeleton Completion)

1. **End-to-End Testing**: Execute the full walking skeleton flow from BOS batch registration through File Service upload to ELS processing
2. **Event Flow Verification**: Confirm ELS properly consumes `EssayContentReady` events and produces `BatchEssaysReady` events
3. **Integration Testing**: Verify BOS consumption of `BatchEssaysReady` and pipeline command emission

### Future Enhancements (Post-Walking Skeleton)

1. **Student Info Parsing**: Replace stub implementation in `parse_student_info` with actual regex-based extraction
2. **File Format Support**: Extend beyond .txt files to support .doc, .docx, .pdf formats
3. **Batch Size Limits**: Implement configurable limits on batch size and file size
4. **Enhanced Error Handling**: Add retry logic for external service calls and dead letter queue handling
5. **Comprehensive Testing**: Add unit tests, integration tests, and contract tests

### Quality Assurance Notes for Planning Team

- **UUID Serialization**: Future Pydantic model serialization for Kafka events must use `mode="json"` parameter
* **Quart File Handling**: File storage objects use synchronous `.read()` method, not async
* **Port Management**: Ensure unique port allocation in docker-compose.yml to avoid conflicts
* **PDM Dependencies**: Avoid version pinning in service dependencies to prevent resolution conflicts
