# CJ Assessment Service

## Overview

The CJ Assessment Service is a microservice dedicated to performing Comparative Judgment (CJ) assessment of essays using Large Language Model (LLM) based pairwise comparisons. The service consumes spellchecked essay texts and produces Bradley-Terry scores and rankings through iterative LLM-driven comparisons.

## Architecture

### Service Type

- **Pattern**: Hybrid Kafka Worker + HTTP API Service
- **Framework**: Quart (HTTP API) + Direct `asyncio` and `aiokafka` for message processing
- **Dependency Injection**: Dishka framework for clean architecture
- **DI Initialization Order**: `QuartDishka(app, container)` is invoked *before* Blueprint registration to satisfy Dishka route injection requirements (see `app.py`)
- **Concurrency**: Both HTTP API and Kafka worker run concurrently via `run_service.py`

### Key Internal Modules

- **`core_logic/`**: Core business logic package containing:
  - **`core_assessment_logic.py`**: Orchestrates the complete CJ workflow from request processing to result publication
  - **`pair_generation.py`**: Generates comparison tasks for iterative CJ assessment
  - **`scoring_ranking.py`**: Handles Bradley-Terry scoring using the `choix` library and ranking calculations
- **`protocols.py`**: Defines behavioral contracts using `typing.Protocol` for all major dependencies
- **`implementations/`**: Concrete implementations of all protocols (database, LLM providers, event publishing, content fetching)
- **`event_processor.py`**: Processes individual Kafka messages, hydrates `student_prompt_ref` via Content Service, records `huleedu_cj_prompt_fetch_failures_total{reason}` on failures, and delegates to core workflow
- **`worker_main.py`**: Kafka consumer lifecycle management and message processing
- **`app.py`**: Lean Quart HTTP API application with health and metrics endpoints
- **`run_service.py`**: Main service runner that orchestrates concurrent Kafka worker and HTTP API
- **`api/health_routes.py`**: Blueprint containing `/healthz` and `/metrics` endpoints

### Dependencies

- **Content Service**: HTTP client for fetching spellchecked essay content
- **LLM Provider Service**: Centralized LLM provider abstraction with queue-based resilience
  - **Immediate Responses (200)**: Direct LLM results when providers available
  - **Queued Responses (202)**: Automatic polling when providers unavailable
  - **Configurable Timeouts**: Customizable polling behavior for different environments
- **Database**: Async SQLAlchemy (SQLite by default for development; **PostgreSQL recommended for production deployments**)
- **Kafka**: Event consumption and publishing via EventEnvelope pattern

## Grade Scale Registry & Calibration

The CJ service now resolves grades from a shared registry defined in
`libs/common_core/src/common_core/grade_scales.py`. Each scale entry provides the
ordered grades, optional population priors, and configuration for handling scores
below the lowest anchor. Today the registry includes:

- `swedish_8_anchor` (default)
- `eng5_np_legacy_9_step`
- `eng5_np_national_9_step`

### How Scales Are Selected

1. **Assignment instructions** (`assessment_instructions` table) carry a
   `grade_scale` column. Migrations have backfilled existing rows to
   `swedish_8_anchor`.
2. **Anchor registration** (`POST /api/v1/anchors/register`) resolves the
   assignment, validates the submitted grade against the configured scale, and
   persists both grade and scale to `anchor_essay_references`.
3. **Batch preparation** fetches only anchors whose `grade_scale` matches the
   assignment, ensuring mixed-scale anchors are never combined.
4. **GradeProjector** loads the registry metadata for the resolved scale,
   applies scale-specific priors/boundaries, and tags every stored projection
   with the active scale for downstream reporting.

### Operational Workflow

To work with a non-default scale (for example ENG5 NP variants):

1. Insert or update the relevant row in `assessment_instructions` with the
   desired `grade_scale` value. (The instructions text remains the canonical
   metadata for the assignment.)
2. Register anchors via the HTTP API or helper CLI; supplied grades will be
   validated against the new scale automatically.
3. Trigger CJ batches as usual. All downstream consumers (context builder,
   projector, events/tests) will operate with the chosen scale.

> **Note**: If you register anchors before inserting the instruction row the API
> will respond with `400 Unknown assignment_id`—seed instructions first, then add
> anchors.

> **Upcoming**: Phase 3.2 will introduce an authenticated admin endpoint/CLI to
> create or update `assessment_instructions` directly. Until then, seed rows via
> the upstream Class Management workflow or manual SQL as outlined above.

### Calibration Highlights

- **Population Priors**: When the registry provides priors they override anchor
  frequency, reducing bias from sparse anchors. If none are supplied a uniform
  prior is generated on the fly.
- **Shrinkage & Extrapolation**: Grades without anchors borrow expected positions
  from the registry ordering, preventing unstable calibrations.
- **Metadata in Projections**: Stored projections now include
  `grade_scale`, `primary_anchor_grade`, and scale-specific boundary metadata to
  simplify analytics and export tooling.

## Admin API & CLI

Phase 3.2 adds an authenticated admin surface for managing
`assessment_instructions` without manual SQL:

- **HTTP blueprint**: `/admin/v1/assessment-instructions` (POST upsert, GET
  list, GET/DELETE per assignment, DELETE per course). Requests must include an
  Identity-issued JWT with `roles` containing `admin`. Validation reuses the
  shared helper in `libs/huleedu_service_libs/auth/`, and the blueprint only
  registers when `CJ_ASSESSMENT_SERVICE_ENABLE_ADMIN_ENDPOINTS` is `true`.
- **Observability**: Structured errors use Rule 048 factories and the Prometheus
  counter `cj_admin_instruction_operations_total{operation,status}` records CRUD
  outcomes.
- **Typer CLI**: `pdm run cj-admin …` authenticates via Identity
  `/v1/auth/login`, caches/refreshes tokens under
  `~/.huleedu/cj_admin_token.json`, supports `CJ_ADMIN_TOKEN` overrides for
  automation, and exposes `instructions create|list|get|delete` plus
  `scales list` commands.

### Admin API Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/admin/v1/assessment-instructions` | Create or update instructions for an assignment or course (body mirrors `AssessmentInstructionUpsertRequest`) |
| `GET` | `/admin/v1/assessment-instructions` | Paginated list with optional `grade_scale` filter |
| `GET` | `/admin/v1/assessment-instructions/assignment/{assignment_id}` | Fetch the latest instructions for an assignment |
| `DELETE` | `/admin/v1/assessment-instructions/assignment/{assignment_id}` | Remove assignment-scoped instructions |
| `DELETE` | `/admin/v1/assessment-instructions/course/{course_id}` | Remove course fallback instructions |

**Enablement checklist**

1. Set `CJ_ASSESSMENT_SERVICE_ENABLE_ADMIN_ENDPOINTS=true` (default outside production) **and**
   supply the shared JWT configuration (`JWT_SECRET_KEY` or `JWT_PUBLIC_KEY` plus `JWT_ISSUER`/`JWT_AUDIENCE`).
2. Issue Identity Service tokens that include `roles: ["admin", …]` (future work may add fine-grained permissions).
3. Expose `/admin/v1/**` through the API Gateway or a secure tunnel—these routes are not meant for public traffic.

### Observability

- Metric: `cj_admin_instruction_operations_total{operation,status}` increments on every CRUD call.
  - Example success panel: `sum(rate(cj_admin_instruction_operations_total{status="success"}[5m])) by (operation)`
  - Example failure alert: fire if `sum(rate(cj_admin_instruction_operations_total{status="failure"}[5m])) > 0.05`
- Logs: structured via Rule 048 factories. Find auth failures with
  `{service="cj_assessment_service"} | json | request_path="/admin/v1/assessment-instructions"`
- Traces: every request carries `CorrelationContext.uuid` so you can stitch admin activity to downstream anchor/grade actions.

Examples:

```bash
# Obtain a token interactively (stores access + refresh tokens locally)
pdm run cj-admin login --email ops@example.com

# Create ENG5 NP instructions for a specific assignment
pdm run cj-admin instructions create \
  --assignment-id 11111111-1111-1111-1111-111111111111 \
  --grade-scale eng5_np_legacy_9_step \
  --instructions-file \
    test_uploads/ANCHOR\ ESSAYS/ROLE_MODELS_ENG5_NP_2016/eng5_np_vt_2017_essay_instruction.md

# List ENG5 NP instructions
pdm run cj-admin instructions list --grade-scale eng5_np_legacy_9_step
```

## LLM Configuration & Dynamic Overrides

### Multi-Provider Support

The service supports multiple LLM providers with configurable defaults:

- **OpenAI**: GPT models via OpenAI API
- **Anthropic**: Claude models via Anthropic API  
- **Google**: Gemini models via Google AI API
- **OpenRouter**: Various models via OpenRouter proxy

### Configuration Hierarchy

LLM parameters follow a three-level fallback hierarchy:

1. **Runtime Overrides**: Via `llm_config_overrides` in event data (highest priority)
2. **Provider Defaults**: Configured per-provider in settings
3. **Global Defaults**: System-wide fallback values

### Supported Override Parameters

```python
class LLMConfigOverrides(BaseModel):
    model_override: Optional[str] = None           # e.g., "gpt-4o", "claude-3-haiku"
    temperature_override: Optional[float] = None   # 0.0-2.0
    max_tokens_override: Optional[int] = None      # Positive integer
    provider_override: Optional[str] = None        # "openai", "anthropic", etc.
```

### Usage Example

```json
{
  "llm_config_overrides": {
    "model_override": "gpt-4o",
    "temperature_override": 0.3,
    "max_tokens_override": 2000,
    "provider_override": "openai"
  }
}
```

## Event Architecture

### Events Consumed

- **`ELS_CJAssessmentRequestV1`**: Incoming requests from Essay Lifecycle Service containing:
  - BOS batch reference (`entity_ref`)
  - List of essays for CJ assessment (`essays_for_cj`)
  - Assessment metadata (language, `course_code`, and prompt metadata from Content Service references)
  - Optional `student_prompt_ref` (Content Service reference hydrated locally before comparisons)
  - Optional `llm_config_overrides` for runtime LLM parameter customization

### Events Produced

- **`CJAssessmentCompletedV1`**: Successful completion events containing:
  - Final essay rankings with Bradley-Terry scores
  - CJ assessment job reference
  - Processing metadata (total comparisons, convergence status)

- **`CJAssessmentFailedV1`**: Failure events with error information and context

## Configuration

### Key Environment Variables (prefix: `CJ_ASSESSMENT_SERVICE_`)

```bash
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
CJ_ASSESSMENT_REQUEST_TOPIC=huleedu.els.cj_assessment.requested.v1
CJ_ASSESSMENT_COMPLETED_TOPIC=huleedu.cj_assessment.completed.v1
CJ_ASSESSMENT_FAILED_TOPIC=huleedu.cj_assessment.failed.v1

# External Services
CONTENT_SERVICE_URL=http://localhost:8002
LLM_PROVIDER_SERVICE_URL=http://llm_provider_service:8090/api/v1
DATABASE_URL_CJ=sqlite+aiosqlite:///./cj_assessment.db

# LLM Queue Polling Configuration
LLM_QUEUE_POLLING_ENABLED=true                    # Enable queue polling for 202 responses
LLM_QUEUE_POLLING_INITIAL_DELAY_SECONDS=2.0       # Initial delay before first poll
LLM_QUEUE_POLLING_MAX_DELAY_SECONDS=60.0          # Maximum delay between polls
LLM_QUEUE_POLLING_EXPONENTIAL_BASE=1.5            # Backoff multiplier
LLM_QUEUE_POLLING_MAX_ATTEMPTS=30                 # Maximum polling attempts
LLM_QUEUE_TOTAL_TIMEOUT_SECONDS=900               # Total timeout (15 minutes)

# LLM Provider API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# CJ Assessment Parameters
MAX_PAIRWISE_COMPARISONS=1000
SCORE_STABILITY_THRESHOLD=0.05
COMPARISONS_PER_STABILITY_CHECK_ITERATION=10

# HTTP API Configuration 
METRICS_PORT=9090          # Port for health and metrics endpoints

# LLM Configuration Overrides Support
# Default models and parameters can be overridden per-request via event data

# Observability
LOG_LEVEL=INFO
```

## Database Schema

### Core Tables

#### `cj_batch_uploads`

- **Purpose**: Tracks CJ assessment batches linked to BOS batches
- **Key Fields**:
  - `id` (int, PK): Internal CJ batch identifier
  - `bos_batch_id` (str): Reference to originating BOS batch
  - `status` (enum): Current processing state
  - `expected_essay_count` (int): Number of essays to process
  - `processing_metadata`: Includes `student_prompt_storage_id` and optional `student_prompt_text` populated after hydration
  - `processing_metadata`: Includes `student_prompt_storage_id` and a boolean `student_prompt_text_present` to signal successful prompt retrieval

#### `cj_processed_essays`

- **Purpose**: Individual essays prepared for CJ assessment
- **Key Fields**:
  - `els_essay_id` (str, PK): ELS essay identifier (string UUID)
  - `cj_batch_id` (int, FK): Reference to CJ batch
  - `assessment_input_text` (text): Spellchecked essay content
  - `current_bt_score` (float): Bradley-Terry score from comparisons

#### `cj_comparison_pairs`

- **Purpose**: Records of LLM-based pairwise comparisons
- **Key Fields**:
  - `essay_a_els_id` (str, FK): First essay in comparison
  - `essay_b_els_id` (str, FK): Second essay in comparison  
  - `winner` (str): Comparison result ("essay_a", "essay_b", "error")
  - `confidence` (float): LLM confidence rating (1-5)
  - `from_cache` (bool): Whether result came from cache

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

## Local Development

### Prerequisites

- Python 3.11+
- PDM for dependency management
- Kafka cluster (or Docker Compose setup)
- Access to Content Service

### Setup

```bash
# Install dependencies
pdm install

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run the complete service (HTTP API + Kafka worker)
pdm run start_service

# Or run components separately:
pdm run start_worker      # Kafka worker only
pdm run start_health_api  # HTTP API only
```

### Testing

```bash
# Run unit tests
pdm run pytest

# Run tests with coverage
pdm run pytest --cov=. --cov-report=html

# Run specific test modules
pdm run pytest tests/test_core_assessment_logic.py -v
```

### Development Workflow

1. **Protocol-First Development**: Define behavioral contracts in `protocols.py`
2. **Implementation**: Create concrete implementations in `implementations/`
3. **Dependency Injection**: Wire dependencies in `di.py`
4. **Testing**: Mock protocols for isolated unit testing

### Key Development Commands

```bash
# Format code
pdm run ruff format .

# Lint code
pdm run ruff check .

# Type checking
pdm run mypy .

# Run complete service locally
pdm run python run_service.py

# Run only Kafka worker 
pdm run python worker_main.py

# Run only health API
pdm run python app.py
```

## Monitoring and Observability

### HTTP Endpoints

- **`GET /healthz`**: Service health check endpoint
- **`GET /metrics`**: Prometheus metrics in OpenMetrics format

### Observability Features

- **Metrics**: Prometheus metrics exposed on configured `METRICS_PORT` (default: 9090)
  - `huleedu_cj_prompt_fetch_failures_total{reason}` tracks prompt hydration failures (Content Service errors, missing refs, legacy fallbacks)
  - Existing counters/histograms for CJ workflow throughput, callbacks, retries, and circuit breakers remain unchanged
- **Logging**: Structured logging via `huleedu_service_libs.logging_utils`
- **Health Checks**: Service responsiveness (extensible to database/Kafka connectivity)
- **Correlation IDs**: Full request tracing across service boundaries

### Circuit Breaker Metrics

Circuit breaker observability is integrated through the service's metrics endpoint:

- **`circuit_breaker_state`**: Current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) with labels: `service`, `circuit_name`
- **`circuit_breaker_state_changes`**: State transition counter with labels: `service`, `circuit_name`, `from_state`, `to_state`
- **`circuit_breaker_calls_total`**: Call result counter with labels: `service`, `circuit_name`, `result` (success/failure/blocked)

Circuit breakers protect Kafka publishing operations when enabled via `CIRCUIT_BREAKER_ENABLED=true`.

### Docker Health Checks

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9090/healthz || exit 1
```

## Integration Points

### Upstream Dependencies

- **Essay Lifecycle Service**: Publishes CJ assessment requests (with optional `student_prompt_ref`)
- **Content Service**: Provides spellchecked essay content and hydrated student prompt text/storage references via HTTP

### Downstream Consumers

- **Batch Orchestrator Service**: Consumes completion/failure events
- **Future Query Services**: Can use `cj_assessment_job_id` for detailed result queries

## Future Enhancements

- **HTTP Query API**: RESTful interface for CJ result queries
- **Advanced Scoring Models**: Beyond Bradley-Terry (e.g., Plackett-Luce)
- **Multi-Language Support**: Localized assessment prompts
- **Real-time Progress**: WebSocket updates for long-running assessments
