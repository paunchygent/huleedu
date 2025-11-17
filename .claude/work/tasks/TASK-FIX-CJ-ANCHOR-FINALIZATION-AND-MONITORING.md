# TASK: Fix CJ Anchor Finalization & Monitoring

**Status**: TODO
**Priority**: HIGH  
**Blocking**: None  
**Created**: 2025-11-14  
**Completed**: (pending)

---

## Context

This task is a follow-up to `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md` and its checklist.

- Anchor persistence, uniqueness, and ENG5 content storage are now **correct and validated** (see
  `.claude/research/data/eng5-anchor-validation-report-2025-11-14.txt`).
- A mock ENG5 execution created **CJ batch 20**, which exposed a separate issue in the **CJ
  finalization and monitoring** path:
  - `cj_batch_uploads.status = COMPLETE_STABLE`
  - `cj_batch_states.state = WAITING_CALLBACKS`
  - `grade_projections = 0`
  - No essays visible as anchors to the projector due to a repository bug.

This task addresses the **CJ-side root causes** and ensures future ENG5 / CJ batches complete with
anchors, grade projections, and monitoring in place. It explicitly **avoids backfill** and instead
uses a **recreate + reseed** strategy via the ENG5 runner, since the current ENG5 data is cheap,
non-production test data that is already fully documented in the validation report.

Child checklist (implementation details, commands, and verification steps):

- `TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING-CHECKLIST.md`

---

## Problem Statement

CJ batch 20 (ENG5 validation run) is stuck in a partially completed state:

- Upload status: `COMPLETE_STABLE` (in `cj_batch_uploads`).
- CJ fine-grained state: `WAITING_CALLBACKS` (in `cj_batch_states`).
- Comparisons: 5/5 completed; partial scoring triggered.
- `grade_projections = 0` in `grade_projections` table.
- No essays flagged as anchors via the `is_anchor` column, even though
  `processing_metadata->>'is_anchor' = 'true'` for anchor rows.

Consequences:

- Bradley–Terry rankings are computed, but the grade projector sees **no anchors** and refuses to
  produce projections.
- The batch finalizer logs a misleading "Completed scoring finalization" message without advancing
  the CJ state machine to `SCORING → COMPLETED`.
- Monitoring currently does **not** alert on the discrepancy between `COMPLETE_STABLE` and
  `WAITING_CALLBACKS` with zero projections.

---

## Root Causes

1. **Anchor flag persistence bug**
   - `PostgreSQLCJRepositoryImpl.create_or_update_cj_processed_essay` previously ignored
     `processing_metadata["is_anchor"]` entirely.
   - Result: `ProcessedEssay.is_anchor` remained `FALSE` even when the metadata indicated
     `is_anchor = true`, so the projector treated all essays as students.

2. **Incomplete CJ state transitions in `BatchFinalizer.finalize_scoring`**
   - The scoring finalizer did not transition the CJ state machine out of `WAITING_CALLBACKS`.
   - It set `CJBatchStatusEnum.COMPLETE_STABLE` but left `cj_batch_states.state` unchanged, leaving
     the batch to be "rescued" only by the 6‑hour batch monitor safety net.

3. **Missing monitoring for stuck batches**
   - There is no alert that fires when a batch:
     - Has `COMPLETE_STABLE` upload status, and
     - Has all comparisons completed, but
     - Has `grade_projections = 0` or CJ state ∈ {`WAITING_CALLBACKS`, `SCORING`} for an extended
       period.

---

## Implementation Plan

This task is implemented in **three phases**. As with the anchor infrastructure task, the parent
document stays **architectural and intent-focused**; detailed steps, commands, and test lists live in
`TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING-CHECKLIST.md`.

### Phase 1: Code correctness & regression coverage

**Goal**: Ensure CJ code correctly exposes anchors to the projector, drives the CJ state machine, and
supports safe re-runs for dev/test batches.

**Key outcomes**:

- `create_or_update_cj_processed_essay` persists `is_anchor` derived from
  `processing_metadata["is_anchor"]` on both insert and update.
- `BatchFinalizer.finalize_scoring` transitions the CJ state machine explicitly:
  - `WAITING_CALLBACKS → SCORING` at the start of finalization.
  - `SCORING → COMPLETED` after dual events are published.
- Dual-event publishing uses the **original BOS correlation_id** from `CJBatchUpload` for external
  events, while internal methods continue to use `uuid.UUID` correlation IDs.
- Diagnostics and tests are in place:
  - `scripts/cj_assessment_service/diagnostics/inspect_batch_state.py` for on-demand snapshots.
  - Unit regression for state transitions.
  - Integration regression for anchor persistence via real Postgres.

**Notes**:

- The underlying code and tests for this phase are already present in the repo; this task is
  primarily about verifying behaviour, keeping the tests green, and documenting them as the
  canonical fix for the Batch 20 incident. No new functional changes are expected unless
  regressions are found during verification.

### Phase 2: Recreate & reseed CJ/ENG5 dev data (no backfill)

**Goal**: Remove reliance on fragile dev-only CJ test data (including Batch 20) and **recreate a
clean, validated ENG5 CJ dataset** using the ENG5 runner, instead of backfilling rows in place.

**All reset/reseed operations in this phase apply only to local/dev/test CJ databases, never staging
or production.**

**Key outcomes**:

- CJ dev database is reset or cleaned to remove stale ENG5 batches (including batch 20) and any
  partial projections.
- ENG5 anchors and sample student essays are **reseeded** via the ENG5 runner CLI, producing at
  least one fresh CJ batch that:
  - Uses the corrected anchor flags.
  - Completes finalization end-to-end.
  - Produces grade projections and dual events.
- The previous ENG5 validation artefacts are preserved only in documentation (validation report and
  review), not in live database rows.

**Design points**:

- This phase explicitly **avoids SQL backfill** such as `UPDATE ... SET is_anchor = TRUE` or manual
  manipulation of `grade_projections`.
- Instead, treat the ENG5 dev CJ data as **ephemeral**:
  - Reset or recreate the CJ dev database (or drop the affected batch and related rows).
  - Run the ENG5 runner in execute mode to create a fresh batch under the corrected code.
- All relevant pre-incident state for Batch 20 is preserved in
  `.claude/research/data/eng5-anchor-validation-report-2025-11-14.txt` and
  `.claude/reviews/REVIEW-CJ-ANCHOR-INFRA-BATCH20.md`.
- The child checklist uses example `assignment-id`, `course-id`, `cj-service-url`, and
  `kafka-bootstrap` values aligned with the default ENG5 dev environment; adjust them only if your
  local or CI configuration differs.

### Phase 3: Monitoring, diagnostics & runbooks

**Goal**: Detect stuck CJ batches (like Batch 20) quickly and provide clear operational guidance.

**Key outcomes**:

- A CJ batch monitoring query or view is established (SQL or application-level) that can answer:
  - For each batch: upload status, CJ state, comparison counts, anchor counts, grade projection
    counts, and timestamps.
- For this task, implement that query or view as a SQL view over the CJ database and add a Grafana
  dashboard panel and alert rule based on it; avoid introducing a new long-running service unless
  explicitly agreed.
- Grafana/Loki (or equivalent) alerts configured for conditions such as:
  - Upload status `COMPLETE_STABLE` AND
  - CJ state ∈ {`WAITING_CALLBACKS`, `SCORING`} AND
  - `grade_projections = 0` AND
  - Condition holds for >5–10 minutes.
- Optional: alerts for `SCORING` state persisting for too long even when comparisons are complete.
- Runbook entries updated to include:
  - How to use `inspect_batch_state.py` to investigate a suspect batch.
  - When to choose **recreate & reseed** for dev/test batches versus any future backfill-style
    repair for real production data (not in scope for this task).

---

## Testing Plan

Testing spans unit, integration, and end-to-end validation:

- **Unit tests** (CJ service):
  - Verify `BatchFinalizer.finalize_scoring` transitions CJ state correctly and logs accurately.
- **Integration tests** (CJ service + Postgres):
  - Verify `create_or_update_cj_processed_essay` persists `is_anchor` correctly on inserts and
    updates.
  - Verify `is_anchor` idempotency: flag persists across updates when `processing_metadata` omits
    the `is_anchor` key (prevents accidental resets that caused the Batch 20 incident).
  - Verify grade projections are stored and linked to the correct `cj_batch_id`.
- **ENG5 end-to-end tests**:
  - Use ENG5 runner execute mode in mock LLM configuration to:
    - Register anchors.
    - Run a batch with comparisons.
    - Confirm via `inspect_batch_state.py` that:
      - Upload status is `COMPLETE_STABLE`.
      - CJ state is `COMPLETED`.
      - `grade_projections > 0`.
      - Anchors are present and excluded correctly from student rankings.

Concrete test lists and commands live in the child checklist.

---

## Success Criteria

- ✅ `ProcessedEssay.is_anchor` correctly reflects `processing_metadata["is_anchor"]` for ENG5 and
  future CJ batches.
- ✅ `BatchFinalizer.finalize_scoring` drives CJ batches from `WAITING_CALLBACKS` to `SCORING` to
  `COMPLETED` without relying on the batch monitor.
- ✅ ENG5 dev data is **recreated and reseeded** via the ENG5 runner (no manual backfill), producing
  at least one healthy CJ batch with non-zero grade projections.
- ✅ `inspect_batch_state.py` shows consistent results for new ENG5 batches:
  - Upload status and CJ state both terminal (`COMPLETE_STABLE` / `COMPLETED`).
  - Anchors present; projections > 0.
- ✅ Monitoring alerts are in place for any future mismatches between upload status, CJ state, and
  grade projections.
- ✅ Runbooks/reference docs clearly distinguish between **dev/test recreate & reseed** (this task)
  and any potential future **production-grade remediation** strategies.

---

## Related Documents & Tasks

- `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md` – Anchor persistence, uniqueness, and Content Service
  migration (parent for anchor infra work).
- `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE-CHECKLIST.md` – Developer checklist for anchor infra.
- `.claude/research/data/eng5-anchor-validation-report-2025-11-14.txt` – Detailed ENG5 validation
  with CJ batch 20 analysis.
- `.claude/reviews/REVIEW-CJ-ANCHOR-INFRA-BATCH20.md` – Root cause and remediation review for the
  CJ anchor/finalization incident.
