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
- CJ event processor fetches `student_prompt_ref` locally, increments `huleedu_cj_prompt_fetch_failures_total{reason=…}`, and forwards prompt metadata into workflow orchestration.
- CJ repository/models now allow nullable `essay_instructions`; metadata captures `student_prompt_storage_id` for batch auditing (migration `20251106_1845_make_cj_prompt_nullable.py`).
- Tests updated to cover success/failure hydration paths (`pdm run pytest-root services/cj_assessment_service/tests -k 'event_processor or batch_preparation'`) with type safety validated via `pdm run typecheck-all`.

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
## Rater Metrics
- `generate_reports.py` now emits `rater_bias_posteriors_eb.csv` with empirical-Bayes posterior bias per rater on the grade-index scale.
- Use `--bias-correction {on,off}` and `--compare-without-bias` to run EB and legacy consensus side-by-side; each invocation writes into `output/bayesian_consensus_model/<run_label or timestamp>/` by default (override with `--output-dir`), with comparison CSV/JSON saved alongside the bias-on results.
- Each run also saves `rater_bias_vs_weight.png`, highlighting high-bias raters against their reliability weights for coaching review.
