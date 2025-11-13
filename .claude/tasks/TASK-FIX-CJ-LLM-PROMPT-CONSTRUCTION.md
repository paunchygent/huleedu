# Task: Fix CJ Assessment LLM Prompt Construction Issues

> **Autonomous AI Execution Prompt**
>
> 2. **Plan, Then Execute Sequentially** — Produce an explicit plan first. Execute exactly one planned task at a time to 100% completion before moving to the next. Re-plan if new information appears.
>
> 3. **Targeted Validation** — After completing each task, run the narrowest relevant `pdm run` quality checks or pytest nodes (include `-s` when debugging) to validate the change, and document the command and outcome.
>
> 4. **Task Document Updates** — Before ending the session, update this task document with clear progress notes so the next contributor can resume seamlessly. Follow Rule `090-documentation-standards.mdc` for concise, intent-focused updates.
>
> 5. **Rule Adherence** — Apply all referenced architecture, DI, testing, and documentation standards in this file without introducing new patterns or fallbacks.

## Status

**IN PROGRESS** – Phase 1.4 complete (admin rubric endpoints refactored to DI-based auth, tests passing).

**2025-11-13 session notes**
- Identity dev issuer now signs HS256 tokens, so CJ admin CLI can log in directly (no manual `CJ_ADMIN_TOKEN`).
- `_fetch_assessment_context()` ships with rubric-detection heuristics; see `services/cj_assessment_service/cj_core_logic/pair_generation.py`.
- Targeted test run: `pdm run pytest-root services/cj_assessment_service/tests/unit/test_pair_generation_context.py -k legacy` (pass).

## Objective

Fix two critical issues in CJ Assessment → LLM Provider prompt construction:
1. **Missing student assignment prompt**: Currently sending LLM judge rubric labeled as "Assignment Prompt" - actual student-facing assignment prompt never included
2. **Essay duplication**: Essays sent twice in each LLM request (once with IDs, once without)

## Problem Statement

### Issue #1: Misleading Field Name & Missing Student Context

**Current behavior:**
```python
# In processing_metadata
{
    "student_prompt_text": "<LLM judge assessment rubric>",  # WRONG - this is judge instructions
    "student_prompt_storage_id": "58970dee..."
}

# In built prompt
**Assignment Prompt:**
<LLM judge rubric with "You are an impartial Comparative Judgement assessor...">
```

**What LLM actually receives:**
- "Assignment Prompt" section contains judge rubric (how to assess), not student assignment (what to write about)
- No information about what the students were actually asked to write

**What LLM should receive:**
- "Assignment Prompt" section = actual student-facing prompt ("Write an essay about role models...")
- "Assessment Instructions" section = judge rubric (current content)
- Separate system prompt with tool-use instructions

### Issue #2: Essay Duplication

**Current behavior:**
```python
# CJ service builds prompt (pair_generation.py:259-260)
prompt_parts.append(f"**Essay A (ID: {essay_a.id}):**\n{essay_a.text_content}")
prompt_parts.append(f"**Essay B (ID: {essay_b.id}):**\n{essay_b.text_content}")

# LLM Provider extracts essays from this prompt (llm_provider_service_client.py:130-142)
base_prompt, essay_a, essay_b = extraction_result

# Then sends to LLM Provider Service
request_body = {
    "user_prompt": base_prompt,   # Contains essay context from headers
    "essay_a": essay_a,            # Extracted essay text
    "essay_b": essay_b             # Extracted essay text
}

# Anthropic provider appends again (anthropic_provider_impl.py:448-449)
formatted = f"{user_prompt}\n\nEssay A:\n{essay_a}\n\nEssay B:\n{essay_b}"
```

**Result:** Each essay sent twice, doubling token usage and potentially confusing the LLM.

## Desired Outcome

### Correct Prompt Structure

```
SYSTEM PROMPT:
You are an expert essay evaluator. Use the comparison_result tool to provide your analysis.

USER MESSAGE:
**Student Assignment:**
Write an essay about role models and their importance in society.
Demonstrate critical thinking and use relevant examples.

**Assessment Rubric:**
<ENG5 rubric from assessment_instructions>

**Essay A (ID: ELS_...):**
<essay text>

**Essay B (ID: ELS_...):**
<essay text>

Based on the rubric and assignment above, determine which essay better fulfills the requirements.
```

**Key requirements:**
- Student assignment prompt included ONCE in correct location
- Assessment rubric/instructions in separate section
- Essays included ONCE (not duplicated)
- Clear separation of concerns

## Root Cause Analysis

### Data Flow Mapping

```
1. ENG5 Runner → Kafka Event
   student_prompt_ref: StorageReference (points to judge rubric file)

2. Event Processor → Database
   prompt_text = hydrate_from_content_service(student_prompt_ref)
   processing_metadata = {
       "student_prompt_text": prompt_text,  # Actually judge rubric
       "student_prompt_storage_id": storage_id
   }

3. Pair Generation → Prompt Building
   context = _fetch_assessment_context(cj_batch_id)
   # Returns: student_prompt_text (judge rubric), assessment_instructions

   prompt = _build_comparison_prompt(
       essay_a, essay_b,
       assessment_instructions=context["assessment_instructions"],
       student_prompt_text=context["student_prompt_text"]  # Mislabeled
   )

4. CJ Service → LLM Provider Client
   user_prompt = prompt  # Full prompt with essays already included

5. LLM Provider Client → Extraction
   base_prompt, essay_a, essay_b = _extract_essays_from_prompt(user_prompt)

6. LLM Provider Service → Anthropic Provider
   provider._format_comparison_prompt(base_prompt, essay_a, essay_b)
   # Appends essays AGAIN since no {essay_a}/{essay_b} placeholders
```

### Architectural Issues

1. **Semantic confusion**: "student_prompt" field actually contains judge instructions
2. **Missing data**: No field for actual student assignment prompt
3. **Unnecessary extraction**: CJ service includes essays, LLM Provider extracts them, then re-appends them
4. **Protocol mismatch**: CJ client sends structured prompt, LLM Provider expects template with placeholders

## Solution Design

### Phase 1: Separate Student Assignment from Judge Instructions

**Data model changes:**

```python
# In assessment_instructions table (already exists)
assignment_id: str
instructions_text: str  # Keep as-is (assessment rubric for teachers)

# NEW: Store student-facing assignment prompt separately
student_assignment_prompt: str | None  # What students see/respond to

# In processing_metadata
{
    "judge_rubric_text": str,           # Rename from student_prompt_text
    "judge_rubric_storage_id": str,     # Rename from student_prompt_storage_id
    "student_assignment_prompt": str,   # NEW - from assessment_instructions
}
```

**Call sites to update:**

```python
# services/cj_assessment_service/event_processor.py:292
# BEFORE:
"student_prompt_text": prompt_text,

# AFTER:
"judge_rubric_text": prompt_text,
"student_assignment_prompt": assignment_instructions.student_assignment_prompt,

# services/cj_assessment_service/cj_core_logic/pair_generation.py:187
# BEFORE:
student_prompt_text = metadata.get("student_prompt_text")

# AFTER:
judge_rubric = metadata.get("judge_rubric_text")
student_assignment = metadata.get("student_assignment_prompt")

# services/cj_assessment_service/cj_core_logic/pair_generation.py:226
# BEFORE:
return {
    "assessment_instructions": assessment_instructions,
    "student_prompt_text": student_prompt_text,
}

# AFTER:
return {
    "assessment_rubric": assessment_rubric,
    "judge_instructions": judge_rubric,
    "student_assignment_prompt": student_assignment,
}
```

### Phase 2: Remove Essay Duplication

**Option A: CJ Service sends template, LLM Provider fills it**

```python
# CJ service builds template (pair_generation.py)
prompt_template = """
**Student Assignment:**
{student_assignment}

**Assessment Rubric:**
{assessment_rubric}

**Essay A (ID: {essay_a_id}):**
{essay_a}

**Essay B (ID: {essay_b_id}):**
{essay_b}

Compare the essays based on the rubric and assignment.
"""

# LLM Provider client (llm_provider_service_client.py)
# REMOVE: _extract_essays_from_prompt()
# Just send template + essays separately

request_body = {
    "prompt_template": prompt_template,
    "essay_a": essay_a.text_content,
    "essay_a_id": essay_a.id,
    "essay_b": essay_b.text_content,
    "essay_b_id": essay_b.id,
    "student_assignment": student_assignment,
    "assessment_rubric": assessment_rubric,
}
```

**Option B: CJ Service sends complete prompt, LLM Provider uses as-is**

```python
# CJ service builds complete prompt (pair_generation.py)
prompt = _build_comparison_prompt(...)

# LLM Provider client (llm_provider_service_client.py)
# REMOVE: _extract_essays_from_prompt()
# REMOVE: Separate essay_a/essay_b fields

request_body = {
    "user_prompt": prompt,  # Complete, ready to send
    "metadata": {...},
    "llm_config_overrides": {...},
}

# Anthropic provider (anthropic_provider_impl.py)
# REMOVE: _format_comparison_prompt()
# Just use user_prompt directly
```

**Recommended:** Option B (simpler, fewer changes, clearer separation of concerns)

## Implementation Checklist

### Phase 0: Data Correction (PREREQUISITE)
**Status – 2025-11-13 verification:** `docker exec huleedu_cj_assessment_db psql ...` queries show
`cj_batch_uploads.processing_metadata` currently contains only
`student_prompt_storage_id` keys (no inline `student_prompt_text` / `judge_rubric_text`), and
`assessment_instructions` is empty. No migration script is required **yet**, but ENG5 docs/CLI
still tell contributors to upload the rubric file as the student prompt, so fix the docs and
re-run the uploads with the correct assets to keep future data clean.

**Note:** Identity’s dev token issuer now signs tokens with real HS256 signatures using the shared
`JWT_SECRET_KEY`, so the CJ admin CLI can authenticate via `pdm run cj-admin login` without the
manual `CJ_ADMIN_TOKEN` override.
- [x] **Upload correct student assignment prompt** for test assignment (2025-11-13)
  ```bash
  pdm run cj-admin prompts upload \
    --assignment-id 00000000-0000-0000-0000-000000000001 \
    --prompt-file "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/eng5_np_vt_2017_essay_instruction.md"
  ```
- [x] **Verify storage ID updated** in `assessment_instructions` table (`2ff7b21dcbc1403592bd4f2d804c0075` for assignment `00000000-0000-0000-0000-000000000001`)
- [ ] **(Optional)** Draft migration script scaffolding for future regressions
  - Script path: `services/cj_assessment_service/scripts/migrate_prompt_metadata.py`
  - Should hydrate via Content Service if legacy rows ever reappear
- [x] **Update ASSIGNMENT_SETUP.md** to clarify judge rubric vs student prompt (already matched; verified 2025-11-13)
  - Current line 42-45: States "Upload prompt text" but example is rubric file
  - Add section distinguishing student assignment from judge assessment instructions

### Phase 1: Fix Prompt Source (CJ Assessment Service)

**Design Question: Where does judge rubric come from?**

**Option A** (Recommended): Store separately in `assessment_instructions` table
- Add new column: `judge_rubric_storage_id` (references Content Service)
- Upload via admin CLI: `pdm run cj-admin rubric upload --assignment-id ... --rubric-file ...`
- Hydrate during batch creation alongside student prompt
- Clean separation: student sees assignment, teachers see rubric, LLM gets both

**Option B**: Store in settings/config as system prompt override
- Global rubric for all ENG5 assignments
- Less flexible, can't vary by assignment
- Already uploaded as file, would need migration

**Recommended: Option A** - maintains existing pattern, provides flexibility.

- [ ] **Add `judge_rubric_storage_id` column** to `assessment_instructions`
  - Migration: `alembic/versions/XXXX_add_judge_rubric_storage_id.py`
- [ ] **Upload judge rubric file** for test assignment
  ```bash
  pdm run cj-admin rubric upload \
    --assignment-id 00000000-0000-0000-0000-000000000001 \
    --rubric-file "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/llm_prompt_cj_assessment_eng5.md"
  ```
- [ ] **Update `_fetch_assessment_context()`** to hydrate both prompts
  - File: `services/cj_assessment_service/cj_core_logic/pair_generation.py:153-228`
  - Fetch `student_prompt_storage_id` → student assignment (existing)
  - Fetch `judge_rubric_storage_id` → judge instructions (NEW)
  - Return both in context dict
- [ ] **Update `_build_comparison_prompt()`** to use correct labels
  - File: `services/cj_assessment_service/cj_core_logic/pair_generation.py:231-269`
  - "Assignment Prompt" → `student_prompt_text` (actual assignment)
  - "Assessment Rubric" → `judge_rubric` (from config/settings)
- [x] **Add fallback detection** for old data in `_fetch_assessment_context()`
  - Log warning if `student_prompt_text` matches rubric heuristics ("You are an impartial", `comparison_result`, etc.)
  - Move legacy text into `judge_rubric_text` and clear `student_prompt_text` to prevent leakage
- [ ] **Run targeted tests**:
  ```bash
  pdm run pytest-root services/cj_assessment_service/tests/unit/test_pair_generation.py -k prompt_context -s
  ```

### Phase 2: Remove Essay Duplication (Cross-Service Contract)

#### 2a. CJ Assessment Client Changes
- [ ] **Remove essay extraction** from `llm_provider_service_client.py:130-142`
  - Delete `_extract_essays_from_prompt()` method (lines 56-100)
  - Update `generate_comparison()` to send complete prompt only
  - Remove `essay_a`, `essay_b` from request body (keep in metadata for correlation)
- [ ] **Update request payload** (lines 145-160):
  ```python
  request_body = {
      "user_prompt": user_prompt,  # Complete prompt with essays
      "metadata": {
          "essay_a_id": essay_a_id,  # Keep for callback correlation
          "essay_b_id": essay_b_id,
          **request_metadata,
      },
      "llm_config_overrides": {...},
      "correlation_id": str(correlation_id),
      "callback_topic": self.settings.LLM_PROVIDER_CALLBACK_TOPIC,
  }
  ```

#### 2b. LLM Provider Service Contract
- [ ] **Make essay fields optional** in `LLMComparisonRequest`
  - File: `services/llm_provider_service/api_models.py:20-63`
  - Change `essay_a: str` → `essay_a: str | None = None`
  - Change `essay_b: str` → `essay_b: str | None = None`
  - Add deprecation notice in docstring
- [ ] **Update orchestrator** to handle optional essays
  - File: `services/llm_provider_service/implementations/llm_orchestrator_impl.py:180-278`
  - Pass `user_prompt` directly when essays are None
- [ ] **Update queue models** if they serialize essays
  - File: `services/llm_provider_service/queue_models.py`

#### 2c. Provider Implementations
- [ ] **Simplify Anthropic provider** `_format_comparison_prompt()`
  - File: `services/llm_provider_service/implementations/anthropic_provider_impl.py:433-450`
  ```python
  def _format_comparison_prompt(self, user_prompt: str, essay_a: str | None, essay_b: str | None) -> str:
      # If essays already in prompt (CJ-style), use as-is
      if essay_a is None and essay_b is None:
          return user_prompt

      # Otherwise honor template placeholders (backwards compatibility)
      if "{essay_a}" in user_prompt and "{essay_b}" in user_prompt:
          return user_prompt.replace("{essay_a}", essay_a or "").replace("{essay_b}", essay_b or "")

      # Fallback: append essays (old behavior)
      return f"{user_prompt}\n\nEssay A:\n{essay_a}\n\nEssay B:\n{essay_b}"
  ```
- [ ] **Update OpenAI provider** similarly
  - File: `services/llm_provider_service/implementations/openai_provider_impl.py`
- [ ] **Update Google provider** similarly
  - File: `services/llm_provider_service/implementations/google_provider_impl.py`

#### 2d. Tests
- [ ] **Unit tests**: Verify providers handle None essays
  ```bash
  pdm run pytest-root services/llm_provider_service/tests/unit/test_anthropic_provider.py -s
  pdm run pytest-root services/llm_provider_service/tests/unit/test_openai_provider.py -s
  ```
- [ ] **Integration tests**: Queue processor + callback flow
  ```bash
  pdm run pytest-root services/llm_provider_service/tests/integration/ -k queue -s
  ```
- [ ] **CJ service tests**: Updated client contract
  ```bash
  pdm run pytest-root services/cj_assessment_service/tests/unit/test_llm_provider_client.py -s
  ```

### Phase 3: End-to-End Validation
- [ ] **Run type check on both services**:
  ```bash
  pdm run mypy services/cj_assessment_service
  pdm run mypy services/llm_provider_service
  ```
- [ ] **Run full validation with ENG5 runner**:
  ```bash
  pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
    --mode execute \
    --assignment-id 00000000-0000-0000-0000-000000000001 \
    --course-id 00000000-0000-0000-0000-000000000002 \
    --batch-id validation-prompt-fix-$(date +%Y%m%d-%H%M) \
    --max-comparisons 2 \
    --kafka-bootstrap localhost:9093 \
    --await-completion \
    --completion-timeout 120 \
    --verbose
  ```
- [ ] **Verify prompt structure in CJ logs**:
  ```bash
  docker logs huleedu-cj-assessment-1 2>&1 | grep -A10 "Fetched assessment context"
  # Should show: has_student_assignment: True, has_judge_rubric: True
  ```
- [ ] **Verify no duplication in LLM Provider logs**:
  ```bash
  docker logs huleedu-llm-provider-1 2>&1 | grep "essay_a\|essay_b"
  # Should NOT see separate essay_a/essay_b fields in request
  ```
- [ ] **Check token usage** - should be ~50% reduction for essay content

### Phase 4: Documentation Updates
- [ ] **Update HANDOFF.md** - mark issues resolved
- [ ] **Update ASSIGNMENT_SETUP.md** with corrected workflow
  - Clarify: `student_prompt_storage_id` = student assignment (what to write)
  - Add: Judge rubric stored separately in config/settings
- [ ] **Update this task document** with completion notes

## Files to Modify

### Database Migration
- `services/cj_assessment_service/alembic/versions/XXXX_add_student_assignment_prompt.py` (NEW)

### Core Logic
- `services/cj_assessment_service/models_db.py:AssessmentInstruction`
- `services/cj_assessment_service/event_processor.py:_process_cj_assessment_requested()`
- `services/cj_assessment_service/cj_core_logic/pair_generation.py:_fetch_assessment_context()`
- `services/cj_assessment_service/cj_core_logic/pair_generation.py:_build_comparison_prompt()`

### LLM Integration
- `services/cj_assessment_service/implementations/llm_provider_service_client.py:generate_comparison()`
- `services/llm_provider_service/implementations/anthropic_provider_impl.py:generate_comparison()`
- `services/llm_provider_service/implementations/openai_provider_impl.py:generate_comparison()`
- `services/llm_provider_service/implementations/google_provider_impl.py:generate_comparison()`

### Tests
- `services/cj_assessment_service/tests/unit/test_pair_generation.py` (update/add)
- `services/cj_assessment_service/tests/unit/test_event_processor_prompt_context.py` (exists)
- `services/llm_provider_service/tests/unit/test_anthropic_provider.py` (update)

## Architecture Decisions (RESOLVED)

### 1. Student Assignment Prompt Source → **Option B** ✅

**Decision**: Store in `assessment_instructions` table, already wired correctly.

**Current System Reality**:
- `AssessmentInstruction.student_prompt_storage_id` is the single source of truth
- Auto-hydrated into CJ batch metadata during `create_cj_batch()` when `assignment_id` present
  - File: `services/cj_assessment_service/cj_core_logic/batch_preparation.py:60-138`
- Admin CLI and API already exist to upload prompt via Content Service
  - File: `services/cj_assessment_service/api/admin_routes.py:344-477`

**Critical Data Correction Required**:
- Historically the ENG5 CLI instructions told people to upload `llm_prompt_cj_assessment_eng5.md`
  (judge rubric) as the "student prompt"; the real student assignment text lives in
  `eng5_np_vt_2017_essay_instruction.md`.
- 2025-11-13 DB verification shows no inline `student_prompt_text` rows (only
  `student_prompt_storage_id="prompt-storage-llm"` placeholders), so nothing needs migrating
  today, but we still need to re-upload the correct file and fix the docs before new batches are
  registered.

**Action**: Update the docs/CLI flow so assignment uploads point to
`eng5_np_vt_2017_essay_instruction.md`, then re-upload prompts/rubrics for the ENG5 assignment and
only build a migration if future data drifts again.

### 2. Metadata Field Naming → **Keep Existing + Fix Data** ✅

**Decision**: Keep `student_prompt_text` field name, fix data loaded into it.

**Alternative (Not Recommended)**: Rename to `student_assignment_prompt` + `judge_rubric_text`
- Would touch ~25 files: batch prep, pair generation, state manager, all tests
- Requires JSON migration for all existing `processing_metadata` rows
- Adds complexity without architectural benefit

**Rationale**: The field name is correct - the data we load into it is wrong.

### 3. Duplication Fix → **Option B with Contract Coordination** ✅

**Decision**: CJ sends complete prompt, LLM Provider uses as-is.

**Required Contract Changes** (coordinated across services):

#### CJ Assessment Service
- Remove `_extract_essays_from_prompt()` from `llm_provider_service_client.py:90-181`
- Remove `essay_a`/`essay_b` from request payload
- Retain essay IDs in metadata for callback correlation

#### LLM Provider Service
- Update `LLMComparisonRequest` to make `essay_a`/`essay_b` **optional** (not removed)
  - File: `services/llm_provider_service/api_models.py:20-63`
- Update orchestrator: `services/llm_provider_service/implementations/llm_orchestrator_impl.py:180-278`
- Update queue models: `services/llm_provider_service/queue_models.py`
- Maintain backwards compatibility for potential other clients

#### Provider Implementations
- Simplify `_format_comparison_prompt()` to no-op when essays already in prompt
  - Still honor placeholder replacement (`{essay_a}`, `{essay_b}`) if present
  - Files:
    - `services/llm_provider_service/implementations/anthropic_provider_impl.py:74-156`
    - `services/llm_provider_service/implementations/openai_provider_impl.py`
    - `services/llm_provider_service/implementations/google_provider_impl.py`

#### Observability
- Ensure queue processor, callback publisher, and prompt SHA hashing work with CJ-supplied string
  - File: `services/llm_provider_service/implementations/anthropic_provider_impl.py:111-155`

**Coordination Requirement**: Feature branch spanning both services, updated in lockstep.

### 4. Backwards Compatibility → **Data Migration Required** ✅

**Problem**: Existing `processing_metadata` contains wrong content in `student_prompt_text`.

**Solution**: One-time data repair script
```sql
-- Find batches with rubric in student_prompt_text field
SELECT id, bos_batch_id,
       processing_metadata->>'student_prompt_text'
FROM cj_batch_uploads
WHERE processing_metadata->>'student_prompt_text' LIKE 'You are an impartial%';

-- Migrate to correct source (fetch from Content Service using storage_id)
-- Implementation: Python script that hydrates correct text
```

**Fallback Logic**: `_fetch_assessment_context()` should detect old data and log warning.

## Success Criteria

- [ ] LLM prompts include actual student assignment prompt in "Student Assignment" section
- [ ] LLM prompts include assessment rubric in "Assessment Rubric" section
- [ ] Essays appear exactly once in prompts
- [ ] Token usage for essay content reduced by ~50%
- [ ] All tests pass
- [ ] Type checking passes
- [ ] End-to-end validation test succeeds with correct prompt structure
- [ ] Documentation updated

## Notes

- Discovered during end-to-end validation (2025-11-12)
- Related to recent prompt hydration work but separate issues
- Both issues affect all LLM providers (Anthropic, OpenAI, Google)
- Current implementation works but wastes tokens and provides incomplete context to LLM
