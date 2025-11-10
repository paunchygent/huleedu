# ENG5 NP Runner - Assignment Setup Workflow

## Overview

The ENG5 NP runner requires a valid `assignment_id` that exists in the CJ Assessment Service's `assessment_instructions` table. This document describes how to set up assignment contexts for use with the runner.

## Prerequisites

- CJ Assessment Service running and accessible
- Admin JWT token with `admin` role
- Assignment details (grade scale, instructions text)

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

## Step 1.5: Register Anchor Essays (One-time Setup)

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

## Step 2: Run the ENG5 NP Runner

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

### With Registered Anchors (Recommended Path)

1. **Content Upload**:
   - Runner uploads **only student essays** to Content Service
   - Anchors already registered, no need to re-upload

2. **CJ Assessment Request**:
   - Runner builds assessment request with student essay references
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT chk_context_type CHECK (
        (assignment_id IS NOT NULL AND course_id IS NULL) OR
        (assignment_id IS NULL AND course_id IS NOT NULL)
    )
);
```

## Available Admin Endpoints

- `POST /admin/v1/assessment-instructions` - Create or update instructions
- `GET /admin/v1/assessment-instructions` - List all instructions (paginated)
- `GET /admin/v1/assessment-instructions/assignment/<id>` - Get by assignment ID
- `DELETE /admin/v1/assessment-instructions/assignment/<id>` - Delete assignment instructions
- `DELETE /admin/v1/assessment-instructions/course/<id>` - Delete course instructions

All admin endpoints require `Authorization: Bearer <jwt>` with `admin` role.
