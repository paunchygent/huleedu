# Gemini Code Assistant - HuleEdu Developer Technical Reference

This document is the authoritative source of truth for all architectural patterns, coding standards, and development practices within the HuleEdu monorepo. All development must adhere to these standards. Always reference the rules in .cursor/rules/ when planning, coding, testing, and debugging.

## **`010: Foundational Principles`**

### 1\. Architecture Overview

HuleEdu implements an event-driven microservice architecture using Domain-Driven Design (DDD) principles. Each service owns its bounded context, communicates primarily asynchronously via Kafka events, and may expose internal or external HTTP APIs for synchronous operations.

### 2\. Tech Stack

* **Core Frameworks & Libraries**: Quart, PDM, Dishka, aiokafka, aiohttp, Pydantic
* **Database & Persistence**: PostgreSQL, SQLAlchemy, asyncpg, SQLite, aiosqlite, Filesystem
* **Containerization & Orchestration**: Docker, Docker Compose
* **Testing**: Pytest
* **Monitoring & Observability**: Prometheus

## **`020: Architectural Mandates`**

### 1\. Service Communication Patterns

* **Asynchronous First**: The default communication pattern between services is asynchronous messaging via Kafka.
* **Synchronous for Queries**: Direct HTTP calls between services are permitted for immediate, read-only queries or when a service requires an immediate response to continue its workflow.
* **No Direct DB Access**: A service **MUST NEVER** access the database of another service directly.

### 2\. Database & Persistence

* **SQLAlchemy ORM**: All database interactions **MUST** use SQLAlchemy's async capabilities with the `asyncpg` driver for PostgreSQL.
  * **Evidence**: The use of `DeclarativeBase` and `Mapped` in **@services/batch\_orchestrator\_service/models\_db.py**.
* **Service-Specific Databases**: Each service requiring persistence **MUST** have its own dedicated PostgreSQL database, managed via **@docker-compose.infrastructure.yml**.

## **`042: Service Architecture & DI Patterns`**

### 1\. HTTP Service Pattern (Quart)

All HTTP services **MUST** follow the Blueprint pattern for modularity.

* **Lean `app.py`**: The main application file is for setup only: Quart app creation, DI container initialization, and Blueprint registration.
* **Blueprints in `api/`**: All routes are defined in separate files within an `api/` directory.
  * **Evidence**: The structure of **@services/file\_service/app.py** and its registration of Blueprints from **@services/file\_service/api/**.

### 2\. Worker Service Pattern (Kafka)

Event-driven services **MUST** separate concerns into distinct modules.

* `worker_main.py`: Handles the service lifecycle, DI setup, and the main consumption loop.
* `event_processor.py`: Contains the core business logic for processing a single message by calling injected protocols.
  * **Evidence**: The structure of **@services/spell\_checker\_service/**.

### 3\. Dependency Injection (Dishka & Protocols)

* **Protocol-First Design**: All internal dependencies **MUST** be defined as interfaces using `typing.Protocol` in a `protocols.py` file.
* **Provider Pattern**: Each service **MUST** define a Dishka `Provider` class in `di.py` to bind protocols to their concrete implementations.
  * **Evidence**: The `CJAssessmentServiceProvider` in **@services/cj\_assessment\_service/di.py**.
* **Scope Management**:
  * `Scope.APP`: Used for stateless singletons (e.g., settings, HTTP client sessions).
  * `Scope.REQUEST`: Used for per-operation instances (e.g., database sessions).

## **`051 & 052: Event System & Data Contracts`**

### 1\. EventEnvelope Standard

All events transmitted via Kafka **MUST** be wrapped in the standardized `EventEnvelope` Pydantic model.

* **Evidence**: The `EventEnvelope` is a `pydantic.BaseModel` defined in **@common\_core/src/common\_core/events/envelope.py**.

```python
# Correct Pydantic Model from @common_core/src/common_core/events/envelope.py
class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_timestamp: datetime
    source_service: str
    correlation_id: Optional[UUID] = None
    data: T_EventData