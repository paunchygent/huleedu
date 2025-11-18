# HuleEdu Microservice Platform

Event-driven microservice platform for automated essay processing and assessment. Built with Python 3.11+, Kafka, PostgreSQL, and Redis in a PDM-managed monorepo.

## Architecture and Design

### Core Architectural Principles

**Domain-Driven Design**: Services by bounded context with strict boundaries. No cross-service database access.

**Event-Driven Architecture**: Kafka-based async communication with `EventEnvelope` wrapper. Dual-phase processing: Phase 1 (student matching), Phase 2+ (pipeline processing).

**Service Autonomy**: Independent deployment, dedicated databases, event-based data sharing.

**Async I/O**: Python async/await with Quart/FastAPI, aiokafka, async SQLAlchemy.

**Dependency Injection**: Dishka DI with Protocol interfaces in `protocols.py`.

**Environment Configuration**: Pydantic `BaseSettings` classes, twelve-factor compliant.

**Observability Stack**:

- OpenTelemetry tracing, Prometheus metrics, structured logging
- Grafana (3000), Prometheus (9091), Jaeger (16686), Loki (3100)

### Credits Preflight & Consumption

- Preflight: API Gateway → BOS preflight → Entitlements bulk check.
  - BOS route: `POST /internal/v1/batches/{batch_id}/pipelines/{phase}/preflight` returns 200/402/429 with required/available and resource breakdown.
  - Entitlements bulk: `POST /v1/entitlements/check-credits/bulk` returns 200 allowed, 402 insufficient, 429 rate-limited.
- Consumption: Post-usage via `ResourceConsumptionV1` events → Entitlements debits and publishes `CreditBalanceChangedV1` via outbox.
- Identity: Org-first selection; per-metric rate limits (user-scoped) prior to balance checks; correlation ID from `X-Correlation-ID` threaded end-to-end.

See also:

- `TASKS/ENTITLEMENT_SERVICE_IMPLEMENTATION_PLAN.md` (final reference + historical appendix)
- `.cursor/rules/020.17-entitlements-service-architecture.md`
- `libs/common_core/src/common_core/entitlements_models.py`

## Testing & Quality

### Standard Test Runner

Use the root-aware runner for consistent config and path resolution across the monorepo.

```bash
# Go-to method
pdm run pytest-root <path-or-nodeid> [pytest args]

# From any directory (helpers)
source scripts/dev-aliases.sh
pyp <path-or-nodeid> [args]                 # run tests via root-aware wrapper
pdmr pytest-root <path-or-nodeid> [args]    # force PDM to use repo root

# Optional global shim (configured above)
pytest-root <path-or-nodeid> [args]
```

See also: `CODEX.md` and `CLAUDE.md`for detailed guidance.

## Monorepo Structure

PDM-managed monorepo with unified dependency management:

- **`common_core/`** – Shared Pydantic models, enums, EventEnvelope format
- **`services/`** – All microservices in dedicated folders
- **`services/libs/`** – Shared infrastructure libraries
- **`scripts/`** – Development and operations scripts
- **`documentation/`** – Architecture docs, PRDs, task breakdowns
- **`.cursor/rules/`** – Development standards and coding rules

## Microservices Overview

### Content Service

HTTP service (port 8001) for binary content storage. REST API: `POST/GET /v1/content`.

### File Service  

HTTP service (port 7001) for file uploads. Supports `.txt`, `.docx`, `.pdf` with Strategy Pattern extraction. Outbox pattern for event delivery.

### Essay Lifecycle Service (ELS)

Hybrid HTTP (port 8000) + Kafka service for essay state management. Phase 1: stateless event routing. Phase 2+: stateful pipeline orchestration via EssayStateMachine.
Events: Consumes BOS commands, publishes essay state transitions.

### Batch Orchestrator Service (BOS)

HTTP service (port 5001) for batch-level coordination. Routes GUEST batches (no class_id) directly to pipeline. Routes REGULAR batches (has class_id) through Phase 1 student matching first.

### Batch Conductor Service (BCS)

HTTP service (port 4002) for dynamic pipeline dependency resolution. Uses Redis to track batch completion state and determine next processing phase.

### Identity Service

HTTP service (port 5003) for authentication and user management. JWT tokens (HS256/RS256), rate limiting, session control. API: `/v1/auth/*` endpoints. RFC 7009 token revocation.

### Spellchecker Service

Kafka consumer for spell/grammar checking. Listens: `huleedu.commands.spellcheck.v1`. Emits: `EssaySpellcheckCompleted`. Metrics: port 8002.

### Comparative Judgment (CJ) Assessment Service

Kafka consumer (port 9090) for AI-assisted essay comparison. Uses LLM Provider Service for pairwise judgments. PostgreSQL storage. Emits: `BatchComparativeJudgmentCompleted`.

### LLM Provider Service

HTTP service (port 8090) for centralized AI API gateway. Redis queue with circuit breakers. Multi-provider (OpenAI, Anthropic). API: `POST /api/v1/comparison` with `callback_topic`. Emits: `LLMComparisonResultV1`.

### NLP Service

Kafka worker with Command Handler pattern for dual-phase processing. Uses PostgreSQL for outbox pattern, no HTTP endpoints.

**Command Handler Architecture:**

- **Phase 1**: `EssayStudentMatchingHandler` processes `BatchStudentMatchingRequestedV1`
- **Phase 2**: `BatchNlpAnalysisHandler` processes `BatchNLPInitiateCommandV1`
- Both handlers implement `CommandHandlerProtocol` for clean separation
- Event routing via `command_handlers` dict in `NlpKafkaConsumer`

**Phase 1: Student Matching (Pre-readiness)**

- Extracts student identifiers using extraction pipeline (Exam.net, headers, email anchors)
- Fuzzy matching against class rosters with confidence scoring
- Emits: `BatchAuthorMatchesSuggestedV1` → Class Management Service

**Phase 2: Text Analysis (Post-readiness)**  

- Linguistic analysis: readability, complexity, NLP metrics
- Language Tool integration for grammar analysis
- Emits: `EssayNlpCompletedV1` (business data) + `BatchNlpAnalysisCompleted` (state management)

**Performance**: <100ms per essay, asyncio.Semaphore(10), max 100 essays/batch

### Class Management Service (CMS)

A Quart-based HTTP CRUD service (port 5002) that manages metadata about classes, students, and their enrollment relationships. It serves as the authoritative source for user domain data and handles Phase 1 student matching validation.

**Core Responsibilities:**

- Class and student enrollment management via REST API (`/v1/classes`, `/v1/students`)
- Phase 1 student matching: receives NLP suggestions via `BatchAuthorMatchesSuggestedV1` events
- Association timeout monitoring: auto-confirms pending associations after 24 hours

**Phase 1 Student Matching:**

- **Association Timeout Monitor**: Auto-confirms pending student-essay associations after 24-hour timeout
- **High Confidence (≥0.7)**: Confirms association with original student using `TIMEOUT` validation method
- **Low Confidence (<0.7)**: Creates UNKNOWN student with email `unknown.{class_id}@huleedu.system`
- **Database Fields**: `batch_id`, `class_id`, `confidence_score`, `validation_status`, `validation_method`

**Key Features:**

- **Authoritative Source**: Single source of truth for user domain data
- **Phase 1 Integration**: Processes NLP student matching suggestions
- **Automated Validation**: 24-hour timeout with confidence-based decision logic
- **REST API**: Full CRUD operations for classes and students
- **Database**: PostgreSQL with Phase 1 association tracking fields

### Result Aggregator Service (RAS)

A hybrid service (Kafka consumer + publisher with HTTP API on port 4003) that aggregates results and coordinates service communication through event publishing.

**Key Features:**

- **Event Aggregation**: Consumes completion events from processing services
- **Event Publishing**: Publishes batch completion and assessment events via transactional outbox
- **Teacher Notifications**: Projects result events to teacher notifications using direct projector invocation
- **Query API**: Provides optimized access to batch and essay results
- **Cache Management**: Redis-based optimization with active invalidation

### API Gateway Service

A FastAPI-based gateway service (port 4001) that serves as the unified entry point for external clients (e.g., a Svelte frontend or third-party applications).

**Core Responsibilities:**

- **Authentication**: Validates JWT tokens for incoming requests
- **Request Validation**: Uses Pydantic models from `common_core`
- **Rate Limiting**: Protects backend services from excessive traffic
- **Request Routing**: Proxies requests to appropriate internal services
- **Event Publishing**: Publishes client requests as Kafka events
- **WebSocket Support**: Enables real-time updates for clients
- **Anti-Corruption Layer**: Translates between internal and client-facing data models

### WebSocket Service

A pure notification router (port 8080) that manages persistent WebSocket connections and delivers teacher notifications through a clean architectural pattern.

**Key Features:**

- **Pure Notification Router**: Consumes only `TeacherNotificationRequestedV1` events, never internal domain events
- **Teacher-Centric**: All notifications routed to teachers with proper authorization validation
- **Real-Time Delivery**: Immediate teacher feedback via Kafka → WebSocket → Redis pipeline
- **Clean Separation**: No business logic, trusts service-validated teacher_id in notification events

### Email Service

Kafka consumer + HTTP dev API (port 8082) for transactional email delivery. Consumes `NotificationEmailRequestedV1` events from Identity Service via NotificationOrchestrator. Provider pattern: mock/SMTP with Namecheap Private Email. Jinja2 templates with subject extraction. Outbox pattern for reliable event publishing.

## Critical Event Flows

### REGULAR Batch (with class_id)

1. File upload → FileService → `FileUploadCompleted`
2. BOS creates batch → `BatchCreated` → ELS Phase 1 routing
3. ELS → `BatchStudentMatchingRequestedV1` → NLP Phase 1 Handler
4. NLP → `BatchAuthorMatchesSuggestedV1` → CMS validation
5. CMS → `StudentAssociationsConfirmedV1` → ELS Phase 2 start
6. Standard pipeline: Spellcheck → CJ → NLP Phase 2 → RAS

### GUEST Batch (no class_id)  

1. File upload → FileService → `FileUploadCompleted`
2. BOS creates batch → `BatchCreated` → direct pipeline routing
3. Skip Phase 1, immediate Phase 2 pipeline execution
4. Standard pipeline: Spellcheck → CJ → NLP Phase 2 → RAS

## Service & Infrastructure Ports

### Microservices

- **Content Service**: 8001
- **File Service**: 7001  
- **Essay Lifecycle (ELS)**: API:6001, Worker:internal
- **Batch Orchestrator (BOS)**: 5001
- **Batch Conductor (BCS)**: 4002
- **Identity Service**: 7005 (API), 9097 (metrics)
- **Class Management (CMS)**: 5002
- **Spellchecker**: 8002
- **CJ Assessment**: 9095
- **NLP Service**: Worker only (no HTTP)
- **LLM Provider**: 8090
- **Result Aggregator (RAS)**: 4003, 9096 (metrics)
- **API Gateway**: 8080
- **WebSocket Service**: 8081
- **Email Service**: 8082 (API), 9098 (metrics)

### Databases (PostgreSQL)

- **Essay Lifecycle DB**: 5433
- **CJ Assessment DB**: 5434
- **Class Management DB**: 5435
- **Result Aggregator DB**: 5436
- **Spellchecker DB**: 5437
- **Batch Orchestrator DB**: 5438
- **File Service DB**: 5439
- **NLP DB**: 5440
- **Batch Conductor DB**: 5441
- **Identity DB**: 5442
- **Email DB**: 5443

### Infrastructure

- **Kafka**: 9092-9093
- **Redis**: 6379
- **Grafana**: 3000
- **Prometheus**: 9091
- **Jaeger**: 16686
- **Loki**: 3100
- **Alertmanager**: 9094

### Observability Exporters

- **Kafka Exporter**: 9308
- **Postgres Exporter**: 9187
- **Redis Exporter**: 9121
- **Node Exporter**: 9100

## Technology Stack

### Core

- **Python 3.11+**: Async support, rich ecosystem
- **Quart**: ASGI web framework for HTTP services  
- **FastAPI**: API Gateway, automatic OpenAPI docs
- **Pydantic**: Schema validation, data models
- **Kafka**: Event streaming via `aiokafka`

### Data

- **PostgreSQL**: Production databases (per-service isolation)
- **SQLAlchemy**: Async ORM, migrations
- **Redis**: Caching, batch coordination, rate limiting, queuing
- **Mock Repositories**: Development/testing (in-memory)

### Infrastructure

- **Docker/Compose**: Service containerization
- **Dishka**: Dependency injection with protocols
- **PDM**: Python dependency management, task runner

### Development

- **Ruff**: Linting, formatting (`pdm run format-all`)
- **MyPy**: Static type checking
- **PyTest**: Unit/integration/contract/e2e tests

## Development Setup

### Prerequisites

- Python 3.11+, Docker/Compose, PDM

### Setup

```bash
git clone <repository-url> && cd huledu-reboot
./scripts/setup_huledu_environment.sh
```

### Essential Commands

```bash
# Docker workflow
pdm run docker-build        # Build images
pdm run docker-up          # Start all services  
pdm run docker-down        # Stop services
pdm run docker-restart     # Rebuild and restart
pdm run docker-logs        # View logs

# Code quality
pdm run format-all         # Format code
pdm run lint-fix --unsafe-fixes  # Run linter
pdm run typecheck-all      # Type checking

# Testing
pdm run test-all           # Run all tests
pdm run test-parallel      # Force parallel
pdm run test-sequential    # Force sequential

# Health checks
docker-compose ps          # Container status
curl localhost:5001/healthz  # BOS health
curl localhost:8000/healthz  # ELS health
```

## AI Agent Quick Reference

### Service Patterns

- **Environment prefix**: `<SERVICE_NAME>_` (e.g., `IDENTITY_`, `CLASS_MANAGEMENT_`)
- **Database URL pattern**: `postgresql+asyncpg://user:pass@host:port/huleedu_<service>`
- **Health check pattern**: `http://localhost:<port>/healthz`
- **Metrics pattern**: `http://localhost:<port>/metrics`
- **Event topics**: `huleedu.<domain>.<event>.<version>`

### Architecture Patterns

- **Command Handler**: NLP service uses `CommandHandlerProtocol` for phase separation
- **Outbox Pattern**: Transactional event publishing via PostgreSQL outbox tables
- **Dual Events**: Thin state events + rich business events (ELS ↔ RAS pattern)
- **Protocol DI**: All dependencies via `typing.Protocol` interfaces in `protocols.py`
- **Request/Response**: Immediate HTTP + async Kafka completion events

### Database Access

```bash
# Source environment first
source .env

# Access service databases
docker exec huleedu_<service>_db psql -U $HULEEDU_DB_USER -d huleedu_<service> -c "SQL"

# Example: Class Management DB
docker exec huleedu_class_management_db psql -U huleedu_user -d huleedu_class_management -c "\dt"
```
