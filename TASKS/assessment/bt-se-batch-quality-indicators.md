---
id: 'bt-se-batch-quality-indicators'
title: 'BT SE batch quality indicators'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-29'
last_updated: '2025-11-29'
related: ['docs/product/epics/cj-stability-and-reliability.md', 'docs/product/epics/cj-grade-projection-quality.md']
labels: ['observability', 'quality']
---
# BT SE batch quality indicators

## Objective

Introduce domain-aligned BT SE diagnostics and comparison coverage flags on `CJBatchState.processing_metadata` that describe batch quality for observability and analysis, without changing PR-2 completion, stability, or success-rate semantics.

## Context

- PR-3 added BT SE capping and per-batch SE diagnostics in logs and grade projections.
- PR-4 refactored BT scoring into a pure helper (`BTScoringResult` / `compute_bt_scores_and_se`) and now persists `bt_se_summary` on `CJBatchState.processing_metadata` from `trigger_existing_workflow_continuation`.
- EPIC-005/EPIC-006 require clear, machine-readable indicators of:
  - When BT standard errors are inflated (high uncertainty).
  - When comparison coverage is sparse or leaves essays isolated in the CJ graph.
- These indicators must be **observability-only** for this task: they inform dashboards, runbooks, and downstream analysis but MUST NOT move PR-2 safety goalposts (completion denominator, stability thresholds, success-rate guard).

## Plan

1. **Thresholds & Settings**
   - Add CJ settings for BT SE and coverage diagnostics, aligned with existing naming:
     - `BT_MEAN_SE_WARN_THRESHOLD`, `BT_MAX_SE_WARN_THRESHOLD`.
     - `BT_MIN_MEAN_COMPARISONS_PER_ITEM` (and optionally `BT_MAX_ISOLATED_ITEMS_TOLERATED`).
   - Document defaults in the CJ service config docstring and runbook as “diagnostic thresholds” only.
2. **Derive `bt_quality_flags` in workflow layer**
   - In `trigger_existing_workflow_continuation`, after `bt_se_summary` is available:
     - Compute:
       - `bt_se_inflated` (mean/max SE above thresholds).
       - `comparison_coverage_sparse` (mean comparisons per item below threshold).
       - `has_isolated_items` (existing `isolated_items > 0`).
   - Extend `metadata_updates` for `merge_batch_processing_metadata` to include:
     - `"bt_se_summary"` (already threaded by PR-4).
     - `"bt_quality_flags"` with the three booleans above.
   - Keep all writes to `CJBatchState` owned by orchestrators; no scoring-layer changes.
3. **Observability wiring**
   - Extend existing “Callback iteration complete; evaluated stability” log entry to include:
     - `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`.
   - (Optional, EPIC-006 scope) Add Prometheus counters for:
     - `cj_bt_se_inflated_batches_total`.
     - `cj_bt_sparse_coverage_batches_total`.
4. **Testing**
   - Unit tests in `test_workflow_continuation.py`:
     - Scenarios with normal vs inflated SE and dense vs sparse coverage; assert `bt_quality_flags` reflects settings and is JSON-serializable together with `bt_se_summary`.
   - (Optional) A small integration guard to fetch `CJBatchState.processing_metadata` after a scoring run and assert presence and shape of `bt_se_summary` + `bt_quality_flags`.
5. **Documentation**
   - Update EPIC-005/EPIC-006 docs to:
     - Reference `bt_se_summary` and `bt_quality_flags` as the canonical location for BT SE diagnostics and comparison coverage flags.
     - State explicitly that these indicators are informational only in this phase and do not alter completion, stability, or grade assignment behaviour.

## Success Criteria

- `CJBatchState.processing_metadata` contains:
  - `bt_se_summary` with the existing SE diagnostics shape.
  - `bt_quality_flags` with `bt_se_inflated`, `comparison_coverage_sparse`, `has_isolated_items`.
- All existing PR-2 tests for completion denominator, stability, and success-rate behaviour pass unchanged.
- New unit tests assert:
  - Correct flag computation from `bt_se_summary` and `Settings`.
  - JSON-serializability of `processing_metadata` including `bt_se_summary` and `bt_quality_flags`.
- Logs and (if implemented) metrics expose the new flags using the same domain language as EPIC-005/EPIC-006 and the CJ runbooks.

## Related

- EPIC-005: `docs/product/epics/cj-stability-and-reliability.md`
- EPIC-006: `docs/product/epics/cj-grade-projection-quality.md`
- PR-3: BT SE diagnostics & observability (SE capping, logging, grade projection SE summary).
- PR-4: BT scoring core refactor (`BTScoringResult`, `compute_bt_scores_and_se`, `bt_se_summary` persisted on `CJBatchState`).
