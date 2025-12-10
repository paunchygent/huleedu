# HANDOFF: Current Session Context

## Purpose

This document contains ONLY what the next developer needs to pick up work.
All completed work, patterns, and decisions live in:

- **TASKS/** – Detailed task documentation with full implementation history
- **readme-first.md** – Sprint-critical patterns, ergonomics, quick start
- **AGENTS.md** – Workflow, rules, and service conventions
- **.claude/rules/** – Implementation standards

---

## NEXT SESSION INSTRUCTION

Role: You are the lead developer and architect of HuleEdu.

### Scope: Phase-2 provider batch API implementation (CJ semantics + ENG5 harness)

You are picking up from sessions that completed Phase-1 serial_bundle and implemented the initial LPS BatchJob* models, BatchJobManagerProtocol + in-memory manager, and a true `QueueProcessingMode.BATCH_API` path in the LLM Provider Service. Focus on **CJ provider_batch_api semantics and ENG5 harness coverage**.

---

## Current Sprint: Phase-2 LLM Provider Batch API

### Context

- **Phase-1 complete:** serial_bundle mode validated end-to-end in ENG5 suites
- **Phase-2 focus:** Provider-native batch jobs (OpenAI/Anthropic batch APIs)
- **BATCH_API scaffolding:** Queue mode exists, uses serial-bundle executor as compatibility layer

### Key TASKs (source of truth)

| TASK | Purpose |
|------|---------|
| `TASKS/integrations/llm-provider-batch-api-phase-2.md` | Phase-2 spec and checklist (2.1-2.5) |
| `TASKS/assessment/cj-llm-provider-batch-api-mode.md` | CJ semantics for provider_batch_api |

### Implementation Focus (Phase 2.3-2.5)

1. **CJ metadata alignment (2.4):**
   - `_resolve_batching_mode(metadata, settings)` in `workflow_continuation.py`
   - Persist `"llm_batching_mode"` in `processing_metadata`

2. **CJ provider_batch_api continuation semantics (2.4):**
   - Ensure single-wave generation up to `max_pairs_cap` for `provider_batch_api`.
   - Finalize when callbacks hit the denominator/cap without requesting additional waves in this mode.

3. **ENG5 harness planning and initial coverage (2.5):**
   - Document which ENG5 tests will grow `provider_batch_api` variants
   - Define and, where feasible, implement metrics assertions for `queue_processing_mode="batch_api"` and `batching_mode="provider_batch_api"` in Heavy C-lane harnesses

### ADRs & Runbooks

- `docs/decisions/0004-llm-provider-batching-mode-selection.md`
- `docs/operations/eng5-np-runbook.md` (batching section)
- `docs/operations/cj-assessment-runbook.md` (batching modes table)

---

## Validation Sequence

```bash
pdm run format-all
pdm run lint-fix --unsafe-fixes
pdm run typecheck-all
pdm run validate-tasks
pdm run python scripts/task_mgmt/validate_front_matter.py --verbose
pdm run python scripts/docs_mgmt/validate_docs_structure.py --verbose
```

### ENG5 Heavy Suites (separate CI, opt-in)

```bash
# CJ docker semantics
pdm run eng5-cj-docker-suite regular
pdm run eng5-cj-docker-suite small-net

# Mock profile parity
pdm run llm-mock-profile cj-generic
pdm run llm-mock-profile eng5-anchor
pdm run llm-mock-profile eng5-lower5
```

---

## Key Rules to Reference

| Rule | Topic |
|------|-------|
| `.claude/rules/020.7-cj-assessment-service.md` | CJ architecture |
| `.claude/rules/020.13-llm-provider-service-architecture.md` | LPS architecture |
| `.claude/rules/070-testing-and-quality-assurance.md` | Testing standards |
| `.claude/rules/071.2-prometheus-metrics-patterns.md` | Metrics conventions |
| `.claude/rules/101-ci-lanes-and-heavy-suites.md` | CI strategy |

---

## Cross-Reference

- **Frontend:** `frontend/.claude/work/session/handoff.md`
- **Rules index:** `.claude/rules/000-rule-index.md`
- **Sprint patterns:** `.claude/work/session/readme-first.md`
