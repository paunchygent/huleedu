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

### ⚠️ ACTIVE: LLM Prompt Construction Issues

**Status**: Core implementation complete ✅ | Known issues require resolution ⚠️

**Problem**: CJ Assessment Service was sending **generic hardcoded prompts** to LLM judges, completely ignoring:
- Assessment instructions from `assessment_instructions.instructions_text`
- Student prompt context from `student_prompt_storage_id`
- Assignment-specific rubrics and criteria

**Implementation Complete (2025-11-12)**:
1. ✅ Added `_fetch_assessment_context()` to fetch instructions + student prompt
2. ✅ Updated `_build_comparison_prompt()` to include context sections
3. ✅ Fixed Content Service client endpoint (`/v1/content`)
4. ✅ Fixed essay extraction regex (markdown format support)
5. ✅ End-to-end validation: Runner → CJ → LLM → Callbacks working
6. ✅ 12 anchors registered, grade projections possible

**Known Issues Requiring Resolution**:

⚠️ **Issue #1: Wrong Student Prompt Content**
- **Problem**: `student_prompt_text` in `processing_metadata` contains LLM judge rubric, NOT actual student assignment prompt
- **Impact**: LLM judges essays without knowing what students were asked to write about
- **Current**: "Assignment Prompt" section shows "You are an impartial CJ assessor..." (judge instructions)
- **Missing**: Actual student-facing assignment prompt ("Write an essay about role models...")
- **Root Cause**: Semantic confusion - field name implies student prompt but contains judge rubric
- **Task**: `.claude/TASKS/TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md`

⚠️ **Issue #2: Essay Content Duplication**
- **Problem**: Each essay sent twice in every LLM request (once with IDs, once plain)
- **Impact**: Doubles token usage (~50% waste), potentially confuses LLM
- **Flow**:
  1. CJ service includes essays in prompt: `**Essay A (ID: ...):** <text>`
  2. LLM Provider extracts essays from prompt
  3. Anthropic provider appends essays again: `Essay A:\n<text>`
- **Root Cause**: Protocol mismatch - CJ sends complete prompt, LLM Provider expects template
- **Task**: `.claude/TASKS/TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md`

**Current Prompt Structure** (Validated 2025-11-12):
```
**Assignment Prompt:**
<LLM judge rubric> ❌ Wrong content

**Assessment Criteria:**
<ENG5 test criteria> ✓ Correct

**Essay A (ID: ...):** <text> ✓ First inclusion
**Essay B (ID: ...):** <text> ✓ First inclusion

Compare these two essays...

Essay A: <text> ❌ Duplicate
Essay B: <text> ❌ Duplicate
```

**Next Steps**:
- Fix semantic confusion in prompt metadata (Issue #1)
- Resolve protocol mismatch to eliminate duplication (Issue #2)
- Re-run validation with correct prompts
- Verify grade projections with full context

**Files**:
- `services/cj_assessment_service/cj_core_logic/pair_generation.py`
- `services/cj_assessment_service/event_processor.py`
- `services/llm_provider_service/implementations/llm_provider_service_client.py`

---

### ⚠️ OPEN: CJ Service Database Issues

**Remaining Issues (NOT runner bugs)**:
- ❌ **CJ DB schema mismatch**: `error_code` column is PostgreSQL ENUM but SQLAlchemy model uses `String(100)`. Blocks error handling. Fix: CJ migration to convert ENUM→VARCHAR(100)
- ⚠️ **Assignment ID validation**: Verify `00000000-0000-0000-0000-000000000001` exists in CJ `assessment_instructions` table
- ⚠️ **Grade scale registration**: Verify `eng5_np_legacy_9_step` exists in CJ configuration

---

## Next Session Priority

### 🔴 URGENT: Resolve Prompt Construction Issues

**Prerequisite**: Fix Issues #1 & #2 above before validation

**Then Run Full Validation**:
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

**Success Criteria**:
- ✅ LLM prompts include correct student assignment prompt (not judge rubric)
- ✅ No essay content duplication
- ✅ Grade projections calculated correctly
- ✅ Token usage optimized (~50% reduction expected)

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

## How to Continue

1. **Review Current Status**: Check README_FIRST.md for architectural overview
2. **Fix Prompt Issues**: Resolve semantic confusion + protocol mismatch (Task document)
3. **Run Validation**: Execute full ENG5 validation with corrected prompts
4. **Start TASK-002**: Follow validation plan in `TASKS/002-eng5-cli-validation.md`
5. **Service Patterns**: Consult service READMEs for implementation patterns
6. **Project Standards**: Check `.claude/rules/000-rule-index.mdc` for rules

---

## Completed Work (Now in Permanent Docs)

**See README_FIRST.md for**:
- §10: CJ Prompt Context Persistence Hardening (Result monad, typed metadata, fallback hydration)
- §20: ENG5 Runner Infrastructure (Kafka DNS, storage IDs, batch validation)
- §21: Database URL Centralization (Phase 1 complete)

**See TASKS/ for**:
- `CJ_PROMPT_CONTEXT_PERSISTENCE_PLAN.md` (marked complete, all phases done)
