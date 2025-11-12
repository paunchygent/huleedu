# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks, architectural decisions, and patterns are documented in:

- **README_FIRST.md** - Architectural overview, decisions, service status
- **Service READMEs** - Service-specific patterns, error handling, testing
- **.claude/rules/** - Implementation standards and requirements
- **Documentation/OPERATIONS/** - Operational runbooks
- **TASKS/** - Detailed task documentation

---

## Current Session Work (2025-11-12)

### ✅ Admin surface refactor
- `services/cj_assessment_service/api/admin_routes.py` removed in favour of modular blueprints (`api/admin/{instructions,student_prompts,judge_rubrics}.py`) wired from `app.py:108`.
- Unit suites now sign JWTs locally (`test_admin_routes.py:240`, `test_admin_prompt_endpoints.py:246`, `test_admin_rubric_endpoints.py:32`) – no shared helpers or monkeypatching.
- CLI rubric export normalised without casts (`cli_admin.py:620`).

### ✅ Phase 2 prompt hydration (CJ service scope)
- Batch creation stores both student prompt and judge rubric metadata (`cj_core_logic/batch_preparation.py:60`).
- Event processor hydrates judge rubric text into `converted_request_data` (`event_processor.py:237`).
- Pair generation prompt now renders **Student Assignment / Assessment Criteria / Judge Instructions** once each (`cj_core_logic/pair_generation.py:238`).
- Unit coverage added for rubric hydration + prompt composition (`tests/unit/test_event_processor_prompt_context.py:226`, `test_pair_generation_context.py:100`, `test_batch_preparation_identity_flow.py:332`).

### 🚧 Outstanding
- Phase 0 data correction (re-upload prompts, migration script, ASSIGNMENT_SETUP.md clarification) **not started**; DB was rebuilt pre-migrations so the migration script can be skipped, but uploads/docs still pending.
- Phase 1 “legacy fallback” (detect old `student_prompt_text` containing rubric copy) still TODO.
- Phase 2 contract work (remove essay duplication, update LLM Provider request schema/providers/tests) untouched.
- Phase 3 validation (mypy/pytest sweeps, ENG5 smoke) not run beyond targeted suites above.
- `TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` still lists Phase 0/Phase 2/Phase 3 tasks as open; needs update once next steps decided.

## Next Steps
1. Perform Phase 0 uploads + documentation tidy-up; note migration script is unnecessary thanks to DB reset.
2. Add guardrails in `_fetch_assessment_context()` for legacy batches and log remediation guidance.
3. Execute Phase 2 contract changes (CJ client payload, LLM Provider API models, providers, associated tests).
4. Complete Phase 3 validation runs and capture token-usage verification once contract work lands.
5. Update `.claude/tasks/TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` with current status and revised plan.
