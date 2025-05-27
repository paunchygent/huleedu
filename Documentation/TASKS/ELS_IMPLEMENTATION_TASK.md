# Task Ticket: Implement Essay Lifecycle Service (ELS) Core Architecture

**Ticket ID**: HULEDU-ELS-IMPL-001
**Date Created**: January 28, 2025
**Reporter**: Development Team
**Assignee**: Development Team

**Title**: Implement Essay Lifecycle Service (ELS) Skeleton - Core State Management and Event Processing Architecture

**Description**:
This ticket outlines the implementation of the Essay Lifecycle Service (ELS), a critical microservice that manages essay state transitions throughout the HuleEdu processing pipeline. The ELS serves as the central orchestrator for essay processing workflows, handling state management, event processing, and coordination between processing phases (spellcheck, NLP, AI feedback). This implementation establishes the foundational architecture required for Phase 2 development while adhering to HuleEdu's architectural mandates and DDD principles.

**Overall Acceptance Criteria**:
* ELS service skeleton implemented with proper DI architecture following spell_checker_service patterns
* Essay state management implemented with persistence layer
* Event processing pipeline for essay lifecycle events
* HTTP API endpoints for essay status queries and state management
* Comprehensive unit tests covering state transitions and event processing
* Service integration with existing Kafka infrastructure
* Docker containerization and compose integration
* Complete service documentation and README

---

## A. Service Foundation & Architecture

### A.1. Service Structure and Project Setup [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Create the ELS service directory structure following established project standards and architectural guidelines.
* **README.md Link/Rationale**: Implements **Service Autonomy** (README Sec 1), establishes proper **Bounded Context** for essay lifecycle management.

* **Implementation Tasks**:
    1. **Directory Structure**: Create `services/essay_lifecycle_service/` with standard layout:
       ```
       services/essay_lifecycle_service/
       ├── app.py                 # Quart application entry point for HTTP API
       ├── worker_main.py         # Kafka consumer worker entry point
       ├── event_router.py        # Event processing and orchestration logic
       ├── core_logic.py          # Core state management and business logic
       ├── protocols.py           # Protocol interfaces for DI
       ├── di.py                  # Dishka DI providers
       ├── config.py              # Pydantic settings configuration
       ├── state_store.py         # Essay state persistence layer
       ├── pyproject.toml         # Service dependencies and scripts
       ├── Dockerfile             # Container configuration
       ├── tests/                 # Test suite
       ├── docs/                  # Service documentation
       └── README.md              # Service overview and setup
       ```

    2. **Service Configuration**: Implement standardized Pydantic settings with:
       * Kafka connection settings
       * HTTP server configuration
       * State store configuration (SQLite for MVP, extensible for production)
       * Logging and observability settings

    3. **Dependencies**: Configure pyproject.toml with required dependencies:
       * `quart` and `hypercorn` for HTTP API
       * `aiokafka` for event processing
       * `aiosqlite` for state persistence
       * `huleedu-common-core` for shared models
       * `huleedu-service-libs` for utilities
       * Development dependencies: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`
       * PDM scripts: `start` (HTTP API), `start_worker` (Kafka consumer), `dev` (development mode)
       * MyPy overrides for `dishka.*` and local modules (`di`, `protocols`, `config`)

* **Acceptance Criteria**:
  * Service directory created with proper structure following project standards
  * pyproject.toml configured with all required dependencies
  * config.py implemented with comprehensive Pydantic settings
  * Basic service can be imported and configured without errors

---

### A.2. Define Protocol Interfaces [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Define typing.Protocol interfaces for all ELS dependencies to enable proper DI and testability.
* **README.md Link/Rationale**: Supports **Explicit Contracts** principle and enables robust testing patterns.

* **Implementation Tasks**:
    1. **Core Protocols**: Define interfaces in `protocols.py`:

       ```python

       from typing import Protocol, Optional
       from uuid import UUID
       from common_core.enums import EssayStatus
       from common_core.metadata_models import EntityReference
       
       class EssayStateStore(Protocol):
           async def get_essay_state(self, essay_id: str) -> Optional[EssayState]: ...
           async def update_essay_state(self, essay_id: str, new_status: EssayStatus, metadata: dict) -> None: ...
           async def create_essay_record(self, essay_ref: EntityReference) -> EssayState: ...
       
       class EventPublisher(Protocol):
           async def publish_status_update(self, essay_ref: EntityReference, status: EssayStatus) -> None: ...
       
       class StateTransitionValidator(Protocol):
           def validate_transition(self, current_status: EssayStatus, target_status: EssayStatus) -> bool: ...
       ```

    2. **HTTP Client Protocol**: Define interface for external service calls:

       ```python

       class ContentClient(Protocol):
           async def fetch_content(self, storage_id: str) -> bytes: ...
           async def store_content(self, content: bytes) -> str: ...
       ```

    3. **Metrics Protocol**: Define observability interface:

       ```python

       class MetricsCollector(Protocol):
           def record_state_transition(self, from_status: str, to_status: str) -> None: ...
           def record_processing_time(self, operation: str, duration_ms: float) -> None: ...
       ```

* **Acceptance Criteria**:
  * All protocol interfaces defined with proper type hints
  * Protocols cover all external dependencies and core business logic
  * Protocol methods match expected usage patterns from other services

---

## B. Core State Management Implementation

### B.1. Essay State Models and Storage [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Implement essay state persistence with proper data models and storage layer.
* **README.md Link/Rationale**: Implements **Data Ownership** within bounded context, supports essay lifecycle tracking.

* **Implementation Tasks**:
    1. **Essay State Model**: Define comprehensive state model using Pydantic BaseModel:

       ```python
       
       from pydantic import BaseModel, Field
       from datetime import datetime
       from typing import Dict, Any, Optional
       from common_core.enums import EssayStatus, ContentType

       class EssayState(BaseModel):
           essay_id: str
           batch_id: Optional[str] = None
           current_status: EssayStatus
           processing_metadata: Dict[str, Any] = Field(default_factory=dict)
           timeline: Dict[str, datetime] = Field(default_factory=dict)
           storage_references: Dict[ContentType, str] = Field(default_factory=dict)
           created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
           updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
       ```

    2. **SQLite Storage Implementation**: Create `state_store.py` with:
       * Async SQLite operations using aiosqlite
       * Essay state CRUD operations
       * State transition logging
       * Query capabilities for batch processing status
       * Simple database schema migration support with version tracking table

    3. **State Transition Logic**: Implement business rules for valid transitions:
       * Status progression validation (uploaded → spellcheck → NLP → completed)
       * Error state handling and recovery paths
       * Batch completion detection logic

* **Acceptance Criteria**:
  * EssayState Pydantic model properly represents all essay lifecycle data with validation
  * SQLite storage layer with async operations
  * State transition validation with comprehensive business rules
  * Database schema migration support with version tracking

---

### B.2. Event Processing Pipeline [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Implement Kafka event processing for essay lifecycle events.
* **README.md Link/Rationale**: Implements **Event-Driven Communication** backbone, processes **Thin Events** with proper contracts.

* **Implementation Tasks**:
    1. **Event Router Implementation**: Create `event_router.py` with:

       ```python

       async def process_single_message(
           msg: ConsumerRecord,
           state_store: EssayStateStore,
           event_publisher: EventPublisher,
           transition_validator: StateTransitionValidator,
               ) -> bool:
            # Deserialize EventEnvelope using EventEnvelope[SpecificEventType].model_validate()
            # Route to appropriate handler based on event type
            # Update essay state
            # Publish status update events
       ```

    2. **Event Handlers**: Implement handlers for:
       * `essay.upload.completed.v1` → Create essay record
       * `essay.spellcheck.completed.v1` → Update to spellchecked status
       * `essay.nlp.completed.v1` → Update to NLP completed status
       * `essay.ai_feedback.completed.v1` → Update to final status

    3. **Worker Main**: Implement Kafka consumer loop in `worker_main.py`:
       * DI container initialization
       * Kafka client lifecycle management
       * Message processing orchestration
       * Error handling and dead letter queue support

* **Acceptance Criteria**:
  * Event router processes all essay lifecycle events
  * State transitions properly validated and persisted
  * Status update events published for downstream consumers
  * Robust error handling with proper logging

---

## C. HTTP API Implementation

### C.1. Essay Status API Endpoints [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Implement Quart-based HTTP API for essay status queries and management operations.
* **README.md Link/Rationale**: Provides **Query Interface** for essay status, supports batch processing coordination.

* **Implementation Tasks**:
    1. **Core API Endpoints**: Implement in `app.py`:

       ```python

       GET /v1/essays/{essay_id}/status
       GET /v1/essays/{essay_id}/timeline
       GET /v1/batches/{batch_id}/status
       POST /v1/essays/{essay_id}/retry
       GET /healthz
       ```

    2. **Quart Application Setup**: Configure with:
       * Dishka DI integration using quart-dishka
       * Pydantic request/response models
       * Proper error handling and API versioning
       * CORS configuration for development

    3. **Response Models**: Define API schemas:
 
       ```python

       class EssayStatusResponse(BaseModel):
           essay_id: str
           current_status: EssayStatus
           processing_progress: Dict[str, bool]
           timeline: Dict[str, datetime]
           storage_references: Dict[ContentType, str]
       
       class BatchStatusResponse(BaseModel):
           batch_id: str
           total_essays: int
           status_breakdown: Dict[EssayStatus, int]
           completion_percentage: float
       ```

* **Acceptance Criteria**:
  * All API endpoints implemented with proper error handling
  * Pydantic models for request/response validation
  * DI integration working with @inject decorators
  * API documentation and OpenAPI spec generation

---

## D. Service Integration and Testing

### D.1. Comprehensive Unit Testing [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Implement comprehensive test suite covering all ELS functionality.
* **README.md Link/Rationale**: Ensures **Service Autonomy** through reliable testing, validates **Contract Compliance**.

* **Implementation Tasks**:
    1. **State Management Tests**: Test suite for:
       * Essay state CRUD operations
       * State transition validation
       * Concurrent access handling
       * Database error scenarios

    2. **Event Processing Tests**: Test coverage for:
       * Event deserialization and routing
       * State transition triggered by events
       * Error handling and retry logic
       * Correlation ID propagation

    3. **HTTP API Tests**: Test endpoints with:
       * Valid and invalid request handling
       * DI integration testing
       * Error response formats
       * API contract compliance

    4. **Integration Tests**: End-to-end scenarios:
       * Complete essay lifecycle processing
       * Batch completion detection
       * Cross-service event flow

* **Acceptance Criteria**:
  * Minimum 90% code coverage for core business logic
  * All state transitions tested with edge cases
  * Event processing pipeline thoroughly tested
  * HTTP API endpoints tested with proper mocking

---

### D.2. Docker Integration and Deployment [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Containerize ELS and integrate with existing Docker Compose infrastructure.
* **README.md Link/Rationale**: Supports **Independent Deployability** and local development environment.

* **Implementation Tasks**:
    1. **Dockerfile Creation**: Multi-stage build with:
       * Python 3.11 slim base image
       * PDM for dependency management
       * Proper user permissions and security
       * Health check implementation

    2. **Docker Compose Integration**: Add ELS services to `docker-compose.yml`:

       ```yaml
       
       essay_lifecycle_service:
         build: ./services/essay_lifecycle_service
         depends_on:
           - kafka_topic_setup
           - content_service
         environment:
           - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
           - CONTENT_SERVICE_URL=http://content_service:8000
         ports:
           - "8002:8000"
       
       essay_lifecycle_worker:
         build: ./services/essay_lifecycle_service
         command: pdm run start_worker
         depends_on:
           - kafka_topic_setup
           - content_service
       ```

    3. **Environment Configuration**: Docker environment setup:
       * Separate HTTP and worker containers
       * Shared volume for SQLite database (development)
       * Proper service dependencies and startup order

* **Acceptance Criteria**:
  * ELS containers build successfully
  * Service starts properly in Docker environment
  * HTTP API accessible from other containers
  * Worker processes Kafka events correctly

---

## E. Documentation and Service README

### E.1. Service Documentation [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Create comprehensive service documentation following project standards.
* **README.md Link/Rationale**: Supports **Service Autonomy** through clear documentation, enables team collaboration.

* **Implementation Tasks**:
    1. **Service README**: Create `services/essay_lifecycle_service/README.md` with:
       * Service purpose and responsibility within bounded context
       * Key domain entities (EssayState, processing pipeline)
       * Events consumed and produced
       * HTTP API overview
       * Local development setup instructions
       * Testing instructions

    2. **API Documentation**: Generate OpenAPI spec and provide:
       * Endpoint descriptions and examples
       * Request/response schemas
       * Error codes and handling
       * Authentication requirements (future)

    3. **Architecture Documentation**: Document:
       * State transition diagrams
       * Event processing flow
       * Data persistence strategy
       * Service integration patterns

* **Acceptance Criteria**:
  * Complete service README following project standards
  * API documentation with clear examples
  * Architecture diagrams and flow documentation
  * Development and deployment instructions

---

## F. Success Metrics and Validation

### F.1. Service Validation Checklist [NOT STARTED]

* **Status**: NOT STARTED
* **Objective**: Validate ELS implementation meets all architectural requirements and quality standards.

* **Validation Criteria**:
    1. **Architectural Compliance**:
       * ✅ Service follows DDD bounded context principles
       * ✅ Proper event-driven communication patterns
       * ✅ Explicit Pydantic contracts for all interactions
       * ✅ Service autonomy maintained

    2. **Technical Quality**:
       * ✅ All linting and type checking passes
       * ✅ Test coverage above 90%
       * ✅ Proper error handling and logging
       * ✅ Performance meets requirements

    3. **Integration Quality**:
       * ✅ Kafka event processing working correctly
       * ✅ HTTP API responses properly formatted
       * ✅ Docker containers start and run reliably
       * ✅ Service integrates with existing infrastructure

    4. **Documentation Quality**:
       * ✅ Service README complete and accurate
       * ✅ API documentation available
       * ✅ Code properly documented with docstrings
       * ✅ Architecture decisions documented

* **Acceptance Criteria**:
  * All validation checkpoints pass
  * Service ready for Phase 2 integration
  * Team can develop and deploy service independently
  * Service provides foundation for NLP and AI feedback processing

---

**Dependencies**:

- **Prerequisite**: Phase 1.2 Δ tasks (Δ-1: Protocols, Δ-2: DI wiring) must be completed
- **Related**: Content Service and Spell Checker Service for integration patterns
- **Follow-up**: Phase 2 NLP Service and AI Feedback Service will consume ELS events

**Estimated Effort**: 3-4 development days
**Priority**: High (blocks Phase 2 development)
**Risk Level**: Medium (new service, complex state management)
