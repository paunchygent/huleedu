---
id: 'batchmonitor-separation-of-concerns'
title: 'US-005.6: BatchMonitor Separation of Concerns'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-07'
last_updated: '2025-12-07'
related: ['ADR-0020', 'ADR-0022', 'EPIC-005']
labels: ['refactoring', 'ddd', 'srp', 'technical-debt']
---
# US-005.6: BatchMonitor Separation of Concerns

## Objective

Eliminate responsibility duplication between `batch_monitor.py` and `BatchFinalizer`. The `_trigger_scoring()` method duplicates ~200 lines of finalization logic that should be centralized in `BatchFinalizer`.

## Context

**SRP Violation in BatchMonitor:**
- **Intended**: Pure monitoring (detect stuck batches, trigger recovery)
- **Actual**: Hybrid monitoring + finalization engine

**Code Duplication (~200 lines):**

| Operation | batch_monitor._trigger_scoring() | BatchFinalizer.finalize_scoring() |
|-----------|----------------------------------|-----------------------------------|
| Fetch batch upload | Lines 468-477 | Lines 150-156 |
| Convert essays | Lines 496-504 | Lines 181-189 |
| Bradley-Terry scoring | Lines 510-518 | Lines 193-201 |
| Grade projections | Lines 533-544 | Lines 214-227 |
| Publish events | Lines 617-625 | Lines 256-264 |

**State Semantics Divergence:**
- BatchFinalizer: `COMPLETE_STABLE`
- BatchMonitor: `COMPLETED` (implicit, no intermediate SCORING)

## Plan

### Phase 1: Add Recovery Status
Add `COMPLETE_FORCED_RECOVERY` to distinguish monitor-forced completions from callback-driven.

### Phase 2: Eliminate Duplication
Replace `_trigger_scoring()` with delegation to `BatchFinalizer.finalize_scoring()`:
```python
# In _handle_stuck_batch(), replace self._trigger_scoring() with:
finalizer = BatchFinalizer(...)
await finalizer.finalize_scoring(batch_id, correlation_id, log_extra={"reason": "monitor_forced"})
```

### Phase 3: Remove Dead Code
Delete `_trigger_scoring()` method (~200 lines).

### Phase 4: Update Tests
- Add BatchFinalizer delegation tests to BatchMonitor
- Verify identical event outputs for both paths

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
  ├─ progress >= 80% → Delegates to BatchFinalizer
  └─ progress < 80% → Publishes failure event directly

BatchFinalizer (Canonical Finalization)
  ├─ finalize_scoring() - all scoring paths
  ├─ finalize_failure() - all failure paths
  └─ finalize_single_essay() - edge case
```

## Success Criteria

- [ ] `BatchMonitor._trigger_scoring()` is removed (~200 lines)
- [ ] `_handle_stuck_batch()` delegates to `BatchFinalizer.finalize_scoring()` for progress >= 80%
- [ ] New `COMPLETE_FORCED_RECOVERY` status distinguishes monitor-forced completions
- [ ] Identical events are published for both callback-driven and monitor-forced paths
- [ ] Unit tests verify BatchFinalizer delegation in monitor path
- [ ] Integration tests confirm event parity between paths
- [ ] All test files under 1000 LoC after splitting

## Implementation Files

### BatchMonitor Consolidation

| File | Action |
|------|--------|
| `services/cj_assessment_service/batch_monitor.py` | Remove `_trigger_scoring()`, add BatchFinalizer delegation |
| `services/cj_assessment_service/cj_core_logic/batch_finalizer.py` | Add optional `source` param for metrics |
| `libs/common_core/.../enums_db.py` | Add `COMPLETE_FORCED_RECOVERY` status |
| `services/cj_assessment_service/tests/unit/test_batch_monitor.py` | Update to verify delegation |

### Test File Splitting

| File | Action |
|------|--------|
| `tests/unit/test_batch_preparation_identity_flow.py` | Split into focused test modules |
| `tests/integration/test_retry_mechanisms_integration.py` | Split basic/advanced |
| `tests/unit/test_grade_projector_swedish.py` | Split projection/boundary |

## Related

- ADR-0020: CJ Assessment Completion Semantics V2
- ADR-0022: BatchMonitor Separation of Concerns (proposed)
- EPIC-005: CJ Stability & Reliability
- `docs/operations/cj-assessment-runbook.md` (80% heuristic docs)
