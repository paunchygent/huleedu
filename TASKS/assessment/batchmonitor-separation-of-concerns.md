---
id: 'batchmonitor-separation-of-concerns'
title: 'US-005.6: BatchMonitor Separation of Concerns'
type: 'task'
status: 'completed'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-07'
last_updated: '2025-12-09'
related: ['ADR-0020', 'ADR-0022', 'EPIC-005']
labels: ['refactoring', 'ddd', 'srp', 'technical-debt']
---
# US-005.6: BatchMonitor Separation of Concerns

## Objective

Eliminate responsibility duplication between `batch_monitor.py` and `BatchFinalizer`. The historical `_trigger_scoring()` method duplicated ~200 lines of finalization logic that is now centralized in `BatchFinalizer`.

## Context

**SRP Violation in BatchMonitor:**
- **Intended**: Pure monitoring (detect stuck batches, trigger recovery)
- **Actual**: Hybrid monitoring + finalization engine

**State Semantics & Ownership (post-refactor):**
- BatchFinalizer:
  - Owns all SCORING → COMPLETED/FAILED transitions.
  - Sets `CJBatchUpload.completed_at` for both success and failure.
  - Publishes dual events via `publish_dual_assessment_events`.
  - Treats all `COMPLETE_*` and `ERROR_*` statuses (including `COMPLETE_FORCED_RECOVERY`) as terminal for idempotency.
- BatchMonitor:
  - Pure monitoring and recovery:
    - Detects stuck batches via timeout + monitored states.
    - For progress >= 80%, forces CJ state to SCORING and delegates to `BatchFinalizer.finalize_scoring(...)` with `completion_status=COMPLETE_FORCED_RECOVERY`.
    - For progress < 80%, marks FAILED and publishes `CJAssessmentFailedV1` directly.

## Plan

### Phase 1: Add Recovery Status
Add `COMPLETE_FORCED_RECOVERY` to distinguish monitor-forced completions from callback-driven.

### Phase 2: Eliminate Duplication
Replace `_trigger_scoring()` with delegation to `BatchFinalizer.finalize_scoring()` (DONE):
```python
# In _handle_stuck_batch(), replace self._trigger_scoring() with:
finalizer = BatchFinalizer(...)
await finalizer.finalize_scoring(
    batch_id=batch_id,
    correlation_id=correlation_id,
    log_extra={"reason": "monitor_forced_recovery"},
    completion_status=CJBatchStatusEnum.COMPLETE_FORCED_RECOVERY,
    source="batch_monitor_forced_recovery",
)
```

### Phase 3: Remove Dead Code
Delete `_trigger_scoring()` method (~200 lines). (DONE)

### Phase 4: Update Tests
- Add BatchFinalizer delegation tests to BatchMonitor (DONE)
  - `services/cj_assessment_service/tests/unit/test_batch_monitor_unit.py::TestBatchMonitorRecoveryStrategy::test_recovery_strategy_high_progress_forces_scoring`
- Verify identical event outputs for both paths (DONE)
  - `services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py::test_finalize_scoring_event_parity_for_forced_recovery`

### Phase 5: Split Test Files (Critical LoC)
Split 3 test files approaching 1000-line limit:

| File | Lines | Split Strategy |
|------|-------|----------------|
| `test_batch_preparation_identity_flow.py` | 961 | Split by flow scenarios |
| `test_retry_mechanisms_integration.py` | 897 | Separate basic vs advanced retry |
| `test_grade_projector_swedish.py` | 888 | Separate projection vs boundary tests |

## Post-Refactoring Architecture

```
BatchMonitor (Pure Monitoring)
  ├─ Detects stuck batches
  ├─ progress >= 80% → Delegates to BatchFinalizer.finalize_scoring(completion_status=COMPLETE_FORCED_RECOVERY)
  └─ progress < 80% → Publishes failure event directly

BatchFinalizer (Canonical Finalization)
  ├─ finalize_scoring() - all scoring paths (including forced recovery)
  ├─ finalize_failure() - all failure paths
  └─ finalize_single_essay() - edge case
```

## Success Criteria

- [x] `BatchMonitor._trigger_scoring()` is removed (~200 lines)
- [x] `_handle_stuck_batch()` delegates to `BatchFinalizer.finalize_scoring()` for progress >= 80%
- [x] New `COMPLETE_FORCED_RECOVERY` status distinguishes monitor-forced completions
- [x] Identical events are published for both callback-driven and monitor-forced paths
      (guarded by `test_batch_finalizer_scoring_state.py::test_finalize_scoring_event_parity_for_forced_recovery`)
- [x] Unit tests verify BatchFinalizer delegation in monitor path
- [x] Integration-style tests confirm event parity between paths
      (BatchFinalizer + scoring + grade projection + dual event publishing exercised together)

## Implementation Files

### BatchMonitor Consolidation

| File | Action |
|------|--------|
| `services/cj_assessment_service/batch_monitor.py` | Remove `_trigger_scoring()`, add BatchFinalizer delegation for forced recovery and completion sweep paths |
| `services/cj_assessment_service/cj_core_logic/batch_finalizer.py` | Accept `completion_status` and `source`, handle COMPLETE_FORCED_RECOVERY, centralize SCORING → COMPLETED transitions and dual-event publishing |
| `services/cj_assessment_service/enums_db.py` | Add `COMPLETE_FORCED_RECOVERY` status to `CJBatchStatusEnum` |
| `services/cj_assessment_service/alembic/versions/20251208_1200_cj_forced_recovery_status.py` | Add `COMPLETE_FORCED_RECOVERY` label to `cj_batch_status_enum` via Alembic migration |
| `services/cj_assessment_service/tests/unit/test_batch_monitor_unit.py` | Verify 80% threshold behavior, forced-to-SCORING metadata, and BatchFinalizer delegation with `completion_status=COMPLETE_FORCED_RECOVERY` and `source='batch_monitor_forced_recovery'` |
| `services/cj_assessment_service/tests/unit/test_batch_finalizer_scoring_state.py` | Verify SCORING → COMPLETED transition, batch completion timestamp, and event parity between callback-driven and forced-recovery paths |
| `services/cj_assessment_service/tests/unit/test_batch_finalizer_idempotency.py` | Treat `COMPLETE_FORCED_RECOVERY` as a terminal status in finalize_scoring idempotency guard |
| `services/cj_assessment_service/tests/integration/test_cj_batch_status_forced_recovery_migration.py` | Guard Alembic head and assert `cj_batch_status_enum` contains `COMPLETE_FORCED_RECOVERY` on a clean PostgreSQL instance |

### Test File Splitting

| File | Action |
|------|--------|
| `tests/unit/test_batch_preparation_identity_flow.py` | Split into focused test modules |
| `tests/integration/test_retry_mechanisms_integration.py` | Split basic/advanced |
| `tests/unit/test_grade_projector_swedish.py` | Split projection/boundary |

> NOTE: Large test file splitting remains as follow-up test-quality refactoring work and is no longer in scope for US-005.6 completion. Track and execute via separate testing/quality tasks.

## Related

- ADR-0020: CJ Assessment Completion Semantics V2
- ADR-0022: BatchMonitor Separation of Concerns (proposed)
- EPIC-005: CJ Stability & Reliability
- `docs/operations/cj-assessment-runbook.md` (80% heuristic docs)
