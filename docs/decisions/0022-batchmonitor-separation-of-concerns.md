---
type: decision
id: ADR-0022
status: proposed
created: '2025-12-07'
last_updated: '2025-12-07'
---
# ADR-0022: BatchMonitor Separation of Concerns

## Status

Proposed

## Context

The `BatchMonitor` class in CJ Assessment Service currently violates the Single Responsibility Principle (SRP) by mixing two distinct responsibilities:

1. **Monitoring**: Detecting stuck batches via timeout thresholds and triggering recovery actions
2. **Finalization**: Implementing a full scoring pipeline via `_trigger_scoring()` method (~200 lines)

This creates several architectural problems:

- **Code duplication**: The `_trigger_scoring()` method duplicates ~200 lines of logic already present in `BatchFinalizer.finalize_scoring()`
- **State semantics divergence**: BatchFinalizer uses `COMPLETE_STABLE` status while BatchMonitor uses `COMPLETED` without intermediate `SCORING` state
- **Maintenance burden**: Changes to finalization logic require updates in two locations
- **Testing complexity**: The monitor-forced completion path is harder to test in isolation

### Current State

| Operation | batch_monitor._trigger_scoring() | BatchFinalizer.finalize_scoring() |
|-----------|----------------------------------|-----------------------------------|
| Fetch batch upload | Lines 468-477 | Lines 150-156 |
| Convert essays | Lines 496-504 | Lines 181-189 |
| Bradley-Terry scoring | Lines 510-518 | Lines 193-201 |
| Grade projections | Lines 533-544 | Lines 214-227 |
| Publish events | Lines 617-625 | Lines 256-264 |

## Decision

**Delegate all finalization logic from BatchMonitor to BatchFinalizer**.

BatchMonitor will be refactored to:
1. Remain responsible only for monitoring (detecting stuck batches)
2. Delegate to `BatchFinalizer.finalize_scoring()` for progress >= 80%
3. Publish failure events directly for progress < 80%

A new batch status `COMPLETE_FORCED_RECOVERY` will distinguish monitor-forced completions from callback-driven completions.

### Post-Refactoring Architecture

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

## Consequences

### Positive

- **Single source of truth**: All finalization logic centralized in BatchFinalizer
- **Reduced maintenance**: Changes to finalization semantics require updates in one location
- **Improved testability**: BatchMonitor can be tested with mocked BatchFinalizer
- **Clear boundaries**: Monitoring and finalization responsibilities cleanly separated per DDD principles
- **~200 lines removed**: Elimination of duplicated code

### Negative

- **Migration effort**: Existing tests for BatchMonitor scoring path need updates
- **Potential behavior differences**: Must verify identical event outputs for both paths

### Neutral

- **New status enum**: `COMPLETE_FORCED_RECOVERY` adds to status vocabulary but improves observability

## References

- ADR-0020: CJ Assessment Completion Semantics V2
- EPIC-005: CJ Stability & Reliability
- Task: `TASKS/assessment/batchmonitor-separation-of-concerns.md`
