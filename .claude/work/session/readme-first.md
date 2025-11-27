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
pdm run format-all
pdm run lint-fix --unsafe-fixes

# Run tests
pdm run pytest-root services/<service>/tests/
pdm run pytest-root tests/integration/  # Cross-service tests
```

## CJ Assessment POC Validation (Sprint Focus)

### Validation Objectives
1. Anchor creation system (human-AI interface) using Bayesian model
2. ENG5 Runner validation with full observability
3. Serial bundle batching mode for cost efficiency
4. Main pipeline compatibility (BOS → ELS → RAS) preserved

### Critical Fixes Applied (2025-11-19 to 2025-11-23)
- ✅ **Batch state tracking**: `total_budget` field, cumulative counters across iterations
- ✅ **Completion logic**: Stability-first, denominator capping (min(budget, nC2))
- ✅ **Error exclusion**: Only valid comparisons count toward completion threshold
- ✅ **Position randomization**: Eliminates 86% anchor bias → ~50% balanced distribution
- ✅ **API failure diagnostics**: Prometheus metrics + detailed HTTP status/error classification
- ✅ **2025-11-24**: Callback persistence and batch completion policies now call `CJRepositoryProtocol` (`get_comparison_pair_by_correlation_id`, `get_batch_state`) instead of raw `AsyncSession` selects; unit tests updated to AsyncMock sessions to drop casts/monkeypatching.

### Validation Status
- **ENG5 Runner**: Execute mode operational, persistent logs at `.claude/research/data/eng5_np_2016/logs/eng5-{batch_id}-{timestamp}.log`
- **Grade Projections**: 12/12 anchor grades resolved, BT-scores valid (no degenerate values)
- **Serial Bundle**: Infrastructure complete (Phases 1-3), awaiting production rollout validation
- **Main Pipeline**: BOS → ELS → RAS flow preserved, no breaking changes
- **Completion Logic**: Stability-first mode active (callbacks trigger scoring immediately, BatchMonitor is recovery-only)
- **Cost Safety**: Default `MAX_PAIRWISE_COMPARISONS` reduced to 150 (per-request overrides honored)

### Result Surface for ENG5 Validation (RAS as Source of Truth)
- **Source of Truth**: Result Aggregator Service (RAS) is the authoritative surface for CJ assessment outputs (including ENG5 validation runs), not the CJ service database.
- **Assignment Context**: `assignment_id` now propagates end-to-end from client → BOS → ELS → CJ → RAS; RAS persists it on `BatchResult.assignment_id` and exposes it via `BatchStatusResponse.assignment_id`.
- **Filename + BT-score Mapping**: For GUEST flows where no student IDs are present, use RAS’ `/internal/v1/batches/{batch_id}/status` API (or the `batch_results`/`essay_results` tables) to join essay-level CJ results (`cj_rank`, `cj_score`) with `filename`. CJ’s internal tables (`cj_processed_essays`, `cj_comparison_pairs`) are implementation details and MUST NOT be used as reporting sources.
- **Functional Guardrail**: `tests/functional/test_e2e_cj_assessment_workflows.py::TestE2ECJAssessmentWorkflows::test_complete_cj_assessment_processing_pipeline` asserts the full `assignment_id` round-trip via RAS to keep ENG5 validation aligned with the production result surface.

### Next Steps
- [ ] Complete serial bundle production validation
- [ ] Finalize ENG5 JSON artefact schema (`Documentation/schemas/eng5_np/assessment_run.schema.json`)
- [ ] Prepare reproducible research bundles for empirical validation

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
- `cj_batch_id`, `cj_source`, `cj_request_type` - emitted by CJ for every request so retries and ENG5 tooling can correlate callbacks with CJ batches and upstream workflows without scraping logs.
- Prompt cache usage (when available): `cache_read_input_tokens`, `cache_creation_input_tokens`, and raw `usage` dict are appended by LPS without overwriting caller metadata.

**Validation**: See `tests/integration/test_cj_lps_metadata_roundtrip.py`

#### LLM Batching Configuration

**CJ Assessment Service**:
```bash
CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=per_request  # or serial_bundle
CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=false  # emit cj_llm_batching_mode
CJ_ASSESSMENT_SERVICE_ENABLE_ITERATIVE_BATCHING_LOOP=false  # emit comparison_iteration
CJ_ASSESSMENT_SERVICE_LLM_BATCH_API_ALLOWED_PROVIDERS="openai,anthropic"  # guardrail provider_batch_api fallback
```

`batch_config_overrides` now accepts `llm_batching_mode_override`, enabling ENG5 runner and admin tooling to request `per_request`, `serial_bundle`, or `provider_batch_api` per batch. CJ enforces `LLM_BATCH_API_ALLOWED_PROVIDERS` when resolving the effective mode and downgrades automatically when the provider is not approved.

**LLM Provider Service**:
```bash
LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=per_request  # QueueProcessingMode: per_request|serial_bundle|batch_api
LLM_PROVIDER_SERVICE_SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL=8  # clamp to 1-64
LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled  # BatchApiMode: disabled|nightly|opportunistic
```
The new enums live inside LPS so CJ's `LLMBatchingMode` remains an external hint. Serial bundling is now active when non-`per_request` modes are enabled: the queue processor drains compatible requests (same provider/model + optional CJ hint) up to the configured per-call limit and processes them in a single queue-loop iteration.

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
  --llm-model claude-sonnet-4-5-20250929 \
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
- Hardening CJ batch throughput before serial_bundle rollout: total_budget tracking + denominator-aware completion logic merged (tests: `test_batch_state_tracking.py`, `test_completion_threshold.py`; commands: `pdm run format-all`, `pdm run lint-fix --unsafe-fixes`, `pdm run typecheck-all`).
- Eliminating CJ pair-position bias: per-pair randomization + optional `CJ_ASSESSMENT_SERVICE_PAIR_GENERATION_SEED` shipped with `test_pair_generation_randomization.py` guarding deterministic + statistical behavior.
- **2025-11-19**: Batch-state locking regression fixed by routing `_update_batch_state_with_totals()` through `get_batch_state(..., for_update=True)`; new unit test `TestBatchProcessor.test_update_batch_state_with_totals_uses_locked_fetch` plus `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_processor.py` + repo-wide format/lint/typecheck runs are green.

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

## Troubleshooting

### Integration Test Failures

```bash
# Ensure services are running for integration tests
docker ps | grep huleedu

# Check service health
curl http://localhost:<port>/healthz

# View service logs for errors
pdm run dev-logs [service]
```

For Docker/database troubleshooting, see `CLAUDE.md` sections on Docker Development and Database Access.

### Admin Surface Note (2025-11-25)
- Admin student prompt upload endpoint now commits inside `upload_student_prompt`; unit tests must supply a session mock that implements `commit`, `rollback`, and `flush` (e.g., `AsyncMock(spec=AsyncSession)`), otherwise the endpoint returns HTTP 500.

## Documentation & Standards

- **`.claude/rules/`** - Development standards and architectural patterns
- **`CLAUDE.md`** - Comprehensive technical reference and workflow guide (includes Docker, database, testing commands)
- **`docs/operations/`** - Operational runbooks and playbooks
- **`TASKS/`** - Detailed task documentation with frontmatter tracking

## Session Addendum (2025-11-24)

- PostgresDataAccess now wraps `session_provider.session()` with `@asynccontextmanager` so the integration fixtures expose a proper async context manager and align with the new typing expectations.
- BatchMonitor unit fixtures drop the obsolete `repository` argument and the multi-round batch state integration test now types `postgres_session_provider` as `CJSessionProviderImpl` per the updated API surface.
- System prompt hierarchy, metadata persistence, pair generation, real database, and async workflow continuation integration suites now call the refactored APIs (no `database=` arguments) and the callback simulator/continuation helpers use the session_provider/repo contracts directly.
- Callback simulator now builds comparison pairs and correlation mappings directly via the shared `SessionProviderProtocol`, fully dropping the legacy `CJRepositoryProtocol` dependency from that helper.
- Additional unit/integration suites (`test_llm_callback_processing`, `test_event_processor_*`, `test_comparison_processing`, `test_workflow_continuation`, `test_cj_idempotency_failures`) have been updated to pass the new session_provider + repo keywords instead of the deprecated `database=` argument.
- Fixed the remaining typecheck blockers for workflow_continuation/callback_state_manager tests, wired the identity-threading fixture and integration suites to the reshaped session_provider/repo APIs, and reran `pdm run typecheck-all` (now reports zero errors).

## Session Addendum (2025-11-26)

- CJ pipeline selection now relies solely on `ClientBatchPipelineRequestV1` resolution. BOS ignores the legacy registration flag (registration logs a deprecation warning and records registration-only metrics). Regression tests guard that requesting CJ after registering without the flag includes CJ, and requesting non-CJ pipelines while it was set does not add CJ.
- Legacy flag removed from contracts (common_core), AGW/BOS code paths, and tests; pipeline selection is request-time only.
- Doc cleanup: Removed lingering references to the deprecated flag from TASKS documentation; repository search currently returns zero matches.

## Session Addendum (2025-11-27)

### Filename Propagation Fix (CRITICAL)

Added `original_file_name: str` field to `EssaySlotAssignedV1` event contract. Teachers can now identify students in CJ results via filename (critical for GUEST batches where filename is the ONLY identifier).

**Files changed**: `essay_lifecycle_events.py`, `content_assignment_service.py`, RAS protocol/handler/repository/updater

### JWT Auth Fix for Functional Tests

`tests/utils/auth_manager.py` now loads JWT secret from `.env` via `dotenv_values()`. Previously fell back to hardcoded `"test-secret-key"` causing 401 errors when AGW container used real secret.

**Pattern**: Always use `dotenv_values()` when test utilities need environment variables that aren't set via `os.environ` in subprocess contexts.

### assignment_id Propagation Gap (Active Investigation)

`assignment_id` from pipeline request never reaches CJ Assessment Service:
- BOS receives in `prompt_payload.assignment_id` ✅
- BOS → ELS command (`BatchServiceCJAssessmentInitiateCommandDataV1`) ❌ Missing field
- ELS → CJ (`ELS_CJAssessmentRequestV1`) ⚠️ Field exists but never populated

**Impact**: CJ cannot mix anchor essays for grade calibration. Fix in progress: `TASKS/assessment/propagate-assignment-id-from-bos-to-cj-request-phase-a.md`

### Functional CJ Test Aligned with ENG5 Runner

`test_e2e_cj_assessment_workflows.py` now uses `load_eng5_runner_student_files()` from `tests/utils/eng5_runner_samples.py` to load the same student essay files (docx) used by the ENG5 validation runner. This ensures functional tests exercise the same content pipeline as production validation.

**Usage**: `essay_files = load_eng5_runner_student_files(max_files=4)`

### LLM Provider Configuration Hierarchy

Documented 3-tier override hierarchy. See `docs/operations/llm-provider-configuration-hierarchy.md`. Key insight: `USE_MOCK_LLM=true` is a DI boot-time decision that cannot be bypassed by request-level `provider_override`.
