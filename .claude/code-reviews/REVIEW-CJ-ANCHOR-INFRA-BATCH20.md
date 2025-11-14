# CJ Anchor Infrastructure / Batch 20 Incident Review

## 1. Incident Summary

- **Service**: CJ Assessment Service
- **Flow**: ENG5 runner → CJ comparisons → Bradley–Terry ranking → grade projection → dual event publication
- **Batch**: `cj_batch_id = 20`
- **Observed wedge**:
  - Upload status: `COMPLETE_STABLE`
  - CJ fine-grained state: `WAITING_CALLBACKS`
  - Comparisons: 5/5 completed, partial scoring triggered
  - `grade_projections = 0`
  - No essays flagged as anchors on the materialized `is_anchor` column

Result: Bradley–Terry rankings were computed for student essays only, but no anchors were visible to the projector. Grade projection was skipped, no dual events were emitted, and the CJ state machine never advanced out of `WAITING_CALLBACKS`, leaving the batch dependent on the 6‑hour batch monitor safety net.

---

## 2. Root-Cause Analysis vs Architecture

### 2.1 Repository behaviour (`db_access_impl.py`)

The concrete implementation of `CJRepositoryProtocol` in
`PostgreSQLCJRepositoryImpl.create_or_update_cj_processed_essay` now behaves as:

- Derives `anchor_flag` from `processing_metadata["is_anchor"]` when present.
- On **insert**:
  - Creates a `ProcessedEssay` row with `is_anchor` set iff `anchor_flag` is not `None`.
- On **update**:
  - Updates core fields and fully replaces `processing_metadata`.
  - Updates `is_anchor` only if `processing_metadata` carries an explicit `is_anchor` key.

This aligns with the intended invariant:

- `processing_metadata["is_anchor"]` is the canonical flag from upstream.
- `ProcessedEssay.is_anchor` is the query-friendly, materialized flag derived from metadata.

The original bug was that the repository **ignored `is_anchor` entirely**, so downstream projectors saw every essay as a student. Given the DB inspection showed `processing_metadata->>'is_anchor' = 'true'` while `is_anchor = false`, the root cause is consistent with the code delta.

### 2.2 Batch finalization (`batch_finalizer.py`)

The `BatchFinalizer.finalize_scoring` implementation now:

1. Loads `CJBatchUpload` by `batch_id`. If missing, logs an error and returns.
2. Transitions the CJ state machine into `SCORING` via `update_batch_state_in_session` with the provided `correlation_id`.
3. Fetches essays via `get_essays_for_cj_batch` and builds `EssayForComparison` models.
4. Invokes `scoring_ranking.record_comparisons_and_update_scores` using the internal `correlation_id`.
5. Sets `CJBatchStatusEnum.COMPLETE_STABLE` on the batch upload.
6. Fetches rankings via `scoring_ranking.get_essay_rankings` and computes projections via `GradeProjector.calculate_projections`.
7. Derives the **original** BOS correlation ID from `batch_upload.event_correlation_id` and threads it into `publish_dual_assessment_events`.
8. Publishes both `CJAssessmentCompletedV1` and `AssessmentResultV1` events through the configured `CJEventPublisherProtocol` implementation.
9. Transitions the CJ state machine from `SCORING` to `COMPLETED` with the internal `correlation_id`.

This behaviour matches the desired architecture:

- Internal flow: uses a request-scoped `uuid.UUID` `correlation_id` for logging and internal threading.
- External events: use the original BOS correlation_id from the batch, satisfying the E2E tests that filter envelopes by stringified UUID.
- CJ state machine: no longer leaves batches in `WAITING_CALLBACKS` after completion; instead it explicitly drives `SCORING → COMPLETED`.

The observed logs – GradeProjector warning about missing anchors followed by a misleading “Completed scoring finalization” log – are fully explained by the previous absence of state transitions and the repository bug.

---

## 3. Idempotency and Transaction Boundaries

### 3.1 Repository idempotency

- `create_or_update_cj_processed_essay` is idempotent at the repository level:
  - A second call with the same `els_essay_id` updates fields and metadata in place.
  - `is_anchor` is only modified when `processing_metadata["is_anchor"]` is explicitly provided, preventing accidental resets.
- Session lifecycle is externalized via `PostgreSQLCJRepositoryImpl.session()` async context manager, which wraps all operations in a transaction with commit/rollback semantics.

This fits the service’s standard pattern (BOS/ELS-style):

- Business logic receives a session from the repository.
- All repository methods participate in the ambient transaction.

### 3.2 `finalize_scoring` idempotency

- `finalize_scoring` **does not include an explicit idempotency guard** (unlike `finalize_single_essay`, which bails out if status is `COMPLETE*` or `ERROR*`).
- Re-running `finalize_scoring` will:
  - Re-enter `SCORING`, recompute scores and projections.
  - Maintain or re-set `COMPLETE_STABLE` status.
  - Re-publish dual events with the same BOS correlation_id.
  - Re-set CJ state to `COMPLETED`.

For the specific Batch 20 incident this is desirable:

- Batch 20 is already `COMPLETE_STABLE` but still `WAITING_CALLBACKS` with `grade_projections = 0`.
- After anchor backfill, a re-run of `finalize_scoring` will:
  - Discover anchors via `ProcessedEssay.is_anchor`.
  - Produce grade projections.
  - Move CJ state to `SCORING → COMPLETED`.

The main architectural requirement is that **downstream consumers treat dual events as idempotent**, which is already a design goal for the event-driven architecture. There may be a duplicate completion for Batch 20 from the perspective of Kafka topics, but this is acceptable given no prior completion events were successfully emitted for this batch.

### 3.3 Transaction boundaries

- `finalize_scoring` assumes the caller manages the `AsyncSession` lifecycle.
- When used inside `async with database.session() as session`, the following operations occur within a single transaction:
  - CJ state updates (`SCORING` and `COMPLETED`).
  - BT scoring updates via `record_comparisons_and_update_scores`.
  - Batch status update to `COMPLETE_STABLE`.
  - Grade projections persistence.
  - Outbox writes via `publish_dual_assessment_events`.

This is consistent with the services’ outbox-based event publishing strategy and ensures atomic updates from the perspective of external observers.

---

## 4. Assessment of the Remediation Plan

### 4.1 Backfill anchors

Proposed SQL:

```sql
UPDATE cj_processed_essays
SET is_anchor = TRUE
WHERE processing_metadata->>'is_anchor' = 'true'
  AND cj_batch_id = 20;
```

Assessment:

- Correctly uses the canonical `processing_metadata` flag to repair the materialized column.
- Restricting to `cj_batch_id = 20` is safe and targeted.

Recommended refinement:

```sql
UPDATE cj_processed_essays
SET is_anchor = TRUE
WHERE processing_metadata->>'is_anchor' = 'true'
  AND cj_batch_id = 20
  AND (is_anchor IS DISTINCT FROM TRUE);
```

Optional one-time global sweep (ops window):

```sql
UPDATE cj_processed_essays
SET is_anchor = TRUE
WHERE processing_metadata->>'is_anchor' = 'true'
  AND (is_anchor IS DISTINCT FROM TRUE);
```

This captures any other silently affected batches prior to deployment of the repository fix.

### 4.2 Re-finalize Batch 20

Operational intent:

- Use application code (not manual SQL) to recompute rankings, projections, and events.
- Transition the CJ state machine out of `WAITING_CALLBACKS`.

Key recommendation on **ordering**:

- Ensure the re-finalization is executed against the **fixed** `BatchFinalizer.finalize_scoring` implementation.
- That means either:
  - Deploy the patched CJ Assessment Service first and then run an admin job inside that environment; or
  - Build and run a one-off admin container from the patched branch and use its context to call `finalize_scoring`.

The call should follow the standard pattern:

```python
async with repository.session() as session:
    await finalizer.finalize_scoring(
        batch_id=20,
        correlation_id=<fresh UUID>,  # internal threading
        session=session,
        log_extra={"batch_id": 20, "source": "admin_refinalization"},
    )
```

The method will internally recover the original BOS correlation ID from `batch_upload.event_correlation_id` for event publishing.

### 4.3 Deploy code changes

Deployment of the updated:

- `PostgreSQLCJRepositoryImpl.create_or_update_cj_processed_essay`
- `BatchFinalizer.finalize_scoring`

will prevent recurrence:

- Future anchors will be persisted correctly.
- Completed batches will no longer remain stuck in `WAITING_CALLBACKS` after projections and event publication.

### 4.4 Smoke tests

Post-deployment, recommended smoke validation:

- Trigger a fresh ENG5 batch in the dev stack (or run existing ENG5 integration tests).
- Use `scripts/cj_assessment_service/diagnostics/inspect_batch_state.py` to verify:
  - Upload status: `COMPLETE_STABLE`.
  - CJ state: `COMPLETED`.
  - `grade_projections > 0` for non-trivial student batches.
  - `is_anchor` materialized flag matches `processing_metadata["is_anchor"]` for anchor essays.
- At the Kafka/event level, confirm:
  - `CJAssessmentCompletedV1` and `AssessmentResultV1` are both present for the batch.
  - `AssessmentResultV1.essay_results` exclude anchors based on `is_anchor = true`.

### 4.5 Monitoring and alerting

The proposed condition:

> Flag any batch where status LIKE 'COMPLETE%' but grade_projections = 0 or CJ state ≠ COMPLETED for >5 minutes.

is directionally correct. To reduce noise and focus on real issues:

- Scope to batches where:
  - Upload status is `COMPLETE_STABLE` (or equivalent finalized upload state).
  - Comparison counts indicate work is finished (if available in the CJ state row).
- Trigger alerts when:
  - CJ state ∈ {`WAITING_CALLBACKS`, `SCORING`} **AND** `grade_projections = 0` for more than N minutes.

This directly guards against the wedge class observed in Batch 20 while avoiding spurious alerts during normal in-flight processing.

---

## 5. Final Recommendations

1. **Accept the team’s root-cause analysis**: It is consistent with the code and the architecture (anchors, CJ state machine, dual-event model).
2. **Keep the repository and finalizer changes** as implemented; they are well-targeted and align with service patterns.
3. **Run the constrained backfill** for Batch 20 and consider a one-time global sweep for safety.
4. **Execute re-finalization against the patched code** using the established `BatchFinalizer.finalize_scoring` path and standard transaction handling.
5. **Complete deployment and smoke verification** using the existing ENG5 test harness and `inspect_batch_state.py`.
6. **Implement focused monitoring** on `COMPLETE_STABLE` batches with missing projections or non-COMPLETED CJ states, with a small time window (5–10 minutes) to avoid transient noise.

Once these steps are executed, Batch 20 will be unblocked and future ENG5 batches should naturally follow the correct completion workflow without requiring manual intervention.
