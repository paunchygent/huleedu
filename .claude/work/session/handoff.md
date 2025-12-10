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

Role: You are the lead developer and architect of HuleEdu. The scope of this session is **frontend design** - redesigning the Teacher Dashboard Vue component to match HuleEdu's brutalist design philosophy.

---

### Scope: Teacher Dashboard Design Polish

You are picking up from a session that completed e2e integration:
- BFF Teacher Service → API Gateway → Frontend data flow working
- `TeacherDashboardView.vue` exists but is a **functional stub only** with no design intent
- Dev login, routing, and navigation all working

Your focus is to **redesign the dashboard component** following HuleEdu's design philosophy.

---

### Before Touching Code

**CRITICAL - Read these design references:**

1. **`frontend/styles/src/dashboard_brutalist_final.html`** - **CANONICAL DASHBOARD PROTOTYPE** (use this!)
2. `frontend/styles/src/huleedu-landing-final.html` - landing page prototype
3. `frontend/docs/product/epics/design-spec-teacher-dashboard.md` - UX specification
4. `frontend/docs/product/epics/design-system-epic.md` - general design principles
5. `frontend/docs/FRONTEND.md` - "Purist, fast, semantic" philosophy

**Do NOT copy patterns from existing `.vue` files** - they are functional stubs.

---

### Design Principles (from user)

1. **Dashboard = Hub, not report** - minimal, actionable items only
2. **No clutter** - avoid bombarding users with success/failure/warning/error symbols everywhere
3. **No emoji-heavy "AI slop"** - pure brutalist, professional tool aesthetic
4. **Information hierarchy** - what does the teacher need to act on RIGHT NOW?
5. **Recent batches focus** - show batches not yet processed or just processed
6. **Hard edges, no rounded corners** - brutalist aesthetic throughout

### Key Patterns from `dashboard_brutalist_final.html`

- **Sidebar navigation** - fixed 224px width, ledger-style border-left active states
- **"Kräver åtgärd" section first** - action items with countdown/urgency indicators
- **Ledger table** - 12-column grid for batch overview, minimal status badges
- **Tactile buttons** - `shadow-brutal` with press-down transform on click
- **Subtle cards** - border-only hover for secondary actions
- **Forest green (`#2d4a3e`)** - muted success color, not bright green
- **Functional SVG icons only** - no decorative elements
- **Credits display** in header utility bar

---

### Files to Redesign

| File | Current State | Action |
|------|---------------|--------|
| `frontend/src/views/TeacherDashboardView.vue` | Functional stub | Redesign from scratch |
| `frontend/src/views/DashboardView.vue` | Static placeholder | Consider redesigning |

---

### Testing the Design

```bash
cd frontend && pnpm dev
# Go to http://localhost:5173/login
# Click "Dev Login (bypass auth)"
# Navigate to "Inlamningar" in nav
```

---

### At Session End

Update:
- `TASKS/frontend/vue-3-teacher-dashboard-integration.md` - mark design complete
- `.claude/work/session/handoff.md` - update status and next steps

---

## ALTERNATIVE: Backend Sprint (Phase-2 LLM Provider Batch API)

If frontend design is not the focus, the backend sprint continues below:

### Scope: Phase-2 provider batch API follow-up (CJ single-wave semantics + ENG5 harness)

You are picking up from sessions that:
- Completed Phase‑1 `serial_bundle` and Phase‑2 LPS scaffolding (BatchJob* models, `BatchJobManagerProtocol`, in‑memory manager, and a real `QueueProcessingMode.BATCH_API` path wired through `BatchApiStrategy` and `QueuedRequestExecutor.execute_batch_api`).
- Added negative‑path unit coverage for LPS batch jobs:
  - `test_batch_api_strategy_handles_collect_results_exception`
  - `test_execute_batch_api_handles_job_manager_error`
- Implemented the first slice of CJ `provider_batch_api` semantics:
  - Persist `"llm_batching_mode": <effective_mode.value>` into `CJBatchState.processing_metadata` on initial submission.
  - Resolve the effective batching mode in `workflow_continuation._resolve_batching_mode(...)`.
  - Guard continuation so `comparison_processing.request_additional_comparisons_for_batch(...)` is **never** called when `llm_batching_mode == "provider_batch_api"` (no further waves in this mode).

Your focus is to finish **CJ provider_batch_api single‑wave generation semantics** and to plan/extend **ENG5 Heavy‑C harness coverage** for the new mode.

---

## Current Sprint: Phase-2 LLM Provider Batch API

### Context

- **Phase-1 complete:** serial_bundle mode validated end-to-end in ENG5 suites
- **Phase-2 focus:** Provider-native batch jobs (OpenAI/Anthropic batch APIs)
- **BATCH_API status:** Queue mode uses a dedicated `BatchApiStrategy` + `BatchJobManager` path with per‑request callbacks preserved (`ExecutionOutcome.result ∈ {success,failure,expired}`) and queue metrics labelled `queue_processing_mode="batch_api"`.

### Key TASKs (source of truth)

| TASK | Purpose |
|------|---------|
| `TASKS/integrations/llm-provider-batch-api-phase-2.md` | Phase-2 spec and checklist (2.1-2.5) |
| `TASKS/assessment/cj-llm-provider-batch-api-mode.md` | CJ semantics for provider_batch_api |

### Implementation Focus (Phase 2.3-2.5)

1. **CJ provider_batch_api generation semantics (2.4 – PR1):**
   - Implement “all‑at‑once up to cap” semantics for `provider_batch_api` by:
     - Threading a per‑call pair‑generation threshold (`existing_pairs_threshold`) into `pair_generation.generate_comparison_tasks(...)`.
     - Ensuring `ComparisonBatchOrchestrator.submit_initial_batch(...)` passes `existing_pairs_threshold == max_pairs_cap` when the effective mode is `LLMBatchingMode.PROVIDER_BATCH_API`.
   - Add/extend unit tests (likely in `test_pair_generation_context.py` / a small orchestrator‑focused file) to prove:
     - No more than `max_pairs_cap` unique pairs are generated.
     - `provider_batch_api` initial submission covers the full cap for typical ENG5 nets.

2. **CJ provider_batch_api continuation semantics (2.4 – PR2 follow‑up):**
   - Review and, if necessary, refine `_build_continuation_context` / `decide(...)` so that for `provider_batch_api`:
     - Finalization is driven by callbacks vs denominator/budget caps (no stability‑driven early stop).
     - The newly added guard (`effective_mode == provider_batch_api ⇒ skip request_additional_comparisons_for_batch`) continues to hold.
   - Keep existing PR‑2/PR‑7 semantics untouched for `per_request` and `serial_bundle`.

3. **ENG5 harness planning and initial coverage (2.5):**
   - Decide which ENG5 docker semantics tests (`tests/functional/cj_eng5/test_cj_*_docker.py`) and mock‑profile parity tests (`tests/eng5_profiles/test_*mock_parity*.py`) should grow `provider_batch_api` variants.
   - Plan initial metrics assertions for:
     - CJ: `cj_llm_requests_total{batching_mode="provider_batch_api"}`, `cj_llm_batches_started_total{batching_mode="provider_batch_api"}`.
     - LPS: `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`, `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",result}`.

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

---

## Frontend Integration Status (2025-12-10)

### Vue 3 Teacher Dashboard - Integration Complete, Design Pending

**TASK:** `TASKS/frontend/vue-3-teacher-dashboard-integration.md`

| Component | Status |
|-----------|--------|
| Zod schema (`limit`, `offset`) | Done |
| Service with pagination/filter params | Done |
| Unit tests (5 passing) | Done |
| TeacherDashboardView.vue | Done (functional stub) |
| Router (`/app/inlamningar`) | Done |
| Nav link ("Inlamningar") | Done |
| TypeScript type-check | Pass |
| E2E verification | Pass (dev login → fetch working) |
| **Design polish** | **PENDING - next session** |

**Files modified:**
- `frontend/src/schemas/teacher-dashboard.ts`
- `frontend/src/services/teacher-dashboard.ts`
- `frontend/src/services/teacher-dashboard.spec.ts`
- `frontend/src/views/TeacherDashboardView.vue` (new - functional stub only)
- `frontend/src/views/LoginView.vue` (fixed dev login navigation)
- `frontend/src/router/index.ts`
- `frontend/src/layouts/AppLayout.vue`
- `frontend/vite.config.ts` (fixed proxy to port 8080 + path rewrite)

### CRITICAL: Design Debt

**Current `.vue` files are NOT design references** - they are functional stubs with no design intent.

**Next session must use:** `frontend/styles/src/dashboard_brutalist_final.html` as the canonical prototype.

See "NEXT SESSION INSTRUCTION" above for full design reference list and principles.
