---
description: 
globs: 
alwaysApply: true
---
# 015: Project Structure Standards

## 1. Root Directory Structure

**Permitted Root Files:**
- `README.md`, `LICENSE`, `pyproject.toml`, `pdm.lock`, `docker-compose.yml`
- `.gitignore`, `.pdm-python`, `.dockerignore`, `AGENTS.md`

**Permitted Root Directories:**
- `.git/`, `.venv/`, `.mypy_cache/`, `__pycache__/`, `.cursor/`, `.ruff_cache/`, `.windsurf/`
- `common_core/`, `services/`, `scripts/`, `Documentation/`

**FORBIDDEN**: Setup scripts, service-specific files, temporary files in root

## 2. Scripts Directory Structure

```
scripts/

```

**Test Script Organization Rules**:
- **Integration Tests**: Use `tests/functional/` for Python pytest-based tests
- **Shell Test Scripts**: Use `scripts/tests/` for bash-based automation and validation
- **Test Utilities**: Use `scripts/tests/` for analysis, tracing, and test support tools

## 3. Services Directory Structure **structural mandates**

```
services/
├── libs/                          # Shared service libraries
├── content_service/               # Individual microservice (Quart HTTP app)
│   ├── app.py                     # Lean Quart application entry point (setup, DI, Blueprint registration)
│   ├── api/                       # **REQUIRED**: Blueprint API routes directory
│   │   ├── __init__.py
│   │   ├── health_routes.py       # Standard health and metrics endpoints
│   │   └── content_routes.py      # Domain-specific API routes
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── config.py                  # Pydantic settings configuration
│   ├── protocols.py               # Optional: Service-specific behavioral contracts
│   ├── tests/
│   └── docs/
├── batch_orchestrator_service/    # Individual microservice (primary orchestrator)
│   ├── app.py                     # Lean Quart application entry point
│   ├── startup_setup.py           # DI initialization, service lifecycle management  
│   ├── metrics.py                 # Prometheus metrics middleware
│   ├── api/                       # **REQUIRED**: Blueprint API routes directory
│   │   ├── __init__.py
│   │   ├── health_routes.py       # Standard health and metrics endpoints
│   │   └── batch_routes.py        # Domain-specific API routes (thin HTTP adapters)
│   ├── implementations/           # **CLEAN ARCHITECTURE**: Protocol implementations
│   │   ├── __init__.py
│   │   ├── batch_repository_impl.py       # MockBatchRepositoryImpl
│   │   ├── event_publisher_impl.py        # DefaultBatchEventPublisherImpl
│   │   ├── essay_lifecycle_client_impl.py # DefaultEssayLifecycleClientImpl
│   │   └── batch_processing_service_impl.py # Service layer business logic
│   ├── protocols.py               # Service-specific behavioral contracts
│   ├── di.py                      # Dishka dependency injection providers
│   ├── config.py                  # Pydantic settings configuration
│   ├── api_models.py              # Request/response models
│   ├── kafka_consumer.py          # Kafka event consumer
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── tests/
│   └── docs/
├── spell_checker_service/         # Example Kafka worker service (no HTTP API)
│   ├── worker_main.py             # Main entry point, DI setup, Kafka consumer loop
│   ├── event_processor.py         # Clean message processing logic with injected dependencies
│   ├── core_logic.py              # Core algorithms and helper functions
│   ├── protocols.py               # Service-specific behavioral contracts
│   ├── config.py                  # Service configuration with Pydantic BaseSettings
│   ├── di.py                      # Dishka dependency injection providers
│   ├── protocol_implementations/  # **CLEAN ARCHITECTURE**: Protocol implementations
│   │   ├── __init__.py
│   │   ├── content_client_impl.py # HTTP content fetching implementation
│   │   ├── result_store_impl.py   # HTTP content storage implementation
│   │   ├── spell_logic_impl.py    # Spell checking orchestration implementation
│   │   └── event_publisher_impl.py # Kafka event publishing implementation
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── tests/
│   └── docs/
├── file_service/                  # File upload and content ingestion service (HTTP + Kafka)
│   ├── app.py                     # Lean Quart application entry point (setup, DI, Blueprint registration)
│   ├── api/                       # **REQUIRED**: Blueprint API routes directory
│   │   ├── __init__.py
│   │   ├── health_routes.py       # Standard health and metrics endpoints
│   │   └── file_routes.py         # File upload and batch processing API routes
│   ├── config.py                  # Pydantic settings configuration
│   ├── protocols.py               # Service-specific behavioral contracts
│   ├── di.py                      # Dishka dependency injection providers
│   ├── core_logic.py              # File processing workflow logic
│   ├── text_processing.py         # Text extraction and student info parsing
│   ├── hypercorn_config.py        # Hypercorn server configuration
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── README.md
│   ├── tests/
│   └── docs/
└── essay_lifecycle_service/       # Hybrid HTTP + Kafka service
    ├── app.py                     # Lean Quart HTTP API entry point
    ├── api/                       # **REQUIRED**: Blueprint API routes directory
    │   ├── __init__.py
    │   ├── health_routes.py       # Standard health and metrics endpoints
    │   └── essay_routes.py        # Essay status and lifecycle API routes
    ├── worker_main.py             # Kafka event consumer entry point
    ├── state_store.py             # Essay state persistence layer
    ├── batch_tracker.py           # Batch coordination and readiness tracking
    ├── batch_command_handlers.py  # Command processing for batch operations
    ├── core_logic.py              # Business logic and state transitions
    ├── protocols.py               # Service behavioral contracts
    ├── config.py                  # Service configuration
    ├── di.py                      # Dependency injection setup (lean, ~114 lines)
    ├── implementations/           # **CLEAN ARCHITECTURE**: Business logic implementations
    │   ├── __init__.py
    │   ├── content_client.py      # HTTP content storage operations
    │   ├── event_publisher.py     # Kafka event publishing logic
    │   ├── metrics_collector.py   # Prometheus metrics collection
    │   ├── batch_command_handler_impl.py # Batch command processing
    │   └── service_request_dispatcher.py # Specialized service request dispatching
    ├── pyproject.toml
    ├── tests/
    └── docs/
```

## 4. HTTP Service Blueprint Structure **MANDATORY**

**For all HTTP services (Quart-based), the following structure is REQUIRED:**

### 4.1. app.py Structure Requirements
- **MUST** be lean (< 150 lines) focused on:
  - Quart app initialization
  - Dependency injection setup
  - Blueprint registration
  - Global middleware (metrics, logging)
  - Startup/shutdown hooks
- **FORBIDDEN**: Direct route definitions in app.py

### 4.2. Standard Blueprint Files

**Note on Worker Service Structure (e.g., `spell_checker_service`):**
- `worker_main.py`: Handles service lifecycle (startup, shutdown), Kafka client management, signal handling, and the primary message consumption loop. Initializes DI container.
- `event_processor.py`: Contains logic for deserializing incoming messages, implementing defined protocols (often by composing functions from `core_logic.py`), and orchestrating the processing flow for a single message.
- `core_logic.py`: Houses the fundamental, reusable business logic, algorithms, and interactions with external systems (like HTTP calls to other services), implemented as standalone functions or simple classes.
- `protocols.py`: Defines `typing.Protocol` interfaces for key internal dependencies and behavioral contracts, facilitating DI and testability.

## 5. Common Core Structure

```
common_core/
├── src/
│   └── common_core/
│       ├── __init__.py
│       ├── enums.py
│       ├── metadata_models.py
│       ├── events/
│       └── py.typed
├── tests/                         
├── pyproject.toml
└── README.md                      
```

## 6. Documentation Directory Structure

```
Documentation/
├── TASKS/
│   ├── PHASE_1.0.md               
│   ├── PHASE_1.1.md
│   └── PHASE_1.2.md
├── dependencies/
├── PDR:s/
└── setup_environment/
```

## 7. Documentation Placement Rules

- **Root README.md**: Project overview and architecture
- **Service README.md**: `services/{service_name}/README.md`
- **Common Core README.md**: `common_core/README.md`
- **FORBIDDEN**: README.md files in separate documentation folders

## 8. File Creation Rules

**MUST** verify target directory exists and follows this structure before creating files.
**MUST** create necessary parent directories if they don't exist.
**FORBIDDEN**: Files that violate this structure.
**HTTP Services**: MUST include api/ directory structure with Blueprint pattern.
