# Batch Orchestrator Service (BOS)

## Service Purpose and Role

The **Batch Orchestrator Service** is the central coordinator for the HuleEdu essay processing pipeline. It implements the **BOS-centric architecture** where all batch processing decisions and orchestration flow through this primary service.

Its key responsibilities include:

* **Batch Lifecycle Management**: Create, configure, and manage the complete lifecycle of essay batches
* **Batch Readiness Coordination**: Implement count-based aggregation pattern to track when all essays are ready for processing
* **Pipeline Orchestration**: Coordinate processing phases across specialized services (spellcheck, NLP, AI feedback, etc.)
* **Processing Decision Authority**: All processing initiation, retry, and failure handling decisions originate from BOS
* **Content Ingestion Coordination**: Work with Content Service and File Service to manage initial essay ingestion
* **Progress Monitoring**: Track and expose batch processing progress to users and external systems

## 🔄 Batch Coordination Architecture

BOS implements the **Count-Based Aggregation Pattern** as the central orchestrator:

### Coordination Flow

1. **Batch Creation**: BOS creates batch with internal essay ID slots and registers with ELS (`BatchEssaysRegistered`)
2. **Content Coordination**: File Service provisions content to ELS for slot assignment
3. **Readiness Notification**: ELS notifies BOS when all slots are filled (`BatchEssaysReady`)
4. **Command Processing**: BOS generates commands with actual essay IDs and dispatches to ELS (`BatchSpellcheckInitiateCommand`)
5. **Progress Monitoring**: BOS tracks progress across all processing phases and provides status to clients

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
├── metrics.py                     # Prometheus metrics middleware
├── api/                           # HTTP Blueprint routes
│   ├── health_routes.py           # Health and metrics endpoints
│   └── batch_routes.py            # Batch operations (thin HTTP adapters)
├── implementations/               # Clean Architecture implementations
│   ├── batch_repository_impl.py   # MockBatchRepositoryImpl
│   ├── event_publisher_impl.py    # DefaultBatchEventPublisherImpl
│   ├── essay_lifecycle_client_impl.py # DefaultEssayLifecycleClientImpl
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
  * Accepts batch registration requests with essay IDs, course code, class designation, and instructions
  * Delegates to `BatchProcessingServiceProtocol.register_new_batch()` service layer
  * Publishes `BatchEssaysRegistered` event to ELS for readiness tracking
  * Returns `202 Accepted` with `batch_id` and `correlation_id`

* **`POST /v1/batches/trigger-spellcheck-test`**:
  * Test endpoint for integration validation
  * Stores dummy content via Content Service
  * Publishes `SpellcheckRequestedDataV1` event to Kafka
  * Returns `202 Accepted` with event details

* **`GET /healthz`**: Service health check returning `{"status": "ok"}`
* **`GET /metrics`**: Prometheus metrics in OpenMetrics format

### Planned Endpoints

* `POST /v1/batches/{batch_id}/initiate-spellcheck`: Initiate batch spellchecking
* `GET /v1/batches/{batch_id}/status`: Get batch processing status

## Event Publishing

Published to Kafka topics for downstream coordination:

* **`huleedu.batch.essays.registered.v1`**:
  * **Data**: `BatchEssaysRegistered` with internal essay ID slots and batch context
  * **Trigger**: After successful batch registration
  * **Consumer**: Essay Lifecycle Service for slot assignment

* **`huleedu.els.spellcheck.initiate.command.v1`**:
  * **Data**: `BatchServiceSpellcheckInitiateCommandDataV1` with batch processing command
  * **Trigger**: After receiving `BatchEssaysReady` event from ELS
  * **Consumer**: Essay Lifecycle Service for command processing

* **`huleedu.essay.spellcheck.requested.v1`**:
  * **Data**: `SpellcheckRequestedDataV1` with essay content reference  
  * **Trigger**: Test endpoint for integration validation
  * **Consumer**: Spell Checker Service

## Event Consumption

Consumed from Kafka for batch coordination:

* **`huleedu.els.batch.essays.ready.v1`**:
  * **Data**: `BatchEssaysReady` with ready essays including actual essay IDs and text_storage_ids
  * **Handler**: Generates spellcheck commands with real essay data and publishes to ELS
  * **Implementation**: Kafka consumer running as background task

## Dependency Injection Architecture

### Dishka Configuration

* **Container**: Configured in `startup_setup.py` using `BatchOrchestratorServiceProvider`
* **Integration**: `quart-dishka` for HTTP route injection via `@inject` decorator
* **Lifecycle**: App-scoped singletons for stateful dependencies (Kafka producer, HTTP client)

### Protocol Implementations

* **Repository Layer**: `MockBatchRepositoryImpl` (in-memory storage for Phase 1.2)
* **Event Publishing**: `DefaultBatchEventPublisherImpl` (Kafka producer wrapper)
* **Service Integration**: `DefaultEssayLifecycleClientImpl` (HTTP client for ELS)
* **Business Logic**: `BatchProcessingServiceImpl` (service layer orchestration)

## Configuration

Environment variables (managed via Pydantic `BaseSettings`):

* **`SERVICE_NAME`**: Service identifier (default: "batch-service")
* **`PORT`**: HTTP server port (default: 5000)
* **`LOG_LEVEL`**: Logging verbosity (default: INFO)
* **`KAFKA_BOOTSTRAP_SERVERS`**: Kafka connection (default: "kafka:9092")
* **`CONTENT_SERVICE_URL`**: Content Service API URL
* **`ESSAY_LIFECYCLE_SERVICE_URL`**: ELS API URL

## Dependencies

### HuleEdu Services

* **Content Service**: HTTP API for essay content storage
* **Essay Lifecycle Service**: Event coordination and essay state management
* **Kafka**: Event publishing and consumption

### Core Libraries

* **Quart + Hypercorn**: Asynchronous HTTP API framework
* **Dishka + quart-dishka**: Dependency injection with HTTP integration
* **aiokafka**: Kafka client for event handling
* **aiohttp**: HTTP client for service communication
* **huleedu-common-core**: Shared models and event schemas
* **huleedu-service-libs**: Logging and service utilities

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
BATCH_ORCHESTRATOR_SERVICE_CONTENT_SERVICE_URL=http://localhost:8001/v1/content
BATCH_ORCHESTRATOR_SERVICE_ESSAY_LIFECYCLE_SERVICE_URL=http://localhost:6001
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

* **API Endpoints**: Registration, health, metrics functionality
* **Service Layer**: Business logic in `BatchProcessingServiceImpl`
* **Event Publishing**: Kafka message publishing and serialization
* **Integration**: Content Service communication (mocked)
* **DI Container**: Protocol implementation injection

### Run Tests

```bash
# From monorepo root
pdm run pytest services/batch_orchestrator_service/tests/ -v

# With coverage
pdm run pytest services/batch_orchestrator_service/tests/ --cov=. -v
```

## Monitoring

### Prometheus Metrics

* **HTTP Requests**: `http_requests_total`, `http_request_duration_seconds`
* **Batch Operations**: `batch_operations_total` with operation and status labels
* **Endpoint**: `GET /metrics` (OpenMetrics format)

### Logging

* **Structured Logging**: JSON format with correlation IDs
* **Service Context**: All logs tagged with service name and request context
* **Integration**: Uses `huleedu_service_libs.logging_utils` patterns
