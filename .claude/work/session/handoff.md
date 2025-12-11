# HANDOFF: Current Session Context

## Purpose

This document contains ONLY what the next developer needs to pick up work.
All completed work, patterns, and decisions live in:

- **TASKS/** – Detailed task documentation with full implementation history
- **readme-first.md** – Sprint-critical patterns, ergonomics, quick start
- **AGENTS.md** – Workflow, rules, and service conventions
- **.agent/rules/** – Implementation standards

---

## NEXT SESSION INSTRUCTION

Role: You are the lead developer and architect of HuleEdu. The scope of this session is **Phase‑2 provider_batch_api metrics + ENG5 harness**, building on the now‑fixed CJ callback completion counters and existing BATCH_API execution path.

---

### Scope: Phase‑2 provider_batch_api follow‑up (metrics + ENG5)

You are picking up from sessions that have:
- Implemented LPS `QueueProcessingMode.BATCH_API` and `BatchApiStrategy` with per‑request error mapping.
- Persisted `llm_batching_mode` into `CJBatchState.processing_metadata` and guarded continuation so `provider_batch_api` never schedules extra waves.
- Fixed CJ callback completion counter regressions by realigning `_update_batch_completion_counters` tests to the canonical `BatchCompletionPolicy` implementation (FOR UPDATE row‑locks, partial‑scoring thresholds) and rerunning targeted CJ + LPS unit suites.
- Wired initial LPS job‑level metrics for BATCH_API:
  - `llm_provider_batch_api_jobs_total{provider,model,status}`.
  - `llm_provider_batch_api_items_per_job{provider,model}`.
  - `llm_provider_batch_api_job_duration_seconds{provider,model}`.

Your focus is to:
1. Finish CJ `provider_batch_api` single‑wave semantics (generation + continuation).
2. Extend ENG5 Heavy‑C harness with `provider_batch_api` variants and metrics assertions.
3. Keep existing serial_bundle semantics and metrics untouched.

---

### Before Touching Code

From repo root, read:

1. Rules / architecture:
   - `.agent/rules/000-rule-index.md`
   - `.agent/rules/020.7-cj-assessment-service.md`
   - `.agent/rules/020.13-llm-provider-service-architecture.md`
   - `.agent/rules/071.2-prometheus-metrics-patterns.md`
   - `.agent/rules/075-test-creation-methodology.md`
   - `.agent/rules/101-ci-lanes-and-heavy-suites.md`
2. Sprint context:
   - `.claude/work/session/readme-first.md`
   - `.claude/work/session/handoff.md` (this file)
3. TASKs (source of truth for this work):
   - `TASKS/integrations/llm-provider-batch-api-phase-2.md`
   - `TASKS/assessment/cj-llm-provider-batch-api-mode.md`
   - `TASKS/assessment/cj-batch-state-and-completion-fixes.md` (for completion semantics + counters)

Operate in **Coding + Testing** mode:
- Short written plan first.
- Small, test‑driven changes.
- Run the quality gates from `readme-first.md` at meaningful milestones.

---

### 1. CJ provider_batch_api single‑wave semantics

Goal: ensure `LLMBatchingMode.PROVIDER_BATCH_API` generates all comparisons for a batch **once up to cap**, with no follow‑up COVERAGE/RESAMPLING waves.

Key files:
- `services/cj_assessment_service/cj_core_logic/comparison_batch_orchestrator.py`
- `services/cj_assessment_service/cj_core_logic/pair_generation.py`
- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
- Tests:
  - `services/cj_assessment_service/tests/unit/test_llm_batching_metadata.py`
  - `services/cj_assessment_service/tests/unit/test_pair_generation_context.py`
  - `services/cj_assessment_service/tests/unit/test_batch_state_tracking.py`

Required behavior:
- `ComparisonBatchOrchestrator.submit_initial_batch(...)`:
  - For `LLMBatchingMode.PROVIDER_BATCH_API`, pass an `existing_pairs_threshold` into `pair_generation.generate_comparison_tasks(...)` equal to the `max_pairs_cap` / budget.
  - Ensure initial generation tries to fill the cap in a single wave, respecting uniqueness and any ENG5‑driven net limits.
- `pair_generation.generate_comparison_tasks(...)`:
  - Honor `existing_pairs_threshold` so that `min(global_cap, per_call_cap)` pairs are generated in one call when `provider_batch_api` is in effect.
- Continuation:
  - Keep the guard that skips `request_additional_comparisons_for_batch(...)` when mode is `provider_batch_api`.
  - Ensure finalization is driven purely by callbacks reaching the denominator / cap (no early stability‑driven stop for this mode).

Validation (CJ):
- Re‑run:
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_llm_batching_metadata.py`
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_pair_generation_context.py`
  - Any new CJ unit tests you add around single‑wave semantics.

---

### 2. LPS batch‑API job metrics – follow‑up checks

The previous session wired job‑level metrics via `QueueProcessorMetrics` and `BatchApiStrategy`:
- New metrics in `services/llm_provider_service/metrics.py`:
  - `llm_provider_batch_api_jobs_total` (labels: `provider, model, status`).
  - `llm_provider_batch_api_items_per_job` (labels: `provider, model`).
  - `llm_provider_batch_api_job_duration_seconds` (labels: `provider, model`).
- `QueueProcessorMetrics` helpers:
  - `record_batch_api_job_scheduled(...)` increments `jobs_total{status="scheduled"}` and observes `items_per_job`.
  - `record_batch_api_job_completed(...)` increments `jobs_total{status∈{"completed","failed"}}` and observes `job_duration_seconds`.
- `BatchApiStrategy.execute(...)` now:
  - Records job metrics on dispatch, successful completion, and job‑manager failure.
  - Has unit coverage in `test_batch_api_strategy.py` for both success and failure paths.

Your follow‑up:
- Confirm these metrics behave correctly under more realistic bundle sizes and mixed success/failure item outcomes.
- If needed, extend:
  - `services/llm_provider_service/tests/integration/test_queue_metrics_batch_api.py` to assert that:
    - `llm_provider_batch_api_jobs_total` and `llm_provider_batch_api_items_per_job` produce samples for BATCH_API.

---

### 3. ENG5 Heavy‑C harness – provider_batch_api variants

Goal: add minimal `provider_batch_api` coverage to ENG5 heavy suites while respecting CI lane rules.

Key files:
- Docker semantics tests:
  - `tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py`
  - `tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py`
  - `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`
- Mock profile parity:
  - `tests/eng5_profiles/test_cj_mock_parity_generic.py`
  - `tests/eng5_profiles/test_eng5_mock_parity_full_anchor.py`
  - `tests/eng5_profiles/test_eng5_mock_parity_lower5.py`
- Metrics helper:
  - `tests/utils/metrics_helpers.py`

Steps:
- Decide one CJ docker semantics test and one ENG5 mock‑profile parity test to extend with `provider_batch_api` variants.
- Use `.env` + harness scripts per Rule 101 (Lane C only):
  - `pdm run eng5-cj-docker-suite regular|small-net`
  - `pdm run llm-mock-profile cj-generic|eng5-anchor|eng5-lower5`
- Add assertions via `metrics_helpers.py`:
  - CJ: `cj_llm_requests_total{batching_mode="provider_batch_api"}`, `cj_llm_batches_started_total{batching_mode="provider_batch_api"}`.
  - LPS: `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`, plus the new job metrics.

Keep heavy suites opt‑in and aligned with `.agent/rules/101-ci-lanes-and-heavy-suites.md`.

---

### 4. Housekeeping & Documentation

Before ending your session:
- Re‑run quality gates from repo root:
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`
  - `pdm run validate-tasks`
  - `pdm run python scripts/task_mgmt/validate_front_matter.py --verbose`
  - `pdm run python scripts/docs_mgmt/validate_docs_structure.py --verbose`
- Update TASKs:
  - `TASKS/integrations/llm-provider-batch-api-phase-2.md` with any newly completed checkboxes (CJ single‑wave semantics, ENG5 coverage).
  - `TASKS/assessment/cj-llm-provider-batch-api-mode.md` if you change CJ behavior.
- Keep this file (`.claude/work/session/handoff.md`) in sync with what you actually implemented.

Finally, write a new **NEXT SESSION INSTRUCTION** for your successor:
- Start with: “Role: You are the lead developer and architect of HuleEdu…”
- Summarize what remains (e.g., deeper ENG5 coverage, production provider wiring).
- Remind them to update TASK docs, rerun quality gates, and update this handoff at the end of their work.

## ALTERNATIVE: Backend Sprint (Phase-2 LLM Provider Batch API)

If frontend design is not the focus, the backend sprint continues below:

### Scope: Phase-2 provider batch API follow-up (CJ single-wave semantics + ENG5 harness)

#### Session 2025-12-10 – provider_batch_api code review (no new code)

- Performed a focused code review of the Phase‑2 slice for:
  - LPS `BatchApiStrategy.execute(...)` + `QueuedRequestExecutor.execute_batch_api(...)` error-path semantics (job-manager failures now yield per-request `result="failure"` outcomes via `handle_request_hule_error(...)`, with `queue_processing_mode="batch_api"` metrics/log labels).
  - CJ `provider_batch_api` metadata persistence (`llm_batching_mode` in `CJBatchState.processing_metadata`) and continuation guards that prevent additional COVERAGE/RESAMPLING waves when `llm_batching_mode == "provider_batch_api"`.
  - Runbooks (`eng5-np-runbook.md`, `cj-assessment-runbook.md`) and TASK docs for consistency with the implemented behaviour.
- Findings recorded in `.claude/archive/code-reviews/phase-2-provider-batch-api-2025-12-10.md`; no behavioural changes were made in this session.
- Next backend slice remains unchanged:
  - Implement true **single-wave generation up to cap** for `provider_batch_api` in CJ (`ComparisonBatchOrchestrator.submit_initial_batch(...)` + pair generation thresholds).
  - Extend ENG5 Heavy‑C harness with `provider_batch_api` variants and metrics assertions once LPS job-level metrics are wired.

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
| `.agent/rules/020.7-cj-assessment-service.md` | CJ architecture |
| `.agent/rules/020.13-llm-provider-service-architecture.md` | LPS architecture |
| `.agent/rules/070-testing-and-quality-assurance.md` | Testing standards |
| `.agent/rules/071.2-prometheus-metrics-patterns.md` | Metrics conventions |
| `.agent/rules/101-ci-lanes-and-heavy-suites.md` | CI strategy |

---

## Cross-Reference

- **Frontend:** `frontend/.claude/work/session/handoff.md`
- **Rules index:** `.agent/rules/000-rule-index.md`
- **Sprint patterns:** `.claude/work/session/readme-first.md`

---

## Frontend Integration Status (2025-12-11)

### Vue 3 Teacher Dashboard - ✅ COMPLETE

**TASK:** `TASKS/frontend/vue-3-teacher-dashboard-integration.md`
**Plan:** `.claude/plans/expressive-squishing-stroustrup.md`

| Component | Status |
|-----------|--------|
| CSS foundation (brutalist patterns) | ✅ Done |
| Pinia stores (dashboard, navigation) | ✅ Done |
| Mock data factory | ✅ Done |
| Layout components (AppHeader, AppSidebar) | ✅ Done |
| UI components (ProgressBar, PulsingDot) | ✅ Done |
| Dashboard components (ActionCard, LedgerRow, LedgerTable, SectionHeader) | ✅ Done |
| Route fix (`/app/dashboard` → TeacherDashboardView) | ✅ Done |
| Swedish copy (diacritics, button labels) | ✅ Done |
| TypeScript type-check | ✅ Pass |
| Production build | ✅ Pass |
| Tailwind v4 hover states | ✅ Fixed |
| LedgerTable grid alignment | ✅ Fixed |

### Tailwind v4 Hover Fix (RESOLVED)

**Problem:** Tailwind v4 uses CSS nesting (`&:hover`) which isn't fully browser-supported.

**Solution applied:**
1. Added `@custom-variant hover (&:hover);` to `frontend/src/styles/main.css:4`
2. Added explicit CSS hover rules for buttons (lines 306-328 in main.css):
   - Secondary button (border-navy → filled navy on hover)
   - Primary button (bg-burgundy → navy on hover)
   - Sidebar button (bg-navy → burgundy on hover)

### LedgerTable Grid Fix (RESOLVED)

**Problem:** Processing rows had `border-l-4` on row div which shifted grid columns.

**Solution:** Moved `border-l-4` from row to first column cell, keeping grid lines aligned.

### Files Created/Modified This Session

**New files:**
- `frontend/src/stores/dashboard.ts`
- `frontend/src/stores/navigation.ts`
- `frontend/src/mocks/dashboard-mocks.ts`
- `frontend/src/components/layout/AppHeader.vue`
- `frontend/src/components/layout/AppSidebar.vue`
- `frontend/src/components/ui/ProgressBar.vue`
- `frontend/src/components/ui/PulsingDot.vue`
- `frontend/src/components/dashboard/ActionCard.vue`
- `frontend/src/components/dashboard/LedgerRow.vue`
- `frontend/src/components/dashboard/LedgerTable.vue`
- `frontend/src/components/dashboard/SectionHeader.vue`

**Modified:**
- `frontend/src/styles/main.css` - Brutalist CSS patterns + hover fixes
- `frontend/src/layouts/AppLayout.vue` - Three-panel layout
- `frontend/src/views/TeacherDashboardView.vue` - Ledger-based design
- `frontend/src/router/index.ts` - Route consolidation

### Prototype Reference

**Source of truth:** `frontend/styles/src/dashboard_brutalist_final.html`

### Next Session Focus

1. **BFF Integration** - Wire real API endpoints via Teacher BFF
2. **WebSocket updates** - Real-time batch status changes
3. **Optional: ESLint setup for Vue frontend**
