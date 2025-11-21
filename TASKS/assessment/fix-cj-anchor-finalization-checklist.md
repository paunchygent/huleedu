---
id: fix-cj-anchor-finalization-checklist
title: Fix Cj Anchor Finalization Checklist
type: task
status: archived
priority: high
domain: assessment
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: cj_assessment_service
owner: ''
program: ''
related: []
labels: []
---

# TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING – Developer Checklist

This checklist is a child document for `TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING.md`.

It is intended for the engineer implementing the CJ-side fixes and verifying that ENG5 / CJ flows
complete end-to-end with anchors, grade projections, and monitoring in place.

---

## Phase 1 – Code correctness & regression coverage

### 1. Verify repository anchor persistence

- [ ] **Confirm `create_or_update_cj_processed_essay` persists `is_anchor`**
  - File: `services/cj_assessment_service/implementations/db_access_impl.py`
  - Behaviour to verify:
    - When `processing_metadata` includes `"is_anchor": True`, `ProcessedEssay.is_anchor` is set to
      `True` for both inserts and updates.
    - When `processing_metadata` omits `"is_anchor"`, existing `is_anchor` values are left
      unchanged.
  - Tests:
    - `services/cj_assessment_service/tests/integration/test_repository_anchor_flag.py`
      - [ ] Run: `pdm run pytest services/cj_assessment_service/tests/integration/test_repository_anchor_flag.py -q`
      - [ ] Confirm test names and assertions match the above behaviour.

- [ ] **Verify `is_anchor` idempotency on update path**
  - Purpose: Ensure the `is_anchor` flag persists across updates when `processing_metadata` does not
    explicitly include an `is_anchor` key, preventing accidental resets.
  - Test file: `services/cj_assessment_service/tests/integration/test_repository_anchor_flag.py`
  - Assumptions:
    - An essay is initially created with `processing_metadata["is_anchor"] = True`, resulting in
      `ProcessedEssay.is_anchor = True`.
    - A subsequent update to the same essay (identified by `els_essay_id`) provides
      `processing_metadata` that omits the `is_anchor` key entirely (e.g., updates other fields like
      `text_storage_id` or adds unrelated metadata).
  - Expected results:
    - After the update, `ProcessedEssay.is_anchor` remains `True` (unchanged from initial insert).
    - The repository does not reset `is_anchor` to `None` or `False` when the key is absent from
      update metadata.
    - This behaviour prevents the Batch 20 incident from recurring on subsequent updates to anchor
      essays.
  - Verification:
    - [ ] Confirm test exercises both insert (with `is_anchor`) and update (without `is_anchor`)
      operations on the same `els_essay_id`.
    - [ ] Confirm assertion validates `is_anchor` remains `True` after update.

### 2. Verify batch finalizer state transitions

- [ ] **Review `BatchFinalizer.finalize_scoring` implementation**
  - File: `services/cj_assessment_service/cj_core_logic/batch_finalizer.py`
  - Confirm the following behaviours:
    - Before scoring, the CJ state is updated to `CoreCJState.SCORING` via
      `update_batch_state_in_session`.
    - After grade projections and dual-event publication, the CJ state is updated to
      `CoreCJState.COMPLETED`.
    - The upload status on `CJBatchUpload` is set to `CJBatchStatusEnum.COMPLETE_STABLE`.
    - Internal correlation_id remains a `UUID` instance; external events use
      `UUID(batch_upload.event_correlation_id)`.

- [ ] **Execute unit tests for finalizer state transitions**
  - File: `services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py`
  - Run:
    ```bash
    pdm run pytest services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py -q
    ```
  - Ensure tests explicitly assert:
    - State change to `SCORING` when finalization begins.
    - State change to `COMPLETED` after dual events are successfully published.

### 3. Validate diagnostics tooling

- [ ] **Confirm `inspect_batch_state.py` behaviour**
  - File: `scripts/cj_assessment_service/diagnostics/inspect_batch_state.py`
  - Behaviour to verify:
    - Prints upload status, CJ state, comparison counts, anchor counts, and grade projection counts
      for a given `cj_batch_id`.
    - Handles non-existent batch IDs gracefully with clear output.
  - Run (example):
    ```bash
    pdm run python scripts/cj_assessment_service/diagnostics/inspect_batch_state.py 20
    ```
  - Confirm the output format aligns with the ENG5 validation report and the Batch 20 incident
    review.

---

## Phase 2 – Recreate & reseed CJ/ENG5 dev data (no backfill)

Goal: Remove reliance on the old Batch 20 dev data and **recreate a clean ENG5 CJ dataset** using
ENG5 runner CLI flows. Do not backfill existing rows; instead, reset/reseed.

### 1. Prepare CJ dev database for recreate

> Note: These steps are **dev/test only** and must not run against any staging or production
> databases.

- [ ] **Stop services that may write to CJ dev DB**
  - At minimum, pause or stop:
    - `cj_assessment_service`
    - ENG5 CLI jobs or scripts
    - Any background workers that might create new CJ batches

- [ ] **Reset or clean the CJ dev database**
  - Options (pick one consistent with your current workflow):
    - **Option A: Full DB reset (preferred for clean dev environments)**
      - Drop and recreate the `huleedu_cj_assessment` database using your standard dev tooling or
        `docker exec` + `psql`.
      - Re-run Alembic migrations to head:
        ```bash
        cd services/cj_assessment_service
        pdm run alembic upgrade head
        pdm run alembic current  # Ensure latest revision
        ```
    - **Option B: Targeted cleanup**
      - Delete existing ENG5 dev batches and projections, including Batch 20:
        - `cj_batch_uploads` rows for the ENG5 assignment.
        - Related `cj_batch_states`, `processed_essays`, `comparison_pairs`, and `grade_projections`
          rows linked by `cj_batch_id`.
      - Keep anchor references intact (since they have already been validated by the anchor infra
        task) unless you explicitly want to reseed them too.
  - Record the chosen option and commands used in your dev notes.

### 2. Reseed ENG5 anchors (if desired)

If you want to also exercise anchor registration end-to-end, re-run the ENG5 anchor registration
flow.

- [ ] **Re-register ENG5 anchors via CLI**
  - Command pattern (example, adjust URLs/flags as needed):
    ```bash
    pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
      --assignment-id 00000000-0000-0000-0000-000000000001 \
      --course-id 00000000-0000-0000-0000-000000000002 \
      register-anchors 00000000-0000-0000-0000-000000000001 \
      --cj-service-url http://localhost:9095
    ```
  - The example `assignment-id`, `course-id`, and `cj-service-url` values match the default ENG5
    dev environment; if your local or CI configuration uses different IDs or ports, adjust them
    accordingly.
  - Verify via SQL or API:
    - Exactly 12 anchor rows exist for the ENG5 assignment.
    - All `text_storage_id` values resolve to HTTP 200 from Content Service.

### 3. Create a fresh ENG5 CJ batch via execute mode

- [ ] **Run ENG5 execute flow against the corrected CJ code**
  - Command (example; adjust flags to your environment):
    ```bash
    pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode execute \
      --assignment-id 00000000-0000-0000-0000-000000000001 \
      --course-id 00000000-0000-0000-0000-000000000002 \
      --batch-id eng5-finalization-$(date +%Y%m%d-%H%M) \
      --max-comparisons 5 \
      --kafka-bootstrap localhost:9093 \
      --await-completion \
      --completion-timeout 60 \
      --verbose
    ```
  - Ensure:
    - Comparisons complete successfully (mock LLM is fine).
    - The CLI reports successful completion (no timeouts, no `RESOURCE_NOT_FOUND`).

- [ ] **Inspect the new batch state using diagnostics**
  - Identify the new `cj_batch_id` (from logs or DB).
  - Run:
    ```bash
    pdm run python scripts/cj_assessment_service/diagnostics/inspect_batch_state.py <new_batch_id>
    ```
  - Confirm the following for the new batch:
    - Upload status: `COMPLETE_STABLE`.
    - CJ state: `COMPLETED`.
    - Comparisons: completed count matches submitted count.
    - Anchor essays: `is_anchor = true` for anchors, consistent with `processing_metadata`.
    - `grade_projections > 0`.

### 4. Capture validation artefacts

- [ ] **Export ENG5 execution artefacts for the new batch**
  - Ensure the ENG5 CLI writes updated artefacts under
    `.claude/research/data/eng5_np_2016/` (or your configured path):
    - Updated `assessment_run.execute.json`.
    - Updated CJ request envelope.
  - Optionally, snapshot:
    - `SELECT * FROM grade_projections WHERE cj_batch_id = <new_batch_id>;`

---

## Phase 3 – Monitoring, diagnostics & runbooks

### 1. Define monitoring query or view

- [ ] **Create a diagnostic query for CJ batch health**
  - Goal: For each `cj_batch_id`, expose:
    - Upload status (`cj_batch_uploads.status`).
    - CJ state (`cj_batch_states.state`).
    - Comparison counts (total, submitted, completed, failed).
    - Anchor count (`COUNT(*) WHERE is_anchor = true`).
    - Grade projection count (`COUNT(*) FROM grade_projections WHERE cj_batch_id = ...`).
    - Last activity timestamps.
  - Implement this as a SQL view (or materialized view if appropriate) over the CJ database that
    can be consumed by Grafana or your DB console.

### 2. Implement alerts for stuck batches

- [ ] **Add alerting rule for stuck batches**
  - Condition example:
    - Upload status is `COMPLETE_STABLE` AND
    - CJ state ∈ {`WAITING_CALLBACKS`, `SCORING`} AND
    - `grade_projections = 0` AND
    - This condition holds for >5–10 minutes.
  - **Primary for this task**: Use the SQL view from the previous step as the data source for a
    Grafana dashboard panel and alert rule.
  - Alternatives (future work if needed):
    - SQL-based metrics exported to Prometheus.
    - Loki/Grafana alert querying logs enriched with batch state.
    - A small periodic health-check job that emits metrics for CJ batch health.

- [ ] **(Optional) Alert on long-running SCORING**
  - Add a secondary alert if a batch stays in `SCORING` beyond a reasonable threshold while
    comparisons and callbacks appear complete.

### 3. Update runbooks and docs

- [ ] **Extend CJ/ENG5 runbook with diagnostic steps**
  - Document how to:
    - Use `inspect_batch_state.py` to investigate a batch.
    - Interpret upload status vs CJ state.
    - Decide between:
      - Recreate & reseed (for dev/test environments – this task).
      - Any future, production-safe remediation (backfill or manual corrections; out of scope here).
  - Expected artefacts for this task:
    - A documented SQL view name and definition for CJ batch health.
    - A Grafana dashboard panel and alert rule referencing that view.
    - Updated ENG5/CJ runbook section describing how to use these tools during incidents.

- [ ] **Update references in `.claude/HANDOFF.md` or related docs**
  - Link:
    - `TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING.md` (parent).
    - This checklist.
    - The Batch 20 review:
      `.claude/reviews/REVIEW-CJ-ANCHOR-INFRA-BATCH20.md`.

---

## Final success checklist (matches parent task)

- [ ] `ProcessedEssay.is_anchor` correctly reflects `processing_metadata["is_anchor"]` for new ENG5
    and future CJ batches.
- [ ] `BatchFinalizer.finalize_scoring` transitions CJ state from `WAITING_CALLBACKS` to `SCORING`
    and then to `COMPLETED` as part of normal finalization.
- [ ] At least one new ENG5 CJ batch, created via ENG5 runner execute mode, completes end-to-end
    with non-zero grade projections and valid anchors.
- [ ] `inspect_batch_state.py` shows consistent, healthy snapshots for the new ENG5 batch(es).
- [ ] Monitoring/alerting is in place for mismatches between upload status, CJ state, and
    grade projections.
- [ ] Runbooks/docs clearly instruct engineers to prefer **recreate & reseed** for dev/test issues
    like Batch 20 instead of ad hoc SQL backfills.
