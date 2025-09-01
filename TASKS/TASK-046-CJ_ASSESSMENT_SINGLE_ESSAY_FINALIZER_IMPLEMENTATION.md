# TASK-046: CJ Assessment — Centralized Finalizer for Single‑Essay Completion

## Summary

- Fix CJ batches that contain fewer than 2 student essays so they do not stall in `PERFORMING_COMPARISONS`/`WAITING_CALLBACKS`.
- Introduce a centralized “finalizer” that consistently completes batches (DB state + rankings + grade projections + dual event publishing) for both normal (scored) flow and the single‑essay fast path.
- Add an explicit batch status `COMPLETE_INSUFFICIENT_ESSAYS` to make the outcome explicit and observable.

## Background & Problem Statement

Current behavior for single‑essay batches:
- `pair_generation.generate_comparison_tasks` returns an empty list when `len(essays) < 2`.
- `comparison_processing.submit_comparisons_for_async_processing` logs a warning and returns early without transitioning to a terminal state or publishing events.
- The batch remains in an active status (`PERFORMING_COMPARISONS`/`WAITING_CALLBACKS`) indefinitely, causing downstream timeouts and monitor interventions.

This violates our EDA principles (events must flow) and leaves the system in an inconsistent state with no completion events or scoring.

## Goals

- Complete single‑essay CJ batches without timeouts or human intervention.
- Preserve event‑driven contracts (ELS thin completion + RAS rich result via TRUE OUTBOX).
- Maintain identity threading and correlation IDs.
- Keep the solution extensible for future “single‑essay vs anchors” support.

## Non‑Goals

- Implement anchor‑only comparison flow (future enhancement).
- Change event schemas; we only add optional metadata in processing_summary.

## Architectural Alignment

- Rules: 010/020/030/042/048/051/052/080
- Patterns used:
  - Transactional outbox for event publishing
  - Async LLM processing via callbacks (normal path)
  - Centralized completion publishing (`dual_event_publisher`)
  - Structured error handling; avoid forcing BT scoring with zero comparisons

## High‑Level Design

1) Centralize completion in a single “finalizer” function that both paths call:
   - Normal path (callbacks): finalize with scoring → rankings → projections → dual events.
   - Single‑essay fast path: skip LLM/scoring, set minimal scores, rankings → projections → dual events.

2) Add a short‑circuit in orchestrator after essay preparation:
   - If student essay count < 2, invoke the finalizer in `single_essay` mode and return.

3) Add explicit batch status:
   - `CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS`, with Alembic migration for the Postgres enum.
   - Also set real‑time `CJBatchStateEnum.COMPLETED` to avoid batch monitor false positives.

4) Preserve event identity/correlation threading using existing publishers/outbox.

## Detailed Implementation Plan

### 1. Add New Batch Status Enum

- File: `services/cj_assessment_service/enums_db.py`
- Add value (uppercase to match existing style):
  - `COMPLETE_INSUFFICIENT_ESSAYS = "COMPLETE_INSUFFICIENT_ESSAYS"`

Note: This is a DB‑backed SQLAlchemy Enum; an Alembic migration is required.

### 2. Alembic Migration (CJ Service)

- Location: `services/cj_assessment_service/alembic/versions/<timestamp>_add_complete_insufficient_essays.py`
- Migration operations:
  - Alter Postgres type `cj_batch_status_enum` to add value `COMPLETE_INSUFFICIENT_ESSAYS`.
  - Use `ALTER TYPE cj_batch_status_enum ADD VALUE IF NOT EXISTS 'COMPLETE_INSUFFICIENT_ESSAYS';`
  - For downgrade, Postgres cannot drop enum values easily; document that downgrade requires manual remediation or leave as no‑op with a clear comment.

Example (raw SQL in Alembic revision):
```python
from alembic import op

revision = "<generated>"
down_revision = "<prev>"

def upgrade() -> None:
    op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'cj_batch_status_enum'
          AND e.enumlabel = 'COMPLETE_INSUFFICIENT_ESSAYS'
      ) THEN
        ALTER TYPE cj_batch_status_enum ADD VALUE 'COMPLETE_INSUFFICIENT_ESSAYS';
      END IF;
    END $$;
    """)

def downgrade() -> None:
    # Enum value removal is not supported natively; no‑op downgrade.
    pass
```

### 3. Centralized Finalizer

- File: `services/cj_assessment_service/cj_core_logic/batch_finalizer.py`
- Introduce a `BatchFinalizer` class to encapsulate completion logic with two focused methods:
  - `finalize_scoring(...)`: Fetches comparisons, computes scores, sets completed status, builds rankings and grade projections, and publishes dual events.
  - `finalize_single_essay(...)`: Sets explicit insufficient-essays completion, updates CJBatchState to COMPLETED, persists minimal score for the single student, builds rankings and grade projections, and publishes dual events.

Behavior by mode:
- scoring (existing):
  - Fetch essays; compute scores using `scoring_ranking.record_comparisons_and_update_scores`.
  - Update `CJBatchUpload.status = COMPLETE_STABLE` (existing behavior), then rankings, grade projections, and dual event publishing via `publish_dual_assessment_events`.

- single_essay (new):
  - Update `CJBatchUpload.status = COMPLETE_INSUFFICIENT_ESSAYS`.
  - Update real‑time state `CJBatchStateEnum.COMPLETED` using `batch_submission.update_batch_state_in_session`.
  - Persist minimal scoring for the single student essay: `current_bt_score = 0.0`, `comparison_count = 0` (call `database.update_essay_scores_in_batch`).
  - Build rankings via `scoring_ranking.get_essay_rankings`.
  - Compute grade projections via `GradeProjector().calculate_projections` (likely `projections_available=False` without anchors).
  - Publish dual events with `publish_dual_assessment_events` using the batch’s original `event_correlation_id`.

Idempotency:
- Before writing/publishing, if `CJBatchUpload.status` is already in a terminal state, short‑circuit to avoid duplicate outbox entries.

### 4. Orchestrator Short‑Circuit

- File: `services/cj_assessment_service/cj_core_logic/workflow_orchestrator.py`
- After `prepare_essays_for_assessment`:
  - Compute `student_count = sum(1 for e in essays_for_api_model if not e.id.startswith("ANCHOR_"))`.
  - If `student_count < 2`, create a `BatchFinalizer` and call `finalize_single_essay(...)` with `batch_id`, `correlation_id`, and the active DB session, then return (events are queued to outbox).

### 5. Optional: Observability Metadata

- File: `services/cj_assessment_service/cj_core_logic/dual_event_publisher.py`
- In ELS thin event `processing_summary`, add `"single_essay_batch": True` if `len(student_rankings) == 1`.
- This is backward‑compatible (additive metadata) and helps downstream analytics.

## Testing Plan

Unit Tests (CJ service):
- Test: Single‑essay path triggers finalizer and publishes events
  - Arrange: mock `database`, `event_publisher`, `content_client`, `settings`. Prepare one student essay.
  - Act: call orchestrator; assert:
    - `update_cj_batch_status` called with `COMPLETE_INSUFFICIENT_ESSAYS`.
    - Batch state updated to `CJBatchStateEnum.COMPLETED`.
    - `publish_assessment_completed` and `publish_assessment_result` called once.
    - Rankings contain that essay with `bradley_terry_score=0.0`, `rank=1`.
    - RAS event publishes grade projections with `projections_available=False` if no anchors.

- Test: Finalizer idempotency
  - Arrange: `CJBatchUpload.status` already terminal.
  - Act: re‑invoke finalizer.
  - Assert: no duplicate outbox writes.

Contract Tests (leveraging existing patterns):
- Verify ELS status selection: with a single essay and score 0.0 → `COMPLETED_SUCCESSFULLY`.
- Verify anchor distribution field remains present (even if empty).

Execution:
- `pdm run test-unit` for CJ service units.
- `pdm run test-all` to run the full test suite.
- `pdm run typecheck-all` and `pdm run lint` from repo root.

## Migration & Deployment

Steps:
1. Apply Alembic migration in `cj_assessment_service`:
   - `cd services/cj_assessment_service`
   - `pdm run alembic upgrade head`
2. Restart services:
   - `pdm run restart cj_assessment_service`
   - `pdm run restart outbox_relay_worker` (if separate)

Rollback:
- Revert code to previous commit.
- DB downgrade cannot drop enum values safely; leave as no‑op. The extra value is benign.

## Risk Assessment

- Enum migration: using `ADD VALUE IF NOT EXISTS` avoids conflicts and is safe.
- Double publishing: mitigated via finalizer idempotency checks or terminal state guard.
- Event semantics: single‑essay treated as completed successfully by setting BT score to 0.0. If product prefers a different ELS status, we can omit the score to yield `FAILED_CRITICALLY` (not recommended).

## Acceptance Criteria

- Single‑essay CJ batches complete without timeouts.
- `CJBatchUpload.status` = `COMPLETE_INSUFFICIENT_ESSAYS`; `CJBatchStateEnum` = `COMPLETED`.
- ELS thin event and RAS rich event published via outbox (verified in logs/tests).
- No score convergence or insufficient comparison errors raised in this path.
- Optional: `processing_summary.single_essay_batch = true` present for single‑essay batches.

## Work Breakdown

1. Add enum constant and Alembic migration.
2. Implement centralized finalizer and wrap existing scoring finalization.
3. Wire orchestrator short‑circuit to finalizer.
4. Optional metadata in dual event publisher.
5. Add unit tests for single‑essay path and idempotency.
6. Run tests, typechecks, lint.
7. Deploy migration and restart services.

## Estimation

- Dev: 0.5–1 day (code + tests)
- Review/QA: 0.5 day
- Deployment: < 1 hour (with migration)

## Appendix: Pseudocode

```python
# orchestrator.py
essays = prepare_essays_for_assessment(...)
student_count = sum(1 for e in essays if not e.id.startswith("ANCHOR_"))
if student_count < 2:
    await finalize_batch_completion(
        mode="single_essay",
        batch_id=cj_batch_id,
        database=database,
        event_publisher=event_publisher,
        content_client=content_client,
        correlation_id=correlation_id,
        settings=settings,
    )
    return CJAssessmentWorkflowResult(rankings=[], batch_id=str(cj_batch_id))

# batch_callback_handler.py
async def finalize_batch_completion(mode: str, batch_id: int, ...):
    if mode == "scoring":
        # existing scoring + publish path
        return await _trigger_batch_scoring_completion(...)
    elif mode == "single_essay":
        # set status + state, set 0.0 score for single essay
        # rankings = get_essay_rankings(...)
        # grade_projections = GradeProjector().calculate_projections(...)
        # publish_dual_assessment_events(...)
        return
```
