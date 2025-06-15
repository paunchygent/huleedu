# Essay Lifecycle Service (ELS)

## 🎯 Service Purpose

ELS acts as a **slot assignment coordinator** and **command processor** in the essay processing pipeline, working in coordination with the **Batch Orchestrator Service (BOS)**. It manages essay slot assignment, processes batch commands using a formal state machine, and coordinates specialized service requests through event-driven architecture. Crucially, it reports phase completion outcomes back to BOS to enable dynamic pipeline orchestration.

## 🔄 Batch Coordination Architecture

ELS implements the **Slot Assignment Pattern** for coordinating content with batch processing:

### Coordination Flow

1. **Slot Registration**: BOS informs ELS about batch slots (`BatchEssaysRegistered`).
2. **Content Assignment**: ELS assigns incoming content from File Service to available slots (`EssayContentProvisionedV1`).
3. **Batch Completion**: ELS notifies BOS when all slots are filled (`BatchEssaysReady`).
4. **Command Processing**: ELS processes batch commands from BOS (`BatchSpellcheckInitiateCommand`) and transitions individual essay states using its state machine.
5. **Phase Outcome Reporting**: After a phase completes for a batch, ELS reports the outcome to BOS (`ELSBatchPhaseOutcomeV1`).

### State Transition Model

- The lifecycle of each essay is strictly governed by the `EssayStateMachine`.
- **File Service Domain**: `UPLOADED` → `TEXT_EXTRACTED` → `CONTENT_INGESTING` → `CONTENT_INGESTION_FAILED`
- **ELS Handoff Point**: `READY_FOR_PROCESSING` (essays ready for pipeline assignment)
- **ELS Pipeline Domain**: `AWAITING_SPELLCHECK` → `SPELLCHECKING_IN_PROGRESS` → `SPELLCHECKED_SUCCESS`/`SPELLCHECK_FAILED` → `ESSAY_CRITICAL_FAILURE`

## 🔄 Service Architecture

ELS is a hybrid service combining a Kafka-based worker for asynchronous processing with an HTTP API for queries:

- **Primary Processing Engine**: A Kafka consumer worker (`worker_main.py`) handles events and commands.
- **API Layer**: A Quart application (`app.py`) provides RESTful endpoints. It's served by Hypercorn.
- **State Persistence**: The service uses a dual-repository pattern. **PostgreSQL** is the production database, implemented via `PostgreSQLEssayRepository`. For development and testing, an `SQLiteEssayStateStore` is used.
- **Dependency Injection**: Utilizes Dishka for managing dependencies. Providers in `di.py` supply implementations for protocols defined in `protocols.py`.
- **Implementation Layer**: Business logic is cleanly separated in the `implementations/` directory, covering command handlers, event publishers, and repository logic.
- **Batch Coordination**: The `batch_tracker.py` module implements count-based aggregation for coordinating batch readiness.

## 🔄 Data Flow: Commands, Events, and Queries

ELS participates in these communication patterns:

- **Consumes from Kafka**:
  - **Batch Registration**: `BatchEssaysRegistered` from BOS.
  - **Content Provisioning**: `EssayContentProvisionedV1` and `EssayValidationFailedV1` from File Service.
  - **Batch Commands**: `BatchService...InitiateCommandDataV1` (e.g., for spellcheck, cj_assessment) from BOS.
  - **Specialized Service Results**: `EssaySpellcheckCompleted`, `CJAssessmentCompleted`, etc.

- **Publishes to Kafka**:
  - **Batch Readiness**: `BatchEssaysReady` to BOS when all slots are filled.
  - **Excess Content**: `ExcessContentProvisionedV1` to BOS for content overflow.
  - **Service Requests**: `EssayLifecycleSpellcheckRequestV1` to specialized services.
  - **Phase Outcome (CRITICAL)**: `ELSBatchPhaseOutcomeV1` to BOS, reporting the result of a completed phase for an entire batch, enabling the next step in the dynamic pipeline.

- **HTTP API**:
  - **Query-Only**: Provides read-only access to essay and batch state information.
  - **No Control Operations**: Does not accept processing commands via HTTP.

## 🚀 API Endpoints (Read-Only Queries)

- **`GET /healthz`**: Standard health check.
- **`GET /v1/essays/{essay_id}/status`**: Get current status, progress, and timeline for a specific essay.
- **`GET /v1/batches/{batch_id}/status`**: Get a summary of essay statuses for a batch.

## ⚙️ Configuration

Configuration is managed via `services/essay_lifecycle_service/config.py`.

- **Environment Prefix**: `ESSAY_LIFECYCLE_SERVICE_`
- **Database URL**: `ELS_DATABASE_URL` is used for the production PostgreSQL connection.
- **Mock Repository**: `USE_MOCK_REPOSITORY` flag controls which database implementation is used.

## 🧱 Dependencies

Key dependencies are listed in `services/essay_lifecycle_service/pyproject.toml` and include `quart`, `aiokafka`, `sqlalchemy`, and `asyncpg`.
