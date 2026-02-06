---
id: 'essay-scoring-statsmodels-diagnostics--catboost-baseline'
title: 'essay-scoring: statsmodels diagnostics + CatBoost baseline'
type: 'task'
status: 'proposed'
priority: 'low'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-06'
last_updated: '2026-02-06'
related: ['improve-essay-scoring-prediction-power-ellipse-cv-first', 'essay-scoring-decision-gate-for-experiment-optimization-dependencies']
labels: []
---
# essay-scoring: statsmodels diagnostics + CatBoost baseline

## Objective

Improve decision quality and baseline confidence by adding:

- `statsmodels` for more formal comparisons/diagnostics (paired/bootstrap summaries across folds),
- `catboost` as an alternate GBM baseline on the same feature matrices.

## Context

- Many CV deltas are within fold noise; we need to avoid chasing "noise wins".
- CatBoost is often competitive with XGBoost and can serve as a strong baseline/sanity check.
- This is lower priority than directly improving prompt-holdout QWK (Optuna / invariance), but can
  improve our confidence in conclusions.

## Plan

### A) Dependencies (decision-gated)

If accepted in ADR-0031, add to `dependency-groups.ml-research`:
- `statsmodels`
- `catboost`

### B) CatBoost baseline (CV-first)

- Train CatBoost on the same stored feature matrices used for XGBoost (no new feature extraction).
- Evaluate under:
  - `scheme=prompt_holdout` (primary)
  - `scheme=stratified_text` (stability check)
- Persist the same evidence surface as other CV runs:
  - `artifacts/cv_metrics.json`
  - `reports/residual_diagnostics.md`

### C) Formal comparisons / diagnostics

- Add a small analysis helper that compares two CV runs (paired by fold) and reports:
  - mean±std delta QWK,
  - a bootstrap confidence interval (or other paired summary),
  - worst-prompt delta (optional).
- Keep the tool lightweight and repo-local (no external services).

## Success Criteria

- We have a CatBoost baseline result that can be compared apples-to-apples to XGBoost.
- We can summarize whether observed deltas are likely real vs fold noise.
- Findings are recorded in the dependency decision research doc and reflected in ADR-0031.

## Related

- ADR: `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Research notes:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
