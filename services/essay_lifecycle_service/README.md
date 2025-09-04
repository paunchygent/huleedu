# Essay Lifecycle Service (ELS)

## 🎯 Service Purpose

ELS acts as a **slot assignment coordinator** and **command processor** in the essay processing pipeline, working in coordination with the **Batch Orchestrator Service (BOS)**. It manages essay slot assignment, processes batch commands using a formal state machine, and coordinates specialized service requests through event-driven architecture. 

**Phase 1 Behavior**: During student matching, ELS operates as a **stateless event router** - publishes events without updating essay states. **Phase 2+**: Normal stateful behavior resumes.

## 🔄 Batch Coordination Architecture

ELS implements the **Slot Assignment Pattern** for coordinating content with batch processing:

### Coordination Flow

1. **Registration**: BOS → ELS `BatchEssaysRegistered`
   - Creates batch expectation with essay IDs
   - Creates `essay_states` rows (status='UPLOADED') as available slots
   
2. **Content Provisioning**: File Service → ELS `EssayContentProvisionedV1`
   - File Service processes uploads and notifies ELS
   - ELS assigns via Option B single UPDATE (UPLOADED → READY_FOR_PROCESSING)
   
3. **Completion**: ELS → BOS `BatchContentProvisioningCompletedV1`
   - COUNT(*) FROM essay_states WHERE status='READY_FOR_PROCESSING'
   - Publishes when provisioned_count == expected_count
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
- **State Persistence**: The service uses a three-tier repository pattern. **PostgreSQL** is the production database, implemented via `PostgreSQLEssayRepository`. For development and testing, a fast in-memory `MockEssayRepository` is used.
- **Event Publishing**: Implements the **Transactional Outbox Pattern** for reliable event delivery. Events are stored in the `event_outbox` table within the same transaction as business logic, then published asynchronously by the Event Relay Worker.
- **Dependency Injection**: Utilizes Dishka for managing dependencies. Providers in `di.py` supply implementations for protocols defined in `protocols.py`.
- **Implementation Layer**: Business logic is cleanly separated in the `implementations/` directory, covering command handlers, event publishers, and repository logic.
- **Batch Coordination**: The `batch_tracker.py` module implements count-based aggregation for coordinating batch readiness.

### Option B Assignment Implementation

```sql
UPDATE essay_states
SET current_status = 'READY_FOR_PROCESSING',
    text_storage_id = :text_storage_id,
    updated_at = NOW()
WHERE batch_id = :batch_id 
  AND current_status = 'UPLOADED'
  AND NOT EXISTS (
    SELECT 1 FROM essay_states e2 
    WHERE e2.batch_id = :batch_id 
    AND e2.text_storage_id = :text_storage_id
  )
ORDER BY essay_id
LIMIT 1
FOR UPDATE SKIP LOCKED
RETURNING essay_id;
```

- **Transaction**: Immediate commit per assignment
- **Idempotency**: IntegrityError on duplicate → read winner
- **Implementation**: `assignment_sql.assign_via_essay_states_immediate_commit()`

### Service Contract Stability

**UNCHANGED**: All service boundaries and event contracts remain identical
- BOS still sends `BatchEssaysRegistered` with essay IDs
- File Service still sends `EssayContentProvisionedV1` per processed file
- ELS still publishes `BatchContentProvisioningCompletedV1` on completion
- **ONLY CHANGE**: Internal assignment uses PostgreSQL UPDATE instead of Redis coordination

## 🔄 Data Flow: Commands, Events, and Queries

ELS participates in these communication patterns:

- **Consumes from Kafka**:
  - **Batch Registration**: `BatchEssaysRegistered` from BOS.
  - **Content Provisioning**: `EssayContentProvisionedV1` and `EssayValidationFailedV1` from File Service.
  - **Phase 1 Commands**: `BatchServiceStudentMatchingInitiateCommandDataV1` from BOS (stateless routing).
  - **Phase 1 Results**: `StudentAssociationsConfirmedV1` from Class Management (stateless routing).
  - **Phase 2+ Commands**: `BatchService...InitiateCommandDataV1` (e.g., for spellcheck, cj_assessment) from BOS.
  - **Spellcheck Phase Completion**: `SpellcheckPhaseCompletedV1` (thin event for state transitions)
  - **CJ Assessment Results**: `CJAssessmentCompleted`, etc.

- **Publishes to Kafka**:
  - **Content Readiness**: `BatchContentProvisioningCompletedV1` to BOS when all slots are filled.
  - **Phase 1 Requests**: `BatchStudentMatchingRequestedV1` to NLP Service (stateless).
  - **Phase 1 Completion**: `BatchEssaysReady` to BOS after student associations confirmed.
  - **Phase 2+ Service Requests**: `EssayLifecycleSpellcheckRequestV1` to specialized services.
  - **Phase Outcome (CRITICAL)**: `ELSBatchPhaseOutcomeV1` to BOS, reporting the result of a completed phase for an entire batch, enabling the next step in the dynamic pipeline.
  - **All events published via Transactional Outbox Pattern** for guaranteed delivery and consistency.

## Event Consumption Patterns

### Spellchecker Integration
ELS consumes **thin events** from the spellchecker service optimized for state management:

- **Event**: `SpellcheckPhaseCompletedV1`
- **Topic**: `huleedu.batch.spellcheck.phase.completed.v1`
- **Purpose**: State transitions only (~300 bytes)
- **Handler**: `handle_spellcheck_phase_completed()` in `ServiceResultHandlerImpl`
- **Data**: entity_id, batch_id, status, corrected_text_storage_id, error_code, processing_duration_ms

This thin event pattern ensures ELS receives only the minimal data needed for state management, improving performance and reducing network overhead.

### Performance Optimizations

**Header-First Processing**: ELS benefits from zero-parse idempotency when processing events with complete Kafka headers:
- Events from OutboxManager-enabled services include `event_id`, `event_type`, `trace_id` headers
- Header-complete messages skip JSON parsing during idempotency checking
- Performance benefit: Reduced CPU usage and faster duplicate detection for high-volume processing

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

## 🔄 TRUE Outbox Pattern

ELS implements the TRUE Outbox Pattern for guaranteed event delivery, where all events are stored in the outbox database first, then published by a relay worker:

### Event Publishing Architecture

```python
# TRUE OUTBOX PATTERN: All events stored in outbox first
async def publish_event(self, event_data: EventEnvelope[Any], ...) -> None:
    try:
        # Store in outbox for transactional safety
        await self.kafka_bus.publish(
            topic=topic,
            key=aggregate_id.encode("utf-8"),
            value=event_data.model_dump_json(mode="json").encode("utf-8"),
        )
        return  # Success - no outbox needed
    
    except Exception as e:
        # Fallback: Store in outbox only on Kafka failure
        await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_data=event_data.model_dump(mode="json"),
        )
        # Wake up relay worker immediately
        await self.redis_client.lpush("outbox:wakeup", "1")
```

### Event Relay Worker (Redis-Driven)

The Event Relay Worker uses Redis BLPOP for instant wake-up when events enter the outbox:

- **Primary Mode**: Waits on Redis BLPOP for zero-delay processing
- **Adaptive Polling**: 0.1s → 1s → 5s intervals when idle (based on ENVIRONMENT)
- **Batch Processing**: Up to 100 events per batch
- **Retry Logic**: 5 attempts with exponential backoff
- **Configuration**: Centralized in huleedu_service_libs based on ENVIRONMENT

### Database Schema

```sql
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id VARCHAR(255) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    event_data JSONB NOT NULL,
    event_key VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT
);

-- Performance indexes
CREATE INDEX ix_event_outbox_unpublished ON event_outbox (published_at, created_at) 
WHERE published_at IS NULL;
```

### Benefits

- **Performance**: All events go through outbox for guaranteed delivery with relay worker optimization
- **Reliability**: Fallback ensures no event loss during Kafka outages
- **Zero-Delay Recovery**: Redis BLPOP enables instant processing when events enter outbox
- **Adaptive Resource Usage**: Polling intervals adjust based on activity and environment
- **Centralized Configuration**: All timing/behavior configured in library based on ENVIRONMENT

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

if essay_machine.trigger_event(CMD_INITIATE_SPELLCHECK):
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
    if essay_machine.trigger_event(CMD_INITIATE_SPELLCHECK):
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
```

## Error Handling Infrastructure

ELS implements the HuleEdu error infrastructure with structured error codes, correlation ID propagation, and OpenTelemetry integration for distributed systems observability.

### HuleEduError Integration

All error scenarios use factory functions for consistent error handling:

```python
# Repository layer - services/essay_lifecycle_service/implementations/essay_repository_postgres_impl.py:156
if not essay_record:
    raise raise_resource_not_found(
        correlation_id=correlation_id,
        operation="get_essay_state",
        details={"essay_id": essay_id}
    )

# Service layer - processing errors with context
raise raise_processing_error(
    correlation_id=correlation_id,
    operation="batch_coordination",
    details={"batch_id": batch_id, "phase": phase_name}
)

# Event publishing - Kafka failures
raise raise_kafka_publish_error(
    correlation_id=correlation_id,
    operation="publish_batch_outcome",
    details={"topic": topic_name, "event_type": event_type}
)
```

### Correlation ID Propagation

Distributed tracing chains maintained across service boundaries:

```python
# API layer extracts or generates correlation IDs
correlation_id = extract_correlation_id_from_headers(request.headers)

# Service operations propagate correlation context
await self.repository.get_essay_state(essay_id, correlation_id=correlation_id)

# OpenTelemetry spans automatically record correlation context
```

### Structured Error Codes

Error scenarios mapped to specific error codes:

- `RESOURCE_NOT_FOUND`: Essay/batch not found in database
- `PROCESSING_ERROR`: State machine transitions, business logic failures  
- `KAFKA_PUBLISH_ERROR`: Event publishing failures with circuit breaker integration
- `CONNECTION_ERROR`: Database connection failures
- `VALIDATION_ERROR`: Input validation, constraint violations

### Contract Testing

Comprehensive error contract testing validates infrastructure compliance:

```python
# services/essay_lifecycle_service/tests/conftest.py error testing utilities
def assert_huleedu_error(
    exception: HuleEduError,
    expected_code: str,
    expected_correlation_id: UUID | None = None,
) -> None:
    """Validate HuleEduError structure and correlation propagation."""

@asynccontextmanager
async def expect_huleedu_error(expected_code: str) -> AsyncGenerator[None, None]:
    """Context manager for exception-based testing patterns."""

# Contract tests cover:
# - ErrorDetail serialization round-trips
# - HuleEduError wrapping and immutability  
# - Correlation ID preservation across service boundaries
# - OpenTelemetry span integration with exception recording
```

### Error Testing Utilities

Test infrastructure follows Rule 070 protocol-based patterns:

- `assert_huleedu_error()`: Validates error structure, correlation ID propagation, service attribution
- `expect_huleedu_error()`: Async context manager for testing expected exceptions
- `assert_correlation_id_propagated()`: Distributed tracing validation utility
- `assert_error_detail_structure()`: Contract validation for ErrorDetail model compliance

14 comprehensive error contract tests ensure infrastructure reliability and cross-service compatibility.
