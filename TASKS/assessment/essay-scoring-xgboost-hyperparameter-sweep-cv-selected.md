---
id: 'essay-scoring-xgboost-hyperparameter-sweep-cv-selected'
title: 'essay-scoring: XGBoost hyperparameter sweep (CV-selected)'
type: 'task'
status: 'proposed'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-04'
related:
  - 'improve-essay-scoring-prediction-power-ellipse-cv-first'
  - 'essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
labels: []
---
# essay-scoring: XGBoost hyperparameter sweep (CV-selected)

## Objective

Improve generalization by selecting XGBoost hyperparameters using CV (never selecting on test).

## Context

The current combined model overfits strongly on a single split (train QWK near 1.0; test ~0.65).
After establishing a CV baseline, the most reliable next step is a small, systematic sweep that
prioritizes regularization and reduced tree complexity.

## Plan

Prereq: baseline CV runs exist with a stable `splits.json`.

Implementation approach (preferred):
- Add a “sweep runner” in `scripts/ml_training/essay_scoring/` that:
  - takes a parameter grid (JSON) + `splits.json` + `scheme`
  - runs CV for each configuration reusing a CV feature store
  - writes a single summary table sorted by mean QWK (and optionally stability)

Suggested starting grid (keep small; expand only if needed):
- `max_depth`: 3, 4, 5
- `min_child_weight`: 5, 10, 20
- `reg_lambda`: 2, 5, 10
- `reg_alpha`: 0, 1
- `subsample`: 0.6, 0.8
- `colsample_bytree`: 0.4, 0.6
- `gamma`: 0, 1

Decision rule:
- optimize for `prompt_holdout` mean QWK first; use `stratified_text` as a stability check.
- if these disagree, do not “cherry-pick”; prefer the configuration that improves prompt-holdout
  without introducing large regressions or instability.

## Success Criteria

- A sweep summary exists with mean±std QWK per configuration for both schemes.
- “Best current” params are recorded in the story and used for subsequent reports.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
