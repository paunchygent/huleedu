# HuleEdu Microservice Platform

HuleEdu is an educational technology platform for automated essay processing and assessment. It is built as a collection of specialized microservices orchestrated into a unified workflow for tasks such as file ingestion, text content storage, spell checking, and AI-based comparative judgment of student essays.

The system has been rebuilt from a legacy monolithic application into a modern event-driven microservice architecture to improve scalability, maintainability, and clear separation of concerns. All services and shared components reside in a single monorepo for synchronized development.

This document provides a technical overview of the system architecture, usage guidelines for developers, development standards, current implementation status, and planned future enhancements.

## Architecture and Design

### Core Architectural Principles

#### Domain-Driven Design (DDD)

The platform is divided into services by bounded context. Each microservice owns its domain logic and data store. Service boundaries are strictly enforced (no direct database access across services, no tightly coupled logic).

#### Event-Driven Architecture (EDA)

Microservices communicate through asynchronous events via Kafka with a clean three-layer separation:

**Internal Domain Events**: Service-to-service coordination only, never consumed by WebSocket service
**Teacher Notification Events**: Single `TeacherNotificationRequestedV1` event type for all teacher notifications
**Notification Projectors**: Each service owns notification decisions through dedicated projectors using canonical direct invocation pattern (no Kafka round-trip)

The platform implements a **dual-phase processing architecture**:

- **Phase 1 (Pre-readiness)**: Student matching for REGULAR batches via event routing
- **Phase 2+ (Pipeline Processing)**: Multi-phase essay analysis with stateful coordination

#### Explicit Data Contracts

All inter-service communication models (event payloads, API request/response schemas) are defined as versioned Pydantic models in a shared `common_core` library. A standardized `EventEnvelope` wrapper is used for all Kafka events to provide metadata (timestamps, origin, schema version, correlation IDs, etc.) and ensure compatibility across services.

#### Service Autonomy

Each service is independently deployable and has its own data persistence. One service will never directly query or write to another service's database; any data sharing occurs via published events or well-defined internal APIs. This autonomy allows services to scale and evolve in isolation.

#### Asynchronous I/O

All services are written using Python's `async`/`await` and asynchronous frameworks:

- **Web Services**: Quart or FastAPI
- **Kafka Clients**: aiokafka
- **Database Access**: async SQLAlchemy

Non-blocking I/O ensures that each service can handle high concurrency efficiently.

#### Dependency Injection (DI)

The codebase employs a custom DI framework (Dishka) to invert dependencies and facilitate testing. Each service defines abstract interfaces (`typing.Protocol` classes in a `protocols.py`) for its key operations or external interactions. Concrete implementations are provided and wired at runtime via a DI container (see each service's `di.py`). This ensures business logic depends on interfaces, making components swappable and modular.

#### Configurable via Environment

Services use Pydantic `BaseSettings` classes (in each service's `config.py`) to load configuration from environment variables (with support for `.env` files in development). This centralizes configuration (e.g. database URLs, API keys, service ports) and makes services twelve-factor compliant. No configuration values are hard-coded; all are injected via environment or configuration files.

#### Comprehensive Observability Stack

HuleEdu implements a production-grade observability architecture with multiple integrated components:

**Core Observability Libraries** (`huleedu_service_libs`):
- **Structured Logging**: `logging_utils` with `configure_service_logging()` and `create_service_logger()`
- **Distributed Tracing**: OpenTelemetry-based tracing with Jaeger backend and W3C Trace Context propagation
- **Metrics Collection**: Prometheus-format metrics via `metrics_middleware` with standard service metrics
- **Health Monitoring**: `database.health_checks` with `DatabaseHealthChecker` for dependency monitoring
- **Error Handling**: Structured error system using `HuleEduError` with automatic OpenTelemetry span recording

**Infrastructure Stack** (Docker Compose):
- **Grafana** (port 3000): Dashboards and visualization
- **Prometheus** (port 9091): Metrics collection and alerting  
- **Jaeger** (port 16686): Distributed tracing UI
- **Loki** (port 3100): Log aggregation with Promtail
- **Alertmanager** (port 9094): Alert routing and management

**Standard Service Integration**:
- `/healthz` endpoints with dependency checks and structured responses
- `/metrics` endpoints with Prometheus-format service and business metrics
- Automatic correlation ID propagation across all telemetry (logs, traces, metrics)
- Circuit breaker metrics and database connection pool monitoring

## Monorepo Structure

The repository is organized as a monorepo managed by PDM (Python Dependency Manager),
containing all services and shared code in one place for easy coordination:

- **`common_core/`** – Shared Python package defining common data models and enums used
  across services. This includes Pydantic models for events and API DTOs (Data Transfer Objects),
  standardized enumerations (e.g., for statuses, error codes), and the base event envelope format.
  This library is the source of truth for inter-service data contracts.

- **`services/`** – Directory holding all microservices, each in its own sub-folder. For example:
  - `services/content_service/`
  - `services/spellchecker_service/`
  - `services/batch_orchestrator_service/`
  
  (See Microservices Overview below for details on each service)

- **`services/libs/`** – Shared service libraries (internal utility packages). These include common
  infrastructure code such as Kafka client wrappers, Redis clients, and logging/monitoring helpers
  that are used by multiple services.

- **`scripts/`** – Utility and setup scripts for development and operations. Notable scripts include:
  - `setup_huledu_environment.sh` – Bootstraps the development environment (installs PDM if
    missing, then installs all packages in the monorepo).
  - `kafka_topic_bootstrap.py` – Script to create all required Kafka topics (run automatically on
    startup in Docker Compose).
  - Other convenience scripts for Docker orchestration and testing (e.g., `docker-rebuild.sh`,
    `validate_batch_coordination.sh`).

- **`documentation/`** – Design and planning documents. This includes product requirement docs
  (PRDs), architecture decision records, and task breakdowns for major development phases. For
  example, the `SERVICE_FUTURE_ENHANCEMENTS/` and `TASKS/` subfolders contain specs and
  implementation notes for new features and phases of the project.

- **`.windsurf/rules/`** – The repository's development standards and rules in machine-readable
  Markdown format. Each rule file (e.g., coding standards, service architecture requirements,
  testing practices) is kept here. The master index `000-rule-index.mdc` lists all rules. These rules are
  used to ensure consistency and quality across the codebase (often enforced via review or
  tooling).

## Microservices Overview

The HuleEdu platform is composed of multiple microservices, each responsible for a specific aspect of
the overall system. All services are implemented in Python (>=3.11) and use asynchronous frameworks.

They communicate via Kafka events and occasional internal HTTP calls. Below is a brief overview of each
service and its role:

### Content Service

A Quart-based HTTP service for binary content storage and retrieval. It handles storing essay files or text in a filesystem-based repository (local disk for development; could be S3 or similar in production). It exposes a simple REST API on port 8001 (e.g., `POST/GET /v1/content` for uploading or fetching content by ID). Other services (like File Service and Essay Lifecycle) use this service to persist and retrieve raw text or file contents.

### File Service

A Quart-based HTTP service (port 7001) that handles file uploads and content ingestion workflow using a **Strategy Pattern** for multi-format text extraction. The service accepts multipart file uploads via `POST /v1/files/batch` and supports `.txt`, `.docx`, and `.pdf` files with extensible architecture for additional formats. Each uploaded file undergoes strategic text extraction (UTF-8 decoding, python-docx parsing, or pypdf processing), content validation, and reliable storage via the Content Service.

The service implements a **TRUE Outbox Pattern** with its own PostgreSQL database for guaranteed event delivery, where all events are stored in the outbox database table first, then asynchronously published to Kafka by a dedicated relay worker for transactional safety. It serves as the entry point for essay data with comprehensive error handling including encrypted PDF detection and structured error reporting.

### Essay Lifecycle Service (ELS)

A hybrid service with both an HTTP API (port 8000) and a Kafka event consumer component that manages essay processing coordination and state management. ELS operates in two distinct modes depending on the processing phase.

**Phase 1 Behavior (Student Matching):**

- Acts as a **stateless event router** - publishes events without updating essay states
- Receives `BatchServiceStudentMatchingInitiateCommandDataV1` from BOS, routes to NLP Service
- Receives `StudentAssociationsConfirmedV1` from CMS, publishes `BatchEssaysReady` to BOS
- No essay state changes during Phase 1 to prevent race conditions

**Phase 2+ Behavior (Pipeline Processing):**

- **Stateful operation** using formal `EssayStateMachine` (via `transitions` library)
- Manages essay state transitions through processing phases
- Receives batch commands (e.g., `BatchSpellcheckInitiateCommand`) and updates essay states
- Coordinates with specialized services (Spellchecker, CJ Assessment, etc.)

**Core Architecture:**

- **Slot Assignment**: Coordinates content provisioning with batch slot management
- **Command Processing**: Routes BOS commands to appropriate services
- **State Management**: Uses mock repository implementation similar to BOS architecture
- **Event Publishing**: Implements transactional outbox pattern for guaranteed delivery

**Key Features:**

- **Dual Mode Operation**: Stateless routing (Phase 1) vs stateful processing (Phase 2+)
- **Batch Coordination**: Tracks batch readiness and essay provisioning
- **Pipeline Orchestration**: Manages multi-phase essay processing workflows
- **Race Condition Prevention**: Stateless Phase 1 prevents premature state transitions

### Batch Orchestrator Service (BOS)

A Quart-based HTTP service (port 5000) that coordinates processing at the batch level and implements the **batch type decision logic** for GUEST vs REGULAR processing flows. BOS serves as the central orchestrator that routes batches through appropriate processing pipelines based on batch characteristics.

**Batch Type Decision Logic:**

- **GUEST Batches** (no class_id): Skip Phase 1 student matching → direct to pipeline processing
- **REGULAR Batches** (has class_id): Require Phase 1 student matching → human validation → pipeline processing

**Processing Flow:**

1. **Content Readiness**: Receives `BatchContentProvisioningCompletedV1` from ELS
2. **Batch Type Decision**: Examines batch context to determine GUEST vs REGULAR flow
3. **Phase 1 Coordination** (REGULAR only): Initiates student matching via `BatchServiceStudentMatchingInitiateCommandDataV1`
4. **Validation Completion**: Processes `StudentAssociationsConfirmedV1` events, transitions to `STUDENT_VALIDATION_COMPLETED`
5. **Pipeline Readiness**: Transitions to `READY_FOR_PIPELINE_EXECUTION` after essays stored
6. **Phase 2+ Orchestration**: Coordinates multi-phase processing with specialized services

**State Machine:**

- `AWAITING_CONTENT_VALIDATION` → `AWAITING_STUDENT_VALIDATION` (REGULAR) / `READY_FOR_PIPELINE_EXECUTION` (GUEST)
- `AWAITING_STUDENT_VALIDATION` → `STUDENT_VALIDATION_COMPLETED`
- `STUDENT_VALIDATION_COMPLETED` → `READY_FOR_PIPELINE_EXECUTION`

**Key Features:**

- **Batch Type Routing**: Intelligent GUEST vs REGULAR flow determination
- **Phase 1 Coordination**: Manages student matching workflow for REGULAR batches
- **State Management**: Implements race condition prevention via intermediate states
- **Dynamic Pipeline**: Consults Batch Conductor Service for phase sequencing
- **Event-Driven**: Reacts to completion events to advance batch processing

### Batch Conductor Service (BCS)

An internal orchestration logic service (Quart-based, port 4002 for its API). BCS's responsibility is dynamic pipeline dependency resolution. BOS delegates to BCS when it needs to determine which phase of processing should happen next for a given batch.

BCS keeps track of what processing has been completed for each batch by consuming all relevant events (e.g., it listens to essay-level completion events from ELS and results from analysis services). Using this information, BCS computes whether the prerequisites for the next phase are satisfied. For example, if the pipeline is `Spell Checking -> Comparative Judgment`, BCS will ensure all essays in the batch have spellcheck results before allowing the BOS to trigger the Comparative Judgment phase.

BCS uses Redis as an in-memory store to manage batch state and coordinate complex transitions (employing atomic operations and optimistic locking via Redis transactions to avoid race conditions in concurrent event processing). It also provides an API (POST /internal/v1/pipelines/define) for BOS to request a pipeline resolution (this API returns the next phase or indicates completion). BCS implements robust error handling: if it detects an inconsistency or failure in phase progression, it can push a message to a Dead Letter Queue (DLQ) topic for later analysis. In summary, BCS adds intelligence to the orchestration process, enabling dynamic pipelines that adapt to real-time results and conditions.

### Spellchecker Service

A Kafka consumer microservice (no public HTTP API) dedicated to spelling and grammar analysis of essay text. This service listens on a Kafka topic (e.g. `huleedu.commands.spellcheck.v1`) for commands to spell-check a particular essay. Upon receiving a command, it retrieves the essay text (from Content Service or included in the event payload), then performs spell checking and linguistic error analysis. It incorporates both standard spell-checking (via libraries like `pyspellchecker`) and second-language (L2) error correction logic for non-native writing issues. After processing, it emits an `EssaySpellcheckCompleted` event containing the results (e.g. lists of errors found and corrections). The Spellchecker Service runs as an asynchronous worker and typically handles many essays in parallel from the event queue. It also exposes a Prometheus metrics endpoint (on a small HTTP server at port 8002) to report its operation status (e.g. number of essays processed, processing duration, etc.). This service is a key part of the first phase in the essay processing pipeline.

**Key Features:**

- **Event-Driven**: Listens on Kafka topic `huleedu.commands.spellcheck.v1`
- **Language Support**:
  - Standard spell-checking (using libraries like `pyspellchecker`)
  - Second-language (L2) error correction for non-native writing
- **Asynchronous Processing**: Handles multiple essays in parallel
- **Monitoring**: Exposes Prometheus metrics endpoint on port 8002

**Workflow:**

- Receives spell-check command via Kafka
- Retrieves essay text from Content Service or event payload
- Performs linguistic analysis
- Emits `EssaySpellcheckCompleted` event with results

### Comparative Judgment (CJ) Assessment Service

A Kafka-driven service (with optional HTTP endpoints for health checks on port 9090) that performs AI-assisted comparative judgment of essays. In comparative judgment, essays are evaluated by comparing them in pairs. This service uses Large Language Model (LLM) APIs to generate pairwise comparisons or scores between essays in a batch. It listens on a Kafka topic (e.g. `huleedu.commands.cj_assess.v1`) for commands to assess a batch or a pair of essays. Internally, the CJ service interacts with the LLM Provider Service (described below) to obtain AI-generated judgments in a resilient way. It may break a large task (ranking a whole batch of essays) into many pairwise comparison queries to the LLM provider. The service collates the results (e.g. which essays won comparisons) and from these produces a ranked list or scores for all essays in the batch. Once comparative assessment for the batch is complete, it emits a `BatchComparativeJudgmentCompleted` event with the outcome (e.g. relative rankings or scores for each essay). This event can then be used by other components (Result Aggregator or BOS) to finalize the batch results. The CJ Assessment Service uses a PostgreSQL database to store intermediate results and ensure consistency (especially since LLM calls may be slow or need retries). Metrics and health endpoints are available (on `/metrics` and `/healthz`) for monitoring. This service enables automated scoring or ranking of essays using AI, providing the core of the grading or feedback mechanism.

**Key Features:**

- **Port**: 9090 (HTTP endpoints for health checks and metrics)
- **Event-Driven**: Listens on Kafka topic `huleedu.commands.cj_assess.v1`
- **AI Integration**: Uses LLM Provider Service for pairwise comparisons
- **Data Persistence**: PostgreSQL database for storing intermediate results
- **Monitoring**:
  - `/metrics` endpoint for Prometheus
  - `/healthz` endpoint for health checks

**Workflow:**

- Receives assessment command via Kafka
- Breaks down batch assessment into pairwise comparisons
- Uses LLM Provider Service for AI judgments
- Collates results into ranked list or scores
- Emits `BatchComparativeJudgmentCompleted` event with outcomes

### LLM Provider Service

A specialized Quart-based HTTP service (port 8080) that acts as a gateway and queue for calls to external Large Language Model providers. Multiple services in the platform (especially the CJ Assessment and future AI-driven services) need to call external AI APIs (like OpenAI, Anthropic, etc.). Instead of each service handling these calls (which can be slow or have rate limits), the LLM Provider Service centralizes this function.

**Event-Driven Architecture**: The service follows HuleEdu's event-driven patterns - consumer services make HTTP requests with a `callback_topic` parameter specifying where completion events should be published. For immediate results, the service returns HTTP 200 with the response. For queued requests (when providers are at capacity), it returns HTTP 202 and publishes `LLMComparisonResultV1` events to the specified Kafka topic when processing completes.

**Resilience Features**: Requests are queued in Redis and processed asynchronously. The service implements circuit breakers and fallback strategies - if one AI provider fails, it switches to alternative providers. The Redis-based queue survives provider outages and service restarts, ensuring reliable AI request processing without requiring consumers to poll for results.

The LLM Provider Service supports multiple AI providers (OpenAI, Anthropic, Google PaLM, OpenRouter, etc.) through a unified interface, and does no caching of responses (each request passes through to preserve the psychometric validity of CJ assessments). It uses Redis both for queuing requests and as a short-term results store. This service is critical for any AI-driven feature in HuleEdu, ensuring those features are robust and scalable.

**Key Features:**

- **Centralized AI API Management**:
  - Handles rate limiting
  - Implements circuit breakers
  - Provides fallback strategies
- **Asynchronous Processing**: Uses Redis for request queuing
- **Multi-Provider Support**: Works with OpenAI, Anthropic, and other LLM providers

**API Endpoints:**

- `POST /api/v1/comparison` - Submit AI comparison request with `callback_topic` for event-driven completion notification
- `GET /api/v1/status/{queue_id}` - Operational monitoring endpoint (production consumers use Kafka events)
- `GET /api/v1/results/{queue_id}` - Operational monitoring endpoint (production consumers use Kafka events)

**Resilience Features:**

- Automatic retries for failed requests
- Load balancing across multiple AI providers
- Graceful degradation when providers are unavailable

### NLP Service

A Kafka-driven worker service that operates in dual phases for both student matching and text analysis. This service handles batch-level processing with parallel execution and partial failure handling. The service uses PostgreSQL database for outbox pattern implementation to ensure reliable event delivery.

**Phase 1: Student Matching (Pre-readiness)**

- Receives `BatchStudentMatchingRequestedV1` events from ELS
- Extracts student identifiers from essay text using multiple strategies (Exam.net format, header patterns, email anchors)
- Matches extracted names against class rosters using fuzzy matching algorithms  
- Returns `BatchAuthorMatchesSuggestedV1` events to Class Management Service with confidence scores

**Phase 2: Text Analysis (Post-readiness)**

- Receives `BatchNLPInitiateCommandV1` events from ELS
- Performs linguistic analysis on essays (readability, complexity, features)
- Returns analysis results for downstream processing

**Key Features:**

- **Dual-Phase Architecture**: Student matching (Phase 1) + text analysis (Phase 2)
- **Batch Processing**: Processes entire batches with parallel execution (asyncio.Semaphore(10))
- **Extraction Pipeline**: Multiple text extraction strategies with confidence thresholds
- **Language Support**: Swedish name patterns and multi-language text analysis
- **Partial Failure Handling**: Continues processing with failed essays marked appropriately
- **Performance**: <100ms per essay, <10s for 30-essay batches, max 100 essays per batch

### Class Management Service (CMS)

A Quart-based HTTP CRUD service (port 5002) that manages metadata about classes, students, and their enrollment relationships. It serves as the authoritative source for user domain data and handles Phase 1 student matching validation.

**Core Responsibilities:**

- Class and student enrollment management via REST API (`/v1/classes`, `/v1/students`)
- Phase 1 student matching: receives NLP suggestions via `BatchAuthorMatchesSuggestedV1` events
- Association timeout monitoring: auto-confirms pending associations after 24 hours

**Phase 1 Student Matching:**

- **Association Timeout Monitor**: Auto-confirms pending student-essay associations after 24-hour timeout
- **High Confidence (≥0.7)**: Confirms association with original student using `TIMEOUT` validation method
- **Low Confidence (<0.7)**: Creates UNKNOWN student with email `unknown.{class_id}@huleedu.system`
- **Database Fields**: `batch_id`, `class_id`, `confidence_score`, `validation_status`, `validation_method`

**Key Features:**

- **Authoritative Source**: Single source of truth for user domain data
- **Phase 1 Integration**: Processes NLP student matching suggestions
- **Automated Validation**: 24-hour timeout with confidence-based decision logic
- **REST API**: Full CRUD operations for classes and students
- **Database**: PostgreSQL with Phase 1 association tracking fields

### Result Aggregator Service (RAS)

A hybrid service (Kafka consumer + publisher with HTTP API on port 4003) that aggregates results and coordinates service communication through event publishing.

**Key Features:**

- **Event Aggregation**: Consumes completion events from processing services
- **Event Publishing**: Publishes batch completion and assessment events via transactional outbox
- **Teacher Notifications**: Projects result events to teacher notifications using direct projector invocation
- **Query API**: Provides optimized access to batch and essay results
- **Cache Management**: Redis-based optimization with active invalidation

### API Gateway Service

A FastAPI-based gateway service (port 4001) that serves as the unified entry point for external clients (e.g., a Svelte frontend or third-party applications).

**Core Responsibilities:**

- **Authentication**: Validates JWT tokens for incoming requests
- **Request Validation**: Uses Pydantic models from `common_core`
- **Rate Limiting**: Protects backend services from excessive traffic
- **Request Routing**: Proxies requests to appropriate internal services
- **Event Publishing**: Publishes client requests as Kafka events
- **WebSocket Support**: Enables real-time updates for clients
- **Anti-Corruption Layer**: Translates between internal and client-facing data models

### WebSocket Service

A pure notification router (port 8080) that manages persistent WebSocket connections and delivers teacher notifications through a clean architectural pattern.

**Key Features:**

- **Pure Notification Router**: Consumes only `TeacherNotificationRequestedV1` events, never internal domain events
- **Teacher-Centric**: All notifications routed to teachers with proper authorization validation
- **Real-Time Delivery**: Immediate teacher feedback via Kafka → WebSocket → Redis pipeline
- **Clean Separation**: No business logic, trusts service-validated teacher_id in notification events

## Technology Stack

HuleEdu leverages a modern Python-based tech stack and tooling:

### Core Technologies

#### Python 3.11+

- Primary programming language for all services
- Chosen for its rich ecosystem and async support

#### Web Frameworks

- **Quart**: ASGI-compatible Flask variant used for most HTTP services
- **FastAPI**: Used for API Gateway and lightweight APIs
  - High performance
  - Built-in data validation
  - Async route handlers
  - Automatic OpenAPI documentation

#### Data Validation & Serialization

- **Pydantic**:
  - Defines schemas for configuration and data models
  - Validates all request/response bodies
  - Ensures data consistency across services
  - Used for Kafka event payloads

#### Event Streaming

- **Apache Kafka**:
  - Backbone of event-driven architecture
  - Uses `aiokafka` for Python clients
  - Provides scalable, durable message queuing
  - Enables asynchronous workflows
  - Supports event replay and ordering

### Database Solutions

#### Database Architecture Pattern

**All HuleEdu services follow a consistent database pattern:**

- **Production**: PostgreSQL with service-specific databases
- **Development/Testing**: Mock repository implementations (in-memory)
- **No SQLite**: Services do not use SQLite in any environment

**Services with Databases:**

- **PostgreSQL Production Databases**: Class Management, Result Aggregator, CJ Assessment, File Service (outbox), NLP Service (outbox), Essay Lifecycle Service
- **Mock Repository Pattern**: All services use mock implementations for development and testing that follow the same interface contracts as production PostgreSQL implementations

### ORM & Database Access

#### SQLAlchemy

- Async ORM for database operations
- Provides abstraction layer over SQL
- Enables database-agnostic code
- Supports migrations and schema management

### Redis

In-memory data store used for caching and transient data coordination.

**Key Use Cases:**

- **Batch Coordination**: Maintains batch state and critical section locks (using WATCH/MULTI transactions)
- **Request Queuing**: Used by LLM Provider and API Gateway
- **Rate Limiting**: Enforces request rate limits
- **Caching**: Speeds up frequent queries (e.g., in RAS)

- Atomic operations for data consistency
- Pub/sub capabilities for event-driven patterns
- Low-latency performance
- Built-in concurrency control

### Dishka (Dependency Injection)

Custom DI framework integrated with Quart (`quart_dishka`) for managing service components.

**Key Features:**

- **Loose Coupling**: Binds implementations to interfaces at runtime.
- **Test-Friendly**: Simplifies testing by allowing easy swapping of implementations.
- **Clean Architecture**: Supports clean architecture patterns through dependency inversion.

**Usage Example:**

```python
# Service definition
class DatabaseService(Protocol):
    def get_data(self) -> Data: ...

# Production implementation
class PostgresDatabaseService(DatabaseService):
    def get_data(self) -> Data:
        # Implementation using PostgreSQL
        pass

# Test implementation
class MockDatabaseService(DatabaseService):
    def get_data(self) -> Data:
        # Mock implementation for testing
        return TestData()
```

## Containerization & Orchestration

### Docker & Docker Compose

**Key Features:**

- Containerization of all services and dependencies
- Consistent runtime environments
- Simplified local development and testing
- Production-parity in development

**Components:**

- **Dockerfiles**: One per microservice
- **docker-compose.yml**: Central configuration for all services
- **Dependencies**:
  - Kafka
  - Zookeeper
  - Redis
  - PostgreSQL

## Development Tools

### PDM (Python Dependency Manager)

PDM is used to manage Python packages in our monorepo. It provides several key benefits:

- **Editable Packages**: Each service can be installed as an editable package
- **Unified Lockfile**: Single source of truth for all dependencies
- **Task Runner**: Built-in support for common development tasks
- **Modern Workflow**: Replaces traditional tools like pip/venv and Makefiles

**Common Commands:**

```bash
# Install dependencies
pdm install

# Run tests
pdm run test

# Run linter
pdm run lint

# Run formatter
pdm run format
```

### Ruff (Linter & Formatter)

Ruff is a fast Python linter and code formatter configured for the project. It enforces coding style (PEP8 compliance, import sorting, etc.) and can automatically apply simple formatting fixes.

The project uses Ruff to:

- Flag style and syntax issues
- Automatically format code (via `pdm run format-all`)
- Enforce consistent code style across the codebase
- Speed up code reviews by catching issues early

### MyPy (Static Type Checker)

MyPy is used throughout the codebase to ensure type safety and catch potential issues at development time.

**Key Benefits:**

- Full type hinting support
- Catches type errors before runtime
- Ensures interface contracts are maintained
- Improves code quality in a large codebase
- Works well with protocols and dependency injection

### PyTest (Testing Framework)

PyTest is the testing framework used for all automated tests in the project.

**Testing Strategy:**

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Verify interactions between components
- **Contract Tests**: Ensure events and APIs conform to expected schemas
- **End-to-End Tests**: Test complete workflows

**Features:**

- Run tests via `pdm run test-all`
- Support for testing with real dependencies
- Temporary database and Kafka instances for testing
- Extensive use of fixtures for test setup
- Plugins for async testing and code coverage

## Development Setup and Usage

This section provides instructions for developers who want to set up, run, or extend the system locally.

### Prerequisites

- **Python 3.11 or above** - Required for running the services and tools
- **Docker with Docker Compose** - Required for running dependencies in containers
- **PDM** - Python Dependency Manager (will be installed automatically if missing)

### Initial Environment Setup

1. Clone the repository to your local machine:

   ```bash
   git clone <repository-url>
   cd huledu-reboot
   ```

2. Run the setup script to install dependencies:

   ```bash
   ./scripts/setup_huledu_environment.sh
   ```

   This script will:

   - Install PDM if not already present
   - Set up a virtual environment (`.venv`)
   - Install all Python dependencies
   - Register each service package in development mode
   - Configure pre-commit hooks

   > **Note:** The project uses PDM instead of pip or Poetry. Do not use `pip install .` directly.
   > The setup script and `pdm install` ensure the correct environment. All commands below assume
   > the PDM-managed virtual environment is active (the setup script activates it automatically, or you
   > can run `pdm shell` manually).

## Running the Full System with Docker Compose

The recommended way to run all microservices together (along with required infrastructure like Kafka)
is using Docker Compose. PDM provides helper scripts to simplify this process.

### Building Service Images

From the project root, build the Docker images for all microservices:

```bash
pdm run docker-build
```

This command will:

1. Build all service images in parallel
2. Tag them with the current branch name and `latest`
3. Cache intermediate layers for faster subsequent builds

This will use the Dockerfiles in each service directory to create images tagged for this project. It may take some time on first build as it installs OS packages and Python dependencies inside the images.

### Launching Services with Docker Compose

To start all services, run:

```bash
pdm run docker-up
```

This command starts the Docker Compose stack defined in `docker-compose.yml`. It will spin up:

**Core Services:**

- Zookeeper and Kafka brokers (for the event bus)
- Redis (for BCS state and LLM queue)
- PostgreSQL (with separate databases for services)
- Kafka topic initializer container (runs once at startup)

**HuleEdu Microservices:**

- Content Service
- File Service
- Essay Lifecycle Service (ELS)
- Batch Orchestrator Service (BOS)
- Batch Conductor Service (BCS)
- NLP Service (dual-phase student matching + text analysis)
- Spellchecker Service
- CJ (Comparative Judgment) Service
- LLM Provider Service
- Class Management Service (CMS)
- Result Aggregator Service (RAS)
- API Gateway Service
- WebSocket Service

### Verifying the Deployment

Once started, services run in the background (detached mode). You can verify they're running by:

1. Checking container status:

   ```bash
   docker-compose ps
   ```

2. Accessing health endpoints:
   - BOS: `http://localhost:5000/healthz`
   - ELS: `http://localhost:8000/healthz`
   - API Gateway: `http://localhost:4001/health`
   - Content Service: `http://localhost:8001/healthz`
   - File Service: `http://localhost:7001/healthz`

### Interacting with the System

Once all containers are up, you can:

1. **Upload Files**:
   - Use the File Service API
   - Or go through the API Gateway

2. **Process Batches**:
   - Trigger batch processing via the BOS API

3. **Monitor Activity**:
   - Observe logs and events
   - Check service metrics and health

For development and testing, you can use the provided scripts or write unit/integration tests. See individual service README files for specific API documentation and examples.

### Shutting Down

To stop all services:

```bash
pdm run docker-down
```

This will:

- Stop and remove all containers
- Preserve data in volumes (PostgreSQL, file storage, etc.)
- Maintain configuration between restarts

### Additional Commands

- **View Logs**:

  ```bash
  pdm run docker-logs
  ```

- **Restart Services**:

  ```bash
  pdm run docker-restart
  ```

- **Remove Volumes** (use with caution):

  ```bash
  docker-compose down -v
  ```

**Note**: The `docker-restart` command combines `docker-down` and `docker-up`, which is useful when you've changed code and rebuilt images.

## Common Development Tasks

All routine development tasks are encapsulated in PDM scripts (see the `[tool.pdm.scripts]` section of `pyproject.toml`). Here are key commands to be run from the project root:

### Code Quality

- **Format Code**: `pdm run format-all` - Auto-format the codebase using Ruff's formatting rules
- **Lint Code**: `pdm run lint-all` - Run the linter (Ruff) on all files
- **Fix Lint Issues**: `pdm run lint-fix` - Automatically fix lint issues where possible
- **Type Checking**: `pdm run typecheck-all` - Execute MyPy across the monorepo

### Testing

- **Run All Tests**: `pdm run test-all` - Execute all tests for all services
- **Parallel Testing**: `pdm run test-parallel` - Force parallel execution (default)
- **Sequential Testing**: `pdm run test-sequential` - Run tests serially when needed

The test suite includes:

- Unit tests for each service
- Integration tests involving multiple services
- Contract tests for shared models

### Docker Workflow

In addition to `docker-up`/`docker-down` mentioned above:

- **Build Images**: `pdm run docker-build` - Build images after making changes
- **View Logs**: `pdm run docker-logs` - Stream logs from all containers
- **Restart All**: `pdm run docker-restart` - Quickly rebuild and relaunch all containers

### Kafka Topic Management

- **Setup Topics**: `pdm run kafka-setup-topics` - Create/reset Kafka topics manually

This runs the `scripts/kafka_topic_bootstrap.py` script to idempotently create all expected topics. Note that this is automatically done on `docker-up` via the compose file, so manual use is only needed in special cases (e.g., running Kafka outside Docker).

**Important**: Developers are expected to use these standardized commands to ensure consistency. Using the formatter and linter ensures code meets the project's style requirements before committing.

## Development Standards and Practices

Development of HuleEdu adheres to strict standards to maintain code quality, readability, and architectural consistency. These standards are documented in the internal rules (see the `.windsurf/rules/` directory) and enforced via tooling and code review:

### Coding Style and Format

- **Style Guidelines**: The codebase follows PEP 8 style guidelines, automatically enforced by Ruff
- **Lint Requirements**: All code must pass lint checks (no unused imports, consistent naming, etc.)
- **Auto-formatting**: Formatting issues should be fixed by the `format-all` command
- **File Size Limits**: Maximum of 400 lines of code per file is recommended to keep modules focused (checked by the linter)
- **Organization**: Descriptive naming and clear module organization are expected

### Static Typing

- **Full Annotation**: All functions, methods, and modules are fully type-annotated
- **Type Checking**: MyPy is used to ensure type correctness across the entire project
- **Maintenance**: Developers must update type hints as code evolves and resolve any MyPy warnings
- **Benefits**: Static typing catches many errors at build time and serves as up-to-date documentation for function interfaces

### Testing and CI

- **Test Requirements**: Every new feature or bug fix must include appropriate tests
- **Coverage Goals**: The project maintains high test coverage including:
  - Unit tests for logic
  - Integration tests for service interactions
  - Contract tests for checking that producers and consumers of events agree on schemas

Tests are run in continuous integration, and builds will fail if tests do not pass or if coverage regresses significantly. Developers are expected to run `pdm run test-all` locally before pushing changes. Additionally, integration tests spin up dependent services (often using Docker or in-memory fakes) to verify end-to-end behavior of critical flows.

### Documentation Updates

Keeping documentation in sync with the code is treated as part of the development process. When a change is made to a service or a core library, any relevant README, architectural document, or rule file must be updated in the same commit.

**Example**: If a new event type is introduced, its definition in `common_core` should be documented and any relevant service README should mention how the service uses that event.

The project's **Rule 090: Documentation Standards** requires that documentation be maintained as an integral part of development, and even minor changes should be reflected in docstrings or markdown docs as appropriate.

### Architectural Consistency

The project has defined patterns that each service must follow, detailed in the rules under `.windsurf/rules/`. Key requirements include:

- **HTTP Services**: Must use a blueprint structure (no route definitions directly in `app.py`)
- **Background Tasks**: All long-running tasks must be idempotent to support retries
- **Cross-Service Communication**: Must go through designated integration points (Kafka or internal APIs)

During code reviews, maintainers check for compliance with these patterns. Significant deviations are not allowed unless a new pattern is being proposed and documented. This ensures that the system remains homogeneous in its architecture and that developers can navigate code across services easily.

### Git Workflow

While no formal contribution guide is included here, the following practices are expected:

- **Pull Requests**: All contributions should go through pull requests with reviews
- **Commit Quality**: Commits should be granular and messages descriptive
- **Pre-commit Hooks**: The repository includes formatting/linting as a pre-commit hook (installed via `setup_huledu_environment.sh`) to catch issues early
- **Merge Requirements**: Merge decisions factor in passing CI checks (tests, lint, type check) and adherence to the above standards

## Current Status of Implementation

All core microservices of the HuleEdu platform have been implemented and integrated into a functioning system. The platform supports both anonymous (GUEST) and class-based (REGULAR) essay processing workflows with comprehensive student matching, automated validation, and real-time teacher notifications.

### Major Achievements

#### Phase 1 Student Matching Architecture

The platform implements a sophisticated **pre-readiness student matching system** for REGULAR batches:

- **NLP Service**: Dual-phase architecture supporting both student matching and text analysis
- **Association Timeout Monitor**: 24-hour auto-confirmation with confidence-based decision logic
- **UNKNOWN Student System**: Creates placeholder students for low-confidence matches
- **Race Condition Prevention**: Intermediate `STUDENT_VALIDATION_COMPLETED` state prevents premature pipeline execution

#### Batch Type Differentiation

**GUEST Batches**: Anonymous processing that bypasses student matching for immediate pipeline execution
**REGULAR Batches**: Class-based processing with complete Phase 1 student matching workflow

#### Dynamic Pipeline Orchestration

The multi-phase processing pipeline supports both batch types with intelligent routing. The Batch Orchestrator and Batch Conductor services work in tandem to support dynamic sequencing of phases based on batch characteristics.

#### Production Observability Implementation

The comprehensive observability stack provides full visibility into the distributed system:

- **Distributed Tracing**: OpenTelemetry with Jaeger backend enables end-to-end request tracing across service boundaries with W3C Trace Context propagation
- **Metrics Collection**: Prometheus scrapes standardized `/metrics` endpoints with service-specific metrics (HTTP requests, Kafka processing, database connections, circuit breaker states)
- **Health Monitoring**: `/healthz` endpoints include dependency checks using `DatabaseHealthChecker` for comprehensive service health assessment  
- **Structured Logging**: JSON-formatted logs with automatic correlation ID propagation enable tracing individual essays through the complete processing pipeline
- **Error Observability**: `HuleEduError` system automatically records exceptions to OpenTelemetry spans with full context and correlation tracking

#### Teacher Notification Architecture

Implemented clean notification projection pattern with complete E2E integration:

- **Separation of Concerns**: Internal domain events separate from teacher-facing notifications
- **Service Ownership**: Each service owns notification decisions through dedicated projectors
- **Canonical Pattern**: Direct projector invocation (no Kafka round-trip) for immediate notifications
- **Complete Integration**: 100% E2E test coverage with Kafka→WebSocket→Redis pipeline validation

**Infrastructure Components**:
- **Grafana**: Centralized dashboards and alerting interface
- **Prometheus**: Metrics storage with alerting rules via Alertmanager
- **Jaeger**: Distributed tracing UI for request flow analysis
- **Loki + Promtail**: Log aggregation and correlation with metrics/traces

This production-grade observability enables effective debugging, performance optimization, and operational monitoring across the microservice ecosystem.

#### WebSocket Teacher Notification Layer

Complete teacher notification system with clean architectural separation:

- **15 Notification Types**: Covering all critical, immediate, high, standard, and low priority events across services
- **Service Projectors**: Class Management, File Service, Essay Lifecycle, Batch Orchestrator, and Result Aggregator services each own their notification decisions
- **Canonical Pattern**: Direct projector invocation ensures immediate teacher feedback without Kafka round-trip delays
- **E2E Validation**: 100% test coverage of complete Kafka→WebSocket→Redis pipeline with all notification types
- **Clean Separation**: WebSocket service is pure notification router, consuming only teacher notification events, never internal domain events

#### Deployment and Containerization

All services run correctly in Docker containers, and the Docker Compose setup has been tested to ensure that a new developer or tester can bring up the entire system with minimal effort. The compose file handles:

- Inter-service networking
- Environment variable wiring
- Initialization tasks like topic creation

This means the system is effectively deployable on any Docker-compatible infrastructure. While not yet deployed to a cloud environment, the necessary pieces (Docker images, network configurations, volume declarations for data) are in place, reducing the effort to move to staging or production servers.
In summary, the HuleEdu platform’s current implementation represents a working “walking skeleton” of
the intended final system: all primary services are functional and integrated in the core workflow of
processing essays. The focus so far has been on back-end architecture correctness and robustness. The
system can handle the end-to-end scenario of a teacher uploading a batch of essays and receiving

analytical results. The foundation is laid for scaling up (both in terms of load and in terms of adding
features).

## Future Development Roadmap

While the core backend is in place, several additional services and features are planned to complete the platform’s capabilities and improve the user experience. These future developments include:

### AI Feedback Service (Planned)

A microservice that will generate individualized feedback for student essays using AI (LLM-based). This service would take an essay (after spellchecking, perhaps) and produce formative feedback (comments on grammar, structure, content relevance, etc.). It will likely use the LLM Provider Service to call an AI model with a prompt to generate feedback, and then emit an event with the feedback results. This service will add an “AI feedback” phase to the processing pipeline, complementing the comparative judgment score with qualitative feedback for the student.

### Enhanced NLP Analytics (Planned)

Extensions to the existing NLP Service to compute additional linguistic metrics on essays. The current NLP Service handles Phase 1 student matching and basic Phase 2 text analysis. Planned enhancements include readability scores, vocabulary complexity analysis, sentence length variance, and plagiarism detection. These computationally intensive analyses would extend the existing Phase 2 text analysis capabilities, with results consumed by the Result Aggregator for comprehensive reporting.

### User Management Service (Planned)

Currently, user and authentication concerns (beyond class/student relationships) are not central. A future User Service will handle platform users (teachers, students, admins), authentication credentials, and roles/permissions. This service would integrate with the API Gateway to provide JWT authentication and would manage login sessions, password resets, etc. This is crucial for a production deployment where multiple schools or institutions might use the platform with separate accounts and data isolation.

### Svelte Frontend Application (In Development)

A modern web frontend (likely built with Svelte) is planned to allow educators and students to interact with HuleEdu. Through the frontend, teachers could upload batches of essays, track processing progress in real time, and review results (scores, feedback) once ready. Students might use it to submit assignments and view feedback. The frontend will communicate exclusively with the API Gateway service. Development of the UI will focus on providing a clean user experience and real-time updates via WebSockets (for example, to show a teacher a live status of their batch processing: “spellchecking 10/30 essays completed…”).

### CJ Assessment Calibration System (Planned)

As the platform relies on AI for scoring (CJ Assessment Service), we are implementing an integrated online check-and-balance system that operates within the CJ Assessment Pipeline itself. This system employs machine learning algorithms similar to traditional Automated Essay Scoring (AES) random forest models to continuously validate and calibrate AI-generated judgments in real-time. The calibration system is directly linked to the NLP Service, which continuously analyzes essays and is intermittently retrained on the growing corpus of submitted student essays using established AES text metrics and essay quality markers.

Unlike traditional offline analytics approaches, this online system provides immediate feedback during the assessment process, flagging potential anomalies (such as essays that appear inconsistent with their assigned rankings) and generating adjustment factors that can be applied by Result Aggregator Service The system produces calibration reports and reliability metrics that can be fed back into the scoring algorithm or presented to instructors for review, ensuring continuous improvement of assessment accuracy and maintaining trust in the AI-generated results.

### Additional Pipeline Phases - NLP Phase and AI Feedback

Beyond Spellcheck, CJ, and AI feedback, other analysis phases can
be incorporated into the pipeline. For example, an NLP Phase will extract additional metrics from the essays, such as readability scores, vocabulary complexity analysis, sentence length variance, and plagiarism detection. These computationally intensive analyses would extend the existing Phase 2 text analysis capabilities, with results consumed by the Result Aggregator for comprehensive reporting and downstream use by Client-> Teacher-> Student. and the planned AI Feedback Service (TASKS/AI_FEEDBACK_SERVICE_IMPLEMENTATION.md)

 The architecture is built to accommodate new phases relatively easily by
adding new services and defining their events/contracts, so the roadmap is open-ended about
integrating more AI/NLP capabilities as the product evolves. Scaling and Performance – As usage grows, certain components may need to be scaled out or
refactored. Future work will include performance optimizations such as: using Kafka consumer
groups to allow multiple instances of worker services (Spellchecker, CJ, etc.) to share load; scaling the API Gateway and other HTTP services horizontally behind a load balancer; optimizing

database interactions (adding indexes, caching frequently accessed data in RAS or CMS); and
possibly partitioning Kafka topics by class or school if needed to handle very large volumes.
While this is not a single feature, it is a continuous effort that will accompany the addition of
users to the platform.

### Cloud Deployment and CI/CD

To prepare for real-world use, the project plans to containerize and deploy on cloud infrastructure (e.g. Kubernetes or a container orchestration service). CI/CD pipelines will be set up to run tests, build images, and deploy to staging/production automatically upon merges. Infrastructure-as-code (Terraform or similar) might be introduced to manage cloud resources (databases, message broker, etc.). Though largely an operations task, this is on the roadmap to transition the project from a purely local-dev setup to a live service.

This roadmap is subject to refinement as the project progresses and user feedback is gathered.
However, it gives a clear direction: the immediate next steps focus on front-end integration (API
Gateway and Svelte UI), richer analysis features (AI feedback, NLP metrics), and robust user
management. These additions, combined with the strong backend foundation already in place, will
move HuleEdu toward a production-ready state suitable for pilot programs and eventually larger
deployments.

## Documentation and Further Information

This README provides a high-level overview of the HuleEdu platform. For more detailed information, consult the following resources:

### Service-Specific Documentation

- Each microservice has its own README file in its root directory (e.g., `/services/content_service/README.md`).
- These files contain detailed information about the service’s responsibilities, API endpoints (if applicable), configuration options, and specific deployment notes.
- If you are working on or using a particular service, refer to its README for in-depth information.

### Architecture & Design Documents

- The `documentation/` directory contains high-level design documents, product requirement documents (PRDs), and technical plans for various features.
- Notable files include detailed discussions of the state machine design, the reasoning behind certain architectural choices, and plans for future phases.
- These documents are useful for understanding the rationale behind the implementation and for onboarding new contributors to the system’s design philosophy.

### Architectural Decision Records (ADRs)

- Key architectural decisions are documented in ADRs, located in the `/docs/adr/` directory.
- These records explain the context, decision, and consequences for significant choices, such as the adoption of event-driven architecture, the selection of RabbitMQ, or the design of the processing pipelines.

### Development Rules

- The `.cursor/rules/` directory defines the project’s development rules and standards in a structured format.
- This covers everything from project structure conventions to coding style, error handling patterns, and documentation requirements.
- The `000-rule-index.mdc` file provides an index of all available rule files.
- Developers should familiarize themselves with these rules, as they codify best practices and are treated as part of the code review criteria.
- They also ensure that as the team grows, the codebase remains uniform and maintainable.

### Changelog

- The `CHANGELOG.md` or commit history can be consulted for a chronological record of major changes and feature additions.
- This can help in understanding how the system evolved to its current state.
