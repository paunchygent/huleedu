# HuleEdu — Spell Checker Service

Kafka worker that performs L2-aware spell-checking on essays.
Exposed HTTP endpoints: `/healthz` and `/metrics`.

## Overview

The Spell Checker Service processes essay spellchecking requests via Kafka, performs L2-aware spell checking, and stores the results. It follows clean architecture principles with clear separation of concerns and dependency injection.

## Runtime Flow

```mermaid
graph TD;
A[huleedu.essay.spellcheck.requested.v1] -->|consume| B(SpellCheckerKafkaConsumer)
B --> C(process_single_message)
C --> D[fetch essay (Content Service)]
D --> E[run L2 + pyspellchecker]
E --> F[store corrected text (Content Service)]
F --> G[persist meta (PostgreSQL)]
G -->|publish| H[huleedu.essay.spellcheck.completed.v1]
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
| `protocol_implementations/` | HTTP, Kafka, spell logic, repo adapters |
| `spell_logic/` | L2 dict loader, filters, correction algorithm |
| `implementations/spell_repository_postgres_impl.py` | Async Postgres repository |
| `di.py` | `SpellCheckerServiceProvider` (Dishka) |
| `tests/` | Unit + integration (Testcontainers-PG) |

## Configuration

Environment variables with `SPELL_CHECKER_SERVICE_` prefix:

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
pdm run pytest -s services/spell_checker_service/tests -v

# Run specific test file
pdm run pytest services/spell_checker_service/tests/path/to/test_file.py -v
```

## Deployment

### Docker

```bash
docker build -f services/spell_checker_service/Dockerfile -t spellchecker-service .
```

### Health Checks

- **Endpoint**: `GET /healthz`
- **Port**: 8002
- **User**: Runs as UID 1000
- **Volumes**:
  - `./data` for correction logs

## Recent Highlights

- Clean architecture refactor with Dishka DI
- Async Postgres repository with Alembic migrations
- OpenTelemetry integration with Jaeger
- Prometheus metrics endpoint
- Language parameter support in events
- Comprehensive test suite (70+ tests)

## License

[Your License Here]