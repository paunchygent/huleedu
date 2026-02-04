---
id: 'essay-scoring-shap-default-full-test-set'
title: 'essay-scoring shap default full test set'
type: 'task'
status: 'done'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-04'
related: []
labels: []
---
# essay-scoring shap default full test set

## Objective

Make SHAP generation default to using the full test split (no sampling) for essay-scoring research
`run` executions, so SHAP artifacts are representative and directly usable for post-run analysis.

## Context

Current SHAP generation samples at most 500 rows (`shap_values.npy` shape `(500, n_features)`).
This is insufficient for “full” post-run analysis and can miss tail behavior. The user requirement
is: SHAP must run on the full set by default.

This affects research code behavior (artifact content + runtime), but is aligned with current
workflow expectations: training/evaluation are already fast once features are cached, and saving
full-test SHAP values is feasible at current dataset sizes.

## Plan

- Change SHAP helper defaults from `max_samples=500` to “no sampling”.
- Keep the ability to downsample via an explicit `max_samples` argument for tests/debug.
- Rerun a SHAP-enabled `run` reusing a cached feature store to confirm:
  - `shap_values.npy` has shape `(n_test_rows, n_features)` (for ELLIPSE: `2430 x 793`).
  - `shap_summary.png` and `shap_summary_bar.png` are generated.
- Update the post-run report with the full-test SHAP details and paths.

## Success Criteria

- Default SHAP artifacts use the full test split (no sampling).
- Existing SHAP smoke tests still pass (they explicitly set `max_samples`).
- Verified on a real ELLIPSE run using `--reuse-feature-store-dir`.

## Related

- Post-run analysis report: `.claude/work/reports/essay-scoring/2026-02-04-ellipse-full-hemma-post-run-analysis.md`
- Decision: `docs/decisions/0029-essay-scoring-shap-uses-full-test-set-by-default.md`
- Runner implementation: `scripts/ml_training/essay_scoring/runner.py`
- SHAP helper: `scripts/ml_training/essay_scoring/training/shap_explainability.py`
