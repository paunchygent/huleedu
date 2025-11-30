# ENG5 NP Anchor Registration - Practical Example

This document provides a complete, step-by-step example of setting up and using anchor essays with the ENG5 NP runner.

## Scenario

You have a new ENG5 assignment called "Role Models Essay 2025" and want to set up persistent anchor essays for grade calibration.

## Prerequisites

- CJ Assessment Service running (`docker compose up cj_assessment_service`)
- Admin JWT token (for this example, assume you have one as `$ADMIN_JWT`)
- 12 graded anchor essay files (F+1 through A2)

## Complete Workflow

### Step 1: Organize Anchor Essay Files

Create a directory structure for your assignment:

```bash
mkdir -p test_uploads/role_models_2025/anchor_essays
mkdir -p test_uploads/role_models_2025/student_essays
```

Place your graded anchor essays in `anchor_essays/` with proper naming:

```
test_uploads/role_models_2025/anchor_essays/
├── F+1.docx    # Grade: F+
├── F+2.docx    # Grade: F+
├── E-.docx     # Grade: E-
├── E+.docx     # Grade: E+
├── D-.docx     # Grade: D-
├── D+.docx     # Grade: D+
├── C-.docx     # Grade: C-
├── C+.docx     # Grade: C+
├── B1.docx     # Grade: B
├── B2.docx     # Grade: B
├── A1.docx     # Grade: A
└── A2.docx     # Grade: A
```

**Important:**
- File naming determines grade extraction
- Trailing numbers (1, 2) are stripped
- Grade symbols (+, -) are preserved
- Supported formats: `.docx`, `.pdf`, `.txt`

### Step 2: Create Assessment Instruction

Register the assignment with the CJ service:

```bash
curl -X POST http://localhost:9095/admin/v1/assessment-instructions \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "assignment_id": "eng5-role-models-2025",
    "course_id": null,
    "instructions_text": "Assess ENG5 Role Models essays based on argumentation, language proficiency, and essay structure. Use the Norwegian national criteria for English level 5.",
    "grade_scale": "eng5_np_legacy_9_step"
  }'
```

**Expected Response (200 OK):**
```json
{
  "id": 1,
  "assignment_id": "eng5-role-models-2025",
  "course_id": null,
  "instructions_text": "Assess ENG5 Role Models essays...",
  "grade_scale": "eng5_np_legacy_9_step",
  "created_at": "2025-01-10T08:30:00Z"
}
```

### Step 3: Register Anchor Essays

Use the `register-anchors` CLI command:

```bash
# Via Docker Compose
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner \
  register-anchors eng5-role-models-2025 \
  --anchor-dir test_uploads/role_models_2025/anchor_essays \
  --cj-service-url http://cj_assessment_service:9090

# Or via PDM (from repo root)
pdm run eng5-np register-anchors eng5-role-models-2025 \
  --anchor-dir test_uploads/role_models_2025/anchor_essays \
  --cj-service-url http://localhost:9095
```

**What Happens:**

For each anchor file:
1. Read file content (extracts text from .docx, .pdf, or .txt)
2. Extract grade from filename (e.g., `A1.docx` → grade "A")
3. POST to `/api/v1/anchors/register`:
   ```json
   {
     "assignment_id": "eng5-role-models-2025",
     "grade": "A",
     "essay_text": "My role model is Malala Yousafzai..."
   }
   ```
4. CJ service:
   - Validates assignment exists
   - Retrieves `grade_scale` from assignment context
   - Validates grade "A" is valid for "eng5_np_legacy_9_step"
   - Stores essay text in Content Service
   - Creates `anchor_essay_references` record

**Expected Output:**
```
Registering 12 anchor essays for assignment eng5-role-models-2025...
✓ Registered F+1.docx (grade: F+) -> anchor_id: 1
✓ Registered F+2.docx (grade: F+) -> anchor_id: 2
✓ Registered E-.docx (grade: E-) -> anchor_id: 3
✓ Registered E+.docx (grade: E+) -> anchor_id: 4
✓ Registered D-.docx (grade: D-) -> anchor_id: 5
✓ Registered D+.docx (grade: D+) -> anchor_id: 6
✓ Registered C-.docx (grade: C-) -> anchor_id: 7
✓ Registered C+.docx (grade: C+) -> anchor_id: 8
✓ Registered B1.docx (grade: B) -> anchor_id: 9
✓ Registered B2.docx (grade: B) -> anchor_id: 10
✓ Registered A1.docx (grade: A) -> anchor_id: 11
✓ Registered A2.docx (grade: A) -> anchor_id: 12

Successfully registered 12 anchors.
```

### Step 4: Verify Anchor Registration

Check the database to confirm anchors were stored:

```bash
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT id, assignment_id, grade, grade_scale, LEFT(text_storage_id, 16) as storage_id FROM anchor_essay_references WHERE assignment_id = 'eng5-role-models-2025' ORDER BY id;"
```

**Expected Output:**
```
 id |      assignment_id      | grade |      grade_scale       |   storage_id
----+-------------------------+-------+------------------------+------------------
  1 | eng5-role-models-2025   | F+    | eng5_np_legacy_9_step  | a1b2c3d4e5f6...
  2 | eng5-role-models-2025   | F+    | eng5_np_legacy_9_step  | b2c3d4e5f6a7...
  3 | eng5-role-models-2025   | E-    | eng5_np_legacy_9_step  | c3d4e5f6a7b8...
  4 | eng5-role-models-2025   | E+    | eng5_np_legacy_9_step  | d4e5f6a7b8c9...
  5 | eng5-role-models-2025   | D-    | eng5_np_legacy_9_step  | e5f6a7b8c9d0...
  6 | eng5-role-models-2025   | D+    | eng5_np_legacy_9_step  | f6a7b8c9d0e1...
  7 | eng5-role-models-2025   | C-    | eng5_np_legacy_9_step  | a7b8c9d0e1f2...
  8 | eng5-role-models-2025   | C+    | eng5_np_legacy_9_step  | b8c9d0e1f2a3...
  9 | eng5-role-models-2025   | B     | eng5_np_legacy_9_step  | c9d0e1f2a3b4...
 10 | eng5-role-models-2025   | B     | eng5_np_legacy_9_step  | d0e1f2a3b4c5...
 11 | eng5-role-models-2025   | A     | eng5_np_legacy_9_step  | e1f2a3b4c5d6...
 12 | eng5-role-models-2025   | A     | eng5_np_legacy_9_step  | f2a3b4c5d6e7...
(12 rows)
```

### Step 5: Run Assessment Batch (First Batch)

Now run the runner with student essays:

```bash
# Place student essays in the student_essays directory
# Files: student_001.docx, student_002.docx, etc.

docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner \
  --mode execute \
  --assignment-id eng5-role-models-2025 \
  --course-id 33333333-3333-3333-3333-333333333333 \
  --grade-scale eng5_np_legacy_9_step \
  --batch-id role-models-batch-001 \
  --max-comparisons 50 \
  --verbose
```

**What Happens:**

1. **Content Upload Phase**:
   - Runner validates that anchors exist and that `--cj-service-url` is provided.
   - `register_anchor_essays` is invoked automatically; if it fails, the CLI aborts before any uploads occur.
   - On success, **only student essays** are uploaded to Content Service (anchors stay DB-owned).

2. **Assessment Request Phase**:
   - Runner builds the CJ assessment request with student essay references and publishes to `huleedu.els.cj_assessment.requested.v1`.
   - Envelope metadata now includes `max_comparisons` when specified (here `50`) so CJ can apply the hint without the runner slicing essays.

3. **CJ Service Processing**:
   - CJ service receives the request, queries `anchor_essay_references` for `assignment_id = 'eng5-role-models-2025'`, and fetches the 12 stored anchors.
   - Creates synthetic IDs (e.g., `ANCHOR_1_a3f2b8c9`) and adds them to the comparison pool with `{"is_anchor": true, "anchor_grade": "A"}` metadata.

4. **Comparative Judgment**:
   - LLM performs pairwise comparisons across student-student, student-anchor, and anchor-anchor pairs.
   - `MAX_PAIRWISE_COMPARISONS` from CJ’s settings determines the global comparison budget; per-wave size emerges from batch size and the matching strategy.

5. **Grade Projection**:
   - Bradley-Terry modelling uses the registered anchors for calibration.
   - Projected grades are emitted for student essays, and results publish to `huleedu.cj_assessment.completed.v1`.

**Expected Log Output (excerpt):**
```
2025-01-10 08:45:12 [info] Loading registered anchors for assignment eng5-role-models-2025
2025-01-10 08:45:12 [info] Found 12 anchor references
2025-01-10 08:45:12 [info] Fetching anchor content from Content Service
2025-01-10 08:45:13 [info] Added ANCHOR_1_a3f2b8c9 (grade: F+) to comparison pool
2025-01-10 08:45:13 [info] Added ANCHOR_2_b4c5d6e7 (grade: F+) to comparison pool
...
2025-01-10 08:45:14 [info] Comparison pool: 12 anchors + 25 students = 37 essays
2025-01-10 08:45:14 [info] Generating 50 comparison pairs
```

### Step 6: Run Subsequent Batches

For additional batches with the same assignment, anchors are **automatically reused**:

```bash
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner \
  --mode execute \
  --assignment-id eng5-role-models-2025 \
  --course-id 33333333-3333-3333-3333-333333333333 \
  --grade-scale eng5_np_legacy_9_step \
  --batch-id role-models-batch-002 \
  --verbose
```

**Efficiency Gain:**
- No anchor re-upload (already in Content Service)
- No re-registration (already in `anchor_essay_references`)
- CJ service loads them automatically
- Consistent calibration across batches

---

## Key Distinctions: Anchors vs Students

| Aspect | Anchor Essays | Student Essays |
|--------|---------------|----------------|
| **Purpose** | Grade calibration (known grades) | Assessment targets (unknown grades) |
| **Lifecycle** | Persistent (per assignment) | Per-batch |
| **Storage** | `anchor_essay_references` table | `cj_processed_essays` table |
| **Registration** | One-time via `register-anchors` | Every batch via runner |
| **Naming** | Grade-based (A1.docx, F+2.txt) | Student-based (student_001.docx) |
| **Reuse** | Yes (all batches for assignment) | No (specific to batch) |
| **Upload** | To Content Service once | To Content Service per batch |
| **IDs** | Synthetic (`ANCHOR_1_a3f2...`) | Real (`els_essay_id`) |
| **Metadata** | `is_anchor=True`, `anchor_grade` | `is_anchor=False` |

---

## Troubleshooting

### Error: "Unknown assignment_id"

**Symptom:**
```
✗ Failed to register A1.docx: {"error": "Unknown assignment_id 'eng5-role-models-2025'"}
```

**Cause:** Assignment context not created in Step 2

**Solution:**
```bash
# Create assignment context first
curl -X POST http://localhost:9095/admin/v1/assessment-instructions \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"assignment_id": "eng5-role-models-2025", ...}'
```

### Error: "Invalid grade 'X' for scale 'eng5_np_legacy_9_step'"

**Symptom:**
```
✗ Failed to register X1.docx: {"error": "Invalid grade 'X' for scale 'eng5_np_legacy_9_step'"}
```

**Cause:** Grade extracted from filename not valid for the configured grade scale

**Valid grades for `eng5_np_legacy_9_step`:**
- A, B, C+, C-, D+, D-, E+, E-, F+

**Solution:**
- Rename file with valid grade (e.g., `X1.docx` → `F+1.docx`)
- Or verify grade scale is correct for your anchors

### Anchor Registration Fails During Execute Mode

**Symptom:**
```
[error] anchor_registration_failed error="401 Unauthorized"
Traceback (most recent call last):
  ...
RuntimeError: Anchor registration failed; aborting EXECUTE run so CJ only uses DB-owned anchors.
```

**Possible Causes:**
1. Anchors not registered yet (check database)
2. `assignment_id` mismatch
3. `grade_scale` filter mismatch
4. `CJ_SERVICE_URL` or admin auth misconfigured

**Solution:**
```bash
# Check anchors exist
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT COUNT(*) FROM anchor_essay_references WHERE assignment_id = 'eng5-role-models-2025';"

# Should return count > 0

# Verify grade_scale matches
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment \
  -c "SELECT DISTINCT grade_scale FROM anchor_essay_references WHERE assignment_id = 'eng5-role-models-2025';"

# Confirm CJ service URL / credentials
echo $CJ_SERVICE_URL
cat ~/.huleedu/cj_admin_token.json
```

---

## Summary

This workflow establishes:

1. **One-time setup**: Create assignment context + register anchors
2. **Efficient batching**: Run multiple batches reusing same anchors
3. **Consistent calibration**: Same anchor set ensures grade consistency
4. **Clear separation**: Anchors (persistent) vs students (per-batch)

The system is designed for research workflows where you assess multiple cohorts of students against the same grading standards, represented by your anchor essays.
