# HuleEdu Monorepo - Sprint Context

## Purpose

Sprint-critical patterns, ergonomics, and quick onboarding. This file complements:
- **handoff.md** – What the next developer should work on
- **AGENTS.md** – Workflow, rules, service conventions
- **TASKS/** – Detailed task documentation

---

## Quick Start

```bash
# Start services (hot-reload)
pdm run dev-build-start

# Restart / recreate specific service
pdm run dev-restart [service]      # Code changes only
pdm run dev-recreate [service]     # Env var changes (rebuilds container)

# Logs
pdm run dev-logs [service]

# Code quality (always in this order)
pdm run format-all
pdm run lint-fix --unsafe-fixes
pdm run typecheck-all

# Tests
pdm run pytest-root services/<service>/tests/
pdm run pytest-root tests/integration/

# Docs & TASKS (docs-as-code)
pdm run validate-docs
pdm run validate-tasks
pdm run index-tasks
```

## Research Tools (Essay Scoring)

```bash
# Install research ML deps
pdm install -G ml-research

# macOS OpenMP runtime for XGBoost
brew install libomp

# Run the whitebox research pipeline CLI
pdm run essay-scoring-research --help

# Readability metrics use TextDescriptives via spaCy (Tier 1 extractor)
```

Note: DeBERTa embeddings require `sentencepiece` + `tiktoken` (included in `ml-research`)
and the first run will download model weights from Hugging Face.

### Hemma Offload (WIP)

Planned workflow (see ADR + runbooks):
- Run `language_tool_service` on Hemma and access via SSH tunnel to `http://127.0.0.1:18085`.
- Run a DeBERTa + spaCy feature offload service on Hemma and access via SSH tunnel to
  `http://127.0.0.1:19000`.

Implemented (2026-02-01):
- Embedding offload server (research-scoped): `scripts/ml_training/essay_scoring/offload/server.py`
- Dockerfile: `scripts/ml_training/essay_scoring/offload/Dockerfile`
- Research CLI flags:
  - `--language-tool-service-url http://127.0.0.1:18085`
  - `--embedding-service-url http://127.0.0.1:19000`

---

## Key Services

| Service | Port | Purpose |
|---------|------|---------|
| API Gateway | 8080 | External API, JWT auth |
| BFF Teacher | 4101 | Teacher dashboard BFF |
| BOS | 5000 | Pipeline coordination |
| BCS | 4002 | Dependency resolution |
| CJ Assessment | 5010 | Comparative judgment |
| LLM Provider | 8080 | LLM abstraction layer |
| Result Aggregator | 4003 | Results compilation |
| CMS | 5002 | Class management |
| File Service | 7001 | File storage |

---

## Sprint-Critical Patterns

### CJ Assessment

**Batch completion math:**
- `CJBatchState` owns `total_budget` and comparison counters
- Always use `completion_denominator()` as single source of truth
- Continuation logic: `workflow_context.py` → `workflow_decision.py` → `workflow_continuation.py`

**Positional fairness (current focus):**
- `FairComplementOrientationStrategy` handles A/B position assignment
- `pair_generation_mode` column tracks COVERAGE vs RESAMPLING pairs
- See `TASKS/assessment/cj-resampling-a-b-positional-fairness.md`

**Small-net semantics:**
- Nets with `expected_essay_count <= MIN_RESAMPLING_NET_SIZE` trigger Phase-2 resampling
- `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` caps resampling iterations

### Cross-Service Rules

- **HTTP contracts**: Use `common_core` only, never import from `services.<name>`
- **SessionProvider**: All data access via `SessionProviderProtocol.session()` + repository protocols
- **DI**: Use Dishka for all dependency injection

---

## Mock Profiles & ENG5 Suites

| Profile | Use Case | Main Tests |
|---------|----------|-----------|
| `cj_generic_batch` | Regular CJ batch | `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py`, `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py`, `tests/eng5_profiles/test_cj_mock_parity_generic.py` |
| `eng5_lower5_gpt51_low` | LOWER5 small-net | `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`, `tests/eng5_profiles/test_eng5_mock_parity_lower5.py` |
| `eng5_anchor_gpt51_low` | Full anchor nets | `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py` |

**Switching profiles & running ENG5 parity suites:**
```bash
# Validate .env + restart LPS + run profile-specific suite
pdm run llm-mock-profile cj-generic
pdm run llm-mock-profile cj-generic-batch-api
pdm run llm-mock-profile eng5-anchor
pdm run llm-mock-profile eng5-lower5
```

**CJ docker semantics (small + regular nets):**
```bash
# Recreate CJ + LPS, then run small-net + regular-batch CJ docker tests
pdm run eng5-cj-docker-suite           # all
pdm run eng5-cj-docker-suite small-net # only LOWER5 small-net
pdm run eng5-cj-docker-suite regular   # only regular ENG5 batch
pdm run eng5-cj-docker-suite batch-api # regular-batch provider_batch_api variant
```

All individual tests remain runnable via `pytest-root`, for example:
```bash
pdm run pytest-root tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py -m "docker and integration" -v
pdm run pytest-root tests/eng5_profiles/test_eng5_mock_parity_lower5.py -m "docker and integration" -v
```

**Metrics helper for ENG5 CJ & parity suites:**
- Use `tests/utils/metrics_helpers.py` to fetch `/metrics` and parse Prometheus text into a simple `metric_name -> list[(labels, value)]` structure when adding or extending Prometheus assertions in:
  - `tests/functional/cj_eng5/test_cj_*_docker.py`
  - `tests/eng5_profiles/test_*eng5_mock_parity*.py`

**CI staging for ENG5 heavy suites (separate from default CI):**
- `ENG5 CJ Docker Semantics (regular + small-net)` (`eng5-cj-docker-regular-and-small-net` in `.github/workflows/eng5-heavy-suites.yml`)
  - Reproduces locally with:
    ```bash
    pdm run eng5-cj-docker-suite regular
    pdm run eng5-cj-docker-suite small-net
    pdm run eng5-cj-docker-suite batch-api
    ```
- `ENG5 Mock Profile Parity Suite` (`eng5-profile-parity-suite` in `.github/workflows/eng5-heavy-suites.yml`)
  - Reproduces locally with:
    ```bash
    pdm run llm-mock-profile cj-generic
    pdm run llm-mock-profile cj-generic-batch-api
    pdm run llm-mock-profile eng5-anchor
    pdm run llm-mock-profile eng5-lower5
    ```

---

## Troubleshooting

**Container not picking up .env changes:**
```bash
pdm run dev-recreate [service]  # NOT dev-restart
```

**Integration test failures:**
```bash
docker ps | grep huleedu        # Check services running
curl http://localhost:<port>/healthz
pdm run dev-logs [service]
```

**Host port resets (Docker Desktop, long-lived infra):**
```bash
# If you see "Connection reset by peer" when tests hit Redis/Kafka/Postgres
docker restart huleedu_redis
docker restart huleedu_kafka
docker restart huleedu_cj_assessment_db
```

**Database access:**
```bash
source .env  # Required first
docker exec huleedu_<service>_db psql -U "$HULEEDU_DB_USER" -d <db_name>
```

**Codex config warning (local):**
If you see a deprecation warning for `[features].web_search_request`, update
`~/.codex/config.toml` to use `web_search = "live"` (or `"cached"` / `"disabled"`).

---

## LLM Configuration

**Default provider:** OpenAI (gpt-5.1)

**Env vars:**
- `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true` – Enable mock LLM (canonical name)
- `LLM_PROVIDER_SERVICE_MOCK_MODE=cj_generic_batch` – Mock profile (default)

**Batching modes:**

| Mode | CJ Env | LPS Env | Status |
|------|--------|---------|--------|
| serial_bundle | `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle` | `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle` | Production |
| provider_batch_api | `=provider_batch_api` | `=batch_api` | Phase-2 (LPS job manager + BATCH_API path implemented; CJ persists `llm_batching_mode`, skips additional waves in this mode, and accepts per-batch overrides from ENG5 `llm_batching_mode_hint` into `BatchConfigOverrides.llm_batching_mode_override`; ENG5 docker/profile harness coverage + metrics assertions implemented – see `tests/functional/cj_eng5/test_cj_regular_batch_provider_batch_api_docker.py` and `tests/eng5_profiles/test_cj_mock_batch_api_metrics_generic.py`) |

**ENG5 metrics guardrails:**
- Queue wait-time: `0 <= avg <= 120s` (broad guardrail for heavy C-lane)
- Serial bundle calls: `>= 1` per profile
- Use `tests/utils/metrics_helpers.py` for Prometheus assertions

---

## Architecture Decisions

1. **Hot-reload**: Quart services use Hypercorn `--reload`, FastAPI services use uvicorn `--reload`
2. **Contracts in common_core**: Services never import from each other
3. **Test organization**: Service tests in `services/<name>/tests/`, cross-service in `tests/integration/`

---

## Documentation References

| Topic | Location |
|-------|----------|
| Rules index | `.agent/rules/000-rule-index.md` |
| Migration standards | `.agent/rules/085-database-migration-standards.md` |
| Test methodology | `.agent/rules/075-test-creation-methodology.md` |
| CJ runbook | `docs/operations/cj-assessment-runbook.md` |
| ENG5 runner | `docs/operations/eng5-np-runbook.md` |
