# HuleEdu Monorepo - README FIRST

## Purpose & Scope

HuleEdu is an educational assessment platform that processes student essays through multiple AI-driven pipelines (spellcheck, NLP analysis, CJ assessment, AI feedback).

## Key Services

1. **API Gateway** (FastAPI) - External API, JWT auth, rate limiting
2. **Batch Orchestrator (BOS)** - Pipeline coordination, phase initiation
3. **Batch Conductor (BCS)** - Pipeline resolution, dependency management
4. **Essay Lifecycle (ELS)** - Phase outcome tracking, state management
5. **Class Management** - Student/batch associations
6. **Content Service** - Essay content storage
7. **File Service** - File upload/processing
8. **Spellchecker** - Grammar/spelling validation
9. **CJ Assessment** - Comparative judgment evaluation
10. **LLM Provider** - LLM integration abstraction layer
11. **Result Aggregator (RAS)** - Results compilation
12. **Entitlements** - Credit management

## Quick Start

### Prerequisites

- Docker & Docker Compose v2
- Python 3.11
- PDM package manager

### Development Commands

```bash
# Start all services (development mode with hot-reload)
pdm run dev-build-start

# Restart specific service
pdm run dev-restart [service]

# View logs
pdm run dev-logs [service]

# Code quality
pdm run typecheck-all
pdm run lint
pdm run format-all

# Run tests
pdm run pytest-root services/<service>/tests/
pdm run pytest-root tests/integration/  # Cross-service tests
```

### Hot-Reload Development

All services use automatic code reload in development:
- **Quart services** (11): `hypercorn --reload`
- **FastAPI services** (2): `uvicorn --reload`

Changes to `.py` files trigger automatic restart (~9-11 seconds). No manual rebuild needed.

## Critical Development Info

### CJ Assessment & LLM Provider Integration

**Status (2025-11-17)**: Production-ready with serial bundle infrastructure

#### HTTP API Contracts (common_core.api_models.llm_provider)
- `LLMConfigOverridesHTTP` - Strict enum-based config for HTTP validation
- `LLMComparisonRequest` - Comparison request with callback topic
- `LLMComparisonResponse` - Comparison result with metrics
- `LLMQueuedResponse` - Async queue acknowledgment

**Import Pattern**: Always use `from common_core import LLMConfigOverridesHTTP`

#### Metadata Contract (CJ ↔ LPS)

**Required Fields** (must be preserved through round-trip):
- `essay_a_id`, `essay_b_id` - Essay identifiers
- `bos_batch_id` - Batch tracking (optional but preserved if present)
- `correlation_id` - Distributed tracing

**Additive Fields** (LPS adds, CJ preserves):
- `prompt_sha256` - Prompt hash for deduplication
- `cj_llm_batching_mode` - Batching hint (when `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`)
- `comparison_iteration` - Stability loop iteration (when iterative batching enabled)

**Validation**: See `tests/integration/test_cj_lps_metadata_roundtrip.py`

#### LLM Batching Configuration

**CJ Assessment Service**:
```bash
CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=per_request  # or serial_bundle
CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=false  # emit cj_llm_batching_mode
CJ_ASSESSMENT_SERVICE_ENABLE_ITERATIVE_BATCHING_LOOP=false  # emit comparison_iteration
```

**LLM Provider Service**:
```bash
LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=per_request  # or serial_bundle
```

**Observability**: Queue metrics available via Prometheus:
- `llm_provider_queue_depth` - Current queue size
- `llm_provider_queue_wait_time_seconds` - Request wait time
- `llm_provider_comparison_callbacks_total` - Callback success/failure

### ENG5 Runner

**Location**: `scripts/cj_experiments_runners/eng5_np/cli.py`

**Modes**:
- `plan` - Inspect dataset without processing
- `dry-run` - Generate artefact stubs (no Kafka)
- `execute` - Full pipeline with optional `--await-completion`

**LLM Overrides**:
```bash
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --mode execute \
  --assignment-id <uuid> \
  --llm-provider anthropic \
  --llm-model claude-3-5-sonnet-20241022 \
  --llm-temperature 0.3
```

**Validation**: All artefacts are schema-compliant (see `Documentation/schemas/eng5_np/`)

### Bayesian Consensus Model

**Location**: `scripts/bayesian_consensus_model/`

**Key Features**:
- Ordinal kernel with feature flags (argmax, leave-one-out, precision-aware weighting)
- D-optimal pair scheduling with Fisher information maximization
- Rater bias estimation with empirical Bayes
- Continuation-aware design (baseline comparisons locked across sessions)

**CLI**: `python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs`
**TUI**: `python -m scripts.bayesian_consensus_model.redistribute_tui`

### Phase 3: Grade Projection Data Pipeline (Ongoing)

**Purpose**: Generate high-quality CJ comparison data to train and validate the Bayesian grade projection model for accurate student essay grading.

**Status** (2025-11-17):
- ✅ Phase 3.1: Grade scale foundations (Swedish + ENG5 NP scales, anchor filtering)
- ✅ Phase 3.2: Service integration (admin endpoints, JWT auth, CLI tooling)
- 🔄 Phase 3.3: Batch tooling & data capture (ENG5 runner validation, artefact schema)

**Workflow**: ENG5 Runner → CJ Comparisons → BT-Scores → Grade Projections → Validation

#### Grade Projection Mechanism

**4-Tier Anchor Grade Fallback** (`grade_projector.py`):
1. Direct `anchor_grade` field in anchor dict or metadata
2. `known_grade` in processing_metadata
3. Lookup by `text_storage_id` in anchor references
4. Lookup by `anchor_ref_id` in anchor references

**Technical Stack**:
- **BT-Score Calculation**: choix.ilsr_pairwise with alpha=0.01 regularization, mean-centered
- **Standard Errors**: Fisher Information matrix via Moore-Penrose pseudoinverse
- **Grade Projection**: Gaussian mixture calibration with resolved anchor grades
- **Storage**: Anchors (known grades) and students (projected grades) separated by design

#### Validation Results (Batch a93253f7)

| Metric | Pre-Fix | Post-Fix | Status |
|--------|---------|----------|--------|
| Grade Projections | 0 | 12 | ✅ Fixed |
| BT-Scores Computed | 24/24 | 24/24 | ✅ Preserved |
| Anchor Grades Resolved | 0/12 | 12/12 | ✅ Fixed |
| Comparison Pairs | 100 | 100 | ✅ Stable |

**Current Focus**:
- Finalizing JSON artefact schema (`Documentation/schemas/eng5_np/assessment_run.schema.json`)
- Validating ENG5 runner execute mode with full observability
- Preparing reproducible research bundles for empirical validation

**Reference**: See `TASKS/phase3_cj_confidence/PHASE3_CJ_CONFIDENCE_HUB.md` for complete task breakdown and `TASKS/phase3_cj_confidence/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md` for implementation details.

## Architecture Decisions

### 1. Hot-Reload Standardization (Nov 2025)

All Quart services use Hypercorn directly for dev/prod parity:
```bash
python -m hypercorn services.<name>.app:app --bind 0.0.0.0:<port> --worker-class asyncio --reload
```

### 2. HTTP API Contracts in common_core (Nov 2025)

**Rule**: Services communicate via published contracts only - never import internal implementations.

**Violation Example** (forbidden):
```python
from services.llm_provider_service.api_models import LLMComparisonRequest  # ❌
```

**Correct Pattern**:
```python
from common_core import LLMComparisonRequest  # ✅
```

**Validation**: `grep -r "from services\." services/ --include="*.py"` must return zero cross-service imports.

### 3. Integration Test Organization (Nov 2025)

**Service Tests** (`services/<name>/tests/`):
- Unit tests: Mock all external dependencies
- Integration tests: May use Docker services but NO cross-service imports

**Root Tests** (`tests/integration/`):
- Cross-service contract validation
- Use real HTTP/Kafka boundaries only
- Require services running (`@pytest.mark.integration`, `@pytest.mark.docker`)

### 4. Database URL Centralization (Nov 2025)

**Pattern**: `build_database_url()` utility with service-specific overrides

**Phase 1 Complete**: Identity service migrated (1/12 services)
**Next**: Batch migration of remaining services

### 5. Prompt Reference Architecture (Nov 2025)

**Contract**: All services use Content Service storage IDs for prompts
- CJ Assessment: `student_prompt_storage_id` in instructions table
- NLP Service: Hydrates via Content Service with fallback
- Result Aggregator: Consumes from event metadata

**Metrics**: Monitor `huleedu_{cj|nlp}_prompt_fetch_failures_total{reason}`

## Configuration Files

- `.env` - Environment variables (not in git)
- `pyproject.toml` - PDM dependencies and scripts
- `docker-compose.yml` - Production config
- `docker-compose.dev.yml` - Development overrides with hot-reload
- `.claude/rules/` - Development standards and patterns
- `CLAUDE.md` - Detailed technical reference

## Common Issues

### Container Build/Start

```bash
# Rebuild specific service
pdm run dev-build [service]

# Force recreation (picks up env var changes)
pdm run dev-recreate [service]

# Check logs for startup errors
pdm run dev-logs [service]
```

### Database Access

```bash
# Source .env first (required for credentials)
source .env

# Access database
docker exec huleedu_<service>_db psql -U "$HULEEDU_DB_USER" -d <db_name>

# Database names follow pattern: huleedu_<service_name>
```

### Test Failures

```bash
# Ensure services are running for integration tests
docker ps | grep huleedu

# Check service health
curl http://localhost:<port>/healthz

# View service logs
pdm run dev-logs [service]
```
