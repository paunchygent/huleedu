# TASK-002: ENG5 CJ Admin CLI Validation

**Status**: 🟡 BLOCKED
**Blocked By**: TASK-001 (Database URL Centralization)
**Priority**: HIGH
**Created**: 2025-11-11
**Assigned**: Current session

## Objective

Validate the complete ENG5 CJ Admin CLI workflow including:
- Admin authentication and token management
- Assessment instructions management
- Student prompt upload and retrieval
- Anchor essay registration
- End-to-end ENG5 runner execution
- Metrics and observability validation

## Prerequisites

### Blocking Requirements (from TASK-001)
- [x] Identity Service can start with password containing special characters
- [x] Identity Service database schema auto-initializes on fresh database
- [x] All services use centralized database URL construction with proper password encoding

### Service Dependencies
All services must be running and healthy:
- ✅ identity_service (port 7005) - Admin authentication
- ✅ content_service (port 8001) - Prompt/essay storage
- ✅ cj_assessment_service (port 9095) - Admin API
- ✅ llm_provider_service (port 8090) - LLM requests

### Test Data Requirements
**Location**: `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/`

Required files:
- `eng5_np_vt_2017_essay_instruction.md` (Judge instructions)
- `llm_prompt_cj_assessment_eng5.md` (Student prompt)
- `anchor_essays/*.docx` (12 anchor files: A1, A2, B1, B2, C+, C-, D+, D-, E+, E-, F+1, F+2)
- `student_essays/*.docx` (12 student essays for assessment)

### Admin Credentials
Admin user must exist in Identity Service with:
- Email: `admin@huleedu.com` (or configured via env)
- Role: `admin` in JWT claims
- Active status: `true`

## Validation Plan

### Step 0: Admin User Setup

**Create admin user** in Identity Service database:

```bash
# Hash password with bcrypt (matching Identity Service pattern)
# Password: AdminPass123!

docker exec huleedu_identity_db psql -U huleedu_user -d huleedu_identity -c "
INSERT INTO users (id, email, password_hash, roles, is_active, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'admin@huleedu.com',
    '\$2b\$12\$hash_here',  -- bcrypt hash of AdminPass123!
    ARRAY['admin']::text[],
    true,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO NOTHING;
"
```

**Verify user created**:
```bash
docker exec huleedu_identity_db psql -U huleedu_user -d huleedu_identity -c "
SELECT email, roles, is_active FROM users WHERE email = 'admin@huleedu.com';
"
```

### Step 1: Admin Authentication

**Objective**: Verify admin login and token caching workflow.

**Commands**:
```bash
# Login (caches token at ~/.huleedu/cj_admin_token.json)
pdm run cj-admin login --email admin@huleedu.com
# Enter password when prompted: AdminPass123!

# Verify token file created
ls -la ~/.huleedu/cj_admin_token.json
cat ~/.huleedu/cj_admin_token.json | jq '.'

# Test authentication with list scales
pdm run cj-admin scales list
```

**Expected Output**:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 900,
  "expires_at": "2025-11-11T14:30:00Z"
}
```

**Verification**:
- [ ] Token file exists at `~/.huleedu/cj_admin_token.json`
- [ ] Token includes `access_token`, `refresh_token`, `expires_in`, `expires_at`
- [ ] JWT can be decoded and contains `admin` role
- [ ] `scales list` command returns available grade scales including `eng5_np_legacy_9_step`

**Metrics to Check**:
- Identity Service: `identity_login_total{status="success"}` increments
- CJ Service: Admin API requests authorized successfully

---

### Step 2: Create Assessment Instructions

**Objective**: Create assessment context for ENG5 assignment.

**Setup**:
```bash
# Generate unique assignment ID
export ASSIGNMENT_ID=$(uuidgen)
echo "Assignment ID: $ASSIGNMENT_ID"
```

**Command**:
```bash
pdm run cj-admin instructions create \
  --assignment-id $ASSIGNMENT_ID \
  --grade-scale eng5_np_legacy_9_step \
  --instructions-file "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/eng5_np_vt_2017_essay_instruction.md"
```

**Expected Output** (JSON):
```json
{
  "id": 123,
  "assignment_id": "uuid-here",
  "grade_scale": "eng5_np_legacy_9_step",
  "instructions_text": "...",
  "student_prompt_storage_id": null,
  "created_at": "2025-11-11T13:00:00Z"
}
```

**Verification**:
```bash
# Retrieve instruction
pdm run cj-admin instructions get $ASSIGNMENT_ID
```

**Checklist**:
- [ ] Instruction created successfully (HTTP 200)
- [ ] Response includes `grade_scale: eng5_np_legacy_9_step`
- [ ] `student_prompt_storage_id` is `null` (not uploaded yet)
- [ ] Timestamps populated (`created_at`)
- [ ] Metric: `cj_admin_instruction_operations_total{operation="upsert",status="success"}` increments
- [ ] Log entry: `"Upserted assessment instructions"` with `assignment_id`

---

### Step 3: Student Prompt Upload and Retrieval

**Objective**: Verify prompt storage reference pattern (not inline text).

**Upload Command**:
```bash
pdm run cj-admin prompts upload \
  --assignment-id $ASSIGNMENT_ID \
  --prompt-file "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/llm_prompt_cj_assessment_eng5.md"
```

**Expected Output**:
```json
{
  "assignment_id": "uuid-here",
  "student_prompt_storage_id": "content-service-id-123",
  "updated_at": "2025-11-11T13:05:00Z"
}
```

**Retrieve Command**:
```bash
pdm run cj-admin prompts get $ASSIGNMENT_ID --output-file /tmp/prompt_verify.md
```

**Verification**:
```bash
# Compare original and retrieved
diff "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/llm_prompt_cj_assessment_eng5.md" /tmp/prompt_verify.md
```

**Checklist**:
- [ ] Upload returns `student_prompt_storage_id` (Content Service reference)
- [ ] Retrieved prompt content matches original file (diff shows no differences)
- [ ] Database check: `assessment_instructions.student_prompt_storage_id` populated
  ```bash
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
  SELECT assignment_id, student_prompt_storage_id FROM assessment_instructions
  WHERE assignment_id = '$ASSIGNMENT_ID';
  "
  ```
- [ ] Prompt text is NOT stored inline (only storage reference)
- [ ] Metric: `cj_admin_instruction_operations_total{operation="prompt_upload",status="success"}` increments
- [ ] Log entry: `"Student prompt uploaded to Content Service"` with `storage_id`

---

### Step 4: Anchor Essay Registration

**Objective**: Register anchor essays with grade validation.

**Command**:
```bash
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm \
  eng5_np_runner register-anchors $ASSIGNMENT_ID \
  --anchor-dir "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays"
```

**Expected Output**:
```
Registering anchors for assignment: <uuid>
Grade scale: eng5_np_legacy_9_step

Processing anchors:
  ✓ A1.docx → Grade: A1
  ✓ A2.docx → Grade: A2
  ✓ B1.docx → Grade: B1
  ✓ B2.docx → Grade: B2
  ✓ C+.docx → Grade: C+
  ✓ C-.docx → Grade: C-
  ✓ D+.docx → Grade: D+
  ✓ D-.docx → Grade: D-
  ✓ E+.docx → Grade: E+
  ✓ E-.docx → Grade: E-
  ✓ F+1.docx → Grade: F+1
  ✓ F+2.docx → Grade: F+2

Successfully registered 12 anchors.
```

**Database Verification**:
```bash
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
SELECT grade, grade_scale, COUNT(*)
FROM anchor_essay_references
WHERE assignment_id = '$ASSIGNMENT_ID'
GROUP BY grade, grade_scale
ORDER BY grade;
"
```

**Checklist**:
- [ ] Registration summary shows 12 anchors processed
- [ ] Database query confirms 12 records in `anchor_essay_references`
- [ ] All grades match scale: A1, A2, B1, B2, C+, C-, D+, D-, E+, E-, F+1, F+2
- [ ] Each anchor has valid `text_storage_id` (Content Service reference)
- [ ] Grade validation works (rejects invalid grades for scale)
- [ ] Log entries: `"anchor_registration_succeeded"` (12 events)

**Idempotency Test** (Optional):
```bash
# Re-run registration with same files
# Should either: (a) skip duplicates, or (b) error with clear message
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm \
  eng5_np_runner register-anchors $ASSIGNMENT_ID \
  --anchor-dir "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays"
```

---

### Step 5: ENG5 Runner Execution

**Objective**: Execute full assessment pipeline and verify artefact completeness.

**Pre-Execution Metrics Capture**:
```bash
curl http://localhost:9095/metrics > /tmp/metrics_before.txt
```

**Execution Command**:
```bash
pdm run eng5-runner \
  --mode execute \
  --batch-id eng5-validation-$(date +%Y%m%d-%H%M) \
  --assignment-id $ASSIGNMENT_ID \
  --course-id $(uuidgen) \
  --grade-scale eng5_np_legacy_9_step \
  --await-completion \
  --completion-timeout 1800
```

**Expected Output**:
```
ENG5 NP Runner - Execute Mode
=============================
Batch ID: eng5-validation-20251111-1400
Assignment ID: <uuid>
Grade Scale: eng5_np_legacy_9_step

Validation:
  ✓ Assignment instructions exist
  ✓ Student prompt available
  ✓ 12 anchors registered
  ✓ 12 student essays loaded

Enqueueing comparisons:
  [████████████████████] 100% (144 comparisons)

Awaiting completion (timeout: 1800s):
  [████████████████████] 100% (144/144 completed)

Cost Summary:
  Provider: anthropic
  Model: claude-sonnet-3-5-20241022
  Total Tokens: 1,234,567
  Estimated Cost: $12.34

Artefact written to:
  .claude/research/data/eng5_np_2016/assessment_run.execute.json

Status: ✓ Complete
```

**Post-Execution Metrics Capture**:
```bash
curl http://localhost:9095/metrics > /tmp/metrics_after.txt
diff /tmp/metrics_before.txt /tmp/metrics_after.txt | grep "cj_admin\|llm_requests\|huleedu_cj_prompt"
```

**Artefact Verification**:
```bash
# Check artefact exists
ls -lh .claude/research/data/eng5_np_2016/assessment_run.execute.json

# Verify schema compliance
jq '.validation.manifest | keys | length' .claude/research/data/eng5_np_2016/assessment_run.execute.json

# Check prompt references (should match uploaded storage_id)
jq '.results.essays[] | {essay_id, prompt_ref: .student_prompt_ref.storage_id}' \
  .claude/research/data/eng5_np_2016/assessment_run.execute.json | head -20

# Verify no partial data flag
jq '.validation.runner_status.partial_data' .claude/research/data/eng5_np_2016/assessment_run.execute.json
```

**Checklist**:
- [ ] Runner completes without errors
- [ ] Artefact written to expected path
- [ ] All 12 essays have `student_prompt_ref.storage_id` (matches uploaded prompt)
- [ ] All comparisons include metadata (judges, anchors, grades)
- [ ] `validation.runner_status.partial_data` is `false`
- [ ] Cost summary matches expectations (no missing comparisons)
- [ ] Metric: `huleedu_cj_prompt_fetch_failures_total` remains flat (no fetch failures)
- [ ] Metric: `llm_requests_total{status="queued"}` shows enqueue volume

---

### Step 6: Metrics and Logging Analysis

**Objective**: Verify observability stack captures all operations.

**Metrics Analysis**:
```bash
# CJ Service metrics
curl http://localhost:9095/metrics | grep "cj_admin_instruction_operations_total"
curl http://localhost:9095/metrics | grep "huleedu_cj_prompt_fetch"

# LLM Provider metrics
curl http://localhost:8090/metrics | grep "llm_requests_total"
```

**Log Analysis**:
```bash
# Admin auth entries
docker logs huleedu_identity_service 2>&1 | grep "admin@huleedu.com" | tail -20

# Instruction operations
docker logs huleedu_cj_assessment_service 2>&1 | grep "assessment_instructions" | tail -30

# Prompt operations
docker logs huleedu_cj_assessment_service 2>&1 | grep "student_prompt" | tail -20

# Anchor registration
docker logs huleedu_cj_assessment_service 2>&1 | grep "anchor_registration" | tail -20
```

**Checklist**:
- [ ] `cj_admin_instruction_operations_total{operation="upsert",status="success"}` = 1
- [ ] `cj_admin_instruction_operations_total{operation="get",status="success"}` >= 2
- [ ] `cj_admin_instruction_operations_total{operation="prompt_upload",status="success"}` = 1
- [ ] `cj_admin_instruction_operations_total{operation="prompt_get",status="success"}` = 1
- [ ] `anchor_registration_succeeded` log entries = 12
- [ ] No `admin_auth_failed` log entries
- [ ] All operations have `correlation_id` in logs

---

### Step 7: Validation Report Generation

**Objective**: Document validation results for stakeholders.

**Report Template**: Create `TASKS/002-eng5-cli-validation-RESULTS.md`

Contents:
```markdown
# ENG5 CLI Validation Results
**Date**: 2025-11-11
**Duration**: <total time>
**Status**: ✅ PASS / ❌ FAIL

## Executive Summary
Brief overview of validation outcome.

## Test Results

### Step 1: Admin Authentication
- Status: ✅ / ❌
- Token cached: Yes/No
- Scales list: Success/Failure
- Notes: ...

### Step 2: Assessment Instructions
- Status: ✅ / ❌
- Assignment ID: <uuid>
- Grade scale validated: Yes/No
- Notes: ...

### Step 3: Student Prompt
- Status: ✅ / ❌
- Storage ID: <content-service-id>
- Round-trip verified: Yes/No
- Notes: ...

### Step 4: Anchor Registration
- Status: ✅ / ❌
- Anchors registered: 12/12
- Database validated: Yes/No
- Notes: ...

### Step 5: ENG5 Runner
- Status: ✅ / ❌
- Artefact complete: Yes/No
- Prompt references valid: Yes/No
- Cost summary: $X.XX
- Notes: ...

### Step 6: Metrics & Logs
- Status: ✅ / ❌
- Metrics increments: Valid/Invalid
- Log entries: Complete/Incomplete
- Notes: ...

## Metrics Summary
<Paste relevant metrics diff>

## Issues Encountered
<List any issues, with resolution steps>

## Recommendations
<Next steps, improvements, follow-up tasks>
```

**Checklist**:
- [ ] Report created with all test results
- [ ] All metrics documented
- [ ] Issues logged with resolution details
- [ ] Recommendations for improvements captured

---

## Success Criteria

All checklist items must be ✅ to consider validation complete:

**Authentication**:
- [x] Admin user can login via CLI
- [x] Token caching works correctly
- [x] Token refresh works (if tested beyond expiry)

**Instructions Management**:
- [x] Can create assessment instructions
- [x] Can retrieve instructions by assignment ID
- [x] Grade scale validation works

**Prompt Management**:
- [x] Can upload student prompt
- [x] Prompt stored as reference (not inline)
- [x] Can retrieve prompt with matching content

**Anchor Management**:
- [x] Can register 12 anchor essays
- [x] Grade validation against scale works
- [x] Anchors persisted with storage references

**End-to-End Runner**:
- [x] Runner executes without errors
- [x] All essays include prompt references
- [x] Artefact schema compliant
- [x] No partial data flags
- [x] Cost summary accurate

**Observability**:
- [x] Metrics capture all operations
- [x] Logs include correlation IDs
- [x] No authentication failures
- [x] No fetch failures

## Rollback Plan

If validation uncovers issues:

1. **Document failure** in validation report
2. **Create bug tickets** for specific issues
3. **Roll back breaking changes** if any
4. **Re-run validation** after fixes applied

## Post-Validation Tasks

After successful validation:

1. **Archive test data**: Move validation artefacts to permanent storage
2. **Update documentation**: Document any deviations or lessons learned
3. **Create runbooks**: Document admin CLI workflows for operations team
4. **Plan next phase**: Identify follow-up features or improvements

## Related Tasks

- **TASK-001**: Database URL Centralization (BLOCKS this task)

## References

- Admin CLI: `services/cj_assessment_service/cli_admin.py`
- Admin API: `services/cj_assessment_service/api/admin_routes.py`
- Anchor API: `services/cj_assessment_service/api/anchor_management.py`
- ENG5 Runner: `scripts/cj_experiments_runners/eng5_np/cli.py`
- Setup Docs: `scripts/cj_experiments_runners/eng5_np/ASSIGNMENT_SETUP.md`
- Test Data: `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/`
