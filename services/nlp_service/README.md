# NLP Service

## Overview

The NLP Service is a pure Kafka worker service responsible for natural language processing tasks on student essays. Currently focused on Phase 1: Student Matching functionality, which identifies and matches student names/emails from essay text against class rosters.

## Architecture

- **Pattern**: Pure Worker Service (Kafka-only)
- **Input**: `BATCH_NLP_INITIATE_COMMAND` events via Kafka
- **Output**: `ESSAY_AUTHOR_MATCH_SUGGESTED` events via Kafka
- **Dependencies**: Content Service (HTTP), Class Management Service (HTTP), Redis (caching)
- **Database**: PostgreSQL with outbox pattern for reliable event publishing

## Key Features

### Phase 1: Student Matching
- Extracts student identifiers (names, emails) from essay text
- Fuzzy matches against class rosters
- Provides confidence-scored match suggestions
- Caches rosters in Redis for performance

### Future Phases (Not Implemented)
- Essay metrics (readability, complexity)
- Text analysis and NLP features
- Language detection and processing

## Service Structure

```
nlp_service/
├── worker_main.py        # Entry point with signal handling
├── kafka_consumer.py     # Kafka consumer with idempotency
├── event_processor.py    # Message processing logic
├── di.py                 # Dependency injection setup
├── protocols.py          # Service interfaces
├── implementations/      # Protocol implementations
├── models_db.py          # Database models
└── repositories/         # Database access layer
```

## Environment Variables

- `NLP_SERVICE_DATABASE_URL`: PostgreSQL connection string
- `NLP_SERVICE_KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses
- `NLP_SERVICE_CONTENT_SERVICE_URL`: Content Service URL
- `NLP_SERVICE_CLASS_MANAGEMENT_SERVICE_URL`: Class Management Service URL
- `NLP_SERVICE_REDIS_URL`: Redis connection string
- `NLP_SERVICE_LOG_LEVEL`: Logging level (default: INFO)

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
- **Metrics**: Prometheus metrics on processing rates, confidence scores
- **Logging**: Structured logging with correlation IDs
- **Tracing**: OpenTelemetry integration

## Database Schema

- `nlp_analysis_jobs`: Tracks NLP processing jobs
- `student_match_results`: Stores match suggestions with confidence scores
- `outbox_events`: Reliable event publishing via outbox pattern