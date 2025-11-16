# Next Session: Complete CJ Metadata Persistence Validation & PR Prep

## Context

**Branch**: `feature/eng5-cj-anchor-comparison-flow`

**Status**: Metadata persistence implementation complete and validated. Continuation rehydration needs validation.

### What Was Completed

1. ✅ Implemented typed metadata models: `OriginalCJRequestMetadata`, `CJAnchorMetadata`, `CJEessayMetadata`
2. ✅ Added merge helpers: `merge_batch_upload_metadata`, `merge_batch_processing_metadata`, `merge_essay_processing_metadata`
3. ✅ Updated `request_additional_comparisons_for_batch` to rehydrate from stored `original_request`
4. ✅ Validated batch 21 (19e9b199-b500-45ce-bf95-ed63bb7489aa) has correct metadata structure
5. ✅ All tests passing (typecheck-all, full test suite, new integration test)

### Validation Batch Details

**Batch 21** (`19e9b199-b500-45ce-bf95-ed63bb7489aa`):
- Created: 2025-11-16 02:54:06 UTC
- ✅ Has `original_request` in both `cj_batch_uploads` and `cj_batch_states`
- ✅ Contains: language=en, assignment_id, max_comparisons_override=100, llm_config_overrides, user_id
- ⏳ Still processing - needs continuation validation

---

## Your Mission

Complete the validation checklist below and prepare the PR for merge. Focus on verifying the continuation rehydration logic works correctly and all invariants are maintained.

---

## Validation Checklist

### 1. Continuation & Budget Semantics ⏳

**Validate:**
- [ ] Monitor batch 21 until it triggers continuation (check if it needs additional comparisons beyond initial 10)
- [ ] When continuation occurs, verify:
  - [ ] `request_additional_comparisons_for_batch` successfully rehydrates from `original_request_payload`
  - [ ] New request has `max_comparisons_override: 100` (from original, not derived from max_pairs_cap)
  - [ ] `comparison_budget.source: "runner_override"` is preserved
  - [ ] `llm_config_overrides` matches original request
  - [ ] `batch_config_overrides` preserved if present
  - [ ] Identity fields (assignment_id, user_id, language, course_code) match original

**Queries to verify:**
```sql
-- Check continuation metadata
SELECT
    bs.processing_metadata->'comparison_budget'->>'source' as budget_source,
    bs.processing_metadata->'original_request'->>'max_comparisons_override' as original_max,
    bs.submitted_comparisons,
    bs.completed_comparisons
FROM cj_batch_states bs
WHERE batch_id = 21;

-- Verify no override derivation from max_pairs_cap
SELECT processing_metadata
FROM cj_batch_states
WHERE batch_id = 21;
-- Ensure max_comparisons_override ONLY comes from original_request, never from max_pairs_cap
```

**Test Coverage:**
- [ ] Verify `test_comparison_processing.py::test_request_additional_comparisons_submits_new_iteration` covers:
  - Rehydration from `original_request_payload`
  - Preservation of `max_comparisons_override`
  - No fallback to `max_pairs_cap` as override source

**Expected Behavior:**
- `comparison_budget.source="service_default"` → no `max_comparisons_override`, analytics treat as "CJ chose budget"
- `comparison_budget.source="runner_override"` → `max_comparisons_override` present, hard external budget
- Continuation NEVER flips service_default → runner_override
- Never derive `max_comparisons_override` from `max_pairs_cap` (guardrail, not intent)

---

### 2. DB Performance in Continuation 🔧

**Action Required:**
Replace full-row load with COUNT in continuation check:

**Current (inefficient):**
```python
stmt = select(ComparisonPair).where(...)
completed_pairs = (await session.execute(stmt)).scalars().all()
completed_count = len(completed_pairs)
```

**Target (efficient):**
```python
from sqlalchemy import func

stmt = (
    select(func.count())
    .select_from(ComparisonPair)
    .where(
        ComparisonPair.cj_batch_id == cj_batch_id,
        ComparisonPair.completed_at.is_not(None),
        # ...other filters...
    )
)
completed_count = (await session.execute(stmt)).scalar_one()
```

**Files to Check:**
- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
- `services/cj_assessment_service/cj_core_logic/comparison_processing.py`

**Validation:**
- [ ] Identify all `select(ComparisonPair)` followed by `len()`
- [ ] Replace with `select(func.count())`
- [ ] Run tests to ensure no regression
- [ ] Verify continuation logic still works correctly

---

### 3. Grade Projector & 4-Tier Anchor Fallback ✅

**Verify Current Implementation:**
- [ ] Confirm 4-tier fallback order in `grade_projector.py`:
  1. Tier 1: `anchor_grade` on ranking dict (future RAS/external flows)
  2. Tier 2: `known_grade` in essay metadata
  3. Tier 3: `text_storage_id` → `AssessmentContext.anchor_essay_refs`
  4. Tier 4: `anchor_ref_id` → `AssessmentContext.anchor_essay_refs`

**Optional Enhancements (if time permits):**
- [ ] Add metrics counters:
  - `cj_anchor_grade_resolution_total{tier="anchor_grade"}`
  - `cj_anchor_grade_resolution_total{tier="known_grade"}`
  - `cj_anchor_grade_resolution_total{tier="storage_id"}`
  - `cj_anchor_grade_resolution_failed_total{...}`

- [ ] Consider caching context lookups if batch volume grows:
  - Build `grades_by_storage` and `grades_by_ref` once per `AssessmentContext`
  - Currently with ~12 anchors this is micro-optimization

---

### 4. Observability & Documentation 📝

**Verify Logging:**
- [ ] Budget resolution logged when original_request is rehydrated
- [ ] Continuation events include budget source and remaining capacity
- [ ] Check logs for batch 21 show clear budget decision trail

**Documentation Updates:**
- [ ] Update `services/cj_assessment_service/README.md`:
  - [ ] Semantics of `comparison_budget.source`
  - [ ] How `max_comparisons_override` interacts with `MAX_PAIRWISE_COMPARISONS`
  - [ ] Continuations always reuse `OriginalCJRequestMetadata`

- [ ] Document anchor metadata contract:
  - [ ] `cj_processed_essays.processing_metadata` for anchors includes:
    - `is_anchor: true`
    - `known_grade: <grade>`
    - `anchor_ref_id: <id>`
  - [ ] External flows can supply `anchor_grade` on rankings for projector reuse

---

### 5. End-to-End Validation (ENG5 Runner) ⏳

**Already Running:**
- Background bash fcb0b5: ENG5 runner with `--max-comparisons 100`

**Validation Steps:**
- [ ] Wait for batch 21 completion or check current status:
  ```bash
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
  SELECT bs.state, bs.submitted_comparisons, bs.completed_comparisons,
         bs.processing_metadata->'comparison_budget' as budget
  FROM cj_batch_states bs WHERE batch_id = 21;"
  ```

- [ ] Verify final state:
  - [ ] `comparison_budget.max_pairs_requested: 100`
  - [ ] `comparison_budget.source: "runner_override"`
  - [ ] No continuation errors in logs
  - [ ] `original_request` metadata present in both tables

**Regression Checks:**
- [ ] Run additional validation with different `--max-comparisons` values (e.g., 150)
- [ ] Verify no continuation errors
- [ ] Confirm metadata structure consistent across all batches

---

### 6. Invariants Around Merge Helpers ✅

**Code Review:**
- [ ] Audit all `processing_metadata` writes in:
  - `batch_preparation.py`
  - `batch_submission.py`
  - `comparison_processing.py`
  - `workflow_continuation.py`

- [ ] Ensure NO direct assignment: `processing_metadata = {...}`
- [ ] All writes use merge helpers or repository methods that merge

**Test Coverage:**
- [ ] Verify `test_batch_preparation_identity_flow.py` asserts:
  - Metadata merge doesn't drop `original_request`
  - New fields append without clobbering existing keys

- [ ] Check `test_metadata_persistence_integration.py` covers:
  - Full lifecycle: creation → continuation → completion
  - Metadata preserved across all phases

---

## Action Plan

### Phase 1: Monitor & Validate Continuation (30 min)
1. Check batch 21 status - is it complete or still processing?
2. If complete without continuation, run new batch with higher essay count to trigger continuation
3. Capture continuation logs and verify rehydration behavior
4. Validate budget semantics preserved

### Phase 2: Performance Optimization (15 min)
1. Identify all `select(ComparisonPair)` + `len()` patterns
2. Replace with `select(func.count())`
3. Run tests
4. Verify no regression

### Phase 3: Documentation (15 min)
1. Update service README with budget semantics
2. Document anchor metadata contract
3. Add continuation rehydration flow documentation

### Phase 4: Final Validation (15 min)
1. Run full test suite one more time
2. Run typecheck-all
3. Review all modified files for direct metadata assignment
4. Check logs for any warnings or errors

### Phase 5: PR Preparation (15 min)
1. Review commit message - ensure it's accurate and complete
2. Update HANDOFF.md with final validation results
3. Create PR description highlighting:
   - Problem solved (continuation budget preservation)
   - Implementation approach (typed models + merge helpers)
   - Validation results
   - Breaking changes (none expected)

---

## Key Files to Review

**Core Implementation:**
- `services/cj_assessment_service/models_api.py` - Pydantic models
- `services/cj_assessment_service/cj_core_logic/batch_preparation.py` - Metadata persistence
- `services/cj_assessment_service/cj_core_logic/batch_submission.py` - Merge helpers
- `services/cj_assessment_service/cj_core_logic/comparison_processing.py` - Rehydration logic
- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py` - Continuation flow

**Tests:**
- `services/cj_assessment_service/tests/unit/test_batch_preparation_identity_flow.py`
- `services/cj_assessment_service/tests/unit/test_comparison_processing.py`
- `services/cj_assessment_service/tests/unit/test_workflow_continuation.py`
- `services/cj_assessment_service/tests/integration/test_metadata_persistence_integration.py`

---

## Success Criteria

- [ ] Batch 21 (or new test batch) completes successfully with continuation
- [ ] Continuation rehydrates from `original_request` correctly
- [ ] Budget semantics preserved (`source: "runner_override"`, `max_comparisons_override: 100`)
- [ ] No direct `processing_metadata` assignments remain
- [ ] DB queries use COUNT() instead of loading full rows
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Ready for PR review

---

## Helpful Commands

```bash
# Check batch status
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
SELECT id, bos_batch_id, bs.state, bs.submitted_comparisons, bs.completed_comparisons
FROM cj_batch_uploads bu
JOIN cj_batch_states bs ON bu.id = bs.batch_id
ORDER BY bu.created_at DESC LIMIT 5;"

# Check metadata structure
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "
SELECT jsonb_pretty(processing_metadata::jsonb)
FROM cj_batch_states WHERE batch_id = 21;" -x

# Check CJ service logs for continuation
docker logs huleedu_cj_assessment_service 2>&1 | grep -E "(continuation|rehydrat|original_request)" | tail -30

# Run tests
pdm run typecheck-all
pdm run pytest-root services/cj_assessment_service/tests

# Run new ENG5 validation
pdm run eng5-runner --mode execute \
  --assignment-id 00000000-0000-0000-0000-000000000001 \
  --course-id 11111111-1111-1111-1111-111111111111 \
  --max-comparisons 150 \
  --await-completion \
  --completion-timeout 1800
```

---

## Notes

- Batch 21 was created with the NEW code (post-rebuild)
- Batch 19 (d77fbc20-38e9-4416-b072-ac7d9acd8ce1) was created with OLD code - don't use for validation
- Service container was rebuilt at 02:51:40 UTC
- Current background runners may still be processing - check their status first

---

**START HERE**: Check batch 21 status and proceed with Phase 1.

Complete Command Reference for CJ Assessment / ENG5 Runner Validation

  🐳 Container Management

  Check Running Containers

  # List all HuleEdu containers
  docker ps --filter "name=huleedu" --format "table 
  {{.Names}}\t{{.Status}}\t{{.Ports}}"

  # Check specific services
  docker ps --filter "name=huleedu" --format "{{.Names}}" | grep -E
  "(cj_assessment|llm_provider|content)"

  # Check all containers (including stopped)
  docker ps -a --filter "name=huleedu" --format "{{.Names}}" | sort

  View Container Logs

  # Follow logs for a specific service
  docker logs -f huleedu_cj_assessment_service

  # Search logs for specific patterns
  docker logs huleedu_cj_assessment_service 2>&1 | grep -E
  "(correlation_id|workflow_continuation|grade_projection)"

  # Get logs for a specific batch UUID
  docker logs huleedu_cj_assessment_service 2>&1 | grep "<BATCH_UUID>"  # replace with target batch UUID

  ---
  🚀 Service Management

  Start Services

  # Start specific services (uses existing images)
  pdm run dev-start cj_assessment_service content_service llm_provider_service

  # Start all services
  pdm run dev-start

  # Build and start services
  pdm run dev-build-start cj_assessment_service llm_provider_service

  # Clean build (no cache)
  pdm run dev-build-clean websocket_service

  Verify Services are Healthy

  # Wait and check health status
  sleep 10 && docker ps --filter "name=huleedu" --format "table 
  {{.Names}}\t{{.Status}}" | grep -E "(cj_assessment|llm_provider|content)"

  ---
  🗄️ Database Access

  Important Notes

  - Database user: huleedu_user (NOT root)
  - Database names follow pattern: huleedu_<service_name>
    - CJ Assessment: huleedu_cj_assessment
    - Content Service: huleedu_content_service
    - etc.

  Access PostgreSQL

  # Method 1: Using hardcoded credentials (RECOMMENDED)
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "SELECT version();"

  # Method 2: Using .env file (may fail if not loaded properly)
  source .env && docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d
  huleedu_cj_assessment -c "SELECT version();"

  Key Database Queries

  Check Batch States:
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT 
    bs.batch_id, 
    bu.bos_batch_id, 
    bs.state, 
    bs.submitted_comparisons, 
    bs.completed_comparisons, 
    bs.current_iteration, 
    bs.processing_metadata 
  FROM cj_batch_states bs 
  JOIN cj_batch_uploads bu ON bs.batch_id = bu.id 
  ORDER BY bs.batch_id DESC 
  LIMIT 5;
  "

  Check Comparison Pairs:
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT 
    cj_batch_id, 
    COUNT(*) as total_pairs, 
    COUNT(winner) as pairs_with_winner 
  FROM cj_comparison_pairs 
  WHERE cj_batch_id = 9  -- replace 9 with target cj_batch_id
  GROUP BY cj_batch_id;
  "

  Check Grade Projections:
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT COUNT(*) as projection_count 
  FROM grade_projections 
  WHERE cj_batch_id = 9;  -- replace 9 with target cj_batch_id
  "

  Check Anchor Essay References:
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT 
    COUNT(*) as total, 
    COUNT(DISTINCT grade) as unique_grades, 
    array_agg(DISTINCT grade) as grades 
  FROM anchor_essay_references 
  WHERE assignment_id = '00000000-0000-0000-0000-000000000001';  -- replace with target assignment_id
  "

  Check Table Schema:
  # List all tables
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "\dt"

  # Describe specific table
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "\d cj_batch_states"

  # Search for tables matching pattern
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "\dt" | grep -i comparison

  Delete Stuck Batches:
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  DELETE FROM cj_batch_uploads WHERE id IN (5, 6);
  SELECT 'Deleted stuck batches' as result;
  "

  ---
  🧪 ENG5 Runner Execution

  Run ENG5 Runner with Budget

  # Run in foreground (blocks until complete)
  pdm run eng5-runner \
    --mode execute \
    --assignment-id 00000000-0000-0000-0000-000000000001 \  # replace with target assignment-id as needed
    --course-id 11111111-1111-1111-1111-111111111111 \      # replace with target course-id as needed
    --max-comparisons 100 \                                 # adjust comparison budget as needed
    --await-completion \
    --completion-timeout 1800

  # Run in background (recommended for long operations)
  pdm run eng5-runner \
    --mode execute \
    --assignment-id 00000000-0000-0000-0000-000000000001 \  # replace with target assignment-id as needed
    --course-id 11111111-1111-1111-1111-111111111111 \      # replace with target course-id as needed
    --max-comparisons 100 \                                 # adjust comparison budget as needed
    --await-completion \
    --completion-timeout 1800 &

  # Store background job ID
  RUNNER_PID=$!

  ---
  🗑️ Redis Cache Management

  Clear Redis Cache

  # Flush all Redis data
  docker exec huleedu_redis redis-cli FLUSHALL

  # Check Redis info
  docker exec huleedu_redis redis-cli INFO

  ---
  📊 Validation Workflow

  Complete Validation Sequence

  # 1. Clear Redis cache
  docker exec huleedu_redis redis-cli FLUSHALL

  # 2. Start required services
  pdm run dev-start cj_assessment_service content_service llm_provider_service

  # 3. Wait for services to be healthy
  sleep 10 && docker ps --filter "name=huleedu" --format "table 
  {{.Names}}\t{{.Status}}" | grep -E "(cj_assessment|llm_provider|content)"

  # 4. Check for stuck batches
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT bs.batch_id, bu.bos_batch_id, bs.state, bs.submitted_comparisons 
  FROM cj_batch_states bs 
  JOIN cj_batch_uploads bu ON bs.batch_id = bu.id 
  WHERE bs.state = 'WAITING_CALLBACKS' 
  ORDER BY bs.batch_id DESC;
  "

  # 5. Delete stuck batches if any (adjust IDs as needed)
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  DELETE FROM cj_batch_uploads WHERE id IN (5, 6);  -- replace with IDs of stuck batches
  "

  # 6. Run ENG5 validation
  pdm run eng5-runner \
    --mode execute \
    --assignment-id 00000000-0000-0000-0000-000000000001 \  # replace with target assignment-id as needed
    --course-id 11111111-1111-1111-1111-111111111111 \      # replace with target course-id as needed
    --max-comparisons 100 \                                 # adjust comparison budget as needed
    --await-completion \
    --completion-timeout 1800

  # 7. After completion, verify results
  # Get the batch UUID from runner output (e.g., 
  2f8dc826-d6c6-4d5b-b9d2-1ed94fb47a50)
  BATCH_UUID=""

  # Check batch state
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT bs.batch_id, bu.bos_batch_id, bs.state, bs.submitted_comparisons, 
  bs.completed_comparisons, 
         bs.processing_metadata->>'comparison_budget' as budget
  FROM cj_batch_states bs 
  JOIN cj_batch_uploads bu ON bs.batch_id = bu.id 
  WHERE bu.bos_batch_id = '${BATCH_UUID}';
  "

  # Check comparison count
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT cj_batch_id, COUNT(*) as total, COUNT(winner) as completed 
  FROM cj_comparison_pairs 
  WHERE cj_batch_id = (SELECT id FROM cj_batch_uploads WHERE bos_batch_id = 
  '${BATCH_UUID}') 
  GROUP BY cj_batch_id;
  "

  # Check grade projections
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "
  SELECT COUNT(*) as projections 
  FROM grade_projections 
  WHERE cj_batch_id = (SELECT id FROM cj_batch_uploads WHERE bos_batch_id = 
  '${BATCH_UUID}');
  "

  ---
  🔍 Service Names Reference

  Infrastructure Services:
  - huleedu_kafka
  - huleedu_zookeeper
  - huleedu_redis
  - huleedu_prometheus
  - huleedu_grafana
  - huleedu_loki
  - huleedu_jaeger
  - huleedu_alertmanager
  - huleedu_promtail

  Application Services:
  - huleedu_cj_assessment_service
  - huleedu_cj_assessment_db
  - huleedu_llm_provider_service
  - huleedu_content_service
  - huleedu_content_service_db
  - huleedu_websocket_service

  Utility:
  - huleedu_kafka_topic_setup (runs once then exits)

  ---
  🎯 Common Troubleshooting

  Service Won't Start

  # Check if image exists
  docker images | grep huleedu

  # Rebuild if needed
  pdm run dev-build-start <service_name>

  # Check logs for errors
  docker logs huleedu_<service_name> 2>&1 | tail -50

  Database Connection Issues

  # Verify database container is running
  docker ps | grep _db

  # Check database logs
  docker logs huleedu_cj_assessment_db 2>&1 | tail -20

  # Verify you can connect
  docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment
   -c "SELECT 1;"

  Runner Stuck or Not Producing Results

  # Check if services are actually running
  docker ps --filter "name=huleedu" --format "{{.Names}}" | grep -E
  "(cj_assessment|llm_provider|content)"

  # Check CJ service logs for the batch UUID
  docker logs huleedu_cj_assessment_service 2>&1 | grep "<batch-uuid>"

  # Check for workflow continuation issues
  docker logs huleedu_cj_assessment_service 2>&1 | grep -i "workflow_continuation" |
   tail -20