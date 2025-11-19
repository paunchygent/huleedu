# Contracts & Schema: Before/After Analysis

## Database Schema Changes

### `assessment_instructions` Table

#### BEFORE
```sql
CREATE TABLE assessment_instructions (
    id SERIAL PRIMARY KEY,
    assignment_id VARCHAR(100) UNIQUE,
    course_id VARCHAR(50),
    instructions_text TEXT NOT NULL,              -- Teacher-facing assessment criteria
    grade_scale VARCHAR(50) NOT NULL DEFAULT 'swedish_8_anchor',
    student_prompt_storage_id VARCHAR(64),        -- Points to judge rubric file ❌
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT chk_context_type CHECK (
        (assignment_id IS NOT NULL AND course_id IS NULL) OR
        (assignment_id IS NULL AND course_id IS NOT NULL)
    )
);
```

**Problem**: `student_prompt_storage_id` points to `llm_prompt_cj_assessment_eng5.md` (judge rubric), not student assignment.

#### AFTER
```sql
CREATE TABLE assessment_instructions (
    id SERIAL PRIMARY KEY,
    assignment_id VARCHAR(100) UNIQUE,
    course_id VARCHAR(50),
    instructions_text TEXT NOT NULL,              -- Teacher-facing assessment criteria
    grade_scale VARCHAR(50) NOT NULL DEFAULT 'swedish_8_anchor',
    student_prompt_storage_id VARCHAR(64),        -- Student assignment prompt ✅
    judge_rubric_storage_id VARCHAR(64),          -- NEW: Judge assessment rubric
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT chk_context_type CHECK (
        (assignment_id IS NOT NULL AND course_id IS NULL) OR
        (assignment_id IS NULL AND course_id IS NOT NULL)
    )
);
```

**Changes**:
- `student_prompt_storage_id` now correctly references student-facing assignment
- `judge_rubric_storage_id` NEW column for LLM judge instructions

**Data Migration Required**:
```sql
-- Current state for test assignment
SELECT
    assignment_id,
    student_prompt_storage_id  -- Points to llm_prompt_cj_assessment_eng5.md
FROM assessment_instructions
WHERE assignment_id = '00000000-0000-0000-0000-000000000001';

-- After migration
-- 1. Upload eng5_np_vt_2017_essay_instruction.md via Content Service
-- 2. Store returned storage_id in judge_rubric_storage_id
-- 3. Upload correct student assignment file
-- 4. Update student_prompt_storage_id with new storage_id
```

---

### `cj_batch_uploads.processing_metadata` (JSON Column)

#### BEFORE
```json
{
    "student_prompt_text": "You are an impartial Comparative Judgement assessor for upper-secondary student essays.\n\n### Assessment Rubric:\n...",
    "student_prompt_storage_id": "58970dee6e53425d9d70ddf958a6b663",
    "assignment_id": "00000000-0000-0000-0000-000000000001",
    "essays_to_process": [...],
    "language": "english",
    "course_code": "ENG5"
}
```

**Problem**: `student_prompt_text` contains judge rubric, not student assignment.

#### AFTER
```json
{
    "student_prompt_text": "Write an essay about role models and their importance in society. Your essay should demonstrate critical thinking and use relevant examples from literature, history, or personal experience.\n\nLength: 600-800 words\nFormat: Academic essay with introduction, body paragraphs, and conclusion",
    "student_prompt_storage_id": "<new_storage_id>",
    "judge_rubric_text": "You are an impartial Comparative Judgement assessor for upper-secondary student essays.\n\n### Assessment Rubric:\n...",
    "judge_rubric_storage_id": "58970dee6e53425d9d70ddf958a6b663",
    "assignment_id": "00000000-0000-0000-0000-000000000001",
    "essays_to_process": [...],
    "language": "english",
    "course_code": "ENG5"
}
```

**Changes**:
- `student_prompt_text`: Now contains actual student assignment (what they write about)
- `judge_rubric_text`: NEW field containing LLM judge instructions
- `judge_rubric_storage_id`: NEW field for Content Service reference

**Migration Script Required**:
```python
# Pseudo-code for migration
for batch in get_batches_with_rubric_in_student_prompt():
    # Fetch correct student prompt from Content Service
    assignment_instructions = fetch_assignment_instructions(batch.assignment_id)
    student_prompt = content_service.get(assignment_instructions.student_prompt_storage_id)
    judge_rubric = content_service.get(assignment_instructions.judge_rubric_storage_id)

    # Update processing_metadata
    batch.processing_metadata.update({
        "student_prompt_text": student_prompt,
        "judge_rubric_text": judge_rubric,
        "judge_rubric_storage_id": assignment_instructions.judge_rubric_storage_id
    })
    session.commit()
```

---

## API Contracts

### CJ Assessment → LLM Provider Service

#### BEFORE

**Request**: `POST /comparison`
```python
# services/cj_assessment_service/implementations/llm_provider_service_client.py
request_body = {
    "user_prompt": "<base_prompt without essays>",  # Context only
    "essay_a": "<full essay A text>",                # Essay extracted from prompt
    "essay_b": "<full essay B text>",                # Essay extracted from prompt
    "metadata": {
        "comparison_id": "...",
        "batch_id": "..."
    },
    "llm_config_overrides": {
        "provider_override": "anthropic",
        "model_override": "claude-sonnet-4-5-20250929",
        "temperature_override": 0.3
    },
    "correlation_id": "4d6fe37b-74d4-4df1-bb50-34e1c8b3f5c2",
    "callback_topic": "huleedu.llm_provider.comparison_result.v1"
}
```

**LLM Provider Contract**: `services/llm_provider_service/api_models.py`
```python
class LLMComparisonRequest(BaseModel):
    user_prompt: str                          # Base prompt (no essays)
    essay_a: str                              # Required ⚠️
    essay_b: str                              # Required ⚠️
    metadata: dict[str, Any] = {}
    llm_config_overrides: LLMConfigOverrides | None = None
    correlation_id: str | None = None
    callback_topic: str | None = None
```

**Provider Processing**: `anthropic_provider_impl.py:433-450`
```python
def _format_comparison_prompt(self, user_prompt: str, essay_a: str, essay_b: str) -> str:
    # No placeholders found, append essays
    if "{essay_a}" not in user_prompt and "{essay_b}" not in user_prompt:
        formatted = f"{user_prompt}\n\nEssay A:\n{essay_a}\n\nEssay B:\n{essay_b}"
    return formatted
```

**Result**: Essays sent twice (once in CJ prompt with IDs, once appended by provider)

---

#### AFTER

**Request**: `POST /comparison`
```python
# services/cj_assessment_service/implementations/llm_provider_service_client.py
request_body = {
    "user_prompt": "<complete_prompt_with_essays>",  # Ready to send to LLM ✅
    "essay_a": None,                                  # Deprecated (optional)
    "essay_b": None,                                  # Deprecated (optional)
    "metadata": {
        "comparison_id": "...",
        "batch_id": "...",
        "essay_a_id": "ELS_...",                      # For callback correlation
        "essay_b_id": "ELS_..."                       # For callback correlation
    },
    "llm_config_overrides": {
        "provider_override": "anthropic",
        "model_override": "claude-sonnet-4-5-20250929",
        "temperature_override": 0.3
    },
    "correlation_id": "4d6fe37b-74d4-4df1-bb50-34e1c8b3f5c2",
    "callback_topic": "huleedu.llm_provider.comparison_result.v1"
}
```

**LLM Provider Contract**: `services/llm_provider_service/api_models.py`
```python
class LLMComparisonRequest(BaseModel):
    """LLM comparison request.

    Note: essay_a and essay_b are deprecated. Clients should include
    essays directly in user_prompt for better control and efficiency.
    """
    user_prompt: str                          # Complete prompt with essays ✅
    essay_a: str | None = None                # Optional (backwards compat)
    essay_b: str | None = None                # Optional (backwards compat)
    metadata: dict[str, Any] = {}
    llm_config_overrides: LLMConfigOverrides | None = None
    correlation_id: str | None = None
    callback_topic: str | None = None
```

**Provider Processing**: `anthropic_provider_impl.py:433-450`
```python
def _format_comparison_prompt(
    self,
    user_prompt: str,
    essay_a: str | None,
    essay_b: str | None
) -> str:
    # If essays not provided separately, prompt is already complete
    if essay_a is None and essay_b is None:
        return user_prompt  # Use as-is ✅

    # Honor template placeholders (backwards compatibility)
    if "{essay_a}" in user_prompt and "{essay_b}" in user_prompt:
        return user_prompt.replace("{essay_a}", essay_a or "").replace("{essay_b}", essay_b or "")

    # Fallback: append essays (old behavior)
    return f"{user_prompt}\n\nEssay A:\n{essay_a}\n\nEssay B:\n{essay_b}"
```

**Result**: Essays sent once, token usage reduced ~50%

---

## Event Contracts (Kafka)

### ELS → CJ Assessment Service

#### BEFORE & AFTER (No Change)

**Topic**: `huleedu.els.cj_assessment.requested.v1`

**Event**: `ELS_CJAssessmentRequestV1`
```python
# libs/common_core/src/common_core/pipeline_models.py
class ELS_CJAssessmentRequestV1(BaseModel):
    event_name: ProcessingEvent
    entity_id: str                           # batch_id
    entity_type: str
    parent_id: str                           # assignment_id
    system_metadata: dict[str, Any]
    essays_for_cj: list[EssayReference]
    language: str
    course_code: str
    student_prompt_ref: StorageReference     # Points to student assignment ✅
    llm_config_overrides: dict[str, Any] | None = None
    assignment_id: str
    user_id: str | None = None
    org_id: str | None = None
```

**No changes required** - the event contract is already correct. The issue is:
1. Current `student_prompt_ref` points to wrong file (rubric instead of assignment)
2. No way to pass judge rubric reference (fetched from `assessment_instructions` instead)

---

### LLM Provider → CJ Assessment (Callback)

#### BEFORE & AFTER (No Change)

**Topic**: `huleedu.llm_provider.comparison_result.v1`

**Event**: `LLMComparisonResultV1`
```python
# Callback contract unchanged
class LLMComparisonResultV1(BaseModel):
    correlation_id: str
    provider: str
    model: str
    winner: Literal["A", "B", "tie"]
    justification: str
    confidence: int
    token_usage: dict[str, int]
    metadata: dict[str, Any]
```

**Essay IDs**: Now passed via `metadata.essay_a_id` and `metadata.essay_b_id` for correlation.

---

## Prompt Structure Changes

### CJ Service Prompt Building

#### BEFORE: `pair_generation.py:_build_comparison_prompt()`
```python
def _build_comparison_prompt(
    essay_a: EssayForComparison,
    essay_b: EssayForComparison,
    assessment_instructions: str | None = None,
    student_prompt_text: str | None = None,  # Actually contains judge rubric ❌
) -> str:
    prompt_parts = []

    # Wrong label - this is judge rubric
    if student_prompt_text:
        prompt_parts.append(f"**Assignment Prompt:**\n{student_prompt_text}")

    # Correct
    if assessment_instructions:
        prompt_parts.append(f"**Assessment Criteria:**\n{assessment_instructions}")

    # Essays with IDs
    prompt_parts.append(f"**Essay A (ID: {essay_a.id}):**\n{essay_a.text_content}")
    prompt_parts.append(f"**Essay B (ID: {essay_b.id}):**\n{essay_b.text_content}")

    prompt_parts.append("Compare these two essays...")

    return "\n\n".join(prompt_parts)
```

**Result Prompt**:
```
**Assignment Prompt:**
You are an impartial Comparative Judgement assessor... ❌ Wrong content

**Assessment Criteria:**
<ENG5 test assignment criteria>

**Essay A (ID: ELS_...):**
<essay text>

**Essay B (ID: ELS_...):**
<essay text>

Compare these two essays...
```

Then LLM Provider appends essays AGAIN:
```
Essay A:
<essay text> ❌ Duplicate

Essay B:
<essay text> ❌ Duplicate
```

---

#### AFTER: `pair_generation.py:_build_comparison_prompt()`
```python
def _build_comparison_prompt(
    essay_a: EssayForComparison,
    essay_b: EssayForComparison,
    assessment_instructions: str | None = None,
    student_assignment_prompt: str | None = None,  # Actual student assignment ✅
    judge_rubric: str | None = None,               # Judge instructions ✅
) -> str:
    prompt_parts = []

    # Correct: Actual student assignment
    if student_assignment_prompt:
        prompt_parts.append(f"**Student Assignment:**\n{student_assignment_prompt}")

    # Correct: Teacher assessment criteria
    if assessment_instructions:
        prompt_parts.append(f"**Assessment Criteria:**\n{assessment_instructions}")

    # Judge rubric for LLM (optional - could go in system prompt)
    if judge_rubric:
        prompt_parts.append(f"**Judge Instructions:**\n{judge_rubric}")

    # Essays with IDs (sent once)
    prompt_parts.append(f"**Essay A (ID: {essay_a.id}):**\n{essay_a.text_content}")
    prompt_parts.append(f"**Essay B (ID: {essay_b.id}):**\n{essay_b.text_content}")

    prompt_parts.append(
        "Based on the student assignment, assessment criteria, and judge instructions "
        "above, compare these two essays. Determine which better fulfills the requirements."
    )

    return "\n\n".join(prompt_parts)
```

**Result Prompt** (sent to LLM Provider as complete `user_prompt`):
```
**Student Assignment:**
Write an essay about role models and their importance in society.
Demonstrate critical thinking and use relevant examples. ✅ Correct

**Assessment Criteria:**
- Argumentation and structure
- Use of examples and evidence
- Language quality and grammar
- Depth of analysis

**Judge Instructions:**
You are an impartial Comparative Judgement assessor...
Follow this rubric: Content (clarity, richness...), Language (fluency...)

**Essay A (ID: ELS_...):**
<essay text> ✅ Single inclusion

**Essay B (ID: ELS_...):**
<essay text> ✅ Single inclusion

Based on the student assignment, assessment criteria, and judge instructions
above, compare these two essays...
```

LLM Provider uses as-is (no appending) → Essays sent once ✅

---

## Summary of Contract Changes

### Breaking Changes
❌ None - all changes are backwards compatible

### Additive Changes
✅ `assessment_instructions.judge_rubric_storage_id` - new column
✅ `processing_metadata.judge_rubric_text` - new field
✅ `processing_metadata.judge_rubric_storage_id` - new field
✅ `LLMComparisonRequest.essay_a` - now optional
✅ `LLMComparisonRequest.essay_b` - now optional
✅ `metadata.essay_a_id` - added for callback correlation
✅ `metadata.essay_b_id` - added for callback correlation

### Data Corrections
🔧 `student_prompt_storage_id` - point to correct file
🔧 `processing_metadata.student_prompt_text` - hydrate correct content
🔧 Upload student assignment via Content Service
🔧 Upload judge rubric via Content Service

### Behavioral Changes
🔄 CJ service sends complete prompt (essays included)
🔄 LLM Provider uses prompt as-is when essays not provided separately
🔄 Essay extraction logic removed from CJ client
🔄 Essay appending logic becomes no-op in provider implementations

### Token Usage Impact
📉 ~50% reduction for essay content (eliminated duplication)
📈 Slight increase for student assignment context (new content)
📊 Net result: More context, fewer tokens, better judgments
