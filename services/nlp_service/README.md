# NLP Service

## Overview

The NLP Service is a dual-phase Kafka worker service responsible for natural language processing tasks on student essays. It handles both Phase 1 (pre-readiness) student matching and Phase 2 (post-readiness) text analysis, processing entire batches of essays with parallel execution and partial failure handling.

## Architecture

- **Pattern**: Pure Worker Service (Kafka-only, no HTTP API)
- **Stack**: Python 3.11, aiokafka, aiohttp, Dishka, thefuzz
- **Phase 1 Input**: `BATCH_STUDENT_MATCHING_REQUESTED` events via Kafka
- **Phase 1 Output**: `BATCH_AUTHOR_MATCHES_SUGGESTED` events via Kafka
- **Phase 2 Input**: `BATCH_NLP_INITIATE_COMMAND` events via Kafka
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
- **Spell Metrics Propagation**: Essay Lifecycle Service forwards `SpellcheckResultV1.correction_metrics`, allowing the NLP handler to reuse Spellchecker totals without re-running the normaliser.
- **Language Tool Integration**: Grammar analysis runs on the spell-normalised text and feeds grammar-related feature extractors.
- **Outputs**: `EssayNlpCompletedV1` rich events include the feature map in `processing_metadata["feature_outputs"]`; thin batch completion events remain unchanged.

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
