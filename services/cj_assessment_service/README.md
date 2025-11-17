# CJ Assessment Service

## Overview

The CJ Assessment Service is a microservice dedicated to performing Comparative Judgment (CJ) assessment of essays using Large Language Model (LLM) based pairwise comparisons. The service consumes spellchecked essay texts and produces Bradley-Terry scores and rankings through iterative LLM-driven comparisons.

## Architecture

### Service Type

- **Pattern**: Hybrid Kafka Worker + HTTP API Service
- **Framework**: Quart (HTTP API) + Direct `asyncio` and `aiokafka` for message processing
- **Dependency Injection**: Dishka framework for clean architecture
- **DI Initialization Order**: `QuartDishka(app, container)` is invoked *before* Blueprint registration to satisfy Dishka route injection requirements (see `app.py`)
- **Concurrency**: Both HTTP API and Kafka worker run concurrently inside `app.py` via Quart lifecycle hooks

### Key Internal Modules

- **`core_logic/`**: Core business logic package containing:
  - **`core_assessment_logic.py`**: Orchestrates the complete CJ workflow from request processing to result publication
  - **`pair_generation.py`**: Generates comparison tasks for iterative CJ assessment
  - **`scoring_ranking.py`**: Handles Bradley-Terry scoring using the `choix` library and ranking calculations
- **`protocols.py`**: Defines behavioral contracts using `typing.Protocol` for all major dependencies
- **`implementations/`**: Concrete implementations of all protocols (database, LLM providers, event publishing, content fetching)
- **`event_processor.py`**: Processes individual Kafka messages, hydrates `student_prompt_ref` via Content Service, records `huleedu_cj_prompt_fetch_failures_total{reason}` on failures, and delegates to core workflow
- **`worker_main.py`**: Kafka consumer lifecycle management and message processing
- **`app.py`**: Integrated Quart application that exposes health/metrics and starts the Kafka workflow via `before_serving`
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

👉  For the full ENG5 NP batch-run procedure (plan/dry-run/execute, monitoring,
and failure handling) follow `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md`.

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

Phase 3.2 introduced an authenticated admin surface for managing
`assessment_instructions`, and Phase 8 extends the surface to cover student
prompt storage references end-to-end:

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
  automation, exposes `instructions create|list|get|delete`, `scales list`, and
  provides a non-interactive token helper `pdm run cj-admin token issue` (reads
  `CJ_ADMIN_EMAIL`/`CJ_ADMIN_PASSWORD` or accepts `--email/--password`).
- **ENG5 NP Dev Runner**: `scripts/cj_experiments_runners/eng5_np` can self-mint
  admin tokens for local development (production runs require
  `HULEEDU_SERVICE_ACCOUNT_TOKEN`). See `scripts/cj_experiments_runners/eng5_np/AUTH.md`.

### Student Prompt Management

- **Storage-by-reference**: `student_prompt_storage_id` lives on
  `assessment_instructions`. Prompt text itself is persisted by the Content
  Service; CJ only stores and propagates the storage reference.
- **Upload workflow**: `POST /admin/v1/student-prompts` validates that the target
  instruction exists, streams prompt text to Content Service via
  `ContentClientProtocol.store_content()`, and re-upserts the instruction while
  preserving grade scale and judge instructions metadata.
- **Retrieval workflow**: `GET /admin/v1/student-prompts/assignment/{assignment_id}`
  emits the authoritative prompt text and storage reference directly from the
  Content Service while echoing the judge instructions metadata for UI review.
- **CLI commands**: `pdm run cj-admin prompts upload` accepts either an inline
  prompt or file path, performs xor validation, and mirrors the API response.
  `pdm run cj-admin prompts get` fetches the same payload and optionally writes
  it to disk. `pdm run cj-admin instructions create` can upload a prompt inline
  during instruction creation via the shared helper.
- **Batch integration**: `cj_core_logic/batch_preparation.py` auto-hydrates
  `student_prompt_storage_id` whenever an assignment-scoped instruction supplies
  one and the incoming request omits the field. The existing Content Service
  hydration metric `huleedu_cj_prompt_fetch_failures_total{reason}` remains the
  observability signal for downstream prompt fetch errors.
- **Auditability**: Structured logs on both endpoints include
  `assignment_id`, `student_prompt_storage_id`, `correlation_id`, and
  `admin_user` (Identity `sub`).

### Admin API Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/admin/v1/assessment-instructions` | Create or update instructions for an assignment or course (body mirrors `AssessmentInstructionUpsertRequest`) |
| `GET` | `/admin/v1/assessment-instructions` | Paginated list with optional `grade_scale` filter |
| `GET` | `/admin/v1/assessment-instructions/assignment/{assignment_id}` | Fetch the latest instructions for an assignment |
| `DELETE` | `/admin/v1/assessment-instructions/assignment/{assignment_id}` | Remove assignment-scoped instructions |
| `DELETE` | `/admin/v1/assessment-instructions/course/{course_id}` | Remove course fallback instructions |
| `POST` | `/admin/v1/student-prompts` | Upload prompt text to Content Service and attach resulting storage ID to an existing assignment instruction |
| `GET` | `/admin/v1/student-prompts/assignment/{assignment_id}` | Fetch hydrated prompt metadata (storage ID + prompt text + instructions context) for an assignment |

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

### Metadata & Budget Semantics

- `comparison_budget.source` captures whether the runner set a hard limit (`"runner_override"`) or the service fell back to `MAX_PAIRWISE_COMPARISONS` (`"service_default"`); only runner overrides persist `max_comparisons_override`, and continuations rehydrate that value from `OriginalCJRequestMetadata` so analytics never infer budgets from `max_pairs_cap`.
- All metadata writes (batch-level or essay-level) must use the merge helpers in `cj_core_logic/batch_submission.py` rather than assigning `processing_metadata = {...}` so existing flags like `original_request`, `comparison_budget`, or anchor diagnostics are preserved.
- Anchor metadata in `cj_processed_essays.processing_metadata` is layered through `merge_essay_processing_metadata` and always includes `is_anchor: true`, any authored `known_grade`, `anchor_ref_id`, and, when available, the runner-submitted `anchor_grade` so the grade projector can apply the 4-tier fallback (ranking `anchor_grade` → essay `known_grade` → `text_storage_id` matches → `anchor_ref_id` matches).
- Continuations reuse the stored `OriginalCJRequestMetadata` snapshot from `cj_batch_states.processing_metadata` to preserve identity fields (`assignment_id`, `course_code`, `language`, `user_id`), `llm_config_overrides`, `batch_config_overrides`, and the `comparison_budget` payload without deriving overrides from `max_pairs_cap`.

Examples:

```bash
# Obtain a token interactively (stores access + refresh tokens locally)
pdm run cj-admin login --email ops@example.com

# Issue token non-interactively (reads env vars, caches JWT)
export CJ_ADMIN_EMAIL=ops@example.com
export CJ_ADMIN_PASSWORD=dev-password
pdm run cj-admin token issue

# Create ENG5 NP instructions for a specific assignment
pdm run cj-admin instructions create \
  --assignment-id 11111111-1111-1111-1111-111111111111 \
  --grade-scale eng5_np_legacy_9_step \
  --instructions-file \
    test_uploads/ANCHOR\ ESSAYS/ROLE_MODELS_ENG5_NP_2016/eng5_np_vt_2017_essay_instruction.md

# List ENG5 NP instructions
pdm run cj-admin instructions list --grade-scale eng5_np_legacy_9_step

# Upload a student prompt from file and verify hydration
pdm run cj-admin prompts upload \
  assignment-id 11111111-1111-1111-1111-111111111111 \
  --prompt-file documentation/prompts/eng5_np_prompt.md
pdm run cj-admin prompts get 11111111-1111-1111-1111-111111111111 --output-file ./prompt.md
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
    system_prompt_override: Optional[str] = None   # Caller-supplied system instructions
```

### Usage Example

```json
{
  "llm_config_overrides": {
    "model_override": "gpt-4o",
    "temperature_override": 0.3,
    "max_tokens_override": 2000,
    "provider_override": "openai",
    "system_prompt_override": "You are an impartial Comparative Judgement assessor..."
  }
}
```

## CJ ↔ LLM Provider Contract

The CJ service treats `libs/common_core/src/common_core/events/cj_assessment_events.py::ELS_CJAssessmentRequestV1`
and `libs/common_core/src/common_core/events/llm_provider_events.py::LLMComparisonResultV1`
as the canonical request/response boundary. The following invariants are now
documented and locked down with unit tests (`tests/unit/test_llm_metadata_adapter.py`,
`tests/unit/test_llm_interaction_impl_unit.py`, and `tests/unit/test_llm_callback_processing.py`):

| Field | Source of Truth | Required? | Purpose |
|-------|-----------------|-----------|---------|
| `request_id` | `QueuedRequest.queue_id` (LPS) | ✅ | 1:1 mapping between queued items and callbacks |
| `correlation_id` | CJ per-comparison UUID | ✅ | Links callbacks to CJ comparison rows |
| `request_metadata.essay_a_id` | `CJLLMComparisonMetadata` | ✅ | Correlates results to essay A |
| `request_metadata.essay_b_id` | `CJLLMComparisonMetadata` | ✅ | Correlates results to essay B |
| `request_metadata.bos_batch_id` | `CJLLMComparisonMetadata` | Optional | BOS/ELS batch identifier when available |
| `request_metadata.prompt_sha256` | LPS queue processor | Optional | Deterministic hash of rendered prompt for replay/debug |
| `request_metadata.cj_llm_batching_mode` | `CJLLMComparisonMetadata` | Optional hint | Emitted when `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`; records `per_request`, `serial_bundle`, or `provider_batch_api`. |
| `request_metadata.comparison_iteration` | `CJLLMComparisonMetadata` | Optional hint | Emitted only when metadata hints **and** the iterative batching loop are enabled; carries the zero-based iteration index used by the stability-driven bundling loop. |

### Metadata construction

- `ComparisonTask` objects feed `CJLLMComparisonMetadata`, the typed adapter that
  serializes metadata into the `LLMComparisonRequest.metadata` dict. The adapter
  enforces the required keys and only emits optional fields when explicitly set,
  keeping the contract additive-only.
- Future batching flags (e.g., `cj_llm_batching_mode`, `comparison_iteration`) are added
  via `CJLLMComparisonMetadata.with_additional_context(...)` so new keys never
  mutate legacy ones. Once the iterative batching loop is online, CJ passes the
  zero-based iteration counter through this helper so callbacks can correlate
  Bradley–Terry recomputations with the originating bundle.

### Callback expectations

- The LLM Provider Service **echoes** the metadata dictionary it receives and only
  appends additive keys (`prompt_sha256`). Tests under
  `services/llm_provider_service/tests/unit/test_callback_publishing.py`
  verify the success and error paths preserve CJ metadata.
- Every queued request produces exactly one callback: `_publish_callback_event*`
  always uses the queue id for `request_id` and removes the queue entry once the
  callback is published, which is exercised by the queue processor integration tests.

This contract ensures that the future batching modes can introduce new metadata fields
without breaking existing CJ or ENG5 consumers while guaranteeing the identifiers
needed for correlation remain present.

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

# LLM Batching Configuration
CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=per_request
CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=false
CJ_ASSESSMENT_SERVICE_ENABLE_ITERATIVE_BATCHING_LOOP=false

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

`CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE` mirrors
`LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE`. `per_request` preserves the current
one-at-a-time behaviour, while `serial_bundle` causes CJ to label requests for the
batch path (still single-item bundles for now) so the queue processor can call
`process_comparison_batch`. `provider_batch_api` is wired end-to-end but behaves
like `serial_bundle` until the provider-native batching work lands. When
`CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS` is `true`, every
`LLMComparisonRequest.metadata` payload gains `cj_llm_batching_mode`. Flip
`CJ_ASSESSMENT_SERVICE_ENABLE_ITERATIVE_BATCHING_LOOP` to `true` once the
stability-driven loop is actually running (serial bundling enabled, `MAX_ITERATIONS > 1`,
and `COMPARISONS_PER_STABILITY_CHECK_ITERATION > 1`). With both flags enabled the
adapter also emits `comparison_iteration`, giving downstream services iteration
numbers alongside the batching mode. Callbacks echo the metadata verbatim, so the
flags are safe to toggle provided consumers tolerate additive keys.

The iterative loop is considered **online** only when all of the following are true:

- `CJ_ASSESSMENT_SERVICE_ENABLE_ITERATIVE_BATCHING_LOOP=true`
- `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE != per_request`
- `COMPARISONS_PER_STABILITY_CHECK_ITERATION > 1` and `MIN_COMPARISONS_FOR_STABILITY_CHECK > 0`
- `MAX_ITERATIONS > 1`

In that state CJ adds `comparison_iteration` to the metadata whenever
`CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`; otherwise the field
is omitted.

`COMPARISONS_PER_STABILITY_CHECK_ITERATION` defines the number of new pairs generated per stability iteration; `MAX_PAIRWISE_COMPARISONS` is an absolute guardrail on the batch. Both values are applied directly by `pair_generation.generate_comparison_tasks`, so adjust them via environment variables rather than hard-coding limits elsewhere.

## Database Schema

### Core Tables

#### `cj_batch_uploads`

- **Purpose**: Tracks CJ assessment batches linked to BOS batches
- **Key Fields**:
  - `id` (int, PK): Internal CJ batch identifier
  - `bos_batch_id` (str): Reference to originating BOS batch
  - `status` (enum): Current processing state
  - `expected_essay_count` (int): Number of essays to process
  - `processing_metadata`: Includes `student_prompt_storage_id` / `student_prompt_text` from hydration **and** an `original_request` snapshot capturing the runner payload (language, overrides, identity). Writes use merge helpers so later updates (e.g., diagnostics) never clobber previously persisted prompt or request context.

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

#### `cj_batch_states`

- **Purpose**: Tracks live workflow progress, retry pools, and continuation budgets per batch
- **Key Fields**:
  - `processing_metadata`: Stores `comparison_budget`, `config_overrides`, optional `llm_overrides`, and the canonical `original_request` snapshot copied from `cj_batch_uploads`. Continuation logic rehydrates `CJAssessmentRequestData` directly from this payload, so all writers must call the merge helpers in `cj_core_logic.batch_submission` instead of reassigning JSON blobs.

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
pdm run start

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
  - `huleedu_cj_prompt_fetch_success_total` counts successful student prompt hydrations across event processing and batch preparation
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
