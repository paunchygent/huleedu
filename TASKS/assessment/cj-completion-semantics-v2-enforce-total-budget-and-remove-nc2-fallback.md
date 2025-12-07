---
id: 'cj-completion-semantics-v2-enforce-total-budget-and-remove-nc2-fallback'
title: 'CJ completion semantics v2: enforce total_budget and remove nC2 fallback'
type: 'task'
status: 'completed'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-03'
last_updated: '2025-12-07'
related: []
labels: []
---
# CJ completion semantics v2: enforce total_budget and remove nC2 fallback

## Objective

Make CJ completion semantics v2 fully budget-only by:

- Treating `CJBatchState.total_budget` as a required invariant for all real CJ batches.
- Removing the silent `nC2`/`total_comparisons` fallbacks from `completion_denominator()`, so missing `total_budget` surfaces as an explicit error instead of being “helped”.
- Auditing tests/docs/epics/ADRs to align with the stricter contract and avoid legacy invariants quietly masking bugs.

## Context

- ADR‑0020 (`docs/decisions/0020-cj-assessment-completion-semantics-v2.md`) defines the v2 model:
  - `total_budget` is the single source of truth for “how much work this batch is allowed to do”.
  - `completion_denominator()` should simply return `total_budget` and treat missing/zero budgets as a bug.
  - Coverage/small‑net semantics (`nC2`, `max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`, `resampling_pass_count`) are handled explicitly via small‑net metadata, not by clamping the denominator to `nC2`.
- Current implementation has partially adopted this:
  - `BatchProcessor._update_batch_state_with_totals()` seeds `CJBatchState.total_budget` from `processing_metadata["comparison_budget"]["max_pairs_requested"]` on first submission.
  - `completion_denominator()` prefers `total_budget` and is used consistently across continuation (`workflow_continuation`), completion checking (`batch_completion_checker`, `batch_completion_policy`), and monitoring (`batch_monitor`).
  - Unit tests (`test_batch_state_tracking.py`, `test_completion_threshold.py`, workflow continuation tests) assume the budget-first behaviour for real batches.
- However, we still retain legacy fallbacks:
  - If `total_budget` is missing/zero, `completion_denominator()` falls back to `total_comparisons` and then to `_max_possible_comparisons()` (`nC2`), which can silently “fix” misconfigured batches instead of failing fast.
  - Some tests and docs still reference `min(total_budget, nC2)` semantics or rely on these fallbacks when constructing synthetic states.
- To fully align with ADR‑0020 and avoid subtle bugs in future ENG5/CJ experiments (including LOWER5), we need a cleanup pass that:
  - Removes the `nC2`/`total_comparisons` fallback from completion math.
  - Ensures all legitimate entrypoints seed `total_budget` deterministically.
  - Updates ADRs/epics/docs/tests to reflect the stricter invariant.

## Plan

1. **Tighten `completion_denominator()` contract**
   - Update `CJBatchState.completion_denominator()` in `services/cj_assessment_service/models_db.py` to:
     - Return `total_budget` when `total_budget > 0`.
     - Raise a descriptive error (e.g. `RuntimeError`) when `total_budget` is missing/invalid for a real batch.
   - Remove use of `_max_possible_comparisons()` from completion math; keep `nC2` only in coverage helpers and repository coverage metrics.

2. **Audit and harden batch creation / state seeding**
   - Confirm all batch creation/submission paths set `total_budget` deterministically:
     - `batch_preparation.create_cj_batch` + `PostgreSQLCJBatchRepository.create_new_cj_batch`.
     - `ComparisonBatchOrchestrator._prepare_batch_state` + `BatchProcessor._update_batch_state_with_totals`.
     - Retry/continuation paths that may touch state without going through the full initial submission (e.g. synthetic harnesses, dev utilities).
   - Add tests (or extend existing ones) so any missing `total_budget` on real batches is caught at unit/integration level (e.g. `test_real_database_integration.py`, `test_batch_state_multi_round_integration.py`).

3. **Update tests that rely on legacy fallbacks**
   - Identify tests that:
     - Assert `min(total_budget, nC2)` behaviour.
     - Construct `CJBatchState` without `total_budget` and still call `completion_denominator()`.
   - Update them to:
     - Set `total_budget` explicitly where the behaviour under test is budget-based.
     - Use explicit coverage helpers (e.g. `get_coverage_metrics_for_batch`, `build_small_net_context`) instead of `completion_denominator()` when testing coverage/nC2 semantics.
     - Expect an exception for deliberately misconfigured states, where appropriate.

4. **Document the stricter invariant in ADR‑0020 and CJ epics**
   - Update ADR‑0020:
     - Set status to “accepted” once implementation lands.
     - Make explicit that `completion_denominator()` raises when `total_budget` is missing/invalid and that any such state is considered a bug.
   - Update CJ stability/continuation epic (`docs/product/epics/cj-stability-and-reliability-epic.md`) to:
     - Reflect “budget-only denominator” semantics.
     - Clarify that coverage (`nC2`) is never used as a denominator or implicit cap — only as coverage diagnostics and small‑net metadata.

5. **Align ENG5/LOWER5 docs and tasks**
   - Update:
     - `TASKS/assessment/cj-completion-semantics-v2--budget-vs-coverage.md`
     - `TASKS/assessment/cj-completion-semantics-v2--eng5--lower5.md`
     - ENG5 program task(s) that reference completion semantics:
       - `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
   - Ensure they all:
     - Describe completion math strictly in terms of `total_budget`.
     - Treat any batch missing `total_budget` as misconfigured.

6. **Add a small safety net for legacy/synthetic utilities**
   - Where we intentionally construct synthetic `CJBatchState` objects for tools (e.g. diagnostics scripts, convergence harness), ensure:
     - These utilities explicitly set `total_budget` in their fixtures, OR
     - They are updated to call coverage helpers directly instead of `completion_denominator()`.
   - Document this behaviour in the relevant scripts’ headers or README sections so future tooling does not accidentally reintroduce hidden fallbacks.

## Success Criteria

- `CJBatchState.completion_denominator()`:
  - Returns `total_budget` for all real CJ batches.
  - Raises a clear error when `total_budget` is missing/invalid instead of silently falling back to `nC2` or `total_comparisons`.
- All batch creation and submission paths deterministically seed `total_budget` (verified by tests and spot‑checking real DB state via `inspect_batch_state.py` or similar diagnostics).
- No tests or docs describe or rely on `min(total_budget, nC2)` behaviour:
  - Unit/integration tests explicitly set `total_budget` when using `completion_denominator()`.
  - Coverage/nC2‑related tests use dedicated coverage helpers/metadata.
- ADR‑0020 and the CJ stability epic are updated to describe the stricter invariant and reference this task.
- ENG5/LOWER5 tasks and docs (especially those guiding experiments) describe completion semantics purely in terms of budget, and no longer mention `nC2` as a denominator.

## Related

- ADR‑0020 `docs/decisions/0020-cj-assessment-completion-semantics-v2.md`
- `docs/architecture/cj-assessment-service-map.md`
- `docs/operations/cj-assessment-runbook.md`
- `docs/product/epics/cj-stability-and-reliability-epic.md`
- `TASKS/assessment/cj-completion-semantics-v2--budget-vs-coverage.md`
- `TASKS/assessment/cj-completion-semantics-v2--eng5--lower5.md`
- `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`

## Progress (2025-12-04)

- Coverage helper semantics have been aligned with Bradley–Terry scoring:
  - `PostgreSQLCJComparisonRepository.get_coverage_metrics_for_batch` now treats any unordered pair with a non-null, non-`"error"` winner as “successful,” regardless of whether the winner originated as an enum or the normalized `"essay_a"` / `"essay_b"` strings.
  - Pairs that only ever produced `"error"` winners are ignored for coverage; pairs that first errored and later succeeded via retry now count as covered.
  - Guarded by `services/cj_assessment_service/tests/unit/test_comparison_repository_coverage_metrics.py`:
    - `test_get_coverage_metrics_for_batch_returns_expected_counts`
    - `test_coverage_ignores_error_only_pairs`
    - `test_coverage_counts_retry_success_after_error`
- Small-net continuation and completion tests have been split into SRP-aligned modules under `services/cj_assessment_service/tests/unit/`:
  - `test_workflow_continuation_check.py` (denominator/budget resolution + continuation gate).
  - `test_workflow_continuation_orchestration.py` (budget/cap and “request more vs finalize” orchestration; now <500 LoC).
  - `test_workflow_continuation_success_rate.py` (success-rate-driven failure semantics).
  - `test_workflow_small_net_resampling.py` (Phase-2 small-net resampling and `resampling_pass_count` caps).
  - `test_workflow_continuation_metadata_bt_flags.py` (BT SE summaries and `bt_quality_flags` propagation).
- These changes ensure coverage (`max_possible_pairs`, `successful_pairs_count`, `unique_coverage_complete`) is fully decoupled from `completion_denominator()` and owned by explicit helpers/metadata, paving the way for enforcing the strict `total_budget`-only denominator described in this task.

## Completed (2025-12-07)

### 1. Tightened `completion_denominator()` contract

**File:** `services/cj_assessment_service/models_db.py:315-334`

- `completion_denominator()` now returns `total_budget` only
- Raises `RuntimeError` when `total_budget` is missing or invalid (None, 0, negative)
- Removed all fallback logic (total_comparisons, nC2)
- Updated `_max_possible_comparisons()` docstring to clarify coverage-only usage

### 2. Updated callers to handle RuntimeError gracefully

All callers now wrap `completion_denominator()` in try/except with structured logging:

| File | Line | Error Handling Strategy |
|------|------|-------------------------|
| `batch_completion_checker.py` | L86-103 | Return `False` (batch not complete) |
| `batch_completion_policy.py` | L30-45, L107-127 | Return `False` / skip partial_scoring_triggered |
| `batch_monitor.py` | L241-257 | Treat as 0% progress (surfaces via stuck batch alerting) |
| `workflow_continuation.py` | L76-91, L216-230 | Return early (cannot continue) |

### 3. Updated tests

- Added explicit `RuntimeError` tests in `test_completion_threshold.py`:
  - `test_completion_denominator_raises_when_total_budget_missing()`
  - `test_completion_denominator_raises_when_total_budget_zero()`
- Updated all test fixtures to explicitly set `total_budget`:
  - `test_callback_state_manager.py`: `create_batch_state(total_budget=10)`
  - `test_batch_monitor_unit.py`: `create_stuck_batch_state(total_budget=total)`
  - `test_callback_state_manager_extended.py`: `create_test_batch_state(total_budget=10)`
  - `test_batch_completion_checker.py`: `sample_batch_state.total_budget = 100`
  - `test_batch_completion_policy.py`: parametrized tests use `total_budget`
  - `test_workflow_continuation_check.py`: `batch_state.total_budget = 10`

### 4. Updated documentation

- `docs/architecture/cj-assessment-service-map.md:34`: Changed `min(total_budget, nC2)` to `total_budget per ADR-0020 v2`
- `docs/product/epics/cj-stability-and-reliability-epic.md`: Updated Phase-1 semantics to describe pure budget-based completion
- `docs/decisions/0020-cj-assessment-completion-semantics-v2.md`: Set status to "accepted"

### Verification

All unit tests pass. Type checking clean.
