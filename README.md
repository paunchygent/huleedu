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

* **Content Service**:
  * **Description**: A Quart-based HTTP service responsible for content storage and retrieval, using a local filesystem backend.
  * **Location**: `services/content_service/`
* **File Service**:
  * **Description**: A Quart-based HTTP service with Kafka worker responsible for file upload handling, text extraction, and content ingestion coordination. Accepts multipart file uploads, processes files to extract text content, coordinates with Content Service for storage, and emits essay readiness events.
  * **Location**: `services/file_service/` *(planned - walking skeleton implementation)*
* **Spell Checker Service**:
  * **Description**: A Kafka consumer worker service that performs advanced spell checking on essays, including L2 error correction and standard spell checking using `pyspellchecker`.
  * **Location**: `services/spell_checker_service/`
* **Batch Orchestrator Service** (formerly Batch Service):
  * **Description**: A Quart-based HTTP service that orchestrates essay processing workflows, initiating tasks by publishing events.
  * **Location**: `services/batch_orchestrator_service/`
* **Essay Lifecycle Service (ELS)**:
  * **Description**: A Kafka consumer worker service responsible for managing the state of individual essays throughout the processing pipeline. It listens to events from specialized services and batch commands to update essay states. Its core infrastructure (DI, protocols, state store) is implemented.
  * **Location**: `services/essay_lifecycle_service/`

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

## Current Development Status & Focus (Phase 1.2)

The project is actively developed. Key recent achievements and ongoing work within Phase 1.2 include:

* **Foundational Refinements**:
  * Enhanced `topic_name()` helper in `common_core` for better diagnosability.
  * MyPy configuration updated for external libraries without type stubs.
  * Root `.dockerignore` file created for optimized Docker builds.
  * Standardized Pydantic `BaseSettings` for configuration across services.
* **Core Service Enhancements**:
  * **Spell Checker Service**: Comprehensive unit tests implemented. The L2 + `pyspellchecker` pipeline from the prototype has been fully integrated, and the service worker was refactored into `worker_main.py`, `event_router.py`, and `core_logic.py`.
  * **Kafka Topic Automation**: Implemented `scripts/kafka_topic_bootstrap.py` and integrated it as a one-shot Docker Compose service to ensure topics exist before other services start.
* **Architectural Infrastructure (Phase 1.2 Δ - "Contracts & Containers")**:
  * **Typed Behavioural Contracts**: Defined service-local `protocols.py` for all running services.
  * **Dishka DI Integration**: Dishka DI containers wired across Batch Orchestrator and Spell Checker services.
  * **File Size Compliance**: Refactored oversized modules to adhere to LoC limits.
  * **`EventEnvelope` Versioning**: Added `schema_version` to `EventEnvelope`.
* **Essay Lifecycle Service (ELS)**:
  * Critical fixes, architectural naming corrections, and type stub completions have been addressed.
  * All required Pydantic models for ELS interactions are in `common_core`.
  * Batch-centric infrastructure (protocols, DI for command handlers and dispatchers) is complete.
  * Implementation of spellcheck handlers in ELS is proceeding following the Spell Checker Service migration.
* **Upcoming Work**:
  * Implementation of Prometheus scrape endpoints for metrics (Δ-4).
  * CI Smoke Test with Docker layer caching.
  * Semantic version bump for internal packages to `0.2.0`.

For detailed current tasks and progress, please refer to the documents in the `Documentation/TASKS/` directory.

## Planned Services and Enhancements

The HuleEdu platform is evolving. The following services and capabilities are planned for future development:

* **Near-Term Service Integrations (coming weeks)**:
  * **AI Judge powered CJ (Comparative Judgement) Assessment Service**: To facilitate AI-driven comparative judgement of essays.
  * **AI Feedback Service**: To provide automated, AI-generated feedback on student essays.
  * **NLP Metrics Service**: To extract and serve detailed Natural Language Processing metrics from essays.
* **Future Architectural Components and Services**:
  * **LLM-Caller Gateway**: A centralized service for managing interactions with various Large Language Models, handling model selection, and standardizing API calls.
  * **API Gateway**: A single entry point for external clients to interact with the HuleEdu microservices.
  * **React Frontend**: A modern user interface for students and educators.
  * **User Service**: To manage user authentication, authorization, and profiles.
  * **Result Aggregator**: A service to collect, aggregate, and present processing results and feedback from various services.

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
