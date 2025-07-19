# HuleEdu Monorepo - Microservices Architecture

Welcome to the HuleEdu Monorepo! This project implements a modern, production-ready microservice-based architecture for the HuleEdu educational platform. The system provides comprehensive essay processing capabilities including content management, spell checking, comparative judgment assessment, and real-time client interactions through a complete web application stack.

## Core Architectural Principles

The HuleEdu platform is built upon a set of core foundational principles to ensure scalability, maintainability, and architectural integrity:

* **Domain-Driven Design (DDD)**: Each microservice maps to a specific business domain (Bounded Context), owning its data and logic. Service boundaries are strictly respected with zero tolerance for architectural deviations.
* **Event-Driven Architecture (EDA)**: Asynchronous, event-driven communication via Kafka is the primary method for inter-service collaboration. Services communicate through standardized `EventEnvelope` structures with deterministic event ID generation for idempotency.
* **Explicit Contracts**: All inter-service data structures (event payloads, API DTOs) are defined as versioned Pydantic models residing in `libs/common_core/src/common_core/`. Contract versioning follows semantic versioning with backward compatibility requirements.
* **Service Autonomy**: Microservices are independently deployable, scalable, and updatable. Each service owns its data store with isolated schemas. Direct cross-service database access is strictly forbidden.
* **Clean Architecture**: Services implement protocol-based dependency injection using `typing.Protocol` interfaces defined in `<service_name>/protocols.py`. Business logic depends on abstractions rather than concrete implementations.
* **Dependency Injection (DI)**: All services utilize the Dishka DI framework with providers defined in `<service_name>/di.py`. DI containers manage service lifecycles, database connections, and external client sessions.
* **Async-First Design**: Services are built with `async/await` for all I/O operations, utilizing frameworks like Quart (HTTP services) and FastAPI (client-facing APIs) for optimal performance.
* **Configuration Management**: Services use Pydantic `BaseSettings` for type-safe configuration, loaded from environment variables and `.env` files as defined in `<service_name>/config.py`.
* **Centralized Logging**: Services employ the centralized logging utility from `huleedu_service_libs.logging_utils` with correlation ID propagation. Direct use of the standard library `logging` module is forbidden.
* **Observability**: Comprehensive monitoring through Prometheus metrics, structured logging, and distributed tracing with OpenTelemetry integration.

## Monorepo Structure Overview

The project is organized as a monorepo managed by PDM:

* **`libs/common_core/`**: A shared Python package containing common Pydantic models for data contracts (events, API DTOs), enums, and shared metadata structures. All inter-service communication contracts are centralized here.
* **`services/`**: Contains the individual microservices, each implementing clean architecture with protocol-based dependency injection.
  * **`services/libs/`**: Shared utility libraries (`huleedu_service_libs`) providing Kafka client wrappers, logging utilities, and common service patterns.
  * Each service follows standardized structure with `protocols.py`, `di.py`, `config.py`, and `api/` directories for HTTP services.
* **`scripts/`**: Project-level automation scripts including environment setup, Kafka topic bootstrapping, Docker operations, and validation utilities.
* **`documentation/`**: Contains architectural documents, task tracking, operational guides, and setup documentation.
* **`.cursor/rules/`**: Contains comprehensive development rules and standards. The [000-rule-index.md](.cursor/rules/000-rule-index.md) serves as an index to all rules covering architecture, coding standards, testing, and deployment.

## Services

The HuleEdu ecosystem comprises the following production-ready services:

### Client-Facing Services

* **API Gateway Service** ✅ **IMPLEMENTED**:
  * **Description**: FastAPI-based client-facing HTTP service providing secure entry point for React frontend applications. Implements JWT authentication, rate limiting, CORS, and request validation while proxying to internal microservices.
  * **Port**: 4001 (Client-facing HTTP API)
  * **Location**: `services/api_gateway_service/`
  * **API**: `/v1/batches`, `/v1/files`, `/v1/classes` endpoints with OpenAPI documentation
  * **Features**: JWT authentication, rate limiting, CORS, batch ownership validation, complete Class Management Service proxy

* **WebSocket Service** ✅ **IMPLEMENTED**:
  * **Description**: FastAPI-based microservice providing real-time WebSocket connections with JWT authentication. Manages user-specific Redis pub/sub channels for real-time notifications to connected clients.
  * **Port**: 8080 (WebSocket connections)
  * **Location**: `services/websocket_service/`
  * **Features**: JWT query parameter authentication, Redis pub/sub integration, connection management with configurable limits, health checks

### Core Processing Services

* **Content Service** ✅ **IMPLEMENTED**:
  * **Description**: Quart-based HTTP service responsible for content storage and retrieval using a local filesystem backend with MD5 validation and content integrity checks.
  * **Port**: 8001 (Internal HTTP API)
  * **Location**: `services/content_service/`
  * **API**: `/v1/content` endpoints for storage and retrieval

* **Spell Checker Service** ✅ **IMPLEMENTED**:
  * **Description**: Kafka consumer worker service performing advanced spell checking on essays, including L2 error correction and standard spell checking using `pyspellchecker`. Features clean architecture with protocol-based DI and comprehensive test coverage.
  * **Port**: 8002 (Metrics)
  * **Location**: `services/spellchecker_service/`
  * **Architecture**: Protocol-based DI with Dishka, language parameter support, event-driven processing

### Orchestration & Coordination Services

* **Batch Orchestrator Service (BOS)** ✅ **IMPLEMENTED**:
  * **Description**: Quart-based HTTP service acting as the central coordinator for essay processing workflows. Features dynamic pipeline orchestration, slot assignment patterns, and integration with Batch Conductor Service for intelligent dependency resolution.
  * **Port**: 5001 (Internal HTTP API)
  * **Location**: `services/batch_orchestrator_service/`
  * **API**: `/v1/batches` endpoints for batch registration, pipeline execution, and coordination
  * **Features**: Dynamic pipeline state management, command generation, event-driven phase progression

* **Batch Conductor Service (BCS)** ✅ **IMPLEMENTED**:
  * **Description**: Internal Quart-based microservice responsible for intelligent pipeline dependency resolution and batch state analysis. Features event-driven batch state projection via Kafka, atomic Redis operations for race condition safety, and comprehensive error handling with DLQ production.
  * **Port**: 4002 (Internal HTTP API)
  * **Location**: `services/batch_conductor_service/`
  * **API**: `/internal/v1/pipelines/define` for pipeline resolution, `/healthz` and `/metrics` endpoints
  * **Architecture**: Protocol-based DI with Dishka, event-driven architecture consuming spellcheck/CJ assessment completion events, Redis-cached state management with atomic WATCH/MULTI/EXEC operations

* **Essay Lifecycle Service (ELS)** ✅ **IMPLEMENTED**:
  * **Description**: Hybrid service (HTTP API + Kafka worker) managing individual essay states via formal state machine (`EssayStateMachine`). Features structured error handling with HuleEduError integration, correlation ID propagation, and OpenTelemetry distributed tracing. Reports batch-level phase outcomes to BOS for dynamic pipeline progression.
  * **Ports**: 6001 (HTTP API), 9091 (Metrics)
  * **Location**: `services/essay_lifecycle_service/`
  * **Database**: Dual-repository pattern with PostgreSQL (production) and SQLite (development/testing)
  * **Architecture**: 183 tests including contract testing and protocol-based mocking infrastructure

### Content & File Management Services

* **File Service** ✅ **IMPLEMENTED**:
  * **Description**: Quart-based HTTP service handling multipart file uploads with text extraction and content ingestion coordination. Features MD5 validation, Kafka event publishing, and integration with Content Service for storage management.
  * **Ports**: 7001 (Internal HTTP API), 9094 (Metrics)
  * **Location**: `services/file_service/`
  * **API**: `POST /v1/files/batch` for batch file uploads with validation
  * **Features**: Text extraction, content provisioning flow, essay readiness event publishing

### Assessment & AI Services

* **CJ Assessment Service** ✅ **IMPLEMENTED**:
  * **Description**: Hybrid Kafka worker + HTTP API service for Comparative Judgment assessment of essays using Large Language Model (LLM) based pairwise comparisons. Integrates with centralized LLM Provider Service for queue-based resilience and psychometric validity.
  * **Port**: 9095 (Health API & Metrics)
  * **Location**: `services/cj_assessment_service/`
  * **API**: `/healthz` and `/metrics` endpoints for health checks and observability
  * **Database**: PostgreSQL with DI-managed connections, provisioned via `docker-compose.yml`
  * **Architecture**: Protocol-based DI with Dishka, event-driven processing, comprehensive error handling

* **LLM Provider Service** ✅ **IMPLEMENTED**:
  * **Description**: Centralized Quart-based HTTP service providing queue-based resilience for LLM provider interactions. Features circuit breakers, Redis primary/local fallback queuing, and multi-provider abstraction (Anthropic, OpenAI, Google, OpenRouter).
  * **Port**: 8090 (Internal HTTP API)
  * **Location**: `services/llm_provider_service/`
  * **API**: `/api/v1/comparison` (200/202 responses), `/api/v1/status/{queue_id}`, `/api/v1/results/{queue_id}`
  * **Key Feature**: NO response caching - preserves psychometric validity with fresh responses for each assessment

### Data Management Services

* **Class Management Service (CMS)** ✅ **IMPLEMENTED**:
  * **Description**: FastAPI-based HTTP service acting as the authoritative source for managing classes, students, and their relationships. Provides synchronous API for data management with complete CRUD operations.
  * **Port**: 5002 (Internal HTTP API)
  * **Location**: `services/class_management_service/`
  * **API**: `/v1/classes` and `/v1/students` for full CRUD operations with PostgreSQL persistence
  * **Features**: Student-class associations, batch validation, comprehensive data integrity

* **Result Aggregator Service (RAS)** ✅ **IMPLEMENTED**:
  * **Description**: Hybrid service (Kafka consumer + HTTP API) aggregating processing results from all services into a materialized view. Provides fast, query-optimized access to batch and essay results for the API Gateway.
  * **Ports**: 4003 (Internal HTTP API), 9096 (Metrics)
  * **Location**: `services/result_aggregator_service/`
  * **API**: `/internal/v1/batches/{batch_id}/status` for comprehensive batch status queries
  * **Database**: PostgreSQL with normalized schema optimized for read queries
  * **Architecture**: CQRS pattern with event sourcing, Redis caching, service-to-service authentication

## Key Technologies

### Core Platform

* **Python**: Version 3.11+ with async/await patterns
* **PDM**: Python dependency management and monorepo tooling with workspace support
* **Docker & Docker Compose**: Containerization and local service orchestration

### Web Frameworks

* **Quart**: Asynchronous web framework for internal HTTP services
* **FastAPI**: High-performance framework for client-facing APIs with OpenAPI support
* **Pydantic**: Data validation, serialization, settings management, and contract definitions

### Event Streaming & Communication

* **Kafka (via aiokafka)**: Event streaming and inter-service communication
* **Redis**: Pub/sub messaging, caching, and atomic operations for coordination
* **WebSockets**: Real-time client communication via FastAPI/Starlette

### Dependency Injection & Architecture

* **Dishka**: Dependency injection framework with protocol-based abstractions
* **typing.Protocol**: Behavioral contracts for clean architecture implementation
* **Transitions**: State machine library for formal state management

### Data Persistence

* **PostgreSQL**: Primary database for production services with normalized schemas
* **SQLite**: Development and testing database with dual-repository patterns
* **SQLAlchemy**: ORM with async support and migration management

### Development & Quality Assurance

* **Ruff**: Code formatting and linting with project-wide standards
* **MyPy**: Static type checking with strict configuration
* **Pytest**: Testing framework supporting unit, integration, and contract tests
* **OpenTelemetry**: Distributed tracing and observability

### Monitoring & Observability

* **Prometheus**: Metrics collection and monitoring
* **Grafana**: Metrics visualization and alerting
* **Structured Logging**: Centralized logging with correlation ID tracking

## Development Environment Setup

### Prerequisites

* **Python 3.11+**: Required for all services with async/await support
* **PDM**: Python Dependency Manager for monorepo tooling (auto-installed by setup script)
* **Docker & Docker Compose**: For containerized development and service orchestration
* **Git**: Version control with proper `.gitignore` configuration

### Automated Setup

Run the comprehensive environment setup script from the project root:

```bash
./scripts/setup_huledu_environment.sh
```

This script performs:
* PDM installation and configuration
* Monorepo dependency installation in editable mode
* Service library setup (`huleedu_service_libs`)
* Development tool configuration (Ruff, MyPy, Pytest)
* Docker environment preparation

### IDE Configuration

For optimal development experience, configure your IDE according to project standards:

* **VS Code/Cursor AI**: Follow the [IDE Setup Guide](documentation/setup_environment/CURSOR_IDE_SETUP_GUIDE.md)
* **Ruff Extension**: Automatic formatting and linting aligned with `.windsurf/rules/`
* **MyPy Extension**: Static type checking with strict configuration
* **Python Path**: Ensure proper module resolution for monorepo structure

### Verification

Verify your setup by running:

```bash
# Check code quality
pdm run lint-all
pdm run typecheck-all

# Run tests
pdm run test-all

# Start services
pdm run docker-up
```

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

## Current Development Status

### Production-Ready Microservices Architecture ✅ COMPLETED

The HuleEdu platform has achieved a **complete, production-ready microservices architecture** with comprehensive essay processing capabilities. All core services are implemented, tested, and integrated:

### Complete Service Ecosystem ✅

* **Client-Facing Layer**: API Gateway Service (FastAPI) and WebSocket Service for real-time React frontend integration
* **Processing Services**: Content Service, Spell Checker Service, CJ Assessment Service with LLM Provider Service integration
* **Orchestration Layer**: Batch Orchestrator Service (BOS) with Batch Conductor Service (BCS) for intelligent pipeline dependency resolution
* **State Management**: Essay Lifecycle Service (ELS) with formal state machine and distributed tracing
* **Data Services**: File Service, Class Management Service, Result Aggregator Service with CQRS patterns
* **Infrastructure**: Comprehensive Docker Compose setup with Kafka, Redis, PostgreSQL

### Architectural Achievements ✅

* **Clean Architecture**: Protocol-based dependency injection (`typing.Protocol`) with Dishka across all services
* **Event-Driven Communication**: Standardized `EventEnvelope` with deterministic event ID generation for idempotency
* **Dynamic Pipeline Orchestration**: BOS ↔ BCS integration enabling intelligent dependency resolution and batch state analysis
* **State Machine Integration**: Formal essay state transitions using `transitions` library with comprehensive error handling
* **Distributed Observability**: OpenTelemetry tracing, Prometheus metrics, structured logging with correlation ID propagation
* **Contract Management**: Comprehensive Pydantic models in `common_core` with versioned schemas

### Testing & Quality Assurance ✅

* **Comprehensive Test Coverage**: Unit, integration, and contract tests across all services
* **ELS Reference Implementation**: 183 tests including protocol-based mocking infrastructure
* **BCS Production Validation**: Event-driven architecture with atomic Redis operations and DLQ production
* **E2E Validation**: Complete pipeline testing from file upload through assessment completion
* **Code Quality**: Ruff formatting, MyPy type checking, 400 LOC file limits enforced

### Key Processing Flows ✅

* **Content Provisioning**: File Service → ELS slot assignment → Content Service storage → Pipeline initiation
* **Essay Processing**: Dynamic pipeline orchestration (Spellcheck → CJ Assessment) with state persistence
* **Real-Time Updates**: WebSocket notifications via Redis pub/sub for client applications
* **Result Aggregation**: CQRS-based materialized views with query-optimized PostgreSQL schemas

### Development Infrastructure ✅

* **Monorepo Management**: PDM with workspace support and automated dependency resolution
* **Containerization**: Complete Docker Compose setup with health checks and automated topic creation
* **Development Standards**: Comprehensive rules in `.windsurf/rules/` covering architecture, coding, testing, and deployment
* **CI/CD Ready**: Automated linting, type checking, and testing workflows

### Current Focus: Production Deployment & Scaling

With the core architecture complete, current development focuses on:

* **Production Hardening**: Performance optimization and resource management
* **Monitoring Enhancement**: Advanced Grafana dashboards and alerting
* **Security Hardening**: JWT authentication, rate limiting, and input validation
* **Documentation**: Comprehensive API documentation and operational guides

## Future Enhancements

With the core microservices architecture complete, future development focuses on advanced features and platform expansion:

### Advanced Processing Services

* **AI Feedback Service**: Intelligent essay feedback generation using advanced LLM capabilities
  * Integration with LLM Provider Service for scalable AI interactions
  * Personalized feedback based on student performance history
  * Multi-language support for diverse educational contexts

* **NLP Metrics Service**: Comprehensive Natural Language Processing analytics
  * Advanced linguistic analysis (readability, complexity, coherence)
  * Writing quality metrics and improvement suggestions
  * Integration with existing assessment pipelines

### Frontend & User Experience

* **Svelte Frontend Application**: Modern, responsive web application
  * Real-time updates via WebSocket Service integration
  * Comprehensive essay management and assessment workflows
  * Teacher dashboards and student progress tracking

* **User Authentication Service**: Centralized identity and access management
  * JWT-based authentication with role-based access control
  * Integration with educational institution SSO systems
  * User profile management and preferences

### Platform Scaling & Operations

* **Advanced Monitoring**: Enhanced observability and alerting
  * Grafana dashboards for service health and performance metrics
  * Automated alerting for system anomalies and performance degradation
  * Distributed tracing visualization and analysis

* **Performance Optimization**: System-wide performance enhancements
  * Database query optimization and connection pooling
  * Caching strategies for frequently accessed data
  * Load balancing and horizontal scaling capabilities

### Integration & Extensibility

* **Plugin Architecture**: Extensible framework for custom processing modules
  * Third-party assessment tool integration
  * Custom grading algorithms and rubrics
  * Educational platform API integrations (Canvas, Blackboard, etc.)

## Project Rules & Documentation

### Development Standards

* **Comprehensive Rules**: Development adheres to the rules defined in the `.windsurf/rules/` directory
* **Rule Index**: The [000-rule-index.md](.windsurf/rules/000-rule-index.md) provides a comprehensive index to all development rules
* **Zero Tolerance**: Architectural deviations and "vibe coding" are strictly forbidden with mandatory refactoring requirements
* **AI Agent Modes**: Specialized interaction modes (planning, coding, testing, debugging, refactoring) defined in rules 110.x series

### Documentation Structure

* **Service Documentation**: Each service in `services/` contains detailed `README.md` with functionality, APIs, and development instructions
* **Library Documentation**: Shared libraries in `services/libs/` have comprehensive documentation with usage patterns and integration guides
* **Architectural Documentation**: Design documents, PRDs, and task tracking in `documentation/` directory
* **Contract Documentation**: Pydantic models in `libs/common_core/` serve as the source of truth for all inter-service contracts

## Getting Started

### Quick Start

1. **Clone Repository**: `git clone <repository-url>`
2. **Environment Setup**: Run `./scripts/setup_huledu_environment.sh` for automated PDM and dependency installation
3. **Start Services**: Use `pdm run docker-up` to launch the complete system with Docker Compose
4. **Verify Setup**: Run `pdm run test-all` to ensure all tests pass

### Development Workflow

1. **Understand Architecture**: Review core principles and service boundaries defined in `.windsurf/rules/`
2. **Follow Standards**: Adhere to coding standards, testing practices, and architectural mandates
3. **Protocol-Based Development**: Use `typing.Protocol` interfaces and Dishka DI for clean architecture
4. **Comprehensive Testing**: Write unit, integration, and contract tests for all changes
5. **Update Documentation**: Keep READMEs, docstrings, and architectural documents current
6. **Code Quality**: Use `pdm run lint-all` and `pdm run typecheck-all` before committing

### Key Resources

* **Service READMEs**: Detailed service-specific documentation in each `services/` directory
* **Development Rules**: Comprehensive standards in `.windsurf/rules/` covering all aspects of development
* **Common Core**: Shared contracts and models in `libs/common_core/` with full API documentation
* **Scripts**: Automation tools in `scripts/` for environment setup, testing, and deployment

---

**HuleEdu Monorepo** - A production-ready microservices architecture for comprehensive essay processing and educational assessment. For detailed information, consult the service-specific documentation and development rules referenced throughout this document.
