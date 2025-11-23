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

### Rule Frontmatter Schema Implementation (2025-11-23)

**Status**: ✅ Complete - All 92 rules have valid Pydantic-compliant frontmatter

**Deliverables**:
- Pydantic schema: `scripts/claude_mgmt/rule_frontmatter_schema.py` (8 fields: 5 required, 3 optional)
- Updated validation: `scripts/claude_mgmt/validate_claude_structure.py` (using Pydantic model)
- Reference data: `.claude/work/session/frontmatter-reference.txt` (git dates + hierarchy)
- Zero validation errors across all 92 rules

**Schema**: Required (`id`, `type`, `created`, `last_updated`, `scope`) + Optional (`parent_rule`, `child_rules`, `service_name`)

**Parent-child hierarchies**: 12 parents with 45 children (bidirectional references)

### Latest Ops Status (2025-11-21)
- CJ pipeline stall resolved after infra restore: Kafka/ZooKeeper/Redis/CJ DB healthy; `huleedu_cj_assessment_service` restarted with BatchMonitor running.
- Stalled batch 588f04f4-219f-4545-9040-eabae4161f72 (corr 4cc75b6c-0fb2-465f-a20d-dfa0fb7de79f) now COMPLETED_STABLE; completion + RAS ready events published at ~11:48:59 UTC.
- No batches remain in WAITING_CALLBACKS/GENERATING_PAIRS; monitor new runs via Loki query `{service="cj_assessment_service"} | json | event="BatchMonitor heartbeat"` and completion sweep logs.
- E2E CJ test latency note: callbacks returned in ~12s, but `completion_threshold` (95% of budget 350) kept batch in WAITING_CALLBACKS until 5‑minute monitor sweep forced completion (~3m42s delay). Pending follow-up to switch completion to stability-first and cap budget to nC2.
- Stability-first completion shipped: callbacks now trigger scoring immediately; batches finalize on stability or when callbacks hit the capped denominator (min(total_budget, nC2)). BatchMonitor is recovery-only.
- Anthropic regression coverage extended to 529 overload + stop_reason=max_tokens; prompt cache metrics (`llm_provider_prompt_cache_events_total`, `llm_provider_prompt_cache_tokens_total`) now available with hit/miss and tokens-saved visibility.
- Anthropic metadata + caching fix (2025-11-23): payload now sends only `metadata.user_id` and adds `anthropic-beta: prompt-caching-2024-07-31`; validator cap raised to 1000 chars, prompt nudges ≤50-char justification. Smoke A unredacted run: 16/16 success, cache reads/writes still 0 (likely model cache unsupported or blocks under threshold); artefacts `.claude/work/reports/benchmarks/20251123T004138Z-prompt-cache-warmup.{json,md}`.
- Prompt cache benchmark ops: run `pdm run prompt-cache-benchmark ...` **without external timeouts**; prior 180s wrapper killed runs after sending requests and prevented artefact writes.
- Grafana wiring: `LLM Provider Prompt Cache` dashboard now shows scope-aware hit rates (assignment vs ad-hoc), block mix, and static vs dynamic token size; alert `LLMPromptCacheLowHitRate` now keys off assignment scope <40%, and new `LLMPromptTTLOutOfOrder` warns on TTL ordering violations.
- Phase 1.3 prompt cache integration plan drafted (see `.claude/work/session/handoff.md`); next action is wiring `PromptTemplateBuilder` through pair generation and dual-sending prompt blocks to LPS.
- Default `MAX_PAIRWISE_COMPARISONS` reduced to 150 for cost safety; per-request overrides still honored; tests updated.
- CJ prompt block serialization guard tightened: non-production now raises (production falls back to legacy prompt), closing prior unit test failure in `test_llm_interaction_impl_unit.py`.
- Prompt cache benchmark runner added (`pdm run prompt-cache-benchmark`; wrappers `scripts/run-prompt-cache-smoke.sh` / `scripts/run-prompt-cache-full.sh`) with serialized seeds, dual buckets, PromQL snapshots, and artefact templates in `.claude/work/reports/benchmarks/`; smoke/full fixtures ready once Anthropic keys are present.
- Prompt cache benchmark runner: now captures raw Anthropic responses (for audit/BT scores). Run without external timeouts; CLI help warns against wrapping. Latest Sonnet ENG5 smoke run artefacts: `.claude/work/reports/benchmarks/20251123T011800Z-prompt-cache-warmup.{json,md}` (hits 16, misses 0, read 43,112/write 1,408 tokens).
- ENG5 fixture exporter: `python -m scripts.prompt_cache_benchmark.build_eng5_fixture` converts the runner's DOCX anchors/students + prompts/rubric/system prompt into `data/eng5_prompt_cache_fixture.json`; use `--fixture-path` flag on the benchmark CLI for real-data runs. Default `--redact-output` (hash/metrics only); `--no-redact-output` for validation (includes essay text, prompts, blocks).
- LLM Provider queue processor completion/removal integration tests now pass (2025-11-23). `_process_request` no longer uses `process_comparison_batch` when `QUEUE_PROCESSING_MODE=serial_bundle`; per-request path is enforced to avoid "Unexpected processing result type" with mocks. Command validated: `pdm run pytest-root services/llm_provider_service/tests/integration/test_queue_processor_completion_removal.py`.

### Hot-Reload Development

All services use automatic code reload in development:
- **Quart services** (11): `hypercorn --reload`
- **FastAPI services** (2): `uvicorn --reload`

Changes to `.py` files trigger automatic restart (~9-11 seconds). No manual rebuild needed.

### Logging & Observability (2025-11-20)

**Infrastructure**: File-based logging + Docker bounded rotation operational. See Rule 043 §3.2, Grafana playbook (Loki access).

**OTEL Trace Context**: ✅ Operational across all 15 API services. Health endpoints log with trace_id/span_id. Jaeger integration active. Use `scripts/validate_otel_trace_context.sh` to validate.

**ENG5 Runner**: Execute mode → persistent logs at `.claude/research/data/eng5_np_2016/logs/eng5-{batch_id}-{timestamp}.log`

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

### Essay Lifecycle Slot Assignment (2025-11-21)
- Added lock-aware retry to Option B content assignment (`assign_via_essay_states_immediate_commit`) to prevent false "no slot" responses under contention.
- Regression coverage: `test_option_b_assignment_retries_when_slots_locked` + distributed `test_concurrent_identical_content_provisioning_race_prevention` now green.

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
