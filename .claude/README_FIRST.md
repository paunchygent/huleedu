# HuleEdu Monorepo - README FIRST

## Purpose & Scope
HuleEdu is an educational assessment platform that processes student essays through multiple AI-driven pipelines (spellcheck, NLP analysis, CJ assessment, AI feedback). Built as an event-driven microservices architecture with strict DDD principles.

## Architecture Overview
- **Pattern**: Event-driven microservices with Domain-Driven Design (DDD)
- **Communication**: Kafka for async events, HTTP for synchronous queries
- **State Management**: Each service owns its PostgreSQL database
- **Service Boundaries**: No direct DB access between services
- **Event Pattern**: EventEnvelope wrapper with correlation tracking
- **Reliability**: Transactional outbox pattern for critical events

## Tech Stack (Exact Versions)
- **Python**: 3.11
- **Frameworks**: Quart (internal), FastAPI (external APIs)
- **Package Manager**: PDM 2.10.4
- **Core Libraries**:
  - Pydantic v2 (data validation)
  - SQLAlchemy 2.0+ (async ORM)
  - Dishka (dependency injection)
  - aiohttp (HTTP client)
- **Infrastructure**:
  - PostgreSQL 15
  - Kafka (Bitnami)
  - Redis (caching/state)
  - Docker & Docker Compose v2
- **Observability**:
  - Prometheus (metrics)
  - Jaeger (tracing)
  - Grafana + Loki (dashboards/logs)

## Key Services
1. **API Gateway** (FastAPI) - External API, JWT auth, rate limiting
2. **Batch Orchestrator (BOS)** - Pipeline coordination, phase initiation
3. **Batch Conductor (BCS)** - Pipeline resolution, dependency management
4. **Essay Lifecycle (ELS)** - Phase outcome tracking, state management
5. **Class Management** - Student/batch associations
6. **Content Service** - Essay content storage
7. **File Service** - File upload/processing
8. **Spellchecker** - Grammar/spelling validation
9. **CJ Assessment** - Content judgment evaluation
10. **NLP Service** - Natural language processing
11. **Result Aggregator (RAS)** - Results compilation
12. **Entitlements** - Credit management

## How to Run

### Prerequisites
```bash
# Ensure Docker & Docker Compose v2 are installed
docker --version  # Should be 20.10+
docker compose version  # Should be 2.x

# Install PDM
pip install pdm==2.10.4
```

### Development Setup
```bash
# 1. Clone and setup
git clone <repo>
cd huledu-reboot
pdm install

# 2. Start all services (development mode with hot-reload)
pdm run dev-start

# 3. Run database migrations
pdm run db-migrate

# 4. Seed test data
pdm run db-seed

# 5. Check service health
docker ps | grep huleedu
pdm run health-check
```

### Running Tests
```bash
# Unit tests
pdm run pytest services/<service_name>/tests/unit

# Integration tests
pdm run pytest services/<service_name>/tests/integration

# Functional E2E tests (requires all services running)
pdm run pytest-root tests/functional/test_e2e_cj_after_nlp_with_pruning.py -v

# With specific markers
pdm run pytest -m "not slow"  # Skip slow tests
pdm run pytest -m integration  # Only integration tests
```

### Common Commands
```bash
# Service management
pdm run restart <service_name>  # Restart specific service
pdm run restart-all             # Restart all services
pdm run logs <service_name>     # View service logs

# Docker shortcuts
docker logs huleedu_<service>_service --tail 50
docker exec huleedu_<service>_db psql -U huleedu_user -d huleedu_<service>

# Linting & formatting
pdm run lint         # Run Ruff linter
pdm run format-all   # Format all code
pdm run typecheck-all # Run MyPy
```

## Recent Decisions & Changes (Dec 2024)

### 1. Redis Caching for BCS Duplicate Calls
**Issue**: BOS makes duplicate calls to BCS (preflight + handler) 9ms apart.
**Solution**: Redis cache with 10s TTL wraps BCS client (cache → circuit breaker → base).
**Config**: `BCS_CACHE_ENABLED=true`, `BCS_CACHE_TTL_SECONDS=10`
**Status**: Plan complete in `TASKS/updated_plan.md`, implementation pending.

### 2. V2 Event Models for Essay Instructions
**Added**: `BatchServiceNLPInitiateCommandDataV2` and `BatchNlpProcessingRequestedV2`.
**Purpose**: Support essay instructions in NLP processing.
**Files**: `libs/common_core/src/common_core/batch_models.py`

### 3. Bayesian Consensus Model
**Location**: `scripts/bayesian_consensus_model/`
**Purpose**: Improve grading accuracy for sparse data scenarios.
**Status**: Implemented and validated.

## Configuration Files
- `.env` - Environment variables (not in git)
- `pyproject.toml` - PDM dependencies and scripts
- `docker-compose.yml` - Production config
- `docker-compose.dev.yml` - Development overrides
- `.claude/rules/` - Development standards and patterns
- `CLAUDE.md` - AI assistant instructions

## Important Notes
- Always use `pdm run pytest-root` for tests (handles monorepo paths)
- Never use `--since` in Docker logs when searching correlation IDs
- Services use APP-scoped DI for singletons, REQUEST-scoped for per-operation
- All events use EventEnvelope wrapper with correlation tracking
- Transactional outbox pattern ensures event delivery reliability