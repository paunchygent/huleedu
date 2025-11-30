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

## CJ Assessment – Sprint-Critical Validation & Patterns

### Current Sprint Focus
1. Stable CJ completion semantics (PR‑2) under high callback failure rates.
2. Robust BT scoring core (PR‑4) with clear transaction ownership and SE diagnostics.
3. ENG5 validation runs that use RAS as the source of truth and respect assignment_id propagation.

### Critical Fixes & Patterns (carry forward)
- **Batch state tracking** (2025‑11‑19): `total_budget` and cumulative comparison counters live on `CJBatchState`; always use `completion_denominator()` as the single source of truth for completion math.
- **Completion logic** (PR‑2): stability‑first behaviour:
  - Recompute BT scores only when a callback iteration is fully complete.
  - Gate early stopping with `MIN_COMPARISONS_FOR_STABILITY_CHECK` and `SCORE_STABILITY_THRESHOLD`.
  - Apply success‑rate guards (`MIN_SUCCESS_RATE_THRESHOLD`) when caps/budgets fire; low/zero‑success batches finalize via `finalize_failure`, not `finalize_scoring`.
- **Error exclusion**: only successful comparisons (`winner in {"essay_a","essay_b"}`) contribute to completion and BT inference; error comparisons are stored but excluded from the BT graph.
- **Batch state access**: callback persistence, completion checks, and monitor logic go through repository protocols with `for_update=True` where needed; no raw `AsyncSession` selects or cross‑service imports against `CJBatchState`.
- **Position randomization**: per‑pair A/B randomization is required to avoid anchor bias; use the shared matching‑strategy helpers and respect `CJ_ASSESSMENT_SERVICE_PAIR_GENERATION_SEED` in tests.

### PR‑4: CJ Scoring Core Refactor (BT inference robustness)
- Introduced `BTScoringResult` and `compute_bt_scores_and_se(...)` as pure BT domain logic:
  - Builds the CJ graph from `EssayForComparison` + `CJ_ComparisonPair`.
  - Delegates to `choix.ilsr_pairwise` + `bt_inference.compute_bt_standard_errors` using `BT_STANDARD_ERROR_MAX`.
  - Returns scores, per‑essay SEs, comparison counts, and a batch‑level SE diagnostics summary.
- `record_comparisons_and_update_scores(...)` is the single scoring entry point that:
  - Uses one `SessionProviderProtocol` session to persist new `CJ_ComparisonPair` rows, reload valid comparisons, update `CJ_ProcessedEssay` scores/SEs/counts, and commit once.
  - Delegates BT math to `compute_bt_scores_and_se` and emits structured SE diagnostics logs (`mean_se`, `max_se`, `min_se`, `item_count`, `comparison_count`, `items_at_cap`, `isolated_items`, comparison‑per‑item stats).
  - Returns `dict[str, float]` BT scores so PR‑2 stability/success‑rate gating in `workflow_continuation` and `BatchFinalizer` remains unchanged.
- `trigger_existing_workflow_continuation` now also persists `bt_se_summary` into `CJBatchState.processing_metadata` using its existing session, keeping BT SE diagnostics available for EPIC‑006 without introducing nested `CJBatchState` writes from scoring helpers.

### ENG5 & RAS Alignment (Sprint-Critical)
- **Result surface**: Result Aggregator Service (RAS) is the authoritative surface for CJ/ENG5 outputs; use RAS APIs or tables for reporting, never CJ service tables directly.
- **Assignment context**: `assignment_id` propagates end‑to‑end (client → BOS → ELS → CJ → RAS); RAS persists it on `BatchResult.assignment_id` and exposes it via `BatchStatusResponse.assignment_id`.
- **Guest flows**: For runs without student IDs, join filenames to CJ metrics (`cj_rank`, `cj_score`) via RAS (`/internal/v1/batches/{batch_id}/status`), not by querying CJ’s internal tables.

## Critical Development Info

### CJ Assessment & LLM Provider Integration

- All CJ↔LLM interactions must use `common_core.api_models.llm_provider` contracts; cross‑service imports from `services.<name>.api_models` are forbidden.
- Metadata contract between CJ and LLM Provider is documented and guarded by tests; see:
  - `docs/operations/eng5-np-runbook.md` for ENG5 runner usage and metadata expectations.
  - `tests/integration/test_cj_lps_metadata_roundtrip.py` for round‑trip coverage.
- LLM batching behaviour (per‑request vs serial‑bundle vs future batch‑API modes) is controlled via settings and metadata hints; treat those as part of the stability/throughput tuning toolkit for EPIC‑005/EPIC‑006 rather than ad‑hoc decisions in code.

### Grade Projection & Phase 3

- Grade projection quality and anchor calibration semantics are owned by EPIC‑006:
  - `docs/product/epics/cj-grade-projection-quality.md`
  - `TASKS/phase3_cj_confidence/PHASE3_CJ_CONFIDENCE_HUB.md`
- The Phase 3 grade‑projection data pipeline (ENG5 runner → CJ comparisons → BT scores → projections) is tracked in:
  - `TASKS/phase3_cj_confidence/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`
- When touching grade projection or ENG5 flows, prefer updating those docs/tasks rather than expanding this README; keep this file focused on sprint‑critical patterns and lessons learned.

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
- **2025-11-30 (PR‑7 Phase‑5)**: Small‑net Phase‑2 semantics, coverage metadata on `CJBatchState.processing_metadata`, and the synthetic convergence harness are implemented and documented; use `convergence_harness.run_convergence_harness` plus CJ settings (`MAX_PAIRWISE_COMPARISONS`, `COMPARISONS_PER_STABILITY_CHECK_ITERATION`, `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`, `MIN_RESAMPLING_NET_SIZE`, `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`) as the reference for convergence tuning and stability experiments.

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

## Recent Sprint Lessons (Cross-Service Patterns)

- **SessionProvider + repos as the default boundary**: All new data‑access code and tests should use `SessionProviderProtocol.session()` (async context manager) plus per‑aggregate repository protocols, not raw `AsyncSession` or `database=` parameters. Integration helpers (callback simulator, workflow continuation, etc.) have been updated to follow this pattern.
- **CJ pipeline selection via request contracts only**: BOS now relies solely on `ClientBatchPipelineRequestV1` to decide whether CJ runs for a batch. The legacy “CJ registration flag” is removed from contracts and code paths; pipeline selection is a request‑time decision, not a registration‑time toggle.
- **Filename propagation for guest flows**: `EssaySlotAssignedV1` includes `original_file_name`. Downstream services (especially RAS) must preserve this so teachers can interpret results for GUEST batches where filename is the only identifier.
- **JWT secrets in tests**: Test utilities that need JWT secrets (e.g. `tests/utils/auth_manager.py`) must load them via `dotenv_values()` or the environment, never hard‑code fallback secrets. This keeps functional tests aligned with container configuration.
- **LLM Provider configuration hierarchy**: `USE_MOCK_LLM=true` is a DI boot‑time decision; request‑level overrides cannot bypass it. See `docs/operations/llm-provider-configuration-hierarchy.md` when changing LLM provider behaviour.
- **Pair matching strategy via DI**: CJ uses a DI‑swappable `PairMatchingStrategyProtocol` with `OptimalGraphMatchingStrategy` as the default implementation. Tests that care about comparison graph structure should use the real strategy via the shared helpers; only A/B position randomization tests should stub the strategy.
- **ENG5 runner handler pattern + tests**: The ENG5 NP runner now uses a handler-based Typer CLI (`cli.py` + `handlers/*.py`) with per-mode unit tests and a small Typer `CliRunner` integration suite under `scripts/cj_experiments_runners/eng5_np/tests/unit/`. Use this as the reference pattern for future CLI refactors and mode-specific handler testing.
