# NLP Service

## Overview

The NLP Service is a dual-phase Kafka worker service responsible for natural language processing tasks on student essays. It handles both Phase 1 (pre-readiness) student matching and Phase 2 (post-readiness) text analysis, processing entire batches of essays with parallel execution and partial failure handling.

## Architecture

- **Pattern**: Pure Worker Service (Kafka-only, no HTTP API)
- **Stack**: Python 3.11, aiokafka, aiohttp, Dishka, thefuzz
- **Phase 1 Input**: `BATCH_STUDENT_MATCHING_REQUESTED` events via Kafka
- **Phase 1 Output**: `BATCH_AUTHOR_MATCHES_SUGGESTED` events via Kafka
- **Phase 2 Input**: `BatchNlpProcessingRequestedV2` events via Kafka (ELS → NLP) carrying optional `student_prompt_ref`
- **Phase 2 Output**: Analysis results (future implementation)
- **Dependencies**: File Service (HTTP), Class Management Service (HTTP), Redis (caching)
- **Database**: PostgreSQL with outbox pattern for reliable event publishing

## Key Features

### Phase 1: Student Matching (Pre-Readiness)
- **Batch Processing**: Processes entire batches of essays in parallel
- **Extraction Pipeline**: Multiple strategies (Exam.net format, header patterns, email proximity)
- **Fuzzy Matching**: Swedish-aware name matching against class rosters
- **Partial Failure Handling**: Continues processing even if some essays fail
- **Performance**: < 10s for 30 essays, max batch size 100
- **Caching**: Rosters cached in Redis (5 minute TTL)

### Phase 2: Text Analysis (Post-Readiness)
- **Feature Pipeline**: Shared `FeaturePipeline` abstraction normalises text, aggregates spell/grammar metrics, and produces the canonical 50-feature vector consumed by both runtime and offline tooling.
- **Prompt Hydration**: Each batch resolves `student_prompt_ref` via the Content Service; prompt text and storage IDs are forwarded to downstream consumers in `processing_metadata`.
- **Failure Telemetry**: Prompt hydration issues increment `huleedu_nlp_prompt_fetch_failures_total{reason="content_service_error|missing_reference|legacy_fallback"}` while continuing with safe fallbacks when possible.
- **Spell Metrics Propagation**: Essay Lifecycle Service forwards `SpellcheckResultV1.correction_metrics`, allowing the NLP handler to reuse Spellchecker totals without re-running the normaliser.
- **Language Tool Integration**: Grammar analysis runs on the spell-normalised text and feeds grammar-related feature extractors.
- **Outputs**: `EssayNlpCompletedV1` rich events include the feature map in `processing_metadata["feature_outputs"]` plus hydrated prompt metadata; thin batch completion events remain unchanged.

### Performance Optimizations
- **Header-First Message Processing**: Benefits from zero-parse idempotency when processing events with complete Kafka headers (event_id, event_type, trace_id)
- **Batch Parallel Processing**: Multiple essays processed concurrently within each batch
- **Redis Caching**: Class rosters cached for 5 minutes to reduce HTTP calls
- **Early Exit**: Extraction strategies stop on high-confidence matches

## Service Structure

```
nlp_service/
├── worker_main.py                          # Kafka consumer lifecycle
├── event_processor.py                      # Event routing (Phase 1/2)
├── matching_algorithms/                    # Student matching algorithms
│   ├── extraction/                         # Text extraction strategies
│   │   ├── base_extractor.py             # Protocol definition
│   │   ├── examnet_extractor.py          # Exam.net 4-paragraph
│   │   ├── header_extractor.py           # Pattern-based headers
│   │   └── extraction_pipeline.py        # Strategy orchestrator
│   └── matching/                          # Roster matching logic
│       ├── base_matcher.py               # Protocol definition
│       ├── name_matcher.py               # Fuzzy name matching
│       └── roster_matcher.py             # Main orchestrator
├── implementations/                        # Service implementations
│   ├── batch_student_matching_handler.py  # Phase 1 handler
│   ├── batch_nlp_analysis_handler.py     # Phase 2 handler (future)
│   ├── content_client_impl.py            # File Service client
│   ├── roster_client_impl.py             # Class Management client
│   └── event_publisher_impl.py           # Outbox publishing
├── protocols.py                           # Service interfaces
├── di.py                                  # Dishka configuration
├── config.py                              # Service settings
├── models_db.py                           # Database models
└── repositories/                          # Database access
```

## Environment Variables

- `NLP_SERVICE_DATABASE_URL`: PostgreSQL connection string
- `NLP_SERVICE_KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses
- `NLP_SERVICE_FILE_SERVICE_URL`: File Service URL for content fetching
- `NLP_SERVICE_CLASS_MANAGEMENT_SERVICE_URL`: Class Management Service URL for rosters
- `NLP_SERVICE_REDIS_URL`: Redis connection string for roster caching
- `NLP_SERVICE_LOG_LEVEL`: Logging level (default: INFO)
- `NLP_SERVICE_EXTRACTION_CONFIDENCE_THRESHOLD`: Confidence to exit extraction early (default: 0.7)
- `NLP_SERVICE_MATCH_NAME_FUZZY_THRESHOLD`: Minimum similarity for name matching (default: 0.7)
- `NLP_SERVICE_MATCH_EMAIL_FUZZY_THRESHOLD`: Minimum similarity for email matching (default: 0.9)
- `NLP_SERVICE_MAX_BATCH_SIZE`: Maximum essays per batch (default: 100)
- `NLP_SERVICE_PROCESSING_TIMEOUT`: Batch processing timeout in seconds (default: 30)

## Development

### Local Setup
```bash
cd services/nlp_service
pdm install
pdm run alembic upgrade head  # Run database migrations
pdm run start-worker
```

### Docker
```bash
docker compose up -d nlp_service
```

### Testing
```bash
pdm run pytest tests/
```

## Monitoring

- **Health**: Via Kafka consumer lag monitoring
- **Metrics**: Prometheus metrics
  - `nlp_phase1_batch_size`: Distribution of batch sizes
  - `nlp_phase1_batch_processing_seconds`: Processing time per batch
  - `nlp_match_confidence_score`: Match confidence distribution
  - `nlp_phase1_batch_match_outcomes_total`: Match/no-match/error counts
  - `huleedu_nlp_prompt_fetch_failures_total{reason}`: Prompt hydration failure counter (Content Service reference issues)
- **Logging**: Structured logging with correlation IDs
- **Tracing**: OpenTelemetry integration for distributed tracing

## Database Schema

- `nlp_analysis_jobs`: Tracks NLP processing jobs with batch_id as primary key
- `student_match_results`: Stores match suggestions per essay within batch
- `outbox_events`: Reliable event publishing via outbox pattern
- `processing_cache`: Idempotency tracking for batch operations

## Critical Design Decisions

1. **Batch-Level Processing**: ALL operations are batch-level (no individual essay events)
2. **No Language Field**: Language inferred from course_code when needed (YAGNI)
3. **Partial Failure Handling**: Failed essays included in response with error markers
4. **Idempotency**: Uses batch_id as idempotency key throughout
5. **Swedish Support**: Built-in Swedish name patterns and character handling

## Error Handling

The service relies on `libs/huleedu_service_libs/error_handling` helpers to guarantee
structured errors with correlation IDs and typed `ErrorCode` mappings.

- **Client helpers**: `DefaultContentClient` calls `raise_content_service_error(...)` for
  Content Service failures while `DefaultClassManagementClient` uses
  `raise_external_service_error(...)` for Class Management HTTP responses, timeouts, and
  schema validation problems.【F:services/nlp_service/implementations/content_client_impl.py†L1-L113】【F:services/nlp_service/implementations/roster_client_impl.py†L1-L141】
- **Language Tool client**: Retries transient HTTP errors and ultimately raises a
  `HuleEduError` once retry budgets are exhausted so downstream handlers can surface
  `ErrorCode.EXTERNAL_SERVICE_ERROR` without duplicating logic.【F:services/nlp_service/implementations/language_tool_client_impl.py†L1-L107】
- **Command handlers**: Batch handlers catch `HuleEduError` instances to preserve the
  structured payload, log the failure with `correlation_id`, and continue with partial
  results so a single essay does not abort an entire batch.【F:services/nlp_service/command_handlers/essay_student_matching_handler.py†L197-L276】【F:services/nlp_service/command_handlers/batch_nlp_analysis_handler.py†L165-L307】
- **ErrorCode coverage**: Runtime helpers emit standard `common_core.error_enums.ErrorCode`
  values like `CONTENT_SERVICE_ERROR`, `EXTERNAL_SERVICE_ERROR`, and
  `RESOURCE_NOT_FOUND`; tests assert those codes so contract regressions are caught early
  (see `test_batch_nlp_analysis_handler.py` and `test_essay_student_matching_handler.py`).
  Reference `libs/common_core/docs/error-patterns.md` for the response schema.

## Testing

### Layout

```
tests/
├── unit/              # Pure-Python + AsyncMock coverage for handlers, matchers, clients
├── integration/       # Testcontainers-backed Redis/PostgreSQL workflows and pipelines
└── contract/          # Reserved for event/model contract checks
```

### Running Tests

```bash
# All service tests
pdm run pytest-root services/nlp_service/tests -v

# Unit tests only (safe in sandbox)
pdm run pytest-root services/nlp_service/tests/unit -v

# Integration tests (requires Docker + testcontainers for Postgres/Redis)
pdm run pytest-root services/nlp_service/tests/integration -v -m integration

# Focus on student matching handler
pdm run pytest-root services/nlp_service/tests/unit/test_essay_student_matching_handler.py -v
```

### Common Markers & Patterns

- `@pytest.mark.asyncio` for coroutine-heavy handlers, extractors, and feature pipeline
  tests.【F:services/nlp_service/tests/unit/test_batch_nlp_analysis_handler.py†L1-L78】
- `@pytest.mark.integration` for suites that spin up Redis/PostgreSQL testcontainers or
  language tool sandboxes.【F:services/nlp_service/tests/integration/test_command_handler_outbox_integration.py†L1-L40】
- `@pytest.mark.slow` on long-running NLP analyzer combinations that hydrate prompts and
  run full feature pipelines.【F:services/nlp_service/tests/integration/test_nlp_analyzer_integration.py†L189-L216】
- Fixtures are declared inline in each module (no `conftest.py`); tests rely on
  `AsyncMock(spec=Protocol)` objects to satisfy Dishka protocol contracts and to verify
  event publication semantics.【F:services/nlp_service/tests/unit/test_batch_nlp_analysis_handler.py†L1-L69】

Reference `.claude/rules/075-test-creation-methodology.md` for additional guidance.

## Migration Workflow

The NLP Service owns PostgreSQL tables (`nlp_analysis_jobs`, `student_match_results`, and
the shared `outbox_events`) and uses Alembic for schema management.

### Creating Migrations

```bash
cd services/nlp_service

# Autogenerate a revision after editing SQLAlchemy models
alembic revision --autogenerate -m "describe_change"

# Apply locally (development DB)
alembic upgrade head
```

### Standards

- Filename format `YYYYMMDD_HHMM_summary.py` in `alembic/versions/` in accordance with
  `.claude/rules/085-database-migration-standards.md`.
- Ensure outbox tables stay aligned with `huleedu_service_libs.outbox` metadata before
  generating revisions.
- Never edit applied migrations—add a corrective revision if schema adjustments are
  required.
- Validate revisions against a disposable database (testcontainers or local Postgres)
  before pushing.

### Existing Migrations

- `4d0dba8c7053_initial_nlp_service_schema_with_event_.py` – bootstraps NLP job +
  student match tables along with the transactional outbox.
- `c07989e7bd66_add_explicit_topic_column_to_event_.py` – adds topic metadata to the
  outbox for filtering downstream consumers.【F:services/nlp_service/alembic/versions/c07989e7bd66_add_explicit_topic_column_to_event_.py†L1-L26】

## CLI Tools

The NLP Service is a Kafka worker only and does not expose a Typer/Click CLI. Operational
scripts run via PDM entry points instead:

```bash
# Start the worker locally with environment variables loaded
source .env
cd services/nlp_service && pdm run start-worker

# Follow logs while reproducing events
cd -
pdm run dev-logs nlp_service
```

CLI utilities will be documented here if/when dedicated tooling (e.g., backfill
commands) ships.
