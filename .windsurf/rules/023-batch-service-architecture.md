---
description: "Rules for batch processing operations. Ensures reliable job scheduling and bulk data processing."
globs: 
  - "services/batch_service/**/*.py"
alwaysApply: true
---
# 023: Batch Orchestrator Service Architecture

## 1. Service Identity

- **Package**: `huleedu-batch-service`
- **Port**: 5000 (HTTP API)
- **Stack**: Quart, aiokafka, aiohttp, asyncpg, SQLAlchemy, Hypercorn, Dishka, Redis
- **Purpose**: Central orchestrator for essay batch processing workflows, acting as the primary **processing decision authority**. Manages the lifecycle of batches and dynamically orchestrates processing phases based on `ProcessingPipelineState`.

## 2. Clean Architecture Implementation

### 2.1. Service Structure

```text
services/batch_orchestrator_service/
├── app.py                         # Lean Quart entry point (<50 lines)
├── startup_setup.py               # DI initialization, DB schema setup, service lifecycle
├── api/                           # HTTP Blueprint routes
│   ├── health_routes.py           # Health and metrics endpoints
│   └── batch_routes.py            # Batch operations (thin HTTP adapters)
├── implementations/               # Clean Architecture implementations
│   ├── batch_repository_postgres_impl.py # Production PostgreSQL repository
│   ├── batch_repository_impl.py   # Mock repository for testing
│   ├── event_publisher_impl.py    # DefaultBatchEventPublisherImpl
│   ├── cj_assessment_initiator_impl.py # CJ Assessment phase initiator
│   ├── spellcheck_initiator_impl.py    # Spellcheck phase initiator
│   ├── batch_essays_ready_handler.py   # Handler for BatchEssaysReady events
│   ├── els_batch_phase_outcome_handler.py # Handler for phase completion events
│   └── batch_processing_service_impl.py # Service layer business logic
├── protocols.py                   # Protocol definitions for DI
├── di.py                          # Dishka providers importing implementations
├── config.py                      # Pydantic settings
├── api_models.py                  # Request/response models
├── kafka_consumer.py              # Kafka event consumer with multiple handlers
├── enums_db.py                    # Service-specific database enums
└── models_db.py                   # SQLAlchemy ORM models
```

### 2.2. Architectural Patterns

- **Service Layer**: Business logic is cleanly separated into `implementations/batch_processing_service_impl.py`.
- **Protocol-Based DI**: All dependencies are injected via `typing.Protocol` abstractions defined in `protocols.py`.
- **Repository Pattern**: Data persistence is abstracted via `BatchRepositoryProtocol`, with `PostgreSQLBatchRepositoryImpl` for production and `MockBatchRepositoryImpl` for testing.
- **Blueprint Pattern**: HTTP routes are organized in the `api/` directory.

## 3. API Endpoints

### 3.1. Current Endpoints

#### POST /v1/batches/register

- **Request**: `BatchRegistrationRequestV1`
- **Response**: `{"batch_id": "uuid", "correlation_id": "uuid", "status": "registered"}`
- **Flow**: HTTP -> Service Layer -> Repository + `BatchEssaysRegistered` Event Publishing.

#### GET /v1/batches/<batch_id>/status

- **Purpose**: Get the current status and detailed pipeline state of a batch.
- **Response**: JSON object with `batch_id`, `batch_context`, and `pipeline_state`.

#### GET /healthz

- **Response**: `{"status": "ok", "message": "Batch Orchestrator Service is healthy"}`

#### GET /metrics

- **Response**: Prometheus metrics in OpenMetrics format.

## 4. Event Architecture

### 4.1. Event Publishing

- **Topic**: `huleedu.batch.essays.registered.v1`
  - **Data**: `BatchEssaysRegistered` (with internal essay ID slots).
- **Topic**: `huleedu.els.spellcheck.initiate.command.v1`
  - **Data**: `BatchServiceSpellcheckInitiateCommandDataV1`.
- **Topic**: `huleedu.batch.cj_assessment.initiate.command.v1`
  - **Data**: `BatchServiceCJAssessmentInitiateCommandDataV1`.

### 4.2. Event Consumption

- **Topic**: `huleedu.els.batch.essays.ready.v1`
  - **Handler**: `BatchEssaysReadyHandler` initiates the first phase of the defined pipeline.
- **Topic**: `huleedu.els.batch_phase.outcome.v1`
  - **Handler**: `ELSBatchPhaseOutcomeHandler` processes phase completion and triggers the next phase in the pipeline.

## 5. Production Repository & Database

- **Technology**: PostgreSQL with `asyncpg` driver.
- **ORM**: Async SQLAlchemy.
- **Atomicity**: The `PostgreSQLBatchRepositoryImpl` is responsible for providing atomic operations for `ProcessingPipelineState` updates to prevent race conditions during phase transitions. It is composed of several specialized modules for `CRUD`, `Context`, `Pipeline State`, and `Configuration` management.
- **Idempotency**: Redis is used for idempotency checks on critical operations.

## 6. Configuration & Monitoring

- **Configuration**: Uses Pydantic `BaseSettings` in `config.py` with the environment variable prefix `BATCH_ORCHESTRATOR_SERVICE_`.
- **Metrics**: Uses the shared `huleedu_service_libs.metrics_middleware` for standard HTTP metrics.
- **Logging**: Uses the shared `huleedu_service_libs.logging_utils` for structured logging.

## 7. Mandatory Production Patterns

- **MUST** implement graceful shutdown with proper async resource cleanup (`startup_setup.py`).
- **MUST** use DI-managed `aiohttp.ClientSession` and `KafkaBus`.
- **MUST** use manual Kafka commits (`enable_auto_commit=False`).
- **MUST** fail fast on startup errors using `logger.critical()` and `raise` in `startup_setup.py`
