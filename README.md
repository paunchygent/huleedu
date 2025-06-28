# HuleEdu Monorepo - Reboot to Microservices

Welcome to the HuleEdu Monorepo! This project is a reboot of the HuleEdu platform, transitioning towards a modern microservice-based architecture. This README provides an overview of the project, its architecture, development setup, current status, and planned enhancements.

## Core Architectural Principles

The HuleEdu platform is built upon a set of core foundational principles to ensure scalability, maintainability, and architectural integrity:

* **Domain-Driven Design (DDD)**: Each microservice maps to a specific business domain (Bounded Context), owning its data and logic. Service boundaries are respected.
* **Event-Driven Architecture (EDA)**: Asynchronous, event-driven communication via Kafka is the primary method for inter-service collaboration. Synchronous API calls between services are minimized.
* **Explicit Contracts**: All inter-service data structures (event payloads, API DTOs) are defined as versioned Pydantic models residing in `common_core/src/common_core/`. The `EventEnvelope` structure is standardized for all events.
* **Service Autonomy**: Microservices are designed to be independently deployable, scalable, and updatable. Each service owns its data store, and direct access to another service's datastore is not permitted.
* **Async Operations**: Services are designed to use `async/await` for all I/O operations.
* **Dependency Injection (DI)**: Services utilize the Dishka DI framework. Business logic depends on abstractions (`typing.Protocol`) defined in `<service_name>/protocols.py`, rather than concrete implementations directly. Providers are defined in `<service_name>/di.py`.
* **Configuration**: Services use Pydantic `BaseSettings` for configuration, loaded from environment variables and `.env` files, as defined in `<service_name>/config.py`.
* **Logging**: Services employ the centralized logging utility from `huleedu_service_libs.logging_utils`. Use of the standard library `logging` module directly in services is avoided. Correlation IDs are used for tracing.

## Monorepo Structure Overview

The project is organized as a monorepo managed by PDM:

* **`common_core/`**: A shared Python package containing common Pydantic models for data contracts (events, API DTOs), enums, and shared metadata structures.
* **`services/`**: Contains the individual microservices.
  * **`libs/`**: Shared utility libraries for services, such as Kafka client wrappers and logging utilities.
  * Each service has its own directory (e.g., `content_service/`, `spell_checker_service/`).
* **`scripts/`**: Project-level scripts for tasks like environment setup and Kafka topic bootstrapping.
* **`Documentation/`**: Contains architectural documents, task tracking (like `TASKS/`), and setup guides.
* **`.cursor/rules/`**: Contains the detailed development rules and standards. The [000-rule-index.mdc](.cursor/rules/000-rule-index.mdc) serves as an index to all rules.

## Services

The HuleEdu ecosystem currently comprises the following services:

* **Content Service** ✅ **IMPLEMENTED**:
  * **Description**: A Quart-based HTTP service responsible for content storage and retrieval, using a local filesystem backend.
  * **Port**: 8001 (HTTP API)
  * **Location**: `services/content_service/`
  * **API**: `/v1/content` endpoints for storage and retrieval

* **Spell Checker Service** ✅ **IMPLEMENTED**:
  * **Description**: A Kafka consumer worker service that performs advanced spell checking on essays, including L2 error correction and standard spell checking using `pyspellchecker`. Integrated with Essay Lifecycle Service for essay slot coordination.
  * **Port**: 8002 (Metrics)
  * **Location**: `services/spell_checker_service/`
  * **Architecture**: Clean architecture with DI, protocols, language parameter support, and comprehensive test coverage

* **Batch Orchestrator Service** ✅ **IMPLEMENTED**:
  * **Description**: A Quart-based HTTP service that acts as the central coordinator, dynamically orchestrating essay processing workflows using a flexible pipeline definition and various phase initiators.
  * **Port**: 5001 (HTTP API)
  * **Location**: `services/batch_orchestrator_service/`
  * **API**: `/v1/batches` endpoints for batch registration and coordination

* **Essay Lifecycle Service (ELS)** ✅ **IMPLEMENTED**:
  * **Description**: A dual-mode service (HTTP API + Kafka worker) that manages individual essay states via a formal state machine (`EssayStateMachine`). It is responsible for reporting batch-level phase outcomes (including updated `text_storage_id`s) to BOS, enabling dynamic pipeline progression.
  * **Ports**: 6001 (HTTP API), 9091 (Metrics)
  * **Location**: `services/essay_lifecycle_service/`
  * **Database**: Follows a dual-repository pattern. The production implementation uses **PostgreSQL**, while SQLite is used for local development and testing.

* **File Service** ✅ **IMPLEMENTED**:
  * **Description**: A Quart-based HTTP service with Kafka event publishing for file upload handling, text extraction, and content ingestion coordination. Accepts multipart file uploads, processes files to extract text content, coordinates with Content Service for storage, and emits essay readiness events.
  * **Port**: 7001 (HTTP API), 9094 (Metrics)
  * **Location**: `services/file_service/`
  * **API**: `POST /v1/files/batch` for batch file uploads
  * **Status**: Fully implemented and integrated into the walking skeleton

* **CJ Assessment Service** ✅ **IMPLEMENTED**:
  * **Description**: A hybrid Kafka worker + HTTP API service for Comparative Judgment assessment of essays using Large Language Model (LLM) based pairwise comparisons. Features dynamic LLM configuration support with multi-provider capabilities (OpenAI, Anthropic, Google, OpenRouter).
  * **Port**: 9095 (Health API & Metrics)
  * **Location**: `services/cj_assessment_service/`
  * **API**: `/healthz` and `/metrics` endpoints for health checks and observability
  * **Database**: The primary implementation uses **PostgreSQL**, provisioned via `docker-compose.yml` and configured in the service's DI provider.

* **Batch Conductor Service (BCS)** ✅ **IMPLEMENTED**:
  * **Description**: An internal Quart-based microservice responsible for intelligent pipeline dependency resolution and batch state analysis. Features event-driven batch state projection via Kafka, atomic Redis operations for race condition safety, and comprehensive error handling with DLQ production.
  * **Port**: 4002 (Internal HTTP API)
  * **Location**: `services/batch_conductor_service/`
  * **API**: `/internal/v1/pipelines/define` for pipeline resolution, `/healthz` and `/metrics` endpoints
  * **Architecture**: Protocol-based DI with Dishka, event-driven architecture consuming spellcheck/CJ assessment completion events, Redis-cached state management with atomic WATCH/MULTI/EXEC operations

* **Class Management Service (CMS)** ✅ **IMPLEMENTED**:
  * **Description**: A Quart-based HTTP service acting as the authoritative source for managing classes, students, and their relationships. Provides a synchronous API for data management.
  * **Port**: 5002 (Internal HTTP API)
  * **Location**: `services/class_management_service/`
  * **API**: `/v1/classes` and `/v1/students` for full CRUD operations.

* **Result Aggregator Service (RAS)** ✅ **IMPLEMENTED**:
  * **Description**: A hybrid service (Kafka consumer + HTTP API) that aggregates processing results from all services into a materialized view. Provides fast, query-optimized access to batch and essay results for the API Gateway.
  * **Ports**: 4003 (Internal HTTP API), 9096 (Metrics)
  * **Location**: `services/result_aggregator_service/`
  * **API**: `/internal/v1/batches/{batch_id}/status` for comprehensive batch status queries
  * **Database**: PostgreSQL with normalized schema optimized for read queries
  * **Architecture**: CQRS pattern with event sourcing, Redis caching, and service-to-service authentication

## Key Technologies

* **Python**: Version 3.11+
* **PDM**: For Python dependency management and monorepo tooling.
* **Docker & Docker Compose**: For containerization and local service orchestration.
* **Quart**: Asynchronous web framework for HTTP-based services.
* **Pydantic**: For data validation, serialization, and settings management.
* **Kafka (via aiokafka)**: For event streaming and inter-service communication.
* **Ruff**: For code formatting and linting.
* **MyPy**: For static type checking.
* **Pytest**: For testing (unit, integration, contract).
* **Dishka**: For dependency injection.
* **PostgreSQL / SQLite**: For service data persistence.

## Development Environment Setup

1. **Prerequisites**:
    * Python 3.11 or higher.
    * PDM (Python Dependency Manager). If not installed, the setup script will attempt to install it.

2. **Automated Setup**:
    Run the environment setup script from the project root:

    ```bash
    ./scripts/setup_huledu_environment.sh
    ```

    This script installs PDM (if needed), monorepo tools, and all services in editable mode.

3. **IDE Configuration**:
    For a consistent development experience, it is recommended to configure VS Code / Cursor AI according to the [Cursor AI IDE Setup Guide](Documentation/setup_environment/CURSOR_IDE_SETUP_GUIDE.md). This includes setting up Ruff and MyPy extensions to align with project standards.

## Development Workflow & Tooling

The project uses PDM for managing dependencies and running common development tasks.

### Key PDM Scripts (run from project root)

* **Code Quality**:
  * `pdm run format-all`: Format all code with Ruff.
  * `pdm run lint-all`: Lint all code with Ruff.
  * `pdm run lint-fix`: Lint and auto-fix issues with Ruff.
  * `pdm run typecheck-all`: Type check all code with MyPy.
* **Testing**:
  * `pdm run test-all`: Run all tests using Pytest (optimized for parallel execution).
  * `pdm run test-parallel`: Explicitly run tests in parallel.
  * `pdm run test-sequential`: Run tests sequentially.
* **Docker Operations**:
  * `pdm run docker-build`: Build Docker images for all services.
  * `pdm run docker-up`: Start all services using Docker Compose in detached mode.
  * `pdm run docker-down`: Stop all services managed by Docker Compose.
  * `pdm run docker-logs`: Follow logs from all services.
  * `pdm run docker-restart`: Restart all services (down, then up with build).
* **Kafka Topic Management**:
  * `pdm run kafka-setup-topics`: Runs the `scripts/kafka_topic_bootstrap.py` script to ensure all necessary Kafka topics are created. This is also handled automatically by Docker Compose on startup.

Refer to the root `pyproject.toml` for a full list of available scripts, including individual service development commands.

## Running the System with Docker Compose

The entire HuleEdu system, including Kafka and all microservices, can be run locally using Docker Compose:

1. **Build Images**:

    ```bash
    pdm run docker-build
    ```

2. **Start Services**:

    ```bash
    pdm run docker-up
    ```

    This command will start all services defined in `docker-compose.yml` in detached mode. It includes Zookeeper, Kafka, the `kafka_topic_setup` one-shot service for automatic topic creation, and all HuleEdu microservices.

## Current Development Status & Focus (BCS Integration & Dynamic Pipeline Orchestration ✅ COMPLETED)

🚀 **BCS Integration & Dynamic Pipeline Orchestration Achieved** - All phases of Dynamic Pipeline Orchestration are complete, including the full implementation and integration of the **Batch Conductor Service (BCS)** for intelligent pipeline dependency resolution. The system now features:

* **BCS Production-Ready Implementation** ✅: Event-driven architecture with 24/24 tests passing, atomic Redis operations, DLQ production, and comprehensive error handling
* **BOS ↔ BCS HTTP Integration** ✅: Complete HTTP client integration with pipeline resolution workflows validated through E2E tests
* **Dynamic Pipeline Resolution** ✅: Intelligent dependency analysis, batch state-aware optimization, and prerequisite validation

BOS coordinates with the Batch Conductor Service (BCS) for intelligent pipeline dependency resolution when clients request pipeline execution, while ELS manages individual essay states via a formal state machine and reports phase outcomes to BOS. Current status includes:

* **Core Services Implemented** ✅:
  * **Content Service**: HTTP API with filesystem storage backend
  * **Spell Checker Service**: Event-driven worker with L2 + pyspellchecker pipeline, comprehensive tests
  * **Batch Orchestrator Service**: HTTP API with slot assignment and command processing
  * **Essay Lifecycle Service**: Dual-mode service with slot coordination and command handling
  * **File Service**: Content provisioning service with MD5 validation and event publishing
  * **Batch Conductor Service (BCS)**: ✅ **NEW** - Internal pipeline dependency resolution with event-driven batch state projection, atomic Redis operations, and intelligent dependency analysis
  * **Class Management Service**: CRUD operations for classes and students with PostgreSQL persistence
  * **Result Aggregator Service**: ✅ **NEW** - CQRS-based materialized view service aggregating results from all processing services with query-optimized PostgreSQL schema
* **Essay ID Coordination Architecture** ✅:
  * **Slot Assignment Pattern**: BOS generates internal essay ID slots, ELS assigns content to slots
  * **Content Provisioning Flow**: File Service → ELS slot assignment → BOS essay storage → Client pipeline request → BOS command generation → ELS service dispatch
  * **Command Processing**: Complete client-triggered BOS→ELS→SpellChecker command flow with actual essay IDs, text_storage_ids, and language support
  * **Event-Driven Coordination**: `EssayContentProvisionedV1`, `BatchEssaysReady`, `BatchSpellcheckInitiateCommand` events
  * **Persistent Storage**: Essay metadata and storage references stored in PostgreSQL database for data persistence across service restarts
* **Foundational Architecture** ✅:
  * **Clean Architecture**: Protocol-based DI across all services with Dishka
  * **Event-Driven Communication**: Standardized EventEnvelope with Kafka integration
  * **Contract Management**: Comprehensive Pydantic models in common_core
  * **Testing Infrastructure**: Unit, integration, and contract tests with comprehensive coverage
  * **Observability**: Prometheus metrics endpoints across services
  * **Docker Integration**: Full containerization with automated topic setup
* **Development Standards** ✅:
  * **Code Quality**: Ruff formatting, MyPy type checking, 400 LOC file limits
  * **Configuration**: Standardized Pydantic BaseSettings across services
  * **Logging**: Centralized correlation ID tracking and structured logging
  * **Dependency Management**: PDM monorepo with proper version resolution

* **Dynamic Pipeline Orchestration** ✅:
  * **Phase 4: All phase initiators (Spellcheck, CJ Assessment, AI Feedback, NLP) implemented and integrated into BOS dynamic orchestration framework.**
  * **Phase 1**: Common core event contracts (`ELSBatchPhaseOutcomeV1`, topic mapping, enums)
  * **Phase 2**: ELS State Machine (transitions library, `EssayStateMachine`, state validation)
  * **Phase 3**: BOS Dynamic Pipeline Orchestration (pipeline state management, Kafka consumer updates)
  * **Event Architecture**: `ELSBatchPhaseOutcomeV1` and various `BatchService<Phase>InitiateCommandDataV1` commands are key for this dynamic flow.
  * **Pipeline Sequences**: Support for flexible pipeline definitions (Spellcheck → CJ Assessment, etc.)

* **Architecture Enhancements** ✅:
  * **State Machine Integration**: Formal state transitions using transitions library in ELS
  * **Pipeline State Management**: `ProcessingPipelineState` tracking through multi-phase sequences
  * **Event-Driven Orchestration**: BOS consumes phase outcomes and triggers next-phase commands
  * **Phase 4 Testing Ready**: Foundation tests (7/7) and testing strategy documented

For detailed implementation and testing history, refer to:

* `Documentation/TASKS/ELS_AND_BOS_STATE_MACHINE_TASK_TICKET.md` (Current implementation status)
* `Documentation/TASKS/PHASE_4_TESTING_STRATEGY.md` (E2E testing approach)

## Planned Services and Enhancements

The HuleEdu platform continues evolving with dynamic pipeline orchestration. The following capabilities are planned for future development:

* **Phase 4 - End-to-End Validation (In Progress)**: ✅ **IMPLEMENTED**
  * Enhanced E2E testing framework following walking skeleton methodology
  * Multi-pipeline sequence validation (Spellcheck → CJ Assessment, etc.)
  * Partial success scenario testing and essay filtering validation

* **Future Enhancements - Extended Pipeline Services**:
  * **AI Feedback Service**: AI-generated feedback on student essays  
  * **NLP Metrics Service**: Detailed Natural Language Processing metrics extraction
  * **CJ (Comparative Judgement) Assessment Service**: ✅ **IMPLEMENTED** - AI-driven comparative judgement of essays with dynamic LLM configuration
* **Future Architectural Components**:
  * **LLM-Caller Gateway**: Centralized service for managing Large Language Model interactions
  * **API Gateway and Websocket**: Single entry point for external clients
  * **React Frontend**: Modern user interface for students and educators
  * **User Service**: Authentication, authorization, and user profiles
  * **Result Aggregator**: Processing results collection and presentation

## Project Rules & Documentation

* **Development Standards**: Development adheres to the rules defined in the `.cursor/rules/` directory. The [000-rule-index.mdc](.cursor/rules/000-rule-index.mdc) provides a comprehensive index to these rules.
* **Architectural Blueprints & Task Tracking**: Further design documents, PRDs, and detailed task breakdowns can be found in the `Documentation/` folder.
* **Service-Specific READMEs**: Each service in the `services/` directory contains its own `README.md` with more detailed information about its specific functionality, API (if any), and local development.

## How to Use

1. **Pull the Repository**: Clone the repository to your local machine.
2. **Install Dependencies**: Run `setup_huledu_environment.sh` to install PDM and set up the project's dependencies.
3. **Understand the Architecture**: It is helpful to be familiar with the core principles and service boundaries. Currently, we need help developing the statistical analysis tools, which will act as a check and balance system for the CJ Essay Service Rankings.
4. **Adhere to Standards**: Development activities align with the coding standards, testing practices, and architectural mandates defined in `.cursor/rules/`.
5. **Write Tests**: New features and bug fixes are typically accompanied by relevant tests (unit, integration, contract).
6. **Update Documentation**: READMEs, docstrings, and architectural documents are kept up-to-date with changes.
7. **Communicate**: Proposed changes, especially those affecting service contracts or shared code, are generally discussed with the team.

---

This README provides a high-level guide to the HuleEdu Monorepo. For more detailed information, please consult the specific documentation linked throughout this document and within the respective service directories.
