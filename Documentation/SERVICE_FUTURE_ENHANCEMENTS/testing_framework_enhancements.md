# Testing Framework Enhancements

## Experimental Judge Rubric Override Feature

### Overview

Research runners need the ability to test alternative judge rubrics without modifying the canonical database rubrics. This feature will allow experimental overrides to be passed via `LLMConfigOverrides`, maintaining database integrity while enabling research flexibility.

### Current Implementation Status

**Completed:**
-  Fix 1: Corrected ENG5 runner file path to use actual student assignment (`eng5_np_vt_2017_essay_instruction.md`) instead of judge rubric

**Pending Implementation:**
- ó Fix 2: Add experimental judge rubric override field
- ó Fix 3: Apply experimental override in pair generation

---

## TODO: Fix 2 - Add Experimental Judge Rubric Override Field

### File
`libs/common_core/src/common_core/events/cj_assessment_events.py`

### Implementation
Add to `LLMConfigOverrides` class (around line 107):

```python
experimental_judge_rubric: str | None = Field(
    default=None,
    description="Experimental judge rubric override for research (bypasses DB canonical rubric)",
)
```

### Purpose
- Allows research runners to test alternative rubrics without database modifications
- Production pipeline continues using database as canonical source
- Maintains clear separation between experimental and production configurations

### Context
When research runners like ENG5 want to test a different rubric (e.g., `llm_prompt_cj_assessment_eng5.md`), they should pass it as an experimental override rather than attempting to upload it via `student_prompt_ref` field.

---

## TODO: Fix 3 - Apply Experimental Override in Pair Generation

### File
`services/cj_assessment_service/cj_core_logic/pair_generation.py`

### Implementation
In `_fetch_assessment_context()` function (around line 240), after fetching DB rubric:

```python
# Fetch canonical rubric from DB (production default)
judge_rubric_storage_id, db_judge_rubric_text = await _hydrate_judge_rubric_context(...)

# Allow experimental override for research runners
if llm_config_overrides and llm_config_overrides.experimental_judge_rubric:
    judge_rubric_text = llm_config_overrides.experimental_judge_rubric
else:
    judge_rubric_text = db_judge_rubric_text
```

### Purpose
- Applies experimental rubric when provided via `LLMConfigOverrides`
- Falls back to database canonical rubric for production workflows
- Maintains backward compatibility with existing production pipelines

### Benefits
1. **Research Flexibility**: Test alternative rubrics without touching production data
2. **Data Integrity**: Database remains canonical source for production
3. **Clear Intent**: Explicit field name indicates experimental nature
4. **Audit Trail**: Override usage can be logged for research transparency

---

## Related Issues Fixed

### ENG5 Runner Student Assignment Missing from Prompts

**Problem:**
The **Student Assignment** section was missing from comparison prompts sent to LLM, reducing assessment accuracy.

**Root Cause:**
ENG5 runner file path misconfiguration in `scripts/cj_experiments_runners/eng5_np/paths.py:31`:
```python
prompt_path = "llm_prompt_cj_assessment_eng5.md"  # L Judge rubric (wrong usage!)
```

**Solution:**
Changed to use actual student assignment file:
```python
prompt_path = "eng5_np_vt_2017_essay_instruction.md"  #  Student assignment (correct)
```

**Impact:**
- LLM now receives proper student assignment context
- Legacy detection warnings eliminated
- Assessment accuracy improved

---

## Verification Steps (Post-Implementation)

After implementing Fix 2 and Fix 3:

1. **Rebuild Containers:**
   ```bash
   pdm run dev-recreate cj_assessment_service
   ```

2. **Run ENG5 Comparison Test:**
   ```bash
   pdm run eng5-np-run \
     --assignment-id 00000000-0000-0000-0000-000000000001 \
     --course-id 00000000-0000-0000-0000-000000000002 \
     --mode execute \
     --batch-id "validation-test-$(date +%H%M)" \
     --max-comparisons 2 \
     --cj-system-prompt \
     --cj-service-url http://localhost:9095 \
     --verbose
   ```

3. **Verify Prompt Structure:**
   ```bash
   docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
   SELECT
     id,
     cj_batch_id,
     SUBSTRING(prompt_text, 1, 500) as prompt_preview
   FROM cj_comparison_pairs
   ORDER BY id DESC LIMIT 1;"
   ```

4. **Expected Result:**
   - Prompt should start with `**Student Assignment:**` followed by "Role Models" text
   - No legacy warning in logs

5. **Check for Legacy Warning (Should be Gone):**
   ```bash
   docker logs huleedu_cj_assessment_service --tail 50 | grep -i "legacy"
   ```

---

## Implementation Priority

**Priority:** Medium
**Effort:** Small (< 1 hour)
**Risk:** Low (isolated changes, clear fallback behavior)

**Recommendation:**
Implement both Fix 2 and Fix 3 together in a single session to ensure proper end-to-end testing of the experimental override flow.
