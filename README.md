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
  * **Description**: A Quart-based HTTP service that orchestrates essay processing workflows, initiating tasks by publishing events.
  * **Port**: 5001 (HTTP API)
  * **Location**: `services/batch_orchestrator_service/`
  * **API**: `/v1/batches` endpoints for batch registration and coordination

* **Essay Lifecycle Service (ELS)** ✅ **IMPLEMENTED**:
  * **Description**: A dual-mode service (HTTP API + Kafka worker) responsible for managing the state of individual essays throughout the processing pipeline. Handles essay state transitions and batch coordination.
  * **Ports**: 6001 (HTTP API), 9091 (Metrics)
  * **Location**: `services/essay_lifecycle_service/`
  * **Architecture**: SQLite-based state management with event-driven coordination

* **File Service** ✅ **IMPLEMENTED**:
  * **Description**: A Quart-based HTTP service with Kafka event publishing for file upload handling, text extraction, and content ingestion coordination. Accepts multipart file uploads, processes files to extract text content, coordinates with Content Service for storage, and emits essay readiness events.
  * **Port**: 7001 (HTTP API), 9094 (Metrics)
  * **Location**: `services/file_service/`
  * **API**: `POST /v1/files/batch` for batch file uploads
  * **Status**: Fully implemented and integrated into the walking skeleton

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
* **SQLite**: For service-local data persistence (ELS).

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

## Current Development Status & Focus (Sprint 1 development Complete and after TESTING is complete → Phase 2 Ready)

🎉 **Walking Skeleton Completion Achieved** - The project has successfully completed Sprint 1 with a fully functional end-to-end essay processing pipeline. Recent achievements include:

* **Core Services Implemented** ✅:
  * **Content Service**: HTTP API with filesystem storage backend
  * **Spell Checker Service**: Event-driven worker with L2 + pyspellchecker pipeline, comprehensive tests
  * **Batch Orchestrator Service**: HTTP API with slot assignment and command processing
  * **Essay Lifecycle Service**: Dual-mode service with slot coordination and command handling
  * **File Service**: Content provisioning service with MD5 validation and event publishing
* **Essay ID Coordination Architecture** ✅:
  * **Slot Assignment Pattern**: BOS generates internal essay ID slots, ELS assigns content to slots
  * **Content Provisioning Flow**: File Service → ELS slot assignment → BOS command generation → ELS service dispatch
  * **Command Processing**: Complete BOS→ELS→SpellChecker command flow with actual essay IDs, text_storage_ids, and language support
  * **Event-Driven Coordination**: `EssayContentProvisionedV1`, `BatchEssaysReady`, `BatchSpellcheckInitiateCommand` events
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

* **Walking Skeleton Validation** ✅:
  * **End-to-End Flow**: Batch registration → File upload → Content provisioning → Slot assignment → Command processing → Service dispatch
  * **Infrastructure Health**: All services healthy and communicating via Kafka
  * **Event Architecture**: Complete event flow validated with proper essay ID coordination

For detailed implementation history, refer to the completed `Documentation/TASKS/ESSAY_ID_COORDINATION_ARCHITECTURE_FIX.md`.

## Planned Services and Enhancements

The HuleEdu platform continues evolving beyond Sprint 1. The following services and capabilities are planned for future development:

* **Phase 2 - AI Processing Pipeline**:
  * **AI Feedback Service**: AI-generated feedback on student essays
  * **NLP Metrics Service**: Detailed Natural Language Processing metrics extraction
  * **AI Judge powered CJ (Comparative Judgement) Assessment Service**: AI-driven comparative judgement of essays
* **Future Architectural Components**:
  * **LLM-Caller Gateway**: Centralized service for managing Large Language Model interactions
  * **API Gateway**: Single entry point for external clients
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
