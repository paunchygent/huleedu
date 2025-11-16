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
9. **CJ Assessment** - Content judgment evaluation
10. **NLP Service** - Natural language processing
11. **Result Aggregator (RAS)** - Results compilation
12. **Entitlements** - Credit management

## How to Run

### Prerequisites

- Docker & Docker Compose v2
- Python 3.11
- PDM package manager

### Development Setup

```bash
# 1. Clone and setup
git clone <repo>
cd huledu-reboot
pdm install

# 2. Start all services (development mode with hot-reload)
pdm run dev-build-start

# 3. Check service health
docker ps | grep huleedu

# 4. View logs
pdm run dev-logs
```

### Running Tests

```bash
# Unit tests
pdm run pytest-root services/<service_name>/tests/unit

# Integration tests
pdm run pytest-root services/<service_name>/tests/integration

# Functional E2E tests (requires all services running)
pdm run pytest-root tests/functional/test_e2e_cj_after_nlp_with_pruning.py -v

# With specific markers
pdm run pytest-root -m "not slow"  # Skip slow tests
pdm run pytest-root -m integration  # Only integration tests
```

### Common Commands

```bash
# Service management
pdm run dev-restart [service]    # Restart service
pdm run dev-recreate [service]   # Force container recreation to pick up env var changes
pdm run dev-logs [service]        # View logs

# Code quality
pdm run lint-all      # Run linter
pdm run format-all    # Format code
pdm run typecheck-all # Type checking

# Database reset (DESTROYS all *_db_data volumes, reruns Alembic via .venv)
pdm run db-reset
```

### Hot-Reload Development Workflow

**Status:** ✅ **Fully Deployed** - All Quart services use Hypercorn `--reload`, verified working

All services automatically detect code changes and restart without manual intervention:

```bash
# 1. Start services in development mode
pdm run dev-start

# 2. Edit code in any service directory (e.g., services/content_service/)
# - Changes to .py files trigger automatic reload
# - Service shuts down gracefully and restarts (~9-11 seconds)
# - NO manual restart or rebuild required

# 3. Watch logs to see reload in action
pdm run dev-logs content_service
# Look for: "shutdown completed" → "startup completed successfully"
```

**Architecture Decision: Hypercorn for All Quart Services**

All 11 Quart services use Hypercorn directly (not `quart run`) for:
- ✅ **Dev/Prod Parity**: Same ASGI server in both environments (only `--reload` differs)
- ✅ **Explicit Configuration**: All flags visible (`--bind`, `--worker-class`, `--reload`)
- ✅ **Production Control**: Can add workers, TLS, logging without switching tools
- ✅ **Consistency**: Matches `uvicorn` pattern used for FastAPI services

**Services with Hypercorn `--reload`:**
- batch_conductor_service ✅ (tested and verified)
- batch_orchestrator_service ✅
- class_management_service ✅
- llm_provider_service ✅
- result_aggregator_service ✅
- file_service ✅
- content_service ✅ (tested and verified)
- identity_service ✅
- email_service ✅
- entitlements_service ✅
- language_tool_service ✅

**Services with uvicorn `--reload`:**
- api_gateway_service ✅ (FastAPI)
- websocket_service ✅ (FastAPI)

**Important Notes:**
- Hot-reload uses volume mounts (`docker-compose.dev.yml`)
- Changes to dependencies (pyproject.toml) still require `pdm run dev-build`
- Worker services (essay_lifecycle_worker, nlp_service worker mode) don't need hot-reload

## Recent Decisions & Changes

### 0. Hot-Reload Standardization on Hypercorn (Nov 2025)

**Completed**: All 11 Quart services migrated to Hypercorn `--reload` for automatic code reload in development.

**Rationale**:
- **Dev/Prod Parity**: Same ASGI server (Hypercorn) in development and production, differing only by `--reload` flag
- **Explicit Configuration**: All server flags (`--bind`, `--worker-class`, `--reload`) visible in compose commands
- **Production Ready**: Can add workers, TLS, custom logging without switching to a different server
- **Consistency**: Matches FastAPI services which use `uvicorn --reload` (also direct ASGI server invocation)

**Implementation**:
- Updated `docker-compose.dev.yml`: All Quart services now use `python -m hypercorn ... --reload`
- Pattern: `hypercorn services.<name>.app:app --bind 0.0.0.0:<port> --worker-class asyncio --reload`
- Tested: content_service and batch_conductor_service verified with ~9-11 second reload cycle
- All 11 services healthy and running

**Before** (old pattern):
```bash
command: ["pdm", "run", "-p", "/app", "quart", "--app", "app:app", "--debug", "run", "--host", "0.0.0.0", "-p", "8000"]
```

**After** (standardized pattern):
```bash
command: ["pdm", "run", "-p", "/app", "python", "-m", "hypercorn", "services.content_service.app:app", "--bind", "0.0.0.0:8000", "--worker-class", "asyncio", "--reload"]
```

### 1. Codex Setup Script Hardening (Nov 2025)

- `scripts/setup_huledu_environment.sh` now finds the repo root via env vars, Git metadata, and Codex `/workspace/<repo>` mounts before running PDM so sandboxes stop erroring out on `common_core`.
- PDM caches/logs are redirected to `.pdm/` inside the repo (ignored via `.gitignore`) and `pdm install --group monorepo-tools --group dev` runs cleanly even when `$HOME` is read-only.
- Script output advertises the Ruff/Mypy/Pytest/dev PDM scripts defined in `pyproject.toml`, so new agents follow Rule 081/083 conventions immediately.

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

### 4. Ordinal Kernel Feature Flags

**What**: Config/CLI toggles for argmax decision, leave-one-out alignment, precision-aware weighting, and neutral ESS metrics.
**Why**: Gives data science control to test each mitigation independently—argmax protects against modal skew, LOO removes self-influence, precision weights emphasise reliable raters, and neutral ESS reveals balanced evidence without enforcing gates.
**How**: Consensus CSVs now surface `neutral_ess` (informational) and `needs_more_ratings`; run `scripts/bayesian_consensus_model/evaluation/harness.py` to produce ablation metrics before changing defaults.

### 5. Harness Metrics (2025-09-25)

- Baseline anchors: mean confidence 0.308, expected grade index 5.888, neutral ESS 0 and no gating triggered.
- Argmax toggle: 3/12 essays flip with +0.0125 mean confidence and unchanged expected indices; gating count stays 0.
- Leave-one-out alignment: no grade flips, mean expected index −0.0005, mean confidence +0.0042.
- Precision-aware weights: no grade flips, mean expected index −0.0289, mean confidence −0.0044.
- Neutral ESS metrics: enabling the flag raises neutral ESS mean to 1.46 but leaves gating count at 0; running all toggles moves JA24 B→A and JP24 E+→E− while still reporting zero `needs_more_ratings`.

### 6. D-Optimal Pair Scheduling (Jan 2025)

- Added `scripts/bayesian_consensus_model/d_optimal_optimizer.py` and `d_optimal_prototype.py` to build Fisher-information-maximizing comparison schedules with anchor adjacency + student bracketing constraints.
- Session 2 optimized outputs:
  - 84-comparison update: log-det gain +3.69, stored in `session_2_planning/20251027-143747/session2_pairs_optimized.csv`.
  - 149-comparison expansion: log-det gain +17.65 with coverage mix anchor_anchor=31, student_anchor=86, student_student=32, stored at `session2_pairs_optimized_149.csv`.
- Follow-up integration & assignment balancing tasks are tracked in `TASKS/d_optimal_pair_optimizer_plan.md`.

### 7. Optimizer Integration & Balanced Redistribution (Jan 2025)

- Typer CLI: `python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs` covers session/synthetic runs, exposes slot/repeat controls, and writes JSON diagnostics.
- Textual TUI: `redistribute_tui.py` now has optimization controls + auto-run toggle; logs show comparison mix, anchor coverage, and repeat counts.
- Rater assignments: `redistribute_core.assign_pairs` delivers balanced comparison mixes so no rater receives anchor-only workloads when student essays exist.
- Tests: `pdm run pytest-root scripts/bayesian_consensus_model/tests/test_redistribute.py` exercises CLI, allocator, and CSV compatibility.

### 8. Continuation-aware D-Optimal Optimizer (Nov 2025)

- Baseline comparisons are now canonicalized and locked into the optimizer so repeat limits and log-det metrics span all sessions; `total_slots` represents new comparisons for the current run while `OptimizationResult` exposes both `new_design` (new-only) and the combined schedule.
- CLI/TUI output CSVs contain only newly scheduled comparisons while summaries/report JSON highlight baseline consumption, mandatory new-slot components (adjacency, locked, coverage), and combined totals.
- Tests expanded (`test_load_dynamic_spec_canonicalizes_previous_comparisons`, multi-session assertions on `new_design`) with automation via `pdm run pytest-root scripts/bayesian_consensus_model/tests/test_redistribute.py`; manual CLI/TUI smoke passes are still recommended per handoff notes.

### 9. NLP Prompt Hydration (Nov 2025)

- `BatchNlpAnalysisHandler` now hydrates `student_prompt_ref` through the Content Service, records failures via `huleedu_nlp_prompt_fetch_failures_total{reason=...}`, and passes `prompt_text`/`prompt_storage_id` into downstream pipelines.
- `EssayNlpCompletedV1.processing_metadata` includes `student_prompt_text` and `student_prompt_storage_id` (legacy `essay_instructions` retained temporarily for backward compatibility).
- Unit coverage added (`pdm run pytest-root services/nlp_service/tests -k batch_nlp_analysis_handler`) to ensure prompt propagation and metric instrumentation.

### 10. CJ Prompt Hydration (Nov 2025)

**Completed (2025-11-12)**: Prompt context persistence hardening with Result monad pattern, typed metadata overlay, and fallback hydration.

**Implementation**:
- Added `Result[T,E]` monad for typed success/failure handling (non-exception control flow)
- Created `PromptHydrationFailure` dataclass for typed error payloads
- Implemented `CJProcessingMetadata` Pydantic model for typed metadata overlay pattern
- Event processor: `_hydrate_prompt_text()` returns `Result[str, PromptHydrationFailure]`
- Batch preparation: Fallback to Content Service hydration when text missing; typed metadata merge preserves unknown keys (`{**existing, **typed.model_dump(exclude_none=True)}`)
- Workflow orchestrator: Threaded `content_client` through batch creation (later re-aligned with Dishka DI)
- Metrics: Added `huleedu_cj_prompt_fetch_success_total` counter alongside existing `failures_total{reason}`
- Repository: Returns `student_prompt_storage_id` for anchor workflow synchronization

**Test Coverage**: 31/31 passing (5 updated files, 2 new test files) | Typecheck clean

**Architecture Notes**:
- Result monad used for internal control flow, exceptions for boundary operations
- Typed metadata overlay balances type safety with extensibility (forbids unknown fields in model, preserves them in dict merge)
- `original_request` payloads (language, overrides, prompt refs, identity) are now persisted to both `cj_batch_uploads` and `cj_batch_states` via merge-only helpers so continuation can faithfully rehydrate `CJAssessmentRequestData`.
- Anchor processing writes must use `CJAnchorMetadata` + `merge_essay_processing_metadata` to append metadata; never reassign JSON blobs (`processing_metadata = {...}`) because that clobbers diagnostic fields and comparison budget state.
- Content client initially threaded explicitly for testability, pending DI re-alignment

**Ref**: `TASKS/CJ_PROMPT_CONTEXT_PERSISTENCE_PLAN.md` (completed 2025-11-12)

### 11. Prompt Reference Migration Step 5 Docs & Observability (2025-11-06)

- Service READMEs (`services/nlp_service/README.md`, `services/cj_assessment_service/README.md`) describe Content Service prompt hydration, fallback semantics, and required metrics wiring.
- `Documentation/OPERATIONS/01-Grafana-Playbook.md` adds a Prompt Hydration Reliability dashboard guide with PromQL for `huleedu_{nlp|cj}_prompt_fetch_failures_total`.
- Child task Step 5 documents residual `essay_instructions` usage (AI Feedback event contracts, Essay Lifecycle persistence, Result Aggregator fixtures) to sequence the final cleanup.

### 12. Phase 3.3 – ENG5 NP Runner Planning (2025-11-08)

- Phase 3.3 section in `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md` now details the ENG5 NP runner/CLI (`pdm run eng5-np-run ...`), modes (`plan`, `dry-run`, `execute`), preflight expectations, and validation strategy aligned with rules 070/075.
- Data-source mapping enumerates ENG5 instructions, prompt references, anchor metadata, and student essay folders under `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016`, plus dependency on `DEFAULT_ANCHOR_ORDER` from `scripts/bayesian_consensus_model/d_optimal_workflow/models.py`.

## Current Session Notes (2025-11-16)

- Phase 1 analysis complete: reviewed the continuation validation checklist, traced relevant `ComparisonPair` queries in `workflow_continuation.py`, and outlined the query optimization plus metadata documentation work before coding begins.
- Phase 2 optimization: `workflow_continuation.py` now counts completed/valid comparisons with `select(func.count())`, the unit tests' fake session exposes `scalar_one()` for the new query pattern, and typecheck plus `test_workflow_continuation.py` were rerun successfully.
- Batch 21 is currently in `SCORING` (10 submitted, 100 completed) with the `runner_override` budget intact, which matches the persisted metadata verified via the `cj_batch_states` query.
- Phase 3 documentation/validation: Added a “Metadata & Budget Semantics” section to `services/cj_assessment_service/README.md` covering `comparison_budget.source`, `max_comparisons_override`, merge-helper requirements, anchor metadata invariants, and continuation rehydration; reran `typecheck-all` and `test_workflow_continuation.py` afterward per validation rules.
- Document review: Confirmed all touched docs align with current CJ continuation budget behavior and Rule 090’s expectations; no divergences or infractions were detected during this verification.
- Phase 4 observability/tests: Verified the running CJ service emits the new `Valid comparisons found` logs for batch 21 (counts 96–100) and reran `typecheck-all`, `test_batch_finalizer_scoring_state.py`, and `test_prompt_metrics.py` so the gating checklist covers logging, metrics, and DB state transitions.
- JSON artefact schema draft lives at `Documentation/schemas/eng5_np/assessment_run.schema.json`, covering metadata, inputs, comparisons, Bradley–Terry stats, grade projections, cost tracking, and manifest validation for reproducible research bundles.

### 13. Documentation Taxonomy Restructure (2025-11-08)

- Legacy `docs/` root was removed; canonical content now lives under `Documentation/` with four primary categories: `Documentation/apis/` (OpenAPI, WebSocket spec, API reference, TypeScript DTOs), `Documentation/guides/` (Claude plugin guide, frontend integration, shared code patterns, Svelte guide), `Documentation/research/` (historical Swedish materials and the rapport payloads), and `Documentation/adr/` (ADR-001/002).
- All task references now point to the new paths, and helper scripts referencing the rapport assets have been re-aligned so future contributors only touch the structured locations.

### 14. ENG5 Runner Scaffold (2025-11-08)

- Added `.claude/research/scripts/eng5_np_batch_runner.py` plus `pdm run eng5-np-run` so engineers can inspect assets (`plan`), emit schema-compliant artefact stubs (`dry-run`), and publish real `ELS_CJAssessmentRequestV1` events via Kafka (`execute`, overridable with `--no-kafka`). Execute mode now supports `--llm-provider/--llm-model/--llm-temperature/--llm-max-tokens` overrides and optional `--await-completion` to tail `huleedu.cj_assessment.completed.v1`.
- Contract-focused tests live at `.claude/research/scripts/test_eng5_np_batch_runner.py`, covering checksum helpers, directory snapshots, stub writer behaviour, real dataset detection, envelope generation, and override plumbing.

### 15. CJ Admin Auth & CLI (2025-11-09)

- `/admin/v1/assessment-instructions` blueprint is live with the shared JWT validator (Identity-issued tokens, `roles` must include `admin`, permissions claim follow-up). Metrics counter `cj_admin_instruction_operations_total` tracks CRUD outcomes.
- `Settings` inherits the `JWTValidationSettings` mixin (new module under `libs/huleedu_service_libs/auth/`) plus `ENABLE_ADMIN_ENDPOINTS` gating (default on outside prod, opt-in for prod).
- API Gateway now imports the shared `decode_and_validate_jwt` helper, so all services share one JWT validation path.
- `pdm run cj-admin …` Typer CLI authenticates via Identity `/v1/auth/login`, caches/refreshes tokens (with optional `CJ_ADMIN_TOKEN` override), and exposes `instructions create/list/get/delete` + `scales list` commands for seeding ENG5 NP instructions.

### 16. Phase 3.2 Typing & Test Hardening (2025-11-09)

- Introduced an `AssessmentInstructionStore` test helper and updated every CJ repository mock (admin routes, shared mocks, anchor helpers, callback manager scenarios, workflow continuation, single-essay finalizer) so they return concrete `AssessmentInstruction` instances without `Any` leakage.
- Tightened the CJ admin Typer CLI by adding JSON type aliases plus a `TokenCache` `TypedDict`, giving `_load_cache`, `_refresh`, `_admin_request`, etc., precise signatures.
- API Gateway middleware/providers now call the shared JWT helpers with explicit `correlation_id`, `service`, and `operation` keywords to satisfy the new signature.
- Added a dedicated `CorrelationContext` fixture for the admin route tests and reran `pdm run typecheck-all` plus the anchor/callback/admin CLI/unit suites to verify the type-safe surface.

### 17. ENG5 Runner Architect Brief (2025-11-09)

- `TASKS/TASK-CJ-PHASE3-ARCHITECT-NEXT-SESSION.md` defines the next architect-led session for Phase 3.3 (metadata enforcement, artefact validation, execute-mode runbook).
- Critical focus: ensure `LLMComparisonResultV1` metadata is mandatory end-to-end, keep runner artefacts schema-compliant, and document the operational steps before the next ENG5 NP execute run.

### 18. ENG5 Metadata Hardening & Runbook (2025-11-09)

- Queue processor now injects `prompt_sha256` even on error callbacks via `services/llm_provider_service/prompt_utils.py` + `_publish_callback_event_error`, and unit tests cover the regression.
- `scripts/cj_experiments_runners/eng5_np/{artefact_io,hydrator,kafka_flow,cli}.py` implement fail-fast metadata handling, duplicate suppression, manifest hashing, cost summaries, and schema-compliant document blobs; tests live in `scripts/tests/test_eng5_np_runner.py` (with `jsonschema` validation).
- Execute-mode guidance consolidated into `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md` (prereqs, commands, monitoring, failure modes).

### 19. Student Prompt Admin Management (Nov 2025)

- Added nullable `student_prompt_storage_id` to CJ Assessment instructions (migration `20251110_1200_add_student_prompt_to_instructions.py`) and repository/API models so prompt references live with judge metadata.
- Implemented admin REST endpoints (`POST /admin/v1/student-prompts`, `GET /admin/v1/student-prompts/assignment/<id>`) plus Typer CLI commands (`cj-admin prompts upload|get`) to upload and retrieve prompt text through the Content Service with Dishka-injected clients, correlation logging, and metrics.
- Batch preparation now auto-hydrates prompts when only `assignment_id` is provided, aligning ENG5 runner + downstream pipelines; tests cover REST, CLI, and workflow integration (`test_student_prompt_workflow.py`).
- Documentation and architecture rules updated (`services/cj_assessment_service/README.md`, `.claude/rules/020.7-cj-assessment-service.mdc`). Step 5 prompt-reference cleanup is complete across downstream consumers (NLP, CJ, Result Aggregator); ongoing focus is on monitoring `huleedu_{cj|nlp}_prompt_fetch_failures_total` and keeping new workflows reference-only.

### 20. ENG5 Runner Content Upload & Event Hardening (Nov 2025)

**Completed (2025-11-12)**: Runner infrastructure validated with storage ID fixes, batch validation, and Kafka DNS resolution.

**Implementation**:
- Storage ID format fix: Removed `prompt::` prefix in runner, now sends raw Content Service UUIDs
- Batch validation: Added defensive guard for empty batch_id with clear error messaging
- Kafka DNS fix: Changed default from `localhost:9092` (internal) to `localhost:9093` (external listener)
- Content upload: Runner uploads essays to Content Service before event composition
- Event validation: Kafka collector uses typed Pydantic models to prevent AttributeError on raw dict payloads
- Docker compose: Wired CONTENT_SERVICE_URL + content service dependency for local execution

**Validation**: Integration test confirmed end-to-end flow (Runner → Kafka → CJ service), correlation_id tracing working, all storage IDs are 32-char UUIDs

### 21. Database URL Centralization (Nov 2025) - Phase 1 Complete

**Status**: ✅ Foundation & Identity Service complete, ready for Batch 1 (1/12 services migrated, validated)

**Phase 1 Complete** (2025-11-11):
- ✅ Shared utility `build_database_url()` with service override, prod/dev branches, password encoding
- ✅ Unit tests: 7/7 passing (encoding, overrides, errors, custom hosts)
- ✅ `SecureServiceSettings.build_database_url()` convenience method
- ✅ Identity Service migrated to uppercase `DATABASE_URL` (Rule 043 compliant)
- ✅ Identity schema auto-init confirmed (startup_setup.py:57-59)
- ✅ Validation: 534/535 unit tests, 1,222 files type-checked, container test successful
- ✅ Special character password working: `omT9VJ#1cvqPjuMzP5exdGp9h#m3zmQn` (# encoded correctly)

**Ready for Batch 1** (4 services):
- ⏸️ class_management, file, result_aggregator, email
- ⏸️ Batch 2 (4 services): essay_lifecycle, nlp, batch_orchestrator, spellchecker
- ⏸️ Batch 3 (3 services): entitlements, batch_conductor, cj_assessment
- ⏸️ Remove 11 docker-compose `*_DATABASE_URL` overrides

**Architecture Decision**: Uppercase `DATABASE_URL` enforced per Rule 043 for all services during migration.

### 22. ENG5 Grade Projector Fix & Validation (Nov 2025)

**Status**: ✅ Implemented and validated with batch a93253f7

**Problem**: Grade projector failed to resolve anchor grades, producing 0 grade projections (required for score band visualization and student grade assignment).

**Solution**: 4-tier anchor grade fallback mechanism in `grade_projector.py:_map_anchor_grades()`:
1. Direct `anchor_grade` field in anchor dict or metadata
2. `known_grade` in processing_metadata
3. Lookup by `text_storage_id` in anchor references
4. Lookup by `anchor_ref_id` in anchor references

**Implementation**:
- `grade_projector.py` lines 241-297: 4-tier fallback logic
- `scoring_ranking.py` lines 307-308: Emit text_storage_id and processing_metadata for Tier 3
- Test coverage: `test_grade_projector_anchor_mapping.py` (unit tests for all fallback tiers)

**Validation Results** (Batch a93253f7-9dd2-4d14-a452-034f91f3e7dc):

| Metric | Pre-Fix | Post-Fix | Status |
|--------|---------|----------|--------|
| Grade Projections | 0 | 12 | ✅ Fixed |
| BT-Scores Computed | 24/24 | 24/24 | ✅ Preserved |
| Anchor Grades Resolved | 0/12 | 12/12 | ✅ Fixed |
| Comparison Pairs | 100 | 100 | ✅ Stable |

**Technical Details**:
- BT-score calculation: choix.ilsr_pairwise with alpha=0.01 regularization, mean-centered
- Standard errors: Fisher Information matrix via Moore-Penrose pseudoinverse
- Grade projection: Gaussian mixture calibration with resolved anchor grades
- Mock LLM: Probabilistic (45% A, 55% B, seed=42) for technical validation only

**Architecture**: Anchors (known grades) and students (projected grades) stored separately by design for downstream service flexibility. BT-scores preserved in `cj_processed_essays.current_bt_score` for all 24 essays.

**Ref**: `.claude/research/2025-11-15_eng5_grade_projector_validation_batch_a93253f7.md` (comprehensive technical report)

### 23. Pydantic Request Data Migration (Nov 2025)

**Status**: ✅ Complete

Migrated CJ Assessment `request_data` from `dict[str, Any]` to `CJAssessmentRequestData` Pydantic model for type safety (IDE autocomplete, mypy validation, runtime checks).

### 24. Event Processor Refactoring (Nov 2025)

**Status**: ✅ Complete

**Objective**: Decompose `event_processor.py` from 952 LoC to comply with <400-500 LoC clean code standards (78% reduction to 202 LoC).

**Implementation**:
- Created focused modules in `cj_core_logic/`: `content_hydration.py` (238 LoC), `request_transformer.py` (70 LoC), `error_categorization.py` (81 LoC)
- Created handler modules in `message_handlers/`: `cj_request_handler.py` (340 LoC), `llm_callback_handler.py` (228 LoC)
- Refactored `event_processor.py` to thin router pattern (202 LoC) - routes messages to handlers, envelope parsing and trace context only
- Clear separation of concerns: routing vs orchestration vs domain logic
- All modules <400 LoC, all existing functionality preserved

**Validation**: All tests passing, typecheck clean

## Configuration Files

- `.env` - Environment variables (not in git)
- `pyproject.toml` - PDM dependencies and scripts
- `docker-compose.yml` - Production config
- `docker-compose.dev.yml` - Development overrides
- `.claude/rules/` - Development standards and patterns
- `CLAUDE.md` - Detailed technical reference

## Rater Metrics

- `generate_reports.py` now emits `rater_bias_posteriors_eb.csv` with empirical-Bayes posterior bias per rater on the grade-index scale.
- Use `--bias-correction {on,off}` and `--compare-without-bias` to run EB and legacy consensus side-by-side; each invocation writes into `output/bayesian_consensus_model/<run_label or timestamp>/` by default (override with `--output-dir`), with comparison CSV/JSON saved alongside the bias-on results.
- Each run also saves `rater_bias_vs_weight.png`, highlighting high-bias raters against their reliability weights for coaching review.

### 8. ENG5 Runner Content Upload & Event Hardening (Nov 2025)

- Execute-mode runner now uploads anchor/student essays to Content Service before composing CJ requests.
- Kafka event collector validates envelopes via typed Pydantic models to avoid AttributeError on raw dict payloads.
- docker-compose.eng5-runner wired with CONTENT_SERVICE_URL + content service dependency to keep uploads local when running in container.
