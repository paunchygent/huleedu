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

## ⚙️ Configuration

Configuration is managed via `services/essay_lifecycle_service/config.py`.

- **Environment Prefix**: `ESSAY_LIFECYCLE_SERVICE_`
- **Database URL**: `ELS_DATABASE_URL` is used for the production PostgreSQL connection.
- **Mock Repository**: `USE_MOCK_REPOSITORY` flag controls which database implementation is used.

## 🧱 Dependencies

Key dependencies are listed in `services/essay_lifecycle_service/pyproject.toml` and include `quart`, `aiokafka`, `sqlalchemy`, and `asyncpg`.

## 🔧 Circuit Breaker Observability

Circuit breaker metrics are integrated into the service's Prometheus metrics:

- **`circuit_breaker_state`**: Current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) with labels: `service`, `circuit_name`
- **`circuit_breaker_state_changes`**: State transition counter with labels: `service`, `circuit_name`, `from_state`, `to_state`
- **`circuit_breaker_calls_total`**: Call result counter with labels: `service`, `circuit_name`, `result` (success/failure/blocked)

Circuit breakers protect Kafka publishing operations and are configurable via `ESSAY_LIFECYCLE_SERVICE_CIRCUIT_BREAKER_` environment variables.

## 📊 Technical Patterns

### Health Check Implementation

ELS implements a comprehensive health check pattern using the DatabaseHealthChecker:

```python
# Health check endpoints with progressive detail levels
@health_bp.route("/healthz")  # Basic health for load balancers
@health_bp.route("/healthz/database")  # Comprehensive database metrics
@health_bp.route("/healthz/database/summary")  # Lightweight polling endpoint

# Startup pattern stores engine for health checks
async def initialize_services(app: Quart, settings: Settings) -> None:
    if settings.ENVIRONMENT != "testing":
        temp_repo = PostgreSQLEssayRepository(settings)
        await temp_repo.initialize_db_schema()
        app.database_engine = temp_repo.engine  # Store for health checks
```

### Dependency Injection Patterns

ELS uses 4 provider classes for clean separation of concerns:

```python
# Provider organization
CoreInfrastructureProvider()     # Settings, Kafka, Redis, Database
ServiceClientsProvider()         # Event publishers, metrics collectors
CommandHandlerProvider()         # Spellcheck, CJ Assessment handlers
BatchCoordinationProvider()      # Batch tracking, phase coordination

# Route injection pattern using FromDishka
@inject
async def get_essay_status(
    essay_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
) -> Response:
    essay_state = await state_store.get_essay_state(essay_id)
```

### Database Monitoring

Comprehensive database monitoring via DatabaseMetrics integration:

```python
def setup_essay_lifecycle_database_monitoring(
    engine: AsyncEngine,
    service_name: str = "essay_lifecycle_service"
) -> DatabaseMetrics:
    # Monitors connection pool, query performance, and health
    return setup_database_monitoring(engine, service_name)

# Metrics exposed via Prometheus:
# - db_pool_size, db_pool_checked_out, db_pool_overflow
# - db_query_duration_seconds (histogram by operation)
# - db_query_errors_total (counter by operation and error_type)
```

### Error Handling Patterns

State machine provides formal error transitions:

```python
# State machine error handling in SpellcheckCommandHandler
essay_machine = EssayStateMachine(
    essay_id=essay_id, 
    initial_status=essay_state_model.current_status
)

if essay_machine.trigger(CMD_INITIATE_SPELLCHECK):
    # Success path - persist state and dispatch
    await self.repository.update_essay_status_via_machine(...)
else:
    # Invalid transition - log and skip
    logger.warning(f"State machine trigger failed for essay {essay_id}")
```

Retry patterns for external services via circuit breakers:

```python
# Resilient Kafka publishing with circuit breaker
kafka_publisher = ResilientKafkaPublisher(
    delegate=base_kafka_bus,
    circuit_breaker=kafka_circuit_breaker,
    retry_interval=30,  # Retry every 30 seconds when open
)
```

### Performance Considerations

Batch processing patterns for efficient coordination:

```python
# Concurrent essay processing in batch commands
successfully_transitioned_essays = []
for essay_ref in command_data.essays_to_process:
    # Process state transitions first
    if essay_machine.trigger(CMD_INITIATE_SPELLCHECK):
        successfully_transitioned_essays.append(essay_ref)

# Then dispatch all at once
if successfully_transitioned_essays:
    await self.request_dispatcher.dispatch_spellcheck_requests(
        essays_to_process=successfully_transitioned_essays,
        language=language_enum,
        correlation_id=correlation_id,
    )
```

Async patterns for concurrent operations:

```python
# Idempotent message processing with Redis
@idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
    return await process_single_message(msg, ...)

# Batch phase aggregation checks
essays_in_phase = await self.repository.list_essays_by_batch_and_phase(
    batch_id=batch_id, phase_name=phase_name.value
)
# Aggregate completion status and publish outcome event
```

Database connection pooling:

```python
# Configured in PostgreSQLEssayRepository
create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
)
