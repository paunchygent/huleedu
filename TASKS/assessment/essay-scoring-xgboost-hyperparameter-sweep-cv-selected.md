---
id: 'essay-scoring-xgboost-hyperparameter-sweep-cv-selected'
title: 'essay-scoring: XGBoost hyperparameter sweep (CV-selected)'
type: 'task'
status: 'done'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-05'
related:
  - 'improve-essay-scoring-prediction-power-ellipse-cv-first'
  - 'essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
  - 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
  - 'essay-scoring-tail-calibration--grade-band-imbalance-mitigation'
labels: []
---
# essay-scoring: XGBoost hyperparameter sweep (CV-selected)

## Objective

Improve generalization by selecting XGBoost hyperparameters using CV (never selecting on test),
while preserving tail-slice behavior (avoid “global QWK wins” that worsen `y_true <= 2.0` or
`y_true >= 4.0`).

## Context

The current combined model overfits strongly on a single split (train QWK near 1.0; test ~0.65).
After establishing a CV baseline, the most reliable next step is a small, systematic sweep that
prioritizes regularization and reduced tree complexity.

## Plan

Prereq: baseline CV runs exist with a stable `splits.json`.

Status (2026-02-05): completed sweep; decision recorded; ready to proceed to ensembling.

Implementation approach (preferred):
- Implemented a sweep runner + CLI command:
  - `pdm run essay-scoring-research xgb-sweep`
  - Code: `scripts/ml_training/essay_scoring/hyperparameter_sweep.py`, wired in `scripts/ml_training/essay_scoring/cli.py`
  - Writes a sweep summary table sorted by **high-tail adjacent accuracy** (primary) then CV mean QWK.
  - Persists:
    - `output/essay_scoring/<SWEEP>/artifacts/sweep_definition.json`
    - `output/essay_scoring/<SWEEP>/artifacts/sweep_results.json` (incremental; safe to monitor)
    - `output/essay_scoring/<SWEEP>/reports/sweep_summary.md`
    - `output/essay_scoring/<SWEEP>/progress.json`

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
- Require residual diagnostics outputs for the top configurations so tails and hard prompts can be
  compared without ad-hoc scripting.

Current sweep run (prompt_holdout; combined; drop-3; weighting+calibration; feature-store reuse):
- run_name: `ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746`
- driver log: `output/essay_scoring/ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746.driver.log`
- sweep dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/`

## Results (Gate E)

Prompt-holdout sweep (54 configs; selection sorted by high-tail adjacent accuracy then mean QWK):
- Sweep summary: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/reports/sweep_summary.md`
- Best config (rank 1): `config_id=97e84d798d`
  - Params: `max_depth=4`, `min_child_weight=20`, `reg_lambda=2.0`, `reg_alpha=0.0`
  - Run dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d/`
  - CV val QWK mean±std: `0.68460 ± 0.01659`
  - OOF tail slices (from `artifacts/residuals_cv_val_oof.csv`):
    - Low tail (`y_true<=2.0`): MAE `0.47887`, mean residual `+0.37324`, adjacent_acc `0.79577`
    - High tail (`y_true>=4.0`): MAE `0.34496`, mean residual `-0.24729`, adjacent_acc `0.87907`

Stability check (stratified_text; same best config):
- Run: `output/essay_scoring/20260205_202126_ellipse_gate_e_xgb_bestparams_stratified_text_20260205_212122/`
- Summary: `output/essay_scoring/20260205_202126_ellipse_gate_e_xgb_bestparams_stratified_text_20260205_212122/reports/sweep_summary.md`
  - CV val QWK mean±std: `0.68509 ± 0.01969`

Decision (Gate E):
- Adopt `max_depth=4`, `min_child_weight=20` (keep `reg_lambda=2.0`, `reg_alpha=0.0`) as the
  “best current” XGBoost params for subsequent CV-first follow-ups (still using Gate D default:
  weighting+calibration + drop-3 handcrafted prune).

## Success Criteria

- A sweep summary exists with mean±std QWK per configuration for prompt-holdout.
- A stratified_text stability check exists for the selected “best current” configuration.
- “Best current” params are recorded in the story and used for subsequent reports.
- Tail slices are evaluated (at minimum: MAE + mean residual for `y_true <= 2.0` and `y_true >= 4.0`)
  for the chosen configuration.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Gate C: `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Tail mitigation: `TASKS/assessment/essay-scoring-tail-calibration--grade-band-imbalance-mitigation.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
- Research hub: `docs/reference/ref-essay-scoring-research-hub.md`
