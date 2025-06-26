# Task Ticket: Complete & Integrate Class Management Service

**Version**: 2.1
**Date**: June 26, 2025
**Status**: In Progress

## 1. Objective

This task is to complete, test, and integrate the existing class-management-service into the HuleEdu platform's runtime environment. The foundational code, including data models and initial service logic for creation operations, is already in place. The work now focuses on implementing the missing update logic, building the API layer, and fully integrating the service into the Docker Compose orchestration to make it operational.

The successful completion of this service is a critical dependency for the upcoming API Gateway and React Frontend workstreams. It will centralize all class and student data, decoupling this domain from other services and establishing it as the authoritative source of truth for user and class information, which is essential for personalizing AI feedback and enabling multi-user features.

## 2. Architectural Context & Evidence

The implementation must strictly adhere to the established architectural patterns of the HuleEdu monorepo. My analysis of the existing codebase provides the following evidence for these patterns:

### Service Structure

*   **Description**: The standard for HTTP services is a lean `app.py` that registers Quart Blueprint modules for routing. Initialization logic is handled in `startup_setup.py`.
*   **Evidence**: `/services/file_service/app.py` and `/services/file_service/startup_setup.py`.
*   **Implication for CMS**: The CMS must replicate this pattern precisely. The `app.py` will be minimal, responsible only for instantiating the Quart app, setting up the DI container with Quart-Dishka, and registering the API blueprints. All startup logic (like creating the DI container) will reside in `startup_setup.py`.

### Database Integration

*   **Description**: New services require their own PostgreSQL container defined in `docker-compose.infrastructure.yml`, with a unique host port mapping to avoid conflicts.
*   **Evidence**: The definitions for `batch_orchestrator_db` (port 5432), `essay_lifecycle_db` (port 5433), and `cj_assessment_db` (port 5434).
*   **Implication for CMS**: A new database service, `class_management_db`, will be added and exposed on host port 5435 to maintain this convention and prevent local port collisions.

### Data Modeling

*   **Description**: Database models are defined in a service-local `models_db.py` using SQLAlchemy `DeclarativeBase`. Enums must use the `SQLAlchemyEnum` type with a `values_callable`.
*   **Evidence**: `/services/batch_orchestrator_service/models_db.py` and rule `/rules/053-sqlalchemy-standards.mdc`.
*   **Implication for CMS**: The `Course` model must correctly use `SQLAlchemyEnum` for the `CourseCode` and `Language` fields to ensure type safety and compatibility with PostgreSQL's ENUM type.

### Data Contracts

*   **Description**: All inter-service data exchange relies on Pydantic models from the `common_core` package.
*   **Evidence**: The `PersonNameV1` model in `/common_core/src/common_core/metadata_models.py` and the `ClassCreatedV1` event in `/common_core/src/common_core/events/class_events.py` are explicitly required by this task.
*   **Implication for CMS**: The `Student` database model must be a superset of the fields in `PersonNameV1`. The event publishing logic must construct `ClassCreatedV1` and `StudentCreatedV1` Pydantic objects, ensuring perfect contract adherence.

### Dependency Injection (DI)

*   **Description**: Services use Dishka, defining contracts in `protocols.py` and binding them to concrete classes from an `implementations/` directory within the service's `di.py`.
*   **Evidence**: The structure and DI wiring in `/services/cj_assessment_service/`.
*   **Implication for CMS**: The `di.py` file must contain a `Provider` class that correctly injects the `PostgreSQLClassRepositoryImpl` for the `ClassRepositoryProtocol` contract into the `ClassManagementServiceImpl`.

### Monorepo Integration

*   **Description**: New services are added to the `[dependency-groups.dev]` section in the root `pyproject.toml` for local development and to the `[tool.pytest.ini_options]` `testpaths`.
*   **Evidence**: The root `/pyproject.toml` file.
*   **Implication for CMS**: The final step will involve updating these sections in the root `pyproject.toml` to make the new service an integral part of the local development and testing workflow.

## 3. Implementation Checkpoints & Current Status

### Checkpoint 2.3: Service Foundation & Database Models

**Status**: 🟢 Partially Completed

**What's Done & Evidence**:

*   The complete directory structure for the service exists at `/services/class_management_service/`.
*   The database models (`UserClass`, `Student`, `Course`, and the many-to-many association table) are correctly defined in `/services/class_management_service/models_db.py`, aligning with SQLAlchemy best practices and properly referencing the `PersonNameV1` and `CourseCode` contracts from `common_core`.
*   The basic scaffolding for the service, including `app.py`, `config.py`, `protocols.py`, and `di.py`, is in place.

**What's Missing & Actionable Requirements**:

*   The repository implementation in `/services/class_management_service/implementations/class_repository_postgres_impl.py` is incomplete. The `update_class` and `update_student` methods are currently empty stubs.

**Requirement**: Implement the `update_class` and `update_student` methods. The logic should first fetch the existing entity by its ID. If found, it should update the entity's attributes with the non-null values from the request model (e.g., `UpdateClassRequest`). Finally, it should commit the transaction and return the updated entity. If the entity is not found, it should return `None`.

### Checkpoint 2.4: API Models & Validation

**Status**: ✅ Completed

**Evidence & Analysis**:

*   The file `/services/class_management_service/api_models.py` contains all required Pydantic models for API requests and responses as specified in the original ticket.
*   Request models like `CreateStudentRequest` correctly embed the `PersonNameV1` model, ensuring contract compliance.
*   Validation rules, such as `EmailStr` for emails, are correctly applied. No further work is needed on this checkpoint.

### Checkpoint 2.5: Event Publishing & Service Logic

**Status**: 🟢 Partially Completed

**What's Done & Evidence**:

*   The `ClassManagementServiceImpl` in `/services/class_management_service/implementations/class_management_service_impl.py` correctly handles the creation logic for new classes and students.
*   Following a successful database transaction, it correctly instantiates and publishes the `ClassCreatedV1` and `StudentCreatedV1` events using the injected `ClassEventPublisherProtocol`. This demonstrates a working implementation of the event publishing pattern.

**What's Missing & Actionable Requirements**:

*   The service logic does not yet handle updates. The methods for updating classes and students need to be implemented.

**Requirement**: In `ClassManagementServiceImpl`, implement the `update_class` and `update_student` methods. These methods will call the corresponding (newly implemented) repository methods. If the repository returns an updated entity, the service method will then construct and publish the appropriate event (`ClassUpdatedV1`, `StudentUpdatedV1`, which need to be defined in `common_core`) before returning the result. This ensures data changes are broadcast to the rest of the system.

### Checkpoint 2.6: API Routes, Docker Integration & Testing

**Status**: 🔴 Not Started

**Analysis & Evidence**:

*   **API Routes**: The files `/services/class_management_service/api/class_routes.py` and `/services/class_management_service/api/health_routes.py` are currently empty placeholders. The service exposes no HTTP endpoints.
*   **Docker Integration**: The service is completely absent from the runtime environment. There are no definitions for `class_management_service` or its required `class_management_db` in `docker-compose.services.yml` or `docker-compose.infrastructure.yml`.

**Actionable Requirements**:

1.  **Implement API Routes**:
    *   In `health_routes.py`, create a Blueprint and implement the standard `/healthz` and `/metrics` endpoints, following the exact pattern in `/services/file_service/api/health_routes.py`.
    *   In `class_routes.py`, create a Blueprint and implement the full suite of CRUD endpoints for classes and students. These routes must be thin adapters that use `@inject` to get the `ClassManagementServiceProtocol` and delegate all business logic to its methods. For example, a `POST /v1/classes` route will call `service.register_new_class(...)`.

2.  **Implement Docker Infrastructure**:
    *   In `docker-compose.infrastructure.yml`, add a new `postgres:15` service named `class_management_db`. It must be configured with a unique host port of `5435`, a named volume `class_management_db_data` for data persistence, and the standard HuleEdu `pg_isready` health check. Environment variables for `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` must be set.

3.  **Implement Docker Service Definition**:
    *   In `docker-compose.services.yml`, add the `class_management_service` definition. This must include the build context pointing to its directory, a unique `container_name`, attachment to the `huleedu_internal_network`, a `depends_on` block for `class_management_db` and `kafka_topic_setup`, and environment variables to connect to its database.
    *   Create the service's `Dockerfile` modeled on `/services/file_service/Dockerfile`.

4.  **Implement Testing**:
    *   Create the `tests/` directory within the service folder.
    *   Write unit tests for the `update_class` and `update_student` repository and service logic, mocking dependencies as needed.
    *   Write integration tests for the newly created API endpoints. These tests should cover success cases (200 OK, 201 Created), validation errors (400 Bad Request), not found errors (404 Not Found), and ensure that the correct events are published upon successful state changes.