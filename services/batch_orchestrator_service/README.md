# Batch Orchestrator Service (BOS)

## Service Purpose and Role

The **Batch Orchestrator Service** is the central coordinator for the HuleEdu essay processing pipeline. It implements the **BOS-centric architecture** where all batch processing decisions and orchestration flow through this primary service.

Its key responsibilities include:

* **Batch Lifecycle Management**: Create, configure, and manage the complete lifecycle of essay batches
* **Batch Type Orchestration**: Determine GUEST (anonymous) vs REGULAR (class-based) batch processing flows
* **Phase 1 Student Matching**: Coordinate student-essay association for REGULAR batches through NLP Service
* **Batch Readiness Coordination**: Implement count-based aggregation pattern to track when all essays are ready for processing
* **Pipeline Orchestration**: Coordinate processing phases across specialized services (spellcheck, NLP, AI feedback, etc.)
* **Processing Decision Authority**: All processing initiation, retry, and failure handling decisions originate from BOS
* **Content Ingestion Coordination**: Work with Content Service and File Service to manage initial essay ingestion
* **Progress Monitoring**: Track and expose batch processing progress to users and external systems

## 🔄 Batch Coordination Architecture

BOS implements the **Count-Based Aggregation Pattern** as the central orchestrator:

### Coordination Flow

#### Phase 0: Batch Setup
1. **Batch Creation**: BOS creates batch with internal essay ID slots, storing `class_id` for REGULAR batches
2. **Registration**: BOS registers batch with ELS (`BatchEssaysRegistered`)
3. **Content Coordination**: File Service provisions content to ELS for slot assignment

#### Phase 1: Content Readiness & Student Matching
4. **Content Provisioning**: ELS notifies BOS when all slots are filled (`BatchContentProvisioningCompletedV1`)
5. **Batch Type Decision**:
   - **GUEST batches** (no class_id): Direct transition to READY_FOR_PIPELINE_EXECUTION
   - **REGULAR batches** (has class_id): Initiate student matching workflow
6. **Student Matching** (REGULAR only): BOS coordinates NLP Service to match essays to students
7. **Human Validation** (REGULAR only): Class Management Service facilitates teacher review
8. **Association Confirmation**: BOS receives confirmed student associations, transitions to ready state

#### Phase 2: Pipeline Processing  
9. **Client-Triggered Processing**: Client explicitly requests pipeline execution via HTTP API
10. **Command Processing**: BOS generates commands with actual essay IDs and dispatches to ELS
11. **Progress Monitoring**: BOS tracks progress across all processing phases and provides status to clients

### Service Boundary Responsibilities

* **BOS**: Owns batch lifecycle, processing decisions, and pipeline orchestration
* **ELS**: Aggregates essay readiness, manages individual essay states
* **File Service**: Processes individual essay content, reports readiness to ELS
* **Specialized Services**: Execute specific processing tasks (spellcheck, NLP, etc.)

This architecture ensures BOS maintains central control while leveraging other services for their domain expertise.

## 🏗️ Clean Architecture Implementation

BOS follows **Clean Architecture** patterns with strict separation of concerns:

### Service Structure

``` text
services/batch_orchestrator_service/
├── app.py                         # Lean Quart entry point (< 50 lines)
├── startup_setup.py               # DI initialization, service lifecycle
├── api/                           # HTTP Blueprint routes
│   ├── health_routes.py           # Health and metrics endpoints
│   └── batch_routes.py            # Batch operations (thin HTTP adapters)
├── implementations/               # Clean Architecture implementations
│   ├── batch_repository_postgres_impl.py # Production PostgreSQL repository
│   ├── batch_repository_impl.py   # Mock repository for testing
│   ├── event_publisher_impl.py    # DefaultBatchEventPublisherImpl
│   ├── batch_conductor_client_impl.py # HTTP client for BCS pipeline resolution
│   ├── batch_essays_ready_handler.py # Handler for ready events
│   ├── els_batch_phase_outcome_handler.py # Handler for phase completion events
│   └── batch_processing_service_impl.py # Service layer business logic
├── protocols.py                   # Protocol definitions for DI
├── di.py                          # Dishka providers importing implementations
├── config.py                      # Pydantic settings
├── api_models.py                  # Request/response models
└── kafka_consumer.py              # Kafka event consumer
```

### Architectural Principles

* **Service Layer**: Business logic extracted from HTTP routes into `BatchProcessingServiceImpl`
* **Protocol-Based DI**: All dependencies injected via `typing.Protocol` abstractions
* **Constructor Injection**: Implementations receive dependencies through constructors
* **Single Responsibility**: Each module has one clear purpose
* **Clean Separation**: HTTP ↔ Service Layer ↔ Repository ↔ External Services

## API Endpoints

### Current Endpoints

* **`POST /v1/batches/register`**:
  * Accepts batch registration requests with essay details.
  * Delegates to `BatchProcessingServiceProtocol.register_new_batch()` service layer.
  * Publishes `BatchEssaysRegistered` event to ELS for readiness tracking.
  * Returns `202 Accepted` with `batch_id` and `correlation_id`.
* **`GET /v1/batches/{batch_id}/status`**:
  * Retrieves the current status and detailed pipeline state of a specific batch.
  * Returns `200 OK` with batch context and pipeline state information.
* **`GET /healthz`**: Service health check returning `{"status": "ok"}`.
* **`GET /metrics`**: Prometheus metrics in OpenMetrics format.

## Event Publishing

Published to Kafka topics for downstream coordination:

* **`huleedu.batch.essays.registered.v1`**:
  * **Data**: `BatchEssaysRegistered` with internal essay ID slots and batch context.
  * **Trigger**: After successful batch registration.
  * **Consumer**: Essay Lifecycle Service for slot assignment.
* **`huleedu.batch.*.initiate.command.v1`**:
  * **Data**: `BatchService<Phase>InitiateCommandDataV1` (e.g., for spellcheck, cj_assessment).
  * **Trigger**: After receiving a phase completion event from ELS, to start the next phase.
  * **Consumer**: Essay Lifecycle Service for command processing.

## Event Consumption

Consumed from Kafka for batch coordination:

* **`huleedu.els.batch.essays.ready.v1`**:
  * **Data**: `BatchEssaysReady` with ready essays including actual essay IDs and text_storage_ids.
  * **Handler**: `BatchEssaysReadyHandler` stores essay metadata and storage references in persistent database and logs readiness, awaiting client pipeline trigger.
* **`huleedu.els.batch_phase.outcome.v1`**:
  * **Data**: `ELSBatchPhaseOutcomeV1` detailing the results of a completed phase from ELS.
  * **Handler**: `ELSBatchPhaseOutcomeHandler` processes the outcome and triggers the next pipeline phase. This is critical for dynamic orchestration.

## Dependency Injection and Repository Architecture

### Dishka Configuration

* **Container**: Configured in `startup_setup.py` using providers from `di.py`.
* **Integration**: `quart-dishka` for HTTP route injection via `@inject` decorator.
* **Lifecycle**: App-scoped singletons for stateful dependencies (Kafka producer, HTTP client, DB repository).

### Repository Pattern

* **Production**: `PostgreSQLBatchRepositoryImpl` provides the production-ready persistence layer using `asyncpg` and SQLAlchemy. It is composed of smaller, single-responsibility modules for CRUD, context, and pipeline state management. Essay metadata and storage references are persistently stored in PostgreSQL database, surviving container restarts and service scaling. The actual essay content remains in Content Service.
* **Testing**: `MockBatchRepositoryImpl` provides an in-memory storage implementation for testing purposes.
* **Atomicity**: The production repository MUST ensure atomic updates of pipeline state to prevent race conditions. This is handled within the `PostgreSQLBatchRepositoryImpl`.

## Configuration

Environment variables (managed via Pydantic `BaseSettings`):

* **`BATCH_ORCHESTRATOR_SERVICE_PORT`**: HTTP server port (default: 5000).
* **`BATCH_ORCHESTRATOR_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD`**: PostgreSQL connection details.
* **`KAFKA_BOOTSTRAP_SERVERS`**: Kafka connection (default: "kafka:9092").
* **`REDIS_URL`**: Redis connection for idempotency.
* **`BCS_URL`**: Batch Conductor Service URL for pipeline resolution (default: "<http://batch-conductor-service:4002>").

## Dependencies

### HuleEdu Services

* **Essay Lifecycle Service**: Event coordination and individual essay state management.
* **Batch Conductor Service (BCS)**: ✅ **INTEGRATED** - HTTP client integration for intelligent pipeline dependency resolution. BOS calls BCS internal API to analyze batch state and resolve optimized pipelines based on current essay processing states.
* **Kafka**: Event publishing and consumption.

### Core Libraries

* **Quart + Hypercorn**: Asynchronous HTTP API framework.
* **Dishka + quart-dishka**: Dependency injection with HTTP integration.
* **aiokafka**: Kafka client for event handling.
* **aiohttp**: HTTP client for service communication.
* **SQLAlchemy + asyncpg**: PostgreSQL database interaction.
* **huleedu-common-core**: Shared models and event schemas.
* **huledu-service-libs**: Logging and service utilities.

## Database Migrations

This service uses Alembic for PostgreSQL schema management. See `.cursor/rules/053-sqlalchemy-standards.mdc` for complete migration patterns.

```bash
# Apply migrations
pdm run migrate-upgrade

# Generate new migration
pdm run migrate-revision "description"

# View migration history
pdm run migrate-history
```

## Local Development

### Prerequisites

```bash
# Start infrastructure from monorepo root
pdm run docker-up
```

### Environment Configuration

Create `.env` file in service directory:

```env
BATCH_ORCHESTRATOR_SERVICE_LOG_LEVEL=DEBUG
BATCH_ORCHESTRATOR_SERVICE_KAFKA_BOOTSTRAP_SERVERS=localhost:9093
# ... other variables like DB credentials
```

### Run Service

```bash
# From monorepo root
pdm run dev-batch

# Or directly
pdm run -p services/batch_orchestrator_service dev
```

## Testing

### Test Coverage

* **API Endpoints**: Registration, status, health, metrics functionality.
* **Service Layer**: Business logic in `BatchProcessingServiceImpl`.
* **Event Publishing & Consumption**: Kafka message handling and serialization.
* **DI Container**: Protocol implementation injection.
* **BCS Integration**: HTTP client integration and pipeline resolution workflows.

### Run Tests

```bash
# From monorepo root
pdm run pytest services/batch_orchestrator_service/tests/ -v

# With coverage
pdm run pytest services/batch_orchestrator_service/tests/ --cov=. -v
```

## Monitoring

### Prometheus Metrics

* **HTTP Requests**: `http_requests_total`, `http_request_duration_seconds`.
* **Batch Operations**: `batch_operations_total` with operation and status labels.
* **Endpoint**: `GET /metrics`.

### Logging

* **Structured Logging**: JSON format with correlation IDs.
* **Service Context**: All logs tagged with service name and request context.
* **Integration**: Uses `huleedu_service_libs.logging_utils` patterns.
