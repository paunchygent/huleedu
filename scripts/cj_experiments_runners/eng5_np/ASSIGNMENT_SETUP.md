# ENG5 NP Runner - Assignment Setup Workflow

## Overview

The ENG5 NP runner requires a valid `assignment_id` that exists in the CJ Assessment Service's `assessment_instructions` table. This document describes how to set up assignment contexts for use with the runner.

## Prerequisites

- CJ Assessment Service running and accessible (admin endpoints enabled)
- `pdm run cj-admin` CLI available (run `pdm install` first)
- Assignment assets: grade scale + instructions text, **and** the prompt markdown file that will be uploaded by the CLI
- Content Service reachable so prompt uploads succeed
- Admin credentials or JWT token (see Authentication Setup below)

## Authentication Setup

All admin CLI commands require authentication. Choose one of the following methods:

### Option A: Environment Variable Token (Recommended for CI/Automation)

```bash
export CJ_ADMIN_TOKEN="your-jwt-token-here"
# Token checked first by AuthManager (no login needed)
```

The `CJ_ADMIN_TOKEN` environment variable provides a direct token override, bypassing cached tokens and login prompts. This is ideal for automated scripts and CI/CD pipelines.

### Option B: Issue Token with Credentials (Recommended for Development)

```bash
# Set credentials in environment
export CJ_ADMIN_EMAIL="admin@example.com"
export CJ_ADMIN_PASSWORD="your-password"

# Generate and cache token (reusable across commands)
pdm run cj-admin token issue

# Token cached to ~/.huleedu/cj_admin_token.json
# Auto-refreshed when expired
```

This method caches the token locally, so you don't need to re-authenticate for subsequent commands. The token is automatically refreshed when it expires.

### Option C: Interactive Login

```bash
pdm run cj-admin login
# Prompts for email/password
# Caches token for reuse
```

This method prompts for credentials interactively and caches the token for future use.

### Authentication Priority

The CLI checks for authentication in this order:
1. `CJ_ADMIN_TOKEN` environment variable (highest priority)
2. Cached token in `~/.huleedu/cj_admin_token.json`
3. Prompt for interactive login (lowest priority)

### Token Management Commands

```bash
# Issue token non-interactively
pdm run cj-admin token issue

# Issue token without caching (prints to stdout only)
pdm run cj-admin token issue --no-cache

# View current token status
cat ~/.huleedu/cj_admin_token.json
```

## Step 1: Create Assessment Context

Use the admin API to create an assessment instruction record:

```bash
curl -X POST http://localhost:9095/admin/v1/assessment-instructions \
  -H "Authorization: Bearer <your-admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "assignment_id": "eng5-np-batch-20250110",
    "course_id": null,
    "instructions_text": "Assess essays based on ENG5 Norwegian Program criteria...",
    "grade_scale": "eng5_np_legacy_9_step"
  }'
```

**Important:**
- Either `assignment_id` OR `course_id` must be set (mutually exclusive)
- The `grade_scale` must be a valid scale registered in `common_core.grade_scales`
- For assignment-specific instructions, set `assignment_id` and leave `course_id` null
- For course-level fallback instructions, set `course_id` and leave `assignment_id` null

## Step 2: Upload Student Assignment Prompt via CJ Admin CLI

**IMPORTANT:** The student prompt is the assignment text that students saw when writing their essays (e.g., "Write a text about role models..."). This is NOT the judge rubric used for assessment.

The CJ service requires the student prompt to be stored by reference. Use the admin CLI to upload the prompt file so `student_prompt_storage_id` is persisted alongside the instructions record.

```bash
# Upload student-facing assignment prompt (what students saw)
pdm run cj-admin prompts upload \
  --assignment-id eng5-np-batch-20250110 \
  --prompt-file "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/eng5_np_vt_2017_essay_instruction.md"
```

This command performs the following:

1. Authenticates via Identity (uses cached token or `CJ_ADMIN_TOKEN` override).
2. Streams the prompt file to CJ's admin API, which forwards the body to the Content Service.
3. Stores only the returned `student_prompt_storage_id` in the `assessment_instructions` table—prompt bodies are no longer kept inline.

Verify the upload and capture the storage reference for observability records:

```bash
pdm run cj-admin prompts get eng5-np-batch-20250110
```

Expected response (truncated):

```text
Student Prompt Details
Assignment ID: eng5-np-batch-20250110
Prompt Storage ID: content-abc123
Prompt SHA256: <hash>
```

Keep the CLI output (or rerun `prompts get`) handy when coordinating execute-mode validation—the ENG5 runner and downstream services rely on the storage ID only.

## Step 3: Upload Judge Rubric via CJ Admin CLI

**IMPORTANT:** The judge rubric contains LLM instructions and assessment criteria (e.g., "You are an impartial judge..."). This is separate from the student prompt.

Upload the judge rubric that the LLM will use to assess essays:

```bash
# Upload judge rubric (LLM assessment instructions)
pdm run cj-admin rubrics upload \
  --assignment-id eng5-np-batch-20250110 \
  --rubric-file "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/llm_prompt_cj_assessment_eng5.md"
```

This command:

1. Authenticates via Identity (uses cached token or `CJ_ADMIN_TOKEN` override).
2. Uploads the rubric to Content Service via CJ's admin API.
3. Stores the returned `judge_rubric_storage_id` in the `assessment_instructions` table.

Verify the upload:

```bash
pdm run cj-admin rubrics get eng5-np-batch-20250110
```

Expected response:

```text
Judge Rubric for eng5-np-batch-20250110
Storage ID: content-xyz789
Grade Scale: eng5_np_legacy_9_step
Created At: <timestamp>
```

## Step 4: Register Anchor Essays (One-time Setup)

Anchor essays are **persistent** graded reference essays used to calibrate the grade projection system. They must be registered once per assignment and will be automatically loaded for all subsequent batches.

### Anchor Essay Organization

Anchor essays should be organized in a directory with proper grade-based filenames:

```
test_uploads/my_assignment/anchor_essays/
├── A1.docx          # Grade: A
├── A2.docx          # Grade: A
├── B1.docx          # Grade: B
├── B2.docx          # Grade: B
├── C+.docx          # Grade: C+
├── C-.docx          # Grade: C-
├── D+.docx          # Grade: D+
├── D-.docx          # Grade: D-
├── E+.docx          # Grade: E+
├── E-.docx          # Grade: E-
├── F+1.docx         # Grade: F+
└── F+2.docx         # Grade: F+
```

**Naming Convention:**
- Format: `<GRADE>[optional-number].<extension>`
- Supported formats: `.docx`, `.pdf`, `.txt`
- Grade extracted by removing trailing digits and extension
- Examples: `A1.docx` → Grade "A", `F+2.txt` → Grade "F+"

### Register Anchors Using CLI

```bash
# Using docker-compose runner
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner \
  register-anchors eng5-np-batch-20250110 \
  --anchor-dir test_uploads/my_assignment/anchor_essays

# Or use PDM directly (from repo root)
pdm run eng5-np register-anchors eng5-np-batch-20250110 \
  --anchor-dir test_uploads/my_assignment/anchor_essays
```

**What Happens:**
1. CLI reads all files from `--anchor-dir` (defaults to `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays/`)
2. Extracts grade from each filename (e.g., `A1.docx` → grade "A")
3. Extracts essay text content from file
4. POSTs to CJ service: `POST /api/v1/anchors/register`
   ```json
   {
     "assignment_id": "eng5-np-batch-20250110",
     "grade": "A",
     "essay_text": "Full essay content..."
   }
   ```
5. CJ service:
   - Validates `assignment_id` exists and retrieves `grade_scale`
   - Validates grade against grade scale
   - Stores essay text in Content Service
   - Creates reference in `anchor_essay_references` table

### Verify Anchor Registration

Check anchors via database query (requires database access):

```bash
# Via docker
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT id, assignment_id, grade, grade_scale FROM anchor_essay_references WHERE assignment_id = 'eng5-np-batch-20250110';"
```

Expected output:
```
 id |     assignment_id      | grade |     grade_scale
----+------------------------+-------+----------------------
  1 | eng5-np-batch-20250110 | A     | eng5_np_legacy_9_step
  2 | eng5-np-batch-20250110 | A     | eng5_np_legacy_9_step
  3 | eng5-np-batch-20250110 | B     | eng5_np_legacy_9_step
...
```

### Persistent vs Ephemeral Anchors

**Persistent Anchors (Recommended):**
- Registered once via `register-anchors` command
- Stored in `anchor_essay_references` table
- Automatically loaded for all batches using this `assignment_id`
- More efficient (no redundant uploads)

**Ephemeral Anchors (Fallback):**
- Used when anchor registration fails or is skipped
- Uploaded with each batch execution
- Not persisted in database
- Runner treats them like student essays but marks as anchors

## Step 5: Run the ENG5 NP Runner

Once the assignment context exists, run the runner with the matching `assignment_id`:

```bash
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner \
  --mode execute \
  --assignment-id eng5-np-batch-20250110 \
  --course-id 22222222-2222-2222-2222-222222222222 \
  --grade-scale eng5_np_legacy_9_step \
  --batch-id eng5-20250110-001 \
  --verbose
```

**Required Parameters:**
- `--assignment-id`: Must match the `assignment_id` created in Step 1
- `--course-id`: Course identifier for metadata

## What Happens During Execution

### With Registered Prompt & Anchors (Recommended Path)

1. **Content Upload**:
   - Runner uploads **only student essays** to Content Service
   - Anchors already registered, no need to re-upload
   - Student prompt reference is auto-hydrated from the `assessment_instructions` record (no inline prompt text is read from disk at runtime)

2. **CJ Assessment Request**:
   - Runner builds assessment request with student essay references
   - CJ service automatically hydrates the stored `student_prompt_storage_id` for the batch metadata
   - CJ service automatically loads registered anchors for this `assignment_id`
   - Anchor loading process:
     - Query `anchor_essay_references` filtered by `assignment_id` + `grade_scale`
     - Fetch anchor content from Content Service using stored `text_storage_id`
     - Add anchors to comparison pool with synthetic IDs (e.g., `ANCHOR_1_a3f2b8c9`)
     - Mark with `is_anchor=True` and `anchor_grade` metadata

3. **Grade Projection**:
   - Comparative judgments performed between students and anchors
   - Bradley-Terry model uses anchor grades for calibration
   - Grade projections generated for student essays

### Without Registered Anchors (Fallback Path)

1. **Ephemeral Mode Detection**:
   - Runner detects no registered anchors for `assignment_id`
   - Falls back to ephemeral anchor mode

2. **Content Upload**:
   - Runner uploads **both anchors and student essays** to Content Service
   - Anchors treated as temporary references for this batch only

3. **Assessment**:
   - Both anchors and students included in comparison pool
   - Anchors not persisted (no `anchor_essay_references` records)
   - Still functions but less efficient for repeated batches

## Verification

Check if assignment context exists:

```bash
curl -H "Authorization: Bearer <your-admin-jwt>" \
  http://localhost:9095/admin/v1/assessment-instructions/assignment/eng5-np-batch-20250110
```

Expected response (200 OK):
```json
{
  "id": 1,
  "assignment_id": "eng5-np-batch-20250110",
  "course_id": null,
  "instructions_text": "Assess essays based on...",
  "grade_scale": "eng5_np_legacy_9_step",
  "created_at": "2025-11-10T06:00:00Z"
}
```

## Troubleshooting

### Error: "Unknown assignment_id"

**Cause**: The `assignment_id` doesn't exist in `assessment_instructions` table

**Solution**: Create the assignment context via admin API (Step 1)

### Error: "Student prompt not found"

**Cause**: Student prompt upload step skipped or Content Service unavailable

**Solution**: Repeat Step 2 (`cj-admin prompts upload`) once services are healthy

### Error: "Judge rubric not found"

**Cause**: Judge rubric upload step skipped or Content Service unavailable

**Solution**: Repeat Step 3 (`cj-admin rubrics upload`) once services are healthy

### Error: "Invalid grade for scale"

**Cause**: Anchor essay grades don't match the configured `grade_scale`

**Solution**:
- Verify the `grade_scale` in the assignment context
- Ensure anchor filenames use grades valid for that scale
- Check `common_core.grade_scales` for valid grades

### Error: "Admin role required"

**Cause**: JWT token doesn't have `admin` role

**Solution**: Obtain a valid admin JWT from Identity Service

## Database Schema

The `assessment_instructions` table structure:

```sql
CREATE TABLE assessment_instructions (
    id SERIAL PRIMARY KEY,
    assignment_id VARCHAR(100) UNIQUE,
    course_id VARCHAR(50),
    instructions_text TEXT NOT NULL,
    grade_scale VARCHAR(50) NOT NULL DEFAULT 'swedish_8_anchor',
    student_prompt_storage_id VARCHAR(255),      -- References Content Service (student-facing assignment)
    judge_rubric_storage_id VARCHAR(255),         -- References Content Service (LLM assessment criteria)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT chk_context_type CHECK (
        (assignment_id IS NOT NULL AND course_id IS NULL) OR
        (assignment_id IS NULL AND course_id IS NOT NULL)
    )
);
```

## Available Admin Endpoints

### Assessment Instructions
- `POST /admin/v1/assessment-instructions` - Create or update instructions
- `GET /admin/v1/assessment-instructions` - List all instructions (paginated)
- `GET /admin/v1/assessment-instructions/assignment/<id>` - Get by assignment ID
- `DELETE /admin/v1/assessment-instructions/assignment/<id>` - Delete assignment instructions
- `DELETE /admin/v1/assessment-instructions/course/<id>` - Delete course instructions

### Student Prompts
- `POST /admin/v1/student-prompts` - Upload student prompt (sets `student_prompt_storage_id`)
- `GET /admin/v1/student-prompts/assignment/<id>` - Get student prompt with hydrated text

### Judge Rubrics
- `POST /admin/v1/judge-rubrics` - Upload judge rubric (sets `judge_rubric_storage_id`)
- `GET /admin/v1/judge-rubrics/assignment/<id>` - Get judge rubric with hydrated text

All admin endpoints require `Authorization: Bearer <jwt>` with `admin` role.

## Validated Test Examples

This section documents end-to-end validated test workflows that confirm all components (Content Service, CJ Assessment, LLM Provider, prompt context hydration) are working correctly.

### Test Assignment Setup (Validation)

The following test assignment configuration has been validated to work correctly:

```bash
# Assignment ID for testing
assignment_id="00000000-0000-0000-0000-000000000001"
course_id="00000000-0000-0000-0000-000000000002"

# Assessment context exists in database with:
# - instructions_text: "Assess clarity, argumentation, and language use..."
# - grade_scale: "eng5_np_legacy_9_step"
# - student_prompt_storage_id: (stored in Content Service - student-facing assignment)
# - judge_rubric_storage_id: (stored in Content Service - LLM assessment criteria)
```

### Validated Workflow: Anchor Registration + Execution

**Step 1: Register Anchor Essays**

```bash
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --course-id 00000000-0000-0000-0000-000000000002 \
  register-anchors \
  --cj-service-url http://localhost:9095
```

**Expected Outcome:**
- 12 anchor essays registered successfully
- Each anchor stored in Content Service with unique `storage_id`
- Database records created in `anchor_essay_references` table
- Grades: A (2x), B (2x), C+ (1x), C- (1x), D+ (1x), D- (1x), E+ (1x), E- (1x), F+ (2x)

**Verification:**
```bash
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT COUNT(*) FROM anchor_essay_references WHERE assignment_id = '00000000-0000-0000-0000-000000000001';"
```

Expected: 12 records

**Step 2: Run Validation Test**

```bash
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --mode execute \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --course-id 00000000-0000-0000-0000-000000000002 \
  --batch-id validation-test-final \
  --max-comparisons 2 \
  --kafka-bootstrap localhost:9093 \
  --await-completion \
  --completion-timeout 60 \
  --verbose
```

**Expected Outcome:**
- 4 student essays uploaded to Content Service
- 12 anchor essays loaded from database (no re-upload)
- Total: 16 essays in comparison pool
- 5 comparison tasks generated (limited by `--max-comparisons 2` means 2 per essay)
- All comparison tasks queued to LLM Provider Service (HTTP 202)
- LLM callbacks received via Kafka
- Grade projections calculated

**Key Validation Points:**

1. **Content Service Integration:**
   - Student essays stored with valid `storage_id`
   - Anchors loaded from existing registrations
   - No 405 errors from Content Service

2. **Context Hydration (Critical):**
   - CJ service logs show: `has_instructions: True, has_student_prompt: True, has_judge_rubric: True`
   - Prompts include student assignment, assessment instructions, and judge rubric
   - Prompt format validated by LLM Provider Service

3. **Prompt Structure:**
   ```
   **Student Assignment:**
   <student-facing assignment text from student_prompt_storage_id>
   Example: "Write a text where you discuss role models..."

   **Assessment Rubric:**
   <LLM judge instructions from judge_rubric_storage_id>
   Example: "You are an impartial judge. Assess based on..."

   **Assessment Instructions:**
   <general assessment criteria from database instructions_text>

   **Essay A (ID: ELS_...):**
   <essay text>

   **Essay B (ID: ELS_...):**
   <essay text>

   Compare these two essays based on the assessment criteria...
   ```

**Verification Commands:**

```bash
# Check CJ batch was created
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT id, bos_batch_id, expected_essay_count, status FROM cj_batch_uploads WHERE bos_batch_id = 'validation-test-final';"

# Check comparison pairs generated
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT COUNT(*) FROM cj_comparison_pairs WHERE cj_batch_id = <cj_batch_id>;"

# Check CJ service logs for context fetching
docker logs huleedu-cj-assessment-1 2>&1 | grep "Fetched assessment context"
# Expected: has_instructions: True, has_student_prompt: True, has_judge_rubric: True

# Check LLM Provider received requests
docker logs huleedu-llm-provider-1 2>&1 | grep "Queued comparison request"
```

**Test Results (2025-11-12):**

- **Correlation ID:** `4d6fe37b-74d4-4df1-bb50-34e1c8b3f5c2`
- **CJ Batch ID:** 10
- **Status:** ✅ All components working correctly
- **Essays:** 4 student + 12 anchors = 16 total
- **Comparisons:** 5 tasks generated and queued
- **Context:** Both instructions and student prompt included in all comparison prompts
- **Callbacks:** Received within milliseconds via Kafka

### Common Issues and Fixes

**Issue 1: "HTTP 405 Method Not Allowed" from Content Service**

**Symptom:**
```
Error registering anchor: 405 Client Error: Method Not Allowed
```

**Cause:** CJ service's Content Service client using wrong endpoint or payload format

**Fix:** Verify `content_client_impl.py` uses:
- Endpoint: `/v1/content` (not `/store`)
- Payload: Raw bytes with `Content-Type` header (not JSON)
- Expected status: 201 (not 200)

**Issue 2: "[VALIDATION_ERROR] Invalid prompt format: Could not extract essays"**

**Symptom:**
```
[VALIDATION_ERROR] Invalid prompt format: Could not extract essays
service=cj_assessment_service operation=generate_comparison
```

**Cause:** LLM Provider Service essay extraction regex doesn't handle markdown format `**Essay A (ID: ...):**`

**Fix:** Verify `llm_provider_service_client.py` line 73 checks for both:
- `stripped.startswith("Essay A")`  # Old format
- `stripped.startswith("**Essay A")`  # New markdown format

**Issue 3: Context not included in prompts**

**Symptom:** CJ logs show `has_instructions: False`, `has_student_prompt: False`, or `has_judge_rubric: False`

**Diagnosis:**
```bash
# Check if assignment context exists
curl -H "Authorization: Bearer <admin-jwt>" \
  http://localhost:9095/admin/v1/assessment-instructions/assignment/<assignment-id>

# Check if student prompt is uploaded
pdm run cj-admin prompts get <assignment-id>

# Check if judge rubric is uploaded
pdm run cj-admin rubrics get <assignment-id>
```

**Fix:**
- Ensure Step 1 (create assessment context) completed successfully
- Ensure Step 2 (upload student prompt) completed successfully
- Ensure Step 3 (upload judge rubric) completed successfully
- Verify `processing_metadata` in `cj_batch_uploads` contains both `student_prompt_text` and `judge_rubric_text`
