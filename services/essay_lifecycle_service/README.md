# HuleEdu Essay Lifecycle Service (ELS)

## 🎯 Service Purpose and Role

The **Essay Lifecycle Service (ELS)** is a crucial stateful microservice within the HuleEdu platform. Its primary responsibility is to **manage and track the processing state of individual essays** as they progress through various analysis and feedback stages, such as spell-checking, NLP analysis, and AI-generated feedback.

ELS acts as a **subordinate orchestrator and stateful command handler** in the essay processing pipeline. It operates under the direction of the **Batch Orchestrator Service (BOS)**, which issues commands to ELS to initiate processing phases for batches of essays. ELS then dispatches tasks for individual essays to specialized services and updates essay states based on the results received.

Key functions include:

* Persistently storing and updating the lifecycle state of each essay (e.g., `AWAITING_SPELLCHECK`, `NLP_COMPLETED_SUCCESS`).
* Processing commands from the Batch Orchestrator Service to start specific processing phases for essays within a batch.
* Dispatching individual essay processing requests to specialized services (like Spell Checker, NLP Service).
* Consuming event results from these specialized services to transition essay states.
* Validating state transitions according to predefined business logic.
* Publishing essay status updates and aggregated batch processing progress/conclusion events to Kafka, primarily for the Batch Orchestrator Service.
* Providing an HTTP API for querying essay and batch statuses and timelines.

## архитектура и технологии

ELS is a hybrid service combining a Kafka-based worker for asynchronous processing with an HTTP API for queries:

* **Primary Processing Engine**: A Kafka consumer worker (`worker_main.py`) handles events and commands.
* **API Layer**: A Quart application (`app.py`) provides RESTful endpoints. It's served by Hypercorn.
* **State Persistence**: Essay states are stored in an SQLite database, accessed asynchronously via `aiosqlite`. The `SQLiteEssayStateStore` in `state_store.py` manages database interactions.
* **Dependency Injection**: Utilizes Dishka for managing dependencies. The `EssayLifecycleServiceProvider` in `di.py` defines providers for various components, which adhere to interfaces defined in `protocols.py`.
* **Core Logic**: Business rules, such as state transition validation, are encapsulated in modules like `core_logic.py`.
* **Command & Event Handling**: The `batch_command_handlers.py` module is responsible for routing incoming Kafka messages (commands from BOS, events from specialized services) to the appropriate processing logic.

Key technologies include Python 3.11+, Quart, AIOKafka, AIOSQLite, Pydantic, and Dishka.

## 🔄 Data Flow: Events, Commands, and Requests

ELS participates in several communication patterns:

* **Consumes from Kafka**:
  * **Batch Commands**: Listens for commands from the Batch Orchestrator Service (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`) on dedicated topics to start processing phases for batches.
  * **Specialized Service Results**: Consumes events from services like the Spell Checker (e.g., carrying `SpellcheckResultDataV1`) indicating the outcome of a processing step for an essay.
  * Listens to topics like `essay.upload.events`, `essay.spellcheck.events`, `essay.nlp.events`, `essay.ai_feedback.events`.
* **Publishes to Kafka** (via `EventPublisher` protocol):
  * General status updates for individual essays (e.g., `essay.status.updated.v1`).
  * Aggregated batch phase progress and conclusion events to the Batch Orchestrator Service (e.g., `batch.phase.progress.v1`, `batch.phase.concluded.v1`).
* **Dispatches Requests to Specialized Services** (via `SpecializedServiceRequestDispatcher` protocol, likely over Kafka):
  * Sends requests like `EssayLifecycleSpellcheckRequestV1` to the Spell Checker Service to process an individual essay.

## 🚀 API Endpoints

The service provides an HTTP API for status queries and management, versioned under `/v1` (configurable via `settings.API_VERSION`).

* **`GET /healthz`**: Standard health check.
* **`GET /v1/essays/{essay_id}/status`**: Get current status, progress, timeline, and storage references for a specific essay.
* **`GET /v1/essays/{essay_id}/timeline`**: Get a detailed processing timeline and metadata for an essay.
* **`GET /v1/batches/{batch_id}/status`**: Get a summary of essay statuses and completion percentage for a batch.
* **`POST /v1/essays/{essay_id}/retry`**: Mark an essay for reprocessing in a specific phase. ELS updates its state; the Batch Orchestrator Service is expected to detect this state and re-initiate the necessary batch command.

## 💾 State Management

* Essay lifecycle states are persisted in an SQLite database (`essay_lifecycle.db` by default).
* The `EssayState` Pydantic model defines the structure of the stored data, including status, metadata, timeline, and references to content stored elsewhere.
* `SQLiteEssayStateStore` class in `state_store.py` provides asynchronous CRUD operations and initializes the database schema.

## ⚙️ Configuration

Configuration is managed via `services/essay_lifecycle_service/config.py` using Pydantic `BaseSettings`, loading from environment variables (prefixed with `ESSAY_LIFECYCLE_SERVICE_`) and/or a `.env` file.

Key settings include:

* Logging (`LOG_LEVEL`)
* Kafka connection details (`KAFKA_BOOTSTRAP_SERVERS`, `CONSUMER_GROUP`)
* HTTP API settings (`HTTP_HOST`, `HTTP_PORT`)
* Database path (`DATABASE_PATH`)
* URLs for dependent services like Content Service and Batch Orchestrator Service.
* Prometheus metrics port (`PROMETHEUS_PORT`).

## 🧱 Dependencies

Key dependencies are listed in `services/essay_lifecycle_service/pyproject.toml`.

* **Internal Libraries**: `huleedu-common-core`, `huleedu-service-libs`.
* **Frameworks/Drivers**: `quart`, `hypercorn`, `aiokafka`, `aiosqlite`, `aiohttp`.
* **Tooling**: `pydantic`, `pydantic-settings`, `dishka`, `quart-dishka`, `prometheus-client`.

## 💻 Local Development

1. **Prerequisites**: Python 3.11+, PDM. Ensure dependent services (Kafka, Content Service, Batch Orchestrator Service) are running.
2. **Install Dependencies**: From monorepo root: `pdm install -G dev`.
3. **Environment Configuration**: Create a `.env` file in `services/essay_lifecycle_service/` (refer to `config.py` for variables).
4. **Run the Service**:
    * **Worker**: From monorepo root, `pdm run -p services/essay_lifecycle_service start_worker`.
    * **API**: From monorepo root, `pdm run -p services/essay_lifecycle_service start` (or `dev` for debug mode).

## 🧪 Testing

Tests for ELS should cover:

* API endpoint functionality.
* Kafka message processing (commands and events).
* State transitions and validation logic.
* Database interactions.
* Interactions with mocked dependent services.

Run tests using Pytest (example from monorepo root):

```bash
pdm run pytest services/essay_lifecycle_service/tests/ -v
