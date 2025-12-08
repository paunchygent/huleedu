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

### Scope: CJ ↔ LPS serial bundling, ENG5/LOWER5 docker suites, and heavy mock separation

**Completed this session (2025-12-07):**
- Moved ENG5 trace-based mock parity tests into `tests/eng5_profiles/`:
  - `test_cj_mock_parity_generic.py`
  - `test_eng5_mock_parity_full_anchor.py`
  - `test_eng5_mock_parity_lower5.py`
  - `test_eng5_profile_suite.py` (orchestrator over the above).
- Kept CJ docker semantics tests in `tests/integration/`:
  - `test_cj_small_net_continuation_docker.py`
  - `test_cj_regular_batch_resampling_docker.py`
  - `test_cj_regular_batch_callbacks_docker.py` (callback counts + preferred_bundle_size invariants).
- Added `scripts/llm_mgmt/eng5_cj_docker_suite.sh` and a PDM alias:
  - `pdm run eng5-cj-docker-suite [all|small-net|regular]`:
    - Recreates `llm_provider_service` + `cj_assessment_service`.
    - Runs LOWER5 small-net and/or regular-batch CJ docker tests.
- Updated:
  - `.claude/work/session/readme-first.md` with the new ENG5/LOWER5 test layout and commands.
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md` with the regular-batch callback test.
  - `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md` paths to `tests/eng5_profiles/...`.
  - `docs/operations/eng5-np-runbook.md` with an **ENG5/CJ serial-bundle test harness** subsection that documents `tests/eng5_profiles/*`, `pdm run eng5-cj-docker-suite`, `pdm run llm-mock-profile <profile>`, and per-file `pytest-root` examples.

**Next session – recommended focus:**
1. Run the ENG5 CJ docker suite under serial_bundle + hints:
   - Ensure `.env` (dev stack) has:
     - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
     - `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`
     - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
   - Run:
     - `pdm run eng5-cj-docker-suite regular`
     - `pdm run eng5-cj-docker-suite small-net`
2. For trace-based ENG5 parity runs, use:
   - `pdm run llm-mock-profile cj-generic`
   - `pdm run llm-mock-profile eng5-anchor`
   - `pdm run llm-mock-profile eng5-lower5`
   and keep these in a separate CI stage from normal docker integration tests.
3. **[NEW] BatchMonitor Separation of Concerns (US-005.6):**
   - Eliminate ~200 lines of duplicated finalization logic in `batch_monitor._trigger_scoring()`
   - Delegate to `BatchFinalizer.finalize_scoring()` for progress >= 80%
   - Add `COMPLETE_FORCED_RECOVERY` status to distinguish monitor-forced completions
   - See: `TASKS/assessment/batchmonitor-separation-of-concerns.md`, `docs/decisions/0022-batchmonitor-separation-of-concerns.md`

**Key files:**
- CJ docker semantics: `tests/integration/test_cj_small_net_continuation_docker.py`, `test_cj_regular_batch_resampling_docker.py`, `test_cj_regular_batch_callbacks_docker.py`
- ENG5 mock parity: `tests/eng5_profiles/*`
- Orchestration scripts: `scripts/llm_mgmt/mock_profile_helper.sh`, `scripts/llm_mgmt/eng5_cj_docker_suite.sh`
- BatchMonitor refactoring: `services/cj_assessment_service/batch_monitor.py`, `services/cj_assessment_service/cj_core_logic/batch_finalizer.py`
- Active tasks:
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`
  - `TASKS/assessment/batchmonitor-separation-of-concerns.md`

---

## BFF Teacher Service (2025-12-08)

**New service added:** `services/bff_teacher_service/`
- FastAPI serving Vue 3 static assets at port 4101
- Docker compose integrated with volume mount for dev
- PDM scripts: `bff-build`, `bff-start`, `bff-logs`, `bff-restart`
- See frontend handoff for details: `frontend/.claude/work/session/handoff.md`

---

## Cross-Reference

- **Frontend session context:** `frontend/.claude/work/session/handoff.md`
- **Git strategy & build:** See `readme-first.md` or `frontend/.claude/work/session/readme-first.md`
