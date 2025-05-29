# Essay Lifecycle Service (ELS)

## 🎯 Service Purpose

ELS acts as a **stateful command handler** in the essay processing pipeline, operating strictly under the direction of the **Batch Orchestrator Service (BOS)**. It manages individual essay states, coordinates with specialized processing services, and implements the **batch readiness aggregation pattern** to enable BOS-centric orchestration.

## 🔄 Batch Coordination Architecture

ELS implements the **Count-Based Aggregation Pattern** for coordinating batch readiness:

### Coordination Flow

1. **Registration**: BOS informs ELS about batch expectations (`BatchEssaysRegistered`)
2. **Aggregation**: ELS tracks individual essay readiness from File Service (`EssayContentReady`)
3. **Completion**: ELS notifies BOS when entire batch is ready (`BatchEssaysReady`)

### State Transition Model

- **File Service Domain**: `UPLOADED` → `TEXT_EXTRACTED` → `CONTENT_INGESTING` → `CONTENT_INGESTION_FAILED`
- **ELS Handoff Point**: `READY_FOR_PROCESSING` (essays ready for pipeline assignment)
- **ELS Pipeline Domain**: `AWAITING_SPELLCHECK` → `SPELLCHECKING_IN_PROGRESS` → `SPELLCHECKED_SUCCESS`/`SPELLCHECK_FAILED` → `ESSAY_CRITICAL_FAILURE`

This architecture ensures clean service boundaries: File Service owns content ingestion, ELS manages pipeline processing, and BOS orchestrates the overall batch lifecycle.

## 🔧 Key Functions

- **Batch Readiness Coordination**: Tracks batch expectations and aggregates individual essay readiness for BOS
- **Command Processing**: Receives and processes batch commands from BOS to initiate processing phases for individual essays
- **State Management**: Maintains comprehensive state tracking for each essay throughout its processing lifecycle
- **Event Publishing**: Publishes essay state change events and batch phase completion summaries back to BOS
- **Progress Tracking**: Provides detailed timeline and status information for monitoring and debugging
- **Important**: ELS does NOT initiate processing decisions. All processing commands originate from BOS.
- **API Scope**: Provides read-only query endpoints for essay state visibility. Control operations are exclusively handled by BOS.

## 🔄 Data Flow: Commands, Events, and Queries

ELS participates in these communication patterns:

- **Consumes from Kafka**:
  - **Batch Registration**: Receives batch expectations from BOS (`BatchEssaysRegistered`)
  - **Essay Readiness**: Receives individual essay readiness from File Service (`EssayContentReady`)
  - **Batch Commands**: Receives commands from BOS (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`) to start processing phases
  - **Specialized Service Results**: Consumes results from specialized services indicating processing outcomes
- **Publishes to Kafka**:
  - **Batch Readiness**: Notifies BOS when all essays in batch are ready (`BatchEssaysReady`)
  - **Essay State Updates**: Individual essay status changes
  - **Batch Phase Conclusions**: Aggregated results sent back to BOS when all essays in a batch complete a pipeline
- **HTTP API**:
  - **Query-Only**: Provides read-only access to essay and batch state information
  - **No Control Operations**: Does not accept processing commands via HTTP

## 🚀 API Endpoints (Read-Only Queries)

The service provides a **read-only HTTP API** for status queries and monitoring, versioned under `/v1`.

- **`GET /healthz`**: Standard health check.
- **`GET /v1/essays/{essay_id}/status`**: Get current status, progress, timeline, and storage references for a specific essay.
- **`GET /v1/essays/{essay_id}/timeline`**: Get a detailed processing timeline and metadata for an essay.  
- **`GET /v1/batches/{batch_id}/status`**: Get a summary of essay statuses and completion percentage for a batch.

**Note**: All processing control (initiation, retry, cancellation) is handled by the Batch Orchestrator Service. ELS provides visibility into essay states but does not accept processing commands via HTTP API.

## архитектура и технологии

ELS is a hybrid service combining a Kafka-based worker for asynchronous processing with an HTTP API for queries:

- **Primary Processing Engine**: A Kafka consumer worker (`worker_main.py`) handles events and commands.
- **API Layer**: A Quart application (`app.py`) provides RESTful endpoints. It's served by Hypercorn.
- **State Persistence**: Essay states are stored in an SQLite database, accessed asynchronously via `aiosqlite`. The `SQLiteEssayStateStore` in `state_store.py` manages database interactions.
- **Dependency Injection**: Utilizes Dishka for managing dependencies. The `EssayLifecycleServiceProvider` in `di.py` defines providers for various components, which adhere to interfaces defined in `protocols.py`.
- **Core Logic**: Business rules, such as state transition validation, are encapsulated in modules like `core_logic.py`.
- **Command & Event Handling**: The `batch_command_handlers.py` module is responsible for routing incoming Kafka messages (commands from BOS, events from specialized services) to the appropriate processing logic.

Key technologies include Python 3.11+, Quart, AIOKafka, AIOSQLite, Pydantic, and Dishka.

## 💾 State Management

- Essay lifecycle states are persisted in an SQLite database (`essay_lifecycle.db` by default).
- The `EssayState` Pydantic model defines the structure of the stored data, including status, metadata, timeline, and references to content stored elsewhere.
- `SQLiteEssayStateStore` class in `state_store.py` provides asynchronous CRUD operations and initializes the database schema.

## ⚙️ Configuration

Configuration is managed via `services/essay_lifecycle_service/config.py` using Pydantic `BaseSettings`, loading from environment variables (prefixed with `ESSAY_LIFECYCLE_SERVICE_`) and/or a `.env` file.

Key settings include:

- Logging (`LOG_LEVEL`)
- Kafka connection details (`KAFKA_BOOTSTRAP_SERVERS`, `CONSUMER_GROUP`)
- HTTP API settings (`HTTP_HOST`, `HTTP_PORT`)
- Database path (`DATABASE_PATH`)
- URLs for dependent services like Content Service and Batch Orchestrator Service.
- Prometheus metrics port (`PROMETHEUS_PORT`).

## 🧱 Dependencies

Key dependencies are listed in `services/essay_lifecycle_service/pyproject.toml`.

- **Internal Libraries**: `huleedu-common-core`, `huleedu-service-libs`.
- **Frameworks/Drivers**: `quart`, `hypercorn`, `aiokafka`, `aiosqlite`, `aiohttp`.
- **Tooling**: `pydantic`, `pydantic-settings`, `dishka`, `quart-dishka`, `prometheus-client`.

## 💻 Local Development

1. **Prerequisites**: Python 3.11+, PDM. Ensure dependent services (Kafka, Content Service, Batch Orchestrator Service) are running.
2. **Install Dependencies**: From monorepo root: `pdm install -G dev`.
3. **Environment Configuration**: Create a `.env` file in `services/essay_lifecycle_service/` (refer to `config.py` for variables).
4. **Run the Service**:
    - **Worker**: From monorepo root, `pdm run -p services/essay_lifecycle_service start_worker`.
    - **API**: From monorepo root, `pdm run -p services/essay_lifecycle_service start` (or `
