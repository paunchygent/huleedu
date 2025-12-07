---
type: decision
id: ADR-0020
status: accepted
created: 2025-12-02
last_updated: 2025-12-07
---

# ADR-0020: CJ Assessment Completion Semantics V2 (Budget vs Coverage)

## Status
Accepted

## Context

Today `CJBatchState.completion_denominator()` (see
`services/cj_assessment_service/models_db.py`) is the single scalar used for
completion math across the CJ service. It is defined as:

```python
completion_denominator = min(
    total_budget or total_comparisons,
    nC2(actual_processed_essays),
)
```

where `nC2(actual_processed_essays)` is derived from the batch’s expected essay
count. This scalar is used by:

- `workflow_continuation.trigger_existing_workflow_continuation`
- `batch_completion_checker` / `batch_completion_policy`
- `batch_monitor`
- the convergence harness and several observability panels

and is documented in:

- `docs/architecture/cj-assessment-service-map.md`
- `docs/operations/cj-assessment-runbook.md`
- `docs/product/epics/cj-stability-and-reliability-epic.md`
- multiple tasks under `TASKS/assessment/`

For large nets, where `total_budget << nC2`, this behaves as intended: the
denominator is effectively the budget. For small nets with explicit budgets and
Phase-2 semantics (e.g. ENG5 LOWER5 with 5 essays and a 60-comparison budget),
the `min(..., nC2)` behaviour becomes pathological:

- `expected_essay_count = 5` → `nC2 = 10`
- even when `MAX_PAIRWISE_COMPARISONS` (and ENG5 overrides) set an effective
  budget of 60 comparisons, `completion_denominator()` returns 10
- as soon as the first coverage wave completes (`callbacks_received = 10`),
  continuation treats “callbacks reached cap” as true and finalizes the batch,
  preventing any budget-driven small-net resampling

At the same time, we have already introduced explicit small-net metadata
(`max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`,
`resampling_pass_count`, `small_net_resampling_cap`) for Phase-2 semantics, and
we have a clear config model for budgets:

- global default: `Settings.MAX_PAIRWISE_COMPARISONS`
- per-request override: `comparison_budget.max_pairs_requested`

The remaining complexity comes from entangling “budget” and “coverage” inside a
single scalar.

## Decision

We will separate **budget** and **coverage** and make `total_budget` the single
source of truth for “how much work this batch is allowed to do”.

1. **Budget as the only denominator**

   - Every real CJ batch must have `CJBatchState.total_budget > 0`.
   - `total_budget` is set once at batch creation as:
     - `comparison_budget.max_pairs_requested` (if present), else
     - `Settings.MAX_PAIRWISE_COMPARISONS`.
   - `completion_denominator()` becomes:

     ```python
     def completion_denominator(self) -> int:
         if not self.total_budget or self.total_budget <= 0:
             raise RuntimeError(
                 "CJBatchState.total_budget must be set before completion math",
             )
         return self.total_budget
     ```

   - No `min(..., nC2)` and no fallback to `total_comparisons` or `nC2`. A real
     batch without `total_budget` is treated as a bug, not a “helped” case.

2. **Coverage and small-net semantics use `nC2` explicitly**

   - `max_possible_pairs = nC2(expected_essay_count)` remains available via
     `_max_possible_comparisons()` but is **not** used as a cap or denominator.
   - Coverage and small-net semantics are driven by:
     - `max_possible_pairs` (coverage_cap)
     - `successful_pairs_count`
     - `unique_coverage_complete`
     - `resampling_pass_count`
     - `small_net_resampling_cap`
   - `ContinuationContext` carries both:
     - `budget_cap = completion_denominator()` (total_budget)
     - `coverage_cap = max_possible_pairs`

3. **Large-net completion remains budget-based**

   - For large nets, completion gating continues to use:
     - `callbacks_received >= budget_cap` (plus stability and success-rate
       checks) as the main stop condition.
   - Because production budgets already satisfy `total_budget << nC2`, this
     preserves current behaviour while simplifying the mental model
     (denominator == budget).

4. **Small-net (e.g. LOWER5) completion uses budget + coverage + resampling**

   - Phase 1: spend comparisons to achieve full coverage of the small net:
     - run until `unique_coverage_complete == True` (`callbacks_received`
       reaches `coverage_cap = nC2`), subject to budget and failure semantics.
   - Phase 2 (small-net resampling):
     - while:
       - `is_small_net`
       - `unique_coverage_complete is True`
       - `callbacks_received < budget_cap`
       - `resampling_pass_count < small_net_resampling_cap`
     - `_can_attempt_small_net_resampling(ctx)` should schedule additional
       comparisons, even though `callbacks_received >= coverage_cap`.
   - Finalization (small nets) only occurs when:
     - stability thresholds and minimum comparison requirements are met, or
     - budget is exhausted (`callbacks_received >= budget_cap`), or
     - `resampling_pass_count == small_net_resampling_cap`, with success-rate
       semantics still enforced.

## Consequences

### Positive

- **Single source of truth for budget**: `total_budget` / `completion_denominator`
  now directly and transparently reflect “how many comparisons this batch may
  perform”.
- **Explicit coverage semantics**: `nC2` is used only where it is meaningful
  (coverage/small-net diagnostics), not mixed into completion math.
- **Small nets behave correctly under explicit budgets**: LOWER5 and similar
  nets can use multi-wave resampling up to their budget and resampling caps,
  rather than being hard-capped at a single coverage wave.
- **Cleaner configuration model**:
  - Docker/env (`MAX_PAIRWISE_COMPARISONS`) defines the default global cap.
  - Per-request overrides (`comparison_budget.max_pairs_requested`) define
    experiment-specific budgets (e.g. ENG5 runs) without touching Docker.

### Negative

- Any tests, docs, or dashboards that assume:

  ```python
  completion_denominator = min(total_budget or total_comparisons, nC2)
  ```

  must be updated.

- Existing synthetic/legacy flows that relied on implicit `nC2` fallbacks will
  need to set `total_budget` explicitly in their fixtures or be retired.

## Implementation Plan

1. **Populate `total_budget` for all real batches**
   - Ensure batch creation paths set `CJBatchState.total_budget` from:
     - `comparison_budget.max_pairs_requested` (when provided), else
     - `Settings.MAX_PAIRWISE_COMPARISONS`.
   - Tighten tests around batch creation and state updates so real batches
     always have `total_budget > 0`.

2. **Update `completion_denominator()`**
   - Change `services/cj_assessment_service/models_db.py` so
     `completion_denominator()` simply returns `total_budget` and raises if it
     is missing or non-positive.
   - Remove use of `_max_possible_comparisons()` from `completion_denominator()`.

3. **Clarify budget vs coverage on `ContinuationContext`**
   - Ensure `_build_continuation_context(...)` passes both:
     - `denominator` (now pure budget)
     - `max_possible_pairs` (coverage) into the context, and that logging and
       diagnostics reflect the new meaning.

4. **Adjust small-net continuation logic**
   - Update `_can_attempt_small_net_resampling(ctx)` and the surrounding logic
     in `workflow_continuation.trigger_existing_workflow_continuation` so that:
     - Phase 2 resampling is allowed while budget remains and resampling cap is
       not reached, even though `callbacks_received >= coverage_cap`.
     - Finalization decisions use `budget_cap`, stability, and success-rate
       thresholds as described above.

5. **Update documentation and epics**
   - Replace the existing “`min(total_budget, nC2)`” description in:
     - `docs/architecture/cj-assessment-service-map.md`
     - `docs/operations/cj-assessment-runbook.md`
     - `docs/product/epics/cj-stability-and-reliability-epic.md`
   - Add references to this ADR where completion semantics are discussed.

6. **Update tests and convergence harness**
   - Update unit and integration tests that assert the old min(nC2, budget)
     semantics (e.g. `test_completion_threshold.py`,
     `test_async_workflow_continuation_integration.py`, batch monitor tests).
   - Add small-net tests for nets like LOWER5 (n=5) with explicit budgets to
     confirm multi-wave resampling behaviour.
   - Re-run convergence harness scenarios to confirm large-net convergence
     remains stable under the new semantics.

## References

- `docs/architecture/cj-assessment-service-map.md`
- `docs/operations/cj-assessment-runbook.md`
- `docs/product/epics/cj-stability-and-reliability-epic.md`
- `docs/decisions/0015-cj-assessment-convergence-tuning-strategy.md`
- `services/cj_assessment_service/models_db.py`
- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`

### Follow-up Work

- Task: `TASKS/assessment/cj-completion-semantics-v2-enforce-total_budget-and-remove-nc2-fallback.md`
  - Purpose: tighten `completion_denominator()` to raise when `total_budget` is missing/invalid, remove `nC2`/`total_comparisons` fallbacks from completion math, and align tests/docs/epics with the strict budget-only invariant described above.
