---
type: decision
id: ADR-0022
status: accepted
created: '2025-12-07'
last_updated: '2025-12-08'
---
# ADR-0022: BatchMonitor Separation of Concerns

## Context

The `BatchMonitor` class in CJ Assessment Service previously violated the Single Responsibility Principle (SRP) by mixing two distinct responsibilities:

1. **Monitoring**: Detecting stuck batches via timeout thresholds and triggering recovery actions
2. **Finalization**: Implementing a full scoring pipeline via an internal `_trigger_scoring()` method (~200 lines, now removed)

This creates several architectural problems:

- **Code duplication**: The `_trigger_scoring()` method duplicates ~200 lines of logic already present in `BatchFinalizer.finalize_scoring()`
- **State semantics divergence**: BatchFinalizer uses `COMPLETE_STABLE` status while BatchMonitor uses `COMPLETED` without intermediate `SCORING` state
- **Maintenance burden**: Changes to finalization logic require updates in two locations
- **Testing complexity**: The monitor-forced completion path is harder to test in isolation

## Decision

**Delegate all finalization logic from BatchMonitor to BatchFinalizer** and remove `_trigger_scoring()` entirely.

BatchMonitor is refactored to:
1. Remain responsible only for monitoring (detecting stuck batches)
2. Delegate to `BatchFinalizer.finalize_scoring()` for progress >= 80% (forced recovery)
3. Publish failure events directly for progress < 80%

A new batch status `COMPLETE_FORCED_RECOVERY` distinguishes monitor-forced completions from callback-driven completions. All terminal states (`COMPLETE_*` and `ERROR_*`) are treated as idempotent terminal statuses in `BatchFinalizer.finalize_scoring()`.

### Post-Refactoring Architecture

```
BatchMonitor (Pure Monitoring)
  ├─ Detects stuck batches
  ├─ progress >= 80% → Delegates to BatchFinalizer.finalize_scoring() with completion_status=COMPLETE_FORCED_RECOVERY
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
- **~200 lines removed**: Elimination of duplicated `_trigger_scoring()` code in BatchMonitor
- **Explicit observability**: Forced recoveries are explicitly labeled via `COMPLETE_FORCED_RECOVERY` and additional `completion_source` metadata (`batch_monitor_forced_recovery` vs `workflow_continuation` / `batch_monitor_completion_sweep`).

### Negative

- **Migration effort**: Existing tests for BatchMonitor scoring path need updates
- **Potential behavior differences**: Must verify identical event outputs for both paths

### Neutral

- **New status enum**: `COMPLETE_FORCED_RECOVERY` adds to status vocabulary but improves observability

## References

- ADR-0020: CJ Assessment Completion Semantics V2
- EPIC-005: CJ Stability & Reliability
- Task: `TASKS/assessment/batchmonitor-separation-of-concerns.md`
