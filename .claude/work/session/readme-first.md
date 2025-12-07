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
```

---

## Key Services

| Service | Port | Purpose |
|---------|------|---------|
| API Gateway | 8000 | External API, JWT auth |
| BOS | 8001 | Pipeline coordination |
| BCS | 8002 | Dependency resolution |
| ELS | 8003 | Phase outcome tracking |
| CJ Assessment | 8010 | Comparative judgment |
| LLM Provider | 8011 | LLM abstraction layer |
| Result Aggregator | 8020 | Results compilation |

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

## Mock Profiles (Docker Tests)

| Profile | Use Case | Test File |
|---------|----------|-----------|
| `cj_generic_batch` | Regular batch tests | `test_cj_regular_batch_resampling_docker.py` |
| `eng5_lower5_gpt51_low` | LOWER5 small-net | `test_cj_small_net_continuation_docker.py` |
| `eng5_anchor_gpt51_low` | Full anchor tests | `test_eng5_mock_parity_full_anchor.py` |

**Switching profiles:**
```bash
# Set profile in .env, then:
pdm run dev-recreate llm_provider_service  # Required for env changes
pdm run llm-mock-profile <profile>         # Validates + runs tests
```

**Profile verification:**
```bash
curl http://localhost:8011/admin/mock-mode
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

**Database access:**
```bash
source .env  # Required first
docker exec huleedu_<service>_db psql -U "$HULEEDU_DB_USER" -d <db_name>
```

---

## Architecture Decisions

1. **Hot-reload**: All Quart services use Hypercorn with `--reload`
2. **Contracts in common_core**: Services never import from each other
3. **Test organization**: Service tests in `services/<name>/tests/`, cross-service in `tests/integration/`

---

## Documentation References

| Topic | Location |
|-------|----------|
| Rules index | `.claude/rules/000-rule-index.md` |
| Migration standards | `.claude/rules/085-database-migration-standards.md` |
| Test methodology | `.claude/rules/075-test-creation-methodology.md` |
| CJ runbook | `docs/operations/cj-assessment-runbook.md` |
| ENG5 runner | `docs/operations/eng5-np-runbook.md` |
