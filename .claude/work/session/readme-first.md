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

### Current Focus (mid-term)
1. Stable CJ completion semantics (PR‑2) under high callback failure rates.
2. Robust BT scoring core (PR‑4) with clear transaction ownership and SE diagnostics.
3. Continuation module split + observability (US‑00YA/US‑00YB): continuation decisions and diagnostics driven purely from `ContinuationContext` + `ContinuationDecision`.

### Critical CJ Patterns (carry forward, compressed)
- **Batch state & completion math**:
  - `CJBatchState` owns `total_budget` and cumulative comparison counters; always use `completion_denominator()` as the single source of truth for completion math.
  - Continuation logic lives in `workflow_context.py` (builds `ContinuationContext`), `workflow_decision.py` (`ContinuationDecision`, `decide(ctx)`), and `workflow_continuation.py` (orchestration).
- **Completion logic (PR‑2)**:
  - Recompute BT scores only when a callback iteration is fully complete.
  - Early stop only when:
    - `callbacks_received >= MIN_COMPARISONS_FOR_STABILITY_CHECK`.
    - `max_score_change <= SCORE_STABILITY_THRESHOLD`.
    - `success_rate` is None or ≥ `MIN_SUCCESS_RATE_THRESHOLD`.
  - Low/zero‑success batches finalize via the failure path, not `finalize_scoring`.
- **Small-net semantics (PR‑7)**:
  - Small‑net / coverage / resampling context is built in `build_small_net_context(...)` and stored on `ContinuationContext` (`is_small_net`, `max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, `resampling_pass_count`, `small_net_resampling_cap`, `small_net_cap_reached`).
  - `_can_attempt_small_net_resampling(ctx)` and the resampling flow in `workflow_continuation.trigger_existing_workflow_continuation(...)` implement Phase‑2 semantics; convergence remains owned by `workflow_continuation` + `BatchFinalizer` and the synthetic `convergence_harness`.
- **BT SE / coverage diagnostics**:
  - `build_bt_metadata_updates(...)` derives `bt_se_summary`, `bt_quality_flags`, and coverage flags (`bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`) and stores them on `ContinuationContext` + `CJBatchState.processing_metadata`.
  - `workflow_diagnostics.record_bt_batch_quality(ctx)` emits `cj_bt_se_inflated_batches_total` and `cj_bt_sparse_coverage_batches_total` from those flags **diagnostically only**.
- **Continuation observability (US‑00YB)**:
  - `workflow_diagnostics.record_workflow_decision(ctx, decision)` emits `cj_workflow_decisions_total{decision=...}` using `ContinuationDecision.value` and is wired from `workflow_continuation.trigger_existing_workflow_continuation(...)`.
  - The structured “Continuation decision evaluated” log uses the same decision vocabulary and includes key context fields (callbacks, caps, stability, small‑net flags, BT SE/coverage flags).
  - See `docs/operations/cj-assessment-runbook.md` and `observability/grafana/dashboards/cj-assessment/HuleEdu_CJ_Assessment_Deep_Dive.json` for example queries/panels.

### ENG5 & RAS Alignment (sprint-critical, compressed)
- **Result surface**: Result Aggregator Service (RAS) is the authoritative surface for CJ/ENG5 outputs; use RAS APIs/tables for reporting, never CJ service tables directly.
- **Assignment context**: `assignment_id` propagates end‑to‑end (client → BOS → ELS → CJ → RAS); RAS persists it on `BatchResult.assignment_id` and exposes it via `BatchStatusResponse.assignment_id`.
- **Guest flows**: For runs without student IDs, join filenames to CJ metrics (`cj_rank`, `cj_score`) via RAS (`/internal/v1/batches/{batch_id}/status`), not by querying CJ’s internal tables.

### ENG5 GPT‑5.1 Anchor-Align Experiments (Dec 2025)

- ENG5 NP runner now supports GPT‑5.1 anchor-align experiments via `ANCHOR_ALIGN_TEST` with anchor-align specific flags (`--anchor-align-provider`, `--anchor-align-model`, `--anchor-align-reasoning-effort`, `--anchor-align-output-verbosity`); Anthropic Haiku/Sonnet + 003 prompts remain the default, GPT‑5.1 is opt‑in.
- Three GPT‑5.1 runs have been completed against the vt_2017 ENG5 anchors using 003 language-control system/rubric prompts and `output_verbosity="medium"`:
  - `eng5-gpt51-none-20251201-142319` (cj_batch_id 137, BOS UUID `05c687fc-463d-4c2d-bcaa-73250d0830ca`)
  - `eng5-gpt51-low-20251201-142416` (cj_batch_id 138, BOS UUID `ddc3f259-b125-4a08-97fb-f4907fa50b3d`)
  - `eng5-gpt51-medium-20251201-142646` (cj_batch_id 139, BOS UUID `7c0dcd60-deeb-482a-ad7c-f851df09f454`)
- LLM Provider callbacks for these batches use `provider="openai"`, `model="gpt-5.1"`, and `resolved_model="gpt-5.1"`; CJ `AssessmentResultV1.model_used` / `model_provider` still report Anthropic Haiku, which is tracked as a CJ metadata bug (scoring is GPT‑5.1; attribution is stale).
- DB-based alignment reports (summary + full, including all comparison justifications) live under `.claude/research/data/eng5_np_2016/anchor_align_db*_*.md` and are the primary artefacts for reasoning-effort analysis; `reasoning_effort="high"` is intentionally deferred until metadata semantics and cost/latency guardrails are agreed.

## Critical Development Info

### CJ Assessment & LLM Provider Integration

- All CJ↔LLM interactions must use `common_core.api_models.llm_provider` contracts; cross‑service imports from `services.<name>.api_models` are forbidden.
- Metadata contract between CJ and LLM Provider now treats `LLMConfigOverridesHTTP.reasoning_effort` / `.output_verbosity` as first‑class HTTP fields and preserves them end‑to‑end via `CJLLMComparisonMetadata` and `request_metadata`; tests guard this boundary:
  - `docs/operations/eng5-np-runbook.md` for ENG5 runner usage and metadata expectations.
  - `tests/integration/test_cj_lps_metadata_roundtrip.py` for round‑trip coverage.
  - `services/cj_assessment_service/tests/integration/test_llm_payload_construction_integration.py` for CJ → LPS HTTP payload construction.
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
- Validating ENG5 LOWER5 small-net behaviour: CJ now respects `total_budget` as the completion denominator for 5-essay nets (no `min(budget, nC2)` clamp), and small-net resampling semantics allow more than `C(5,2)` comparisons when budget and `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` permit. Next work is to run LOWER5 experiments under these semantics and analyse DB-based reports (see `TASKS/assessment/cj-completion-semantics-v2--eng5--lower5.md` and `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`).
- **2025-11-19**: Batch-state locking regression fixed by routing `_update_batch_state_with_totals()` through `get_batch_state(..., for_update=True)`; new unit test `TestBatchProcessor.test_update_batch_state_with_totals_uses_locked_fetch` plus `pdm run pytest-root services/cj_assessment_service/tests/unit/test_batch_processor.py` + repo-wide format/lint/typecheck runs are green.
- **2025-11-30 (PR‑7 Phase‑5)**: Small‑net Phase‑2 semantics, coverage metadata on `CJBatchState.processing_metadata`, and the synthetic convergence harness are implemented and documented; use `convergence_harness.run_convergence_harness` plus CJ settings (`MAX_PAIRWISE_COMPARISONS`, `COMPARISONS_PER_STABILITY_CHECK_ITERATION`, `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`, `MIN_RESAMPLING_NET_SIZE`, `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`) as the reference for convergence tuning and stability experiments.

**Reference**: See `TASKS/phase3_cj_confidence/PHASE3_CJ_CONFIDENCE_HUB.md` for complete task breakdown and `TASKS/phase3_cj_confidence/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md` for implementation details.

### CJ/ENG5 Mock Profiles – Docker Coverage Layer (Dec 2025)

- LLM Provider mock profiles for CJ generic, ENG5 full-anchor, and ENG5 LOWER5 are now pinned against recorded LLM traces via docker-backed tests:
  - CJ generic:
    - Core parity and multi-batch coverage tests in `tests/integration/test_cj_mock_parity_generic.py` (mock profile `cj_generic_batch`, trace `cj_lps_roundtrip_mock_20251205`).
  - ENG5 full-anchor:
    - Full 12-anchor (66 comparison) parity test in `tests/integration/test_eng5_mock_parity_full_anchor.py` (mock profile `eng5_anchor_gpt51_low`, trace `eng5_anchor_align_gpt51_low_20251201`).
  - ENG5 LOWER5:
    - LOWER5 parity + small-net diagnostics tests in `tests/integration/test_eng5_mock_parity_lower5.py` (mock profile `eng5_lower5_gpt51_low`, trace `eng5_lower5_gpt51_low_20251202`).
- LPS admin mock-mode endpoint:
  - `GET /admin/mock-mode` (implemented in `services/llm_provider_service/api/admin_routes.py`, registered in `services/llm_provider_service/app.py`).
  - Payload:
    - `use_mock_llm`: current value of `Settings.USE_MOCK_LLM` in the running container.
    - `mock_mode`: current mock profile (`"cj_generic_batch"`, `"eng5_anchor_gpt51_low"`, `"eng5_lower5_gpt51_low"`) or `null` when `MockMode.DEFAULT` is active.
    - `default_provider`: string form of `Settings.DEFAULT_LLM_PROVIDER`.
  - Availability:
    - Enabled when `Settings.ADMIN_API_ENABLED` is `True` (default in dev/CI).
    - Returns `404` with `{"error": "admin_api_disabled"}` when `ADMIN_API_ENABLED=False`.
- Docker-backed CJ/ENG5 parity tests now:
  - Use `ServiceTestManager`’s validated `base_url` for `llm_provider_service`.
  - Call `/admin/mock-mode` at the start of each test to assert profile correctness and `pytest.skip` when `use_mock_llm` is `false` or `mock_mode` does not match the expected profile.
  - Use the same `base_url` for `/api/v1/comparison`, keeping profile detection and traffic routing aligned.
- Use `pdm run llm-mock-profile <profile>` (with `.env` set to the desired mock mode and `./scripts/dev-shell.sh` for env loading) as the entry point for per-profile docker test runs (CJ generic, ENG5 anchor, ENG5 LOWER5). This helper:
  - Validates `.env` profile settings.
  - Recreates `llm_provider_service` so `/admin/mock-mode` reflects the intended profile.
  - Runs the corresponding docker-backed parity tests, which rely on `/admin/mock-mode` as the single source of truth for the running container’s mock mode.

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

### ENG5 GPT‑5.1 attribution, prompt variants, and LOWER5 loop (Dec 2025)
- CJ batch-level LLM attribution for ENG5 anchor-align runs is now derived
  from `ComparisonPair.processing_metadata["provider"]` / `["model"]` via
  batch aggregation in `BatchFinalizer` / `BatchMonitor`, so
  `AssessmentResultV1.model_used` / `model_provider` can reflect OpenAI
  GPT‑5.1 rather than legacy Anthropic defaults.
- ENG5 treats OpenAI `gpt-5.1` with `reasoning_effort="low"` and
  `output_verbosity="low"` as the canonical GPT‑5.1 analysis configuration
  for anchor-align experiments (003 language-control prompts by default).
- A 006 usage/content parity prompt pair (50-word justifications) is
  available under `scripts/cj_experiments_runners/eng5_np/prompts/{system, rubric}/`
  for GPT‑5.1 low experiments; see
  `docs/operations/eng5-np-runbook.md` for the CLI pattern.
- For LOWER5 tail-only experiments:
  - CJ tuning is applied via `docker-compose.eng5-lower5.override.yml`
    (`MAX_PAIRWISE_COMPARISONS=20`, `MIN_COMPARISONS_FOR_STABILITY_CHECK=20`,
    `DEFAULT_BATCH_SIZE=20`, `MIN_RESAMPLING_NET_SIZE=10`,
    `MAX_RESAMPLING_PASSES_FOR_SMALL_NET=1`).
  - The ENG5 runner uses `ENG5_ANCHOR_DIR_OVERRIDE` to point at
    `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays_5_lowest_grades`
    so ANCHOR_ALIGN_TEST operates only on the 5 weakest anchors.
  - Canonical LOWER5 config: `openai` / `gpt-5.1`, `reasoning_effort="low"`,
    `output_verbosity="low"`, system prompt
    `007_usage_guard.txt`, rubric
    `006_usage_content_parity_rubric.txt`, DB reports produced with the
    same prompt pair via `scripts.cj_experiments_runners/eng5_np/db_alignment_report.py`.
  - Latest LOWER5 runs (2025-12-01, GPT‑5.1 low/low and none/low):
    - 007 system + 006 rubric (usage guard + parity rubric, `reasoning_effort="low"`): `batch_id=eng5-gpt51-lower5-007-20251202-001714`, `batch_uuid=50f4509e-2e8c-4c62-a19d-93cf0739eefd`, `cj_batch_id=147`; DB summary and full reports at `.claude/research/data/eng5_np_2016/anchor_align_db_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md` and `.claude/research/data/eng5_np_2016/anchor_align_db_full_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`, with Kendall’s tau `= 1.000`, `0` direct inversions, and one zero‑win F+ anchor (ladder `D‑ > E+ > E‑ > F+ > F+`).
    - 006 system + 006 rubric (pure usage/content parity, `reasoning_effort="low"`): `batch_id=eng5-gpt51-lower5-006-20251202-002205`, `batch_uuid=ec9c935c-e589-448c-b829-56ad545862f5`, `cj_batch_id=148`; DB summary and full reports at `.claude/research/data/eng5_np_2016/anchor_align_db_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md` and `.claude/research/data/eng5_np_2016/anchor_align_db_full_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`, with Kendall’s tau `= 0.800`, `1` direct inversion where F+ `ANCHOR_ESSAY_ENG_5_363940D5` beats E‑ `ANCHOR_ESSAY_ENG_5_73127661` (“Clearer structure, richer content”), and one zero‑win F+ anchor; top of the ladder (D‑, E+) remains stable.
    - 007 system + 006 rubric with `reasoning_effort="none"`: `batch_id=eng5-gpt51-lower5-007-none-20251202-003112`, `batch_uuid=4ce7468b-bf15-46b8-8a97-ebe51f79d45f`, `cj_batch_id=149`; DB summary and full reports at `.claude/research/data/eng5_np_2016/anchor_align_db_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md` and `.claude/research/data/eng5_np_2016/anchor_align_db_full_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md`, with Kendall’s tau `= 0.800`, `1` direct inversion where F+ `ANCHOR_ESSAY_ENG_5_D298E687` beats E‑ `ANCHOR_ESSAY_ENG_5_73127661` (strong structure/ideas justification) and one zero‑win F+ anchor.
    - 006 system + 006 rubric with `reasoning_effort="none"`: `batch_id=eng5-gpt51-lower5-006-none-20251202-003200`, `batch_uuid=8cb7d51a-abc9-486c-bc4f-3654c19da7e1`, `cj_batch_id=150`; DB summary and full reports at `.claude/research/data/eng5_np_2016/anchor_align_db_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md` and `.claude/research/data/eng5_np_2016/anchor_align_db_full_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md`, with Kendall’s tau `= 1.000`, `0` direct inversions, and one zero‑win F+ anchor (ladder `D‑ > E+ > E‑ > F+ > F+`), i.e. perfect LOWER5 alignment despite the weaker NONE-level behavior on the full anchor set.
