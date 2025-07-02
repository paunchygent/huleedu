# Claude Code Assistant - HuleEdu Developer Rule Reference

## **Workflow: The Unchanging Ritual**

Your operational process for **every task** is fixed and non-negotiable.

### **Step 1: Ingest Core Architectural Knowledge (Mandatory First Action)**

#### **.cursor/rules/015-project-structure-standards.mdc MUST be RESPECTED**

#### **Begin each conversation by reading the following files:
.cursor/rules/010-foundational-principles.mdc
.cursor/rules/020-architectural-mandates.mdc
.cursor/rules/030-event-driven-architecture-eda-standards.mdc
.cursor/rules/040-service-implementation-guidelines.mdc
.cursor/rules/041-http-service-blueprint.mdc
.cursor/rules/042-async-patterns-and-di.mdc
.cursor/rules/044-service-debugging-and-troubleshooting.mdc
.cursor/rules/050-python-coding-standards.mdc
.cursor/rules/080-repository-workflow-and-tooling.mdc
.cursor/rules/100-terminology-and-definitions.mdc
.cursor/rules/110.1-planning-mode.mdc
.cursor/rules/110.2-coding-mode.mdc

Before analyzing any specific task, you **MUST** first read and internalize the entire **Technical Reference** section of this document This summary of our core principles is your primary context. You must also access all rules referenced (.cursor/rules/) by using the index referenced in the below instructions (070 = .cursor/rules/070-testing-and-quality-assurance.mdc)

### **Step 2: Task-Specific Analysis**

1. **Select Interaction Mode:** Use the `.cursor/rules/110-ai-agent-interaction-modes.mdc` rule to select the correct mode for the given task (e.g., Planning, Coding, Debugging).
2. **Consult Rule Index:** Use `.cursor/rules/000-rule-index.mdc` to identify any additional service-specific or pattern-specific rules relevant to the task.
3. **Read Task Documentation:** Read the full task description from the `TASKS/` directory.

When encountering errors or architectural questions:

  1. **Investigate First, Propose Second**
     - ALWAYS check the actual implementation before proposing changes
     - Verify your assumptions by reading the code
     - Look at how existing services solve similar problems

  2. **Prefer Existing Patterns**
     - Follow established patterns in the codebase
     - Don't introduce new patterns without compelling reasons
     - Simpler solutions are usually better

  3. **Avoid Premature Architecture**
     - Don't propose "dual" patterns, factories, or abstractions unless absolutely
  necessary
     - Single implementation > Multiple implementations
     - Self-contained > Complex dependency injection

  4. **Root Cause Analysis**
     - Error messages often mask the real issue
     - Import errors can cause cascade failures that look like design problems
     - Fix the immediate issue before redesigning the system

  Remember: The codebase already has working patterns. Use them.

### **Step 3: Execution and Documentation**

- **Document Progress:** As you complete meaningful work, update the relevant task document. Adhere to the standards in `/.cursor/rules/090-documentation-standards.mdc`. **NEVER CREATE FILES IN ROOT: FOLLOW THE APPROPRIATE FOLDER PATTERN**
- **Update Rules:** If you identify outdated patterns or develop new best practices, you are required to propose updates to the rule files to ensure our architectural knowledge base remains current.
- **Test and Verify:** All functional code changes require tests. Tests are only considered complete after they have been run at least once and confirmed as passing. Before concluding a task, run the appropriate test scope and verify that no regressions have been introduced.

-----

## **Technical Reference**

### **`010: Foundational Principles`**

#### 1\. Architecture Overview

HuleEdu implements an event-driven microservice architecture using Domain-Driven Design (DDD) principles. Each service owns its bounded context, communicates primarily asynchronously via Kafka events, and may expose internal or external HTTP APIs for synchronous operations.

#### 2\. Tech Stack

- **Core Frameworks & Libraries**: Quart, PDM, Dishka, aiokafka, aiohttp, Pydantic (FastAPI in API Gateway)
- **Database & Persistence**: PostgreSQL, SQLAlchemy, asyncpg, SQLite, aiosqlite, Filesystem
- **Containerization & Orchestration**: Docker, Docker Compose
- **Testing**: Pytest
- **Monitoring & Observability**: Prometheus

### **`020: Architectural Mandates`**

#### 1\. Service Communication Patterns

- **Asynchronous First**: The default communication pattern between services is asynchronous messaging via Kafka.
- **Synchronous for Queries**: Direct HTTP calls between services are permitted for immediate, read-only queries or when a service requires an immediate response to continue its workflow.
- **No Direct DB Access**: A service **MUST NEVER** access the database of another service directly.

#### 2\. Database & Persistence

- **SQLAlchemy ORM**: All database interactions **MUST** use SQLAlchemy's async capabilities with the `asyncpg` driver for PostgreSQL.
  - **Evidence**: The use of `DeclarativeBase` and `Mapped` in **@services/batch\_orchestrator\_service/models\_db.py**.
- **Service-Specific Databases**: Each service requiring persistence **MUST** have its own dedicated PostgreSQL database, managed via **@docker-compose.infrastructure.yml**.

### **`042: Service Architecture & DI Patterns`**

#### 1\. HTTP Service Pattern (Quart)

All HTTP services **MUST** follow the Blueprint pattern for modularity.

- **Lean `app.py`**: The main application file is for setup only: Quart app creation, DI container initialization, and Blueprint registration.
- **Blueprints in `api/`**: All routes are defined in separate files within an `api/` directory.
  - **Evidence**: The structure of **@services/file\_service/app.py** and its registration of Blueprints from **@services/file\_service/api/**.

#### 2\. Worker Service Pattern (Kafka)

Event-driven services **MUST** separate concerns into distinct modules.

- `worker_main.py`: Handles the service lifecycle, DI setup, and the main consumption loop.
- `event_processor.py`: Contains the core business logic for processing a single message by calling injected protocols.
  - **Evidence**: The structure of **@services/spell\_checker\_service/**.

#### 3\. Dependency Injection (Dishka & Protocols)

- **Protocol-First Design**: All internal dependencies **MUST** be defined as interfaces using `typing.Protocol` in a `protocols.py` file.
- **Provider Pattern**: Each service **MUST** define a Dishka `Provider` class in `di.py` to bind protocols to their concrete implementations.
  - **Evidence**: The `CJAssessmentServiceProvider` in **@services/cj\_assessment\_service/di.py**.
- **Scope Management**:
  - `Scope.APP`: Used for stateless singletons (e.g., settings, HTTP client sessions).
  - `Scope.REQUEST`: Used for per-operation instances (e.g., database sessions).

### **`051 & 052: Event System & Data Contracts`**

#### 1\. EventEnvelope Standard

All events transmitted via Kafka **MUST** be wrapped in the standardized `EventEnvelope` Pydantic model.

- **Evidence**: The `EventEnvelope` is a `pydantic.BaseModel` defined in **@common\_core/src/common\_core/events/envelope.py**.

<!-- end list -->

```python
# Correct Pydantic Model from @common_core/src/common_core/events/envelope.py
class EventEnvelope(BaseModel, Generic[T_EventData]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_timestamp: datetime
    source_service: str
    correlation_id: Optional[UUID] = None
    data: T_EventData
```

#### 2\. Topic Naming Convention

Topic names **MUST** be generated via the `topic_name()` utility function.

- **Evidence**: The `topic_name` function in **@common\_core/src/common\_core/event\_enums.py**.

#### 3\. Thin Events

For large data payloads, the event **MUST** contain a `StorageReferenceMetadata` object pointing to the content in the `Content Service`, not the content itself.

### **`050 & 084: Coding & Containerization Standards`**

#### 1\. Import Conventions

- **Local Development**: All local execution **MUST** be done through `pdm run ...`.
- **Docker**: All service `Dockerfile`s **MUST** include `ENV PYTHONPATH=/app`.
  - **Evidence**: The `Dockerfile` for **@services/file\_service/Dockerfile**.

#### 2\. Code Quality

- **File Size Limit**: Python files **MUST NOT** exceed 400 lines of code (LoC).
- **Linting & Formatting**: All code **MUST** be formatted and linted with Ruff using the configuration in the root **@pyproject.toml**.

### **`070: Testing Architecture`**

#### 1\. Protocol-Based Mocking

Tests **MUST** mock the protocol interfaces, not the concrete implementations.

```python
# Correct testing pattern
async def test_my_service_logic(
    # Mocks are of the protocol type
    mock_repo: AsyncMock(spec=ClassRepositoryProtocol),
    mock_publisher: AsyncMock(spec=ClassEventPublisherProtocol)
):
    # Arrange: Instantiate the service with mocks
    service = ClassManagementServiceImpl(repo=mock_repo, event_publisher=mock_publisher)
    
    # Act
    await service.register_new_class(...)
    
    # Assert
    mock_repo.create_class.assert_called_once()
    mock_publisher.publish_class_event.assert_called_once()
```

#### 2\. Contract Testing

Tests for any event-producing or consuming logic **MUST** include a serialization "round-trip" test to ensure the Pydantic models are correctly configured.

#### 3\. Test Execution Scope

When validating changes, you **MUST NOT** run the entire test suite (`pdm run test-all`) by default, as this is inefficient. You **MUST** run tests with a targeted scope.

- **For New Features**: Run only the new test files you have created.
  - **Example**: `pdm run pytest services/class_management_service/tests/api/test_class_routes.py`
- **For Changes to Existing Code**: Run the tests for the specific service or module that has been affected.
  - **Example**: `pdm run pytest services/file_service/tests/`
- The `test-all` command should only be used for final validation before a major merge or when explicitly instructed.

### **`080: Development Workflow & Tooling`**

All standard development tasks are executed via PDM scripts defined in the root **@pyproject.toml**.

#### 1\. Code Quality & Formatting

- `pdm run format-all`: Formats all code across the monorepo using Ruff.
- `pdm run lint-all`: Lints all code using Ruff.
- `pdm run lint-fix`: Lints and automatically fixes all possible issues with Ruff.

#### 2\. Static Analysis

- `pdm run typecheck-all`: Runs MyPy on the entire codebase to perform static type checking.

#### 3\. Testing

- `pdm run test-all`: Runs the complete test suite using `pytest`. (See Rule 070 for scoping).
- `pdm run test-parallel`: Runs tests in parallel across multiple CPU cores (`pytest -n auto`).
- `pdm run -p services/<service_name> test`: Runs the specific test suite for an individual service.
