# Class Management Service

## 1. Overview

The Class Management Service is a synchronous, internal HTTP microservice that serves as the authoritative source of truth for managing classes, students, and their relationships within the HuleEdu ecosystem. It provides a RESTful API for creating, retrieving, updating, and deleting these core educational entities.

The service is built on the Quart asynchronous framework and uses PostgreSQL for data persistence via the SQLAlchemy ORM with the `asyncpg` driver. It adheres to the established architectural patterns of the HuleEdu platform, including protocol-based dependency injection with Dishka and event-driven notifications for state changes.

## 2. Architecture

The service follows the standard HuleEdu HTTP service blueprint, emphasizing a clean separation of concerns.

- **Application Entrypoint (`app.py`)**: A lean Quart application setup responsible for initializing the Dishka DI container, registering API Blueprints, and managing application lifecycle hooks (`@app.before_serving`, `@app.after_serving`).
- **API Blueprints (`api/`)**: API routes are organized into Blueprints. `health_routes.py` provides the standard `/healthz` and `/metrics` endpoints, while `class_routes.py` defines all business logic endpoints under the `/v1/classes` prefix.
- **Dependency Injection (`di.py`, `protocols.py`)**: The service heavily relies on DI.
  - `protocols.py` defines the behavioral contracts (`ClassRepositoryProtocol`, `ClassEventPublisherProtocol`, `ClassManagementServiceProtocol`) using `typing.Protocol` and generics for type safety with `UserClass` and `Student` models.
  - `di.py` contains the `Provider` classes that bind these protocols to their concrete implementations. It manages the lifecycle of dependencies such as the database session, Kafka bus, and Redis client.
- **Implementations (`implementations/`)**: This directory holds the concrete business logic.
  - `class_repository_postgres_impl.py`: Implements the `ClassRepositoryProtocol` and contains all SQLAlchemy logic for database interactions.
  - `class_management_service_impl.py`: Implements the `ClassManagementServiceProtocol`, orchestrating calls to the repository and the event publisher to execute business logic.
  - `event_publisher_impl.py`: Implements the `ClassEventPublisherProtocol`, handling the dual-channel event notification system.

## 3. Database Schema

Persistence is managed via PostgreSQL. The schema is defined in `models_db.py` using SQLAlchemy ORM models.

- **`Course`**: Represents a course (e.g., ENG5, SV1).
- **`UserClass`**: A specific class instance created by a teacher, linked to a `Course`.
- **`Student`**: Represents a student, with a unique constraint on the combination of `email` and the `created_by_user_id` to prevent duplicates per teacher.
- **`class_student_association`**: A many-to-many table linking `UserClass` and `Student` records.
- **`EssayStudentAssociation`**: A one-to-many table linking an `Essay` (by its UUID) to a `Student`.

## 4. API Specification

All API endpoints are prefixed with `/v1/classes`. Requests must include an `X-User-ID` header for ownership validation.

- `POST /`: Creates a new class.
  - **Request Body**: `CreateClassRequest`
  - **Response**: `201 Created` with class ID and name.
- `GET /<class_id>`: Retrieves a class by its UUID.
- `PUT /<class_id>`: Updates a class's name or associated course codes.
  - **Request Body**: `UpdateClassRequest`
- `DELETE /<class_id>`: Deletes a class.
- `POST /students`: Creates a new student and optionally associates them with existing classes.
  - **Request Body**: `CreateStudentRequest`
  - **Response**: `201 Created` with student ID and full name.
- `GET /students/<student_id>`: Retrieves a student by their UUID.
- `PUT /students/<student_id>`: Updates a student's name, email, or class associations.
  - **Request Body**: `UpdateStudentRequest`
- `DELETE /students/<student_id>`: Deletes a student.

All request and response bodies are strictly validated against Pydantic models defined in `api_models.py`.

## 5. Event-Driven Integration

The service publishes events to notify the rest of the ecosystem about state changes. The `DefaultClassEventPublisherImpl` handles this dual-channel notification.

1. **Kafka**: Formal, durable events are published to Kafka for asynchronous processing by other services.
    - **Published Events**: `ClassCreatedV1`, `ClassUpdatedV1`, `StudentCreatedV1`, `StudentUpdatedV1`.
    - **Mechanism**: Uses the shared `KafkaBus` library.
2. **Redis Pub/Sub**: Real-time, "fire-and-forget" notifications are published to user-specific Redis channels to power live UI updates.
    - **Mechanism**: The publisher extracts the `user_id` from the event and publishes a tailored JSON payload to a channel named `ws:{user_id}`. This is consumed by the `api_gateway_service` and forwarded to the correct client via WebSockets.

## 6. Configuration

Service configuration is managed by `config.py` using `pydantic-settings`.

- **Environment Prefix**: `CLASS_MANAGEMENT_SERVICE_`
- **Database**: The `DATABASE_URL` is assembled from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` variables.
- **Infrastructure**: `KAFKA_BOOTSTRAP_SERVERS`, `REDIS_URL`.
- **Testing**: A `USE_MOCK_REPOSITORY` flag allows for switching to an in-memory repository for testing purposes.

## 7. Local Development

- **Run Service**: `pdm run -p services/class_management_service dev`
- **Dependencies**: Requires running PostgreSQL, Kafka, and Redis instances, as defined in `docker-compose.infrastructure.yml`.
- **Testing**: The service includes integration tests in `tests/test_api_integration.py` that use a mocked repository to validate API and service logic.
