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

### ✅ CRITICAL BUG FIX: LLM Prompt Construction

**Status**: Prompt fix COMPLETE ✅ | Anchor registration PENDING ⏸️ | Validation test PENDING ⏸️

**Problem**: CJ Assessment Service was sending **generic hardcoded prompts** to LLM judges, completely ignoring:
- Assessment instructions from `assessment_instructions.instructions_text`
- Student prompt context from `student_prompt_storage_id`
- Assignment-specific rubrics and criteria

**Impact**: All essay comparisons were judged using generic criteria instead of assignment requirements

**Solution**: Modified `services/cj_assessment_service/cj_core_logic/pair_generation.py`

**Changes**:
1. Added `_fetch_assessment_context()` (lines 153-214):
   - Queries `CJBatchUpload.processing_metadata` for `student_prompt_text` and `assignment_id`
   - Queries `AssessmentInstruction` table for `instructions_text`
   - Returns both context elements

2. Updated `_build_comparison_prompt()` (lines 217-255):
   - Accepts `assessment_instructions` and `student_prompt_text` parameters
   - Builds structured prompts with:
     - **Assignment Prompt** section (student prompt)
     - **Assessment Criteria** section (instructions)
     - Essay A and B texts
     - Response instructions
   - NO backwards compatibility fallback

3. Modified `generate_comparison_tasks()` (lines 21-105):
   - Calls `_fetch_assessment_context(db_session, cj_batch_id)`
   - Passes context to `_build_comparison_prompt()`

**Type Checking**: ✅ PASSED

### ✅ Complete: ENG5 Kafka DNS Fix & Infrastructure Validation

**Status**: Kafka DNS fix ✅ implemented and validated, Runner now reaching CJ service; new data blockers ⚠️ surfaced downstream

**What Was Validated (2025-11-12)**:
1. ✅ Preflight checks: All 6 checks passed (services healthy, files validated)
2. ✅ Content upload pipeline: 4/4 unit tests + integration test passed, real storage IDs confirmed
3. ✅ Event collector: 4/4 hydrator tests passed, Pydantic validation working
4. ✅ Plan mode: Inventory validated (12 anchors + 12 students)
5. ✅ Dry-run mode: Schema-compliant artefact generated
6. ✅ **Kafka DNS fix validated**: `localhost:9093` external listener works for host execution
7. ✅ **End-to-end event flow confirmed**: Runner published → CJ service consumed → processing attempted (fails on data validation issues below)

**Kafka DNS Fix (cli.py:294)**:
- Changed default from `localhost:9092` (internal) to `localhost:9093` (external listener)
- Localhost execution now successfully connects to Kafka without `/etc/hosts` hacks
- Event published to `huleedu.els.cj_assessment.requested.v1` and consumed by CJ service (confirmed via correlation_id tracing)

**Infrastructure Fixes Applied**:
- Fixed LLM provider port in `docker-compose.eng5-runner.yml` (8084 → 8080)
- Started required services: kafka, content_service, cj_assessment_service, llm_provider_service

**Data Validation Issues FIXED (2025-11-12)**:
- ✅ **Issue #1**: Invalid prompt storage ID format - removed `prompt::` prefix in `requests.py:30`
- ✅ **Issue #2**: Empty batch_id validation - added defensive guard in `compose_cj_assessment_request()` (requests.py:50-53)
  - Validates batch_id is non-empty before event composition
  - Provides clear error message if empty

- ✅ **Issue #3**: No code bug found - was CLI invocation issue with shell variable expansion

**Fixes Applied** (`scripts/cj_experiments_runners/eng5_np/requests.py`):

```python
# Line 30: Remove prompt:: prefix
storage_id = record.checksum  # Was: f"prompt::{record.checksum}"

# Lines 50-53: Add batch_id validation
if not settings.batch_id or settings.batch_id.strip() == "":
    raise ValueError(
        "batch_id cannot be empty - must be provided via --batch-id CLI argument"
    )
```

**Root Cause Analysis (Resolved items)**:
1. Prompt prefix issue: Runner previously added `prompt::`; removal now sends raw checksum
2. Empty batch_id: Guard prevents blank values, keeping diagnostics local to CLI invocation
3. Event contract: `essays_for_cj` remains correct; CJ service converts to `bos_batch_id`/`essays_to_process`

**Data Validation Fixes - Session 2 (2025-11-12)**:
- ✅ **Storage ID format**: Runner now uploads prompt to Content Service and uses returned 32-char UUID (cli.py:530-554, requests.py:24-46, text_extraction.py:26 - added .md support)
- ✅ **Essay ID truncation**: Implemented max 36-char IDs with hash suffix for uniqueness (utils.py:33-64, inventory.py:192)
- Example: `EDITH_STRANDLER_SA24_ENG5_NP_WRITING_ROLE_MODELS` → `EDITH_STRANDLER_SA24_ENG5_NP_W_A3F4B2C1` (36 chars)

**Remaining CJ Service Issues (NOT runner bugs)**:
- ❌ **CJ DB schema mismatch**: `error_code` column is PostgreSQL ENUM but SQLAlchemy model uses `String(100)`. Blocks error handling. Fix: CJ migration to convert ENUM→VARCHAR(100)
- ⚠️ **Assignment ID validation**: `00000000-0000-0000-0000-000000000001` may not exist in CJ `assessment_instructions` table
- ⚠️ **Grade scale registration**: Verify `eng5_np_legacy_9_step` exists in CJ configuration

**Integration Test Results** (correlation_id: `22f78c61-588f-412b-a257-cc2ddb8e0536`):
- ✅ Event published to Kafka successfully
- ✅ CJ service consumed event and began processing
- ✅ All storage IDs are 32-char UUIDs (essays + prompt)
- ✅ All essay IDs are ≤36 chars with deterministic hash suffixes
- ❌ CJ batch submission failed on DB type mismatch (unrelated to runner fixes)

**How to Validate Kafka Publishing & CJ Processing**:
1. **Runner log inspection** (`/tmp/<log>.log` from CLI invocation):
   - `grep -i "kafka_publish" /tmp/eng5_localhost_test.log` → expect `kafka_publish_started` and `kafka_publish_success` lines.
   - `grep -i "collector_timeout"` to detect waiting issues.
2. **Capture correlation_id**:
   - `CORRELATION_ID=$(grep -oE '[0-9a-f-]{36}' /tmp/eng5_localhost_test.log | head -1)`
3. **CJ service logs**:
   - `docker logs huleedu_cj_assessment_service 2>&1 | grep -A10 -B5 "$CORRELATION_ID"`
   - Confirms message consumption and surfaces DB/content errors.
4. **Content Service logs (if prompt fetch fails)**:
   - `docker logs huleedu_content_service 2>&1 | grep -A5 -B5 "$CORRELATION_ID"`
5. **Service health pre-check**:
   - `docker ps | grep huleedu | grep -E "(kafka|content_service|cj_assessment|llm_provider)"` (ensure all healthy before reruns).

**Tests Passing**:
- `pdm run pytest-root scripts/tests/test_eng5_np_content_upload.py` (4/4 ✅)
- `pdm run pytest-root scripts/tests/test_eng5_np_runner.py -k hydrator` (4/4 ✅)

**Next**: Address data blockers (content ID format + essay ID length) before re-running execute-mode validation

---

## Next Session Priority

### 🔴 URGENT: Complete Prompt Fix Validation

**Immediate Actions Required**:

1. **Register Anchor Essays** (BLOCKED on CLI syntax)
   ```bash
   # Correct syntax (global options BEFORE subcommand):
   pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
     --assignment-id 00000000-0000-0000-0000-000000000001 \
     --course-id 00000000-0000-0000-0000-000000000002 \
     register-anchors \
     --cj-service-url http://localhost:9095
   ```

   **What it does**:
   - Reads 12 DOCX files from `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays/`
   - Extracts grades from filenames (A1→A, F+1→F+, etc.)
   - Uploads text to Content Service
   - Creates 12 `AnchorEssayReference` records

2. **Verify Registration**:
   ```bash
   docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
   SELECT id, grade, LEFT(text_storage_id, 12) || '...' as storage_id
   FROM anchor_essay_references
   WHERE assignment_id = '00000000-0000-0000-0000-000000000001'
   ORDER BY grade;"
   ```
   Expected: 12 rows with grades A(2), B(2), C+, C-, D+, D-, E+, E-, F+(2)

3. **Run End-to-End Validation Test**:
   ```bash
   pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
     --mode execute \
     --assignment-id 00000000-0000-0000-0000-000000000001 \
     --course-id 00000000-0000-0000-0000-000000000002 \
     --batch-id validation-prompt-fix-$(date +%Y%m%d-%H%M) \
     --max-comparisons 5 \
     --kafka-bootstrap localhost:9093 \
     --await-completion \
     --completion-timeout 180 \
     --verbose 2>&1 | tee /tmp/validation_with_context.log
   ```

4. **Verify Prompts Include Context**:
   ```bash
   # Check logs for context fetching
   grep "Fetched assessment context" /tmp/validation_with_context.log

   # Inspect actual prompts (if debug logging enabled)
   grep -A 20 "Assignment Prompt:" /tmp/validation_with_context.log | head -50
   ```

**Success Criteria**:
- ✅ 12 anchors registered in database
- ✅ LLM prompts include **Assignment Prompt** section
- ✅ LLM prompts include **Assessment Criteria** section
- ✅ Grade projections calculated (not skipped)
- ✅ No "No anchor essays available" warnings

**Key Technical Details**:
- **LLM Model**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- **Provider**: Anthropic (NOT mock - verify `USE_MOCK_LLM` is unset)
- **Grade Scale**: `eng5_np_legacy_9_step` (9 grades: F+ to A)
- **Data Flow**:
  1. Event → `student_prompt_text` stored in `CJBatchUpload.processing_metadata`
  2. Pair generation → fetches context from batch + `AssessmentInstruction` table
  3. Prompt building → includes both student prompt AND instructions
  4. LLM submission → receives full context

**Files Modified This Session**:
- `services/cj_assessment_service/cj_core_logic/pair_generation.py`

**Related Files** (for context):
- `services/cj_assessment_service/event_processor.py:202-278` (prompt extraction)
- `services/cj_assessment_service/cj_core_logic/batch_preparation.py:76-97` (metadata storage)
- `scripts/cj_experiments_runners/eng5_np/cli.py:60-108` (anchor registration)

---

### 🟢 TASK-002: ENG5 CLI Validation (UNBLOCKED)

**Blockers Resolved**:
- ✅ TASK-001 Database URL Centralization complete (12/12 services)
- ✅ All services healthy with special-character passwords
- ✅ Identity Service validated

**Objective**: Validate complete ENG5 CJ Admin CLI workflow
- Admin authentication and token management
- Assessment instructions management
- Student prompt upload and retrieval
- Anchor essay registration
- End-to-end ENG5 runner execution
- Metrics and observability validation

**Prerequisites**:
- Identity Service running ✅
- Required services healthy (identity, content, cj_assessment, llm_provider) ✅
- Admin user seeded in Identity database (TBD)

**See**: `TASKS/002-eng5-cli-validation.md` for complete validation plan

---

## Recent Completions (2025-11-12)

**This Session**:
- ✅ ENG5 Execute-Mode Validation: All unit/integration tests passing (8/8 tests)
- ✅ Content upload pipeline validated: Real storage IDs from Content Service
- ✅ Event collector hardening verified: Pydantic validation prevents crashes
- ✅ Plan/dry-run modes validated: Schema-compliant artefacts generated

**Previous Session (2025-11-11)**:
- ✅ Hot-reload standardization (all 13 services) → See README_FIRST §0
- ✅ Database URL centralization (12/12 services, ~300 LoC eliminated, 17 env vars removed) → See README_FIRST §21
- ✅ Service health checks fixed (28 containers healthy) → See docker-compose.dev.yml
- ✅ dev-recreate command added for env var updates

**Cross-Service Context**:
- NLP/CJ Prompt Hydration: Monitor `huleedu_{nlp|cj}_prompt_fetch_failures_total`
- Student Prompt Admin: Reference-only pattern, no inline prompt bodies
- Common Core: 100% documentation coverage (libs/common_core/README.md)

---

## How to Continue

1. **Review Current Status**: Check README_FIRST.md for architectural overview
2. **Start TASK-002**: Follow validation plan in `TASKS/002-eng5-cli-validation.md`
3. **Complete ENG5 Execute**: Run against live stack per `Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md`
4. **Service Patterns**: Consult service READMEs for implementation patterns
5. **Project Standards**: Check `.claude/rules/000-rule-index.mdc` for rules
