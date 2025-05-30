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
- **Section D: BOS Modifications** - ✅ COMPLETED & VERIFIED (2025-01-30)
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

### D. Batch Orchestrator Service (BOS) Modifications (`services/batch_orchestrator_service/`) ✅ COMPLETED & VERIFIED (2025-01-30)

**Implementation Summary:**

1. ✅ **API Request Model Created** (`api_models.py`): Implemented `BatchRegistrationRequestV1` with fields for `expected_essay_count`, `essay_ids`, `course_code`, `class_designation`, and `essay_instructions` using proper Pydantic validation
2. ✅ **Registration Endpoint Added** (`api/batch_routes.py`): Implemented `POST /register` endpoint with:
   - Full request validation using `BatchRegistrationRequestV1`
   - Batch context storage via updated repository protocol
   - Lightweight `BatchEssaysRegistered` event publishing to ELS
   - Comprehensive error handling and correlation ID tracking
   - Prometheus metrics integration
3. ✅ **Repository Protocol Enhanced** (`protocols.py`): Added `store_batch_context()` and `get_batch_context()` methods to `BatchRepositoryProtocol` for storing full batch registration data
4. ✅ **Mock Repository Updated** (`di.py`): Enhanced `MockBatchRepository` with internal storage dictionaries for batch contexts and implemented new protocol methods
5. ✅ **Kafka Consumer Logic Implemented** (`kafka_consumer.py` + `app.py`):
   - Complete Kafka consumer for `BatchEssaysReady` events from ELS
   - Language inference from course codes (SV→sv, ENG→en, etc.)
   - `BatchServiceSpellcheckInitiateCommandDataV1` command construction and publishing
   - Idempotency checks and pipeline state management
   - Background task integration with Quart application lifecycle
   - **Walking Skeleton Documentation**: Comprehensive documentation of mock `text_storage_id` pattern following established codebase style (`mock-storage-id-{essay_id}`)

**Key Architectural Decisions:**

- **Thin Events**: `BatchEssaysReady` maintains thin event principle (essay_ids only, no storage references)
- **Context Storage**: BOS stores full batch context for later pipeline initiation
- **Walking Skeleton Pattern**: Used consistent mock storage ID pattern for File Service coordination gap
- **Language Inference**: Helper function maps course codes to language codes for specialized service commands

**Topic Mapping Added**:

- `BATCH_ESSAYS_READY` → `"huleedu.els.batch.essays.ready.v1"`
- `BATCH_SPELLCHECK_INITIATE_COMMAND` → `"huleedu.els.spellcheck.initiate.command.v1"`

**Verification**: All components tested with functional tests, imports, type checking, and linting compliance

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
