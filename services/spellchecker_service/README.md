# HuleEdu — Spell Checker Service

Kafka worker that performs L2-aware spell-checking on essays.
Exposed HTTP endpoints: `/healthz` and `/metrics`.

## Overview

The Spell Checker Service processes essay spellchecking requests via Kafka, performs L2-aware spell checking, and stores the results. It follows clean architecture principles with clear separation of concerns and dependency injection.

## Dual Event Publishing Pattern

The service implements a dual event pattern optimized for different consumer needs:

### Thin Event: State Management
- **Event**: `SpellcheckPhaseCompletedV1`
- **Topic**: `huleedu.batch.spellcheck.phase.completed.v1`
- **Consumers**: ELS (Essay Lifecycle Service), BCS (Batch Conductor Service)
- **Purpose**: Minimal state transition data (~300 bytes)
- **Fields**: entity_id, batch_id, status, corrected_text_storage_id, error_code, processing_duration_ms

### Rich Event: Business Data
- **Event**: `SpellcheckResultV1`
- **Topic**: `huleedu.essay.spellcheck.results.v1`
- **Consumer**: RAS (Result Aggregator Service)
- **Purpose**: Complete business metrics and processing details
- **Fields**: Full correction metrics, word counts, L2 vs spelling corrections, correction density

### Benefits
- **Performance**: ELS/BCS receive minimal data for state transitions
- **Separation of Concerns**: State management vs business analytics
- **Network Efficiency**: Reduces data transfer for state-only consumers

### Internal Architecture Note

#### Legacy Model Usage (Temporary)
The service internally uses `SpellcheckResultDataV1` for backward compatibility during the transition to the dual-event pattern. This model is converted to the new dual events before publishing:
- `SpellcheckPhaseCompletedV1` (thin event for state transitions)
- `SpellcheckResultV1` (rich event with business metrics)

This internal usage will be removed in a future refactoring once all components are verified working with the dual-event pattern.

### Header Processing

Events from OutboxManager-enabled services include Kafka headers:

- `event_id`, `event_type`, `trace_id`, `source_service` headers
- Header-complete messages skip JSON parsing during idempotency processing
- `headers_used` field logged for utilization tracking

## Runtime Flow

```mermaid
graph TD;
A[huleedu.essay.spellcheck.requested.v1] -->|consume| B(SpellCheckerKafkaConsumer)
B --> C(process_single_message)
C --> D[fetch essay (Content Service)]
D --> E[run L2 + pyspellchecker]
E --> F[store corrected text (Content Service)]
F --> G[persist meta (PostgreSQL)]
G --> H{Dual Event Publishing}
H -->|thin event| I[huleedu.batch.spellcheck.phase.completed.v1]
H -->|rich event| J[huleedu.essay.spellcheck.results.v1]
I --> K[ELS/BCS State Management]
J --> L[RAS Business Data]
```

## Tech Stack

- **Runtime**: Python 3.11 / asyncio
- **Messaging**: aiokafka
- **HTTP**: aiohttp, Quart + Dishka DI (`QuartDishka`)
- **Database**: SQLAlchemy 2 async + Alembic, Postgres 15 (`pg_trgm`, GIN)
- **Observability**:
  - Prometheus metrics at `/metrics`
  - OpenTelemetry → Jaeger (OTLP gRPC)
- **Security**: Runs as non-root (UID 1000) in Docker

## Architecture

| Path | Purpose |
|------|---------|
| `worker_main.py` | Bootstrap, signals, tracing, DI |
| `event_processor.py` | Orchestrator (`process_single_message`) |
| `protocols.py` | `typing.Protocol` contracts |
| `implementations/` | HTTP, Kafka, spell logic, repo adapters |
| `spell_logic/` | L2 dict loader, filters, correction algorithm |
| `implementations/spell_repository_postgres_impl.py` | Async Postgres repository |
| `di.py` | `SpellCheckerServiceProvider` (Dishka) |
| `tests/` | Unit + integration (Testcontainers-PG) |

## Configuration

Environment variables with `SPELLCHECKER_SERVICE_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://spellchecker:pass@spellchecker_db:5432/spellchecker` | Postgres connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Comma-separated Kafka brokers |
| `CONTENT_SERVICE_URL` | `http://content_service:8000/v1/content` | Content service endpoint |
| `CONSUMER_GROUP` | `spellchecker-service-group-v1.1` | Kafka consumer group |
| `PRODUCER_CLIENT_ID` | `spellchecker-service-producer` | Kafka producer ID |
| `DEFAULT_LANGUAGE` | `en` | Fallback language |
| `ENABLE_L2_CORRECTIONS` | `true` | Toggle L2 correction stage |
| `ENABLE_CORRECTION_LOGGING` | `true` | Log diffs to `data/` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OpenTelemetry collector |
| `OTEL_SERVICE_NAME` | - | Service name for tracing |

## Observability

### Metrics

- **Endpoint**: `/metrics` (Prometheus format)
- **Metrics**:
  - Processed messages counter
  - Failure counter
  - Correction statistics

### Tracing

- **Implementation**: `huleedu_service_libs.observability.init_tracing()`
- **Exporter**: OTLP gRPC
- **UI**: [Jaeger](http://localhost:16686)

## Persistence

- **Repository**: `PostgreSQLSpellcheckRepository`
- **Database**: PostgreSQL with `pg_trgm` extension
- **Migrations**: Alembic

## Dependency Injection

- **Framework**: Dishka
- **Contracts**: `typing.Protocol`
- **Provider**: `SpellCheckerServiceProvider`

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

## Development

### Prerequisites

- Docker
- Python 3.11
- PDM

### Local Setup

```bash
# Start dependencies
docker compose up -d spellchecker_db kafka

# Install dependencies
pdm install

# Run service
pdm run start

# Verify
curl http://localhost:8002/healthz
open http://localhost:8002/metrics
```

## Testing

```bash
# Run all tests (uses Testcontainers-Postgres)
pdm run pytest -s services/spellchecker_service/tests -v

# Run specific test file
pdm run pytest services/spellchecker_service/tests/path/to/test_file.py -v
```

## Deployment

### Docker

```bash
docker build -f services/spellchecker_service/Dockerfile -t spellchecker-service .
```

### Health Checks

- **Endpoint**: `GET /healthz`
- **Port**: 8002
- **User**: Runs as UID 1000
- **Volumes**:
  - `./data` for correction logs

## Circuit Breaker Observability

Circuit breaker metrics are exposed via the `/metrics` endpoint:

- **`circuit_breaker_state`**: Current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) with labels: `service`, `circuit_name`
- **`circuit_breaker_state_changes`**: State transition counter with labels: `service`, `circuit_name`, `from_state`, `to_state`  
- **`circuit_breaker_calls_total`**: Call result counter with labels: `service`, `circuit_name`, `result` (success/failure/blocked)

Circuit breakers protect Kafka publishing operations and are configured via `SPELLCHECKER_SERVICE_CIRCUIT_BREAKER_` environment variables.

## Recent Highlights

- **Dual Event Pattern**: Optimized publishing for state management vs business data
- **Enhanced Metrics**: L2 correction tracking, word counts, correction density
- **Outbox Pattern**: Reliable dual event publishing via transactional outbox
- Clean architecture refactor with Dishka DI
- Async Postgres repository with Alembic migrations
- OpenTelemetry integration with Jaeger
- Prometheus metrics endpoint
- Language parameter support in events
- Comprehensive test suite (70+ tests)

## License

Apache License 2.0
