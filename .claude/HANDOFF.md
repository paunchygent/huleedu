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

### ✅ JWT Configuration Fix & Validation Tooling
**Root Cause:** Commit `6ccfb9b4` (Nov 9) added `JWTValidationSettings` to CJ Assessment Service config but docker-compose was never updated with required `JWT_SECRET_KEY` environment variable.

**Symptoms:** Admin endpoints returned 500 errors with misleading "Authorization header required" → "JWT verification key not configured" errors.

**Fix Applied:**
- Added `CJ_ASSESSMENT_SERVICE_JWT_SECRET_KEY=${JWT_SECRET_KEY}` to `docker-compose.services.yml:409`
- Fixed API Gateway: changed `JWT_SECRET_KEY` → `API_GATEWAY_JWT_SECRET_KEY` (line 448)

**New Tooling:**
- Created `scripts/validate_service_config.py` - validates service configs against docker-compose
- Checks: JWT requirements, database config, Kafka config, port conflicts
- Usage: `pdm run validate-config` (added to pyproject.toml)
- Caught both JWT misconfigurations immediately on first run

**Pattern Established:**
- Services inheriting `JWTValidationSettings` MUST have `<ENV_PREFIX>JWT_SECRET_KEY` in docker-compose
- Current services requiring JWT: `api_gateway_service`, `cj_assessment_service`
- Validation script enforces this pattern automatically

### ✅ Admin surface refactor
- `services/cj_assessment_service/api/admin_routes.py` removed in favour of modular blueprints (`api/admin/{instructions,student_prompts,judge_rubrics}.py`) wired from `app.py:108`.
- Unit suites now sign JWTs locally (`test_admin_routes.py:240`, `test_admin_prompt_endpoints.py:246`, `test_admin_rubric_endpoints.py:32`) – no shared helpers or monkeypatching.
- CLI rubric export normalised without casts (`cli_admin.py:620`).

### ✅ Phase 2 prompt hydration (CJ service scope)
- Batch creation stores both student prompt and judge rubric metadata (`cj_core_logic/batch_preparation.py:60`).
- Event processor hydrates judge rubric text into `converted_request_data` (`event_processor.py:237`).
- Pair generation prompt now renders **Student Assignment / Assessment Criteria / Judge Instructions** once each (`cj_core_logic/pair_generation.py:238`).
- Unit coverage added for rubric hydration + prompt composition (`tests/unit/test_event_processor_prompt_context.py:226`, `test_pair_generation_context.py:100`, `test_batch_preparation_identity_flow.py:332`).

### ✅ ENG5 assignment bootstrap (Phase 0 partial)
- Identity dev tokens now use real HS256 signatures, so `pdm run cj-admin login` works without overrides; used the CLI to upsert assignment `00000000-0000-0000-0000-000000000001` with grade scale `eng5_np_legacy_9_step`.
- Uploaded the correct student assignment prompt (`eng5_np_vt_2017_essay_instruction.md`) via `pdm run cj-admin prompts upload …`, producing Content Service storage ID `2ff7b21dcbc1403592bd4f2d804c0075` (visible in `assessment_instructions.id=1`).
- All ENG5 docs now call out the correct prompt vs. rubric mapping; no DB migration needed because there were no inline prompt texts.

### ✅ Phase 1 legacy fallback heuristics
- `_fetch_assessment_context()` now detects mis-labelled student prompts (look for phrases such as “You are an impartial …”, `comparison_result`, etc.), logs remediation guidance, and migrates the detected text into `judge_rubric_text` so the prompt doesn’t include rubric instructions twice (`cj_core_logic/pair_generation.py`).
- Added `test_fetch_assessment_context_detects_legacy_prompt` under `services/cj_assessment_service/tests/unit/test_pair_generation_context.py` to lock in the safety net.


- **New Task**: See `TASKS/infrastructure/TASK-IDENTITY-RS256-JWT-ROLLOUT.md` for the production RS256 migration plan (captures key distribution + JWKS plumbing so we don’t regress).

### 🚧 Outstanding
- Phase 2 contract work (remove essay duplication, update LLM Provider request schema/providers/tests) untouched.
- Phase 3 validation (mypy/pytest sweeps, ENG5 smoke) not run beyond targeted suites above.
- `TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` still lists Phase 0/Phase 2/Phase 3 tasks as open; needs update once next steps decided.

## Next Steps
1. Finish Phase 0 doc tidy-up (migration script optional; ENG5 assets already corrected).
2. Execute Phase 2 contract changes (CJ client payload, LLM Provider API models, providers, associated tests).
3. Complete Phase 3 validation runs and capture token-usage verification once contract work lands.
4. Update `.claude/tasks/TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` with current status and revised plan.

## Task Management Utilities (TASKS/)

- Scripts live under `scripts/task_mgmt/` and are harness-independent for LLM Agents.
- Common commands:
  - Create: `python scripts/task_mgmt/new_task.py --title "Title" --domain frontend`
  - Validate: `python scripts/task_mgmt/validate_front_matter.py --verbose`
  - Index: `python scripts/task_mgmt/index_tasks.py`
  - Archive: `python scripts/task_mgmt/archive_task.py --path TASKS/<relative-path>.md [--git]`
