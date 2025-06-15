---
description: Defines the architecture and implementation details of the HuleEdu Essay Lifecycle Service
globs: 
alwaysApply: false
---
# 025: Essay Lifecycle Service Architecture

## 1. Service Identity

- **Package**: `huleedu-essay-lifecycle-service`
- **Ports (Host:Container)**: `6001:6000` (HTTP API), `9091:9090` (Metrics)
- **Stack**: Quart, `aiokafka`, SQLAlchemy (`asyncpg`), Dishka, `transitions`
- **Purpose**: Manage individual essay states via a formal state machine, process batch commands from BOS, and publish batch phase outcomes to drive dynamic pipeline orchestration.

## 2. Core Architecture

### 2.1. Dual-Mode Service

- **HTTP API (`app.py`)**: Provides read-only query endpoints for essay and batch status. **FORBIDDEN**: Control operations.
- **Kafka Worker (`worker_main.py`)**: Consumes commands from BOS and results from specialized services, driving all state changes.

### 2.2. State Machine Driven

- **MANDATORY**: All essay state transitions **MUST** be governed by the `EssayStateMachine` class.
- Business logic (e.g., in handlers) **MUST** use triggers (e.g., `CMD_INITIATE_SPELLCHECK`, `EVT_SPELLCHECK_SUCCEEDED`) to change state, not direct status updates.

### 2.3. Clean DI Architecture

- **DI**: `di.py` is a lean provider importing from the `implementations/` directory.
- **Protocols**: All dependencies are defined in `protocols.py`.
- **Implementations**: Business logic is encapsulated in single-responsibility classes within the `implementations/` directory.

## 3. Event Integration

### 3.1. Consumed Events

- **BOS Commands**: `BATCH_SPELLCHECK_INITIATE_COMMAND`, `BATCH_CJ_ASSESSMENT_INITIATE_COMMAND`
- **Coordination Events**: `BATCH_ESSAYS_REGISTERED`, `ESSAY_CONTENT_PROVISIONED`, `ESSAY_VALIDATION_FAILED`
- **Service Results**: `ESSAY_SPELLCHECK_COMPLETED`, `CJ_ASSESSMENT_COMPLETED`

### 3.2. Published Events

- **Phase Outcome (CRITICAL)**: `ELS_BATCH_PHASE_OUTCOME` is published to BOS to report the result of a phase for an entire batch, enabling the next pipeline step.
- **Service Requests**: Publishes requests to specialized services (e.g., `ESSAY_LIFECYCLE_SPELLCHECK_REQUEST`).
- **Coordination Events**: `BATCH_ESSAYS_READY`, `EXCESS_CONTENT_PROVISIONED`.

## 4. Database & Repository

- **Production**: PostgreSQL, using `PostgreSQLEssayRepository`.
- **Development/Testing**: SQLite, using `SQLiteEssayStateStore`.
- **Schema**: Defined in `models_db.py` for PostgreSQL.
- **Standard Compliance**: Follows all SQLAlchemy standards from Rule `052`.

## 5. Configuration

- **Environment Prefix**: `ESSAY_LIFECYCLE_SERVICE_`
- **Database URL**: `ELS_DATABASE_URL` for production PostgreSQL connection.
- **Mock Repository**: Controlled by `USE_MOCK_REPOSITORY` flag.

## 6. Mandatory Production Patterns

- **MUST** implement graceful shutdown (`worker_main.py` signal handling).
- **MUST** use DI-managed `aiohttp.ClientSession` and `KafkaBus`.
- **MUST** use manual Kafka commits (`enable_auto_commit=False`).
- **MUST** implement `/healthz` and `/metrics` endpoints.
