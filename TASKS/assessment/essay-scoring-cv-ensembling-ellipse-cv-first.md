---
id: 'essay-scoring-cv-ensembling-ellipse-cv-first'
title: 'essay-scoring: CV ensembling (ELLIPSE CV-first)'
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
labels: []
---
# essay-scoring: CV ensembling (ELLIPSE CV-first)

## Objective

Improve **out-of-sample** essay score prediction by reducing variance via simple CV-time
ensembling (bagging) without changing feature quality. Selection remains **CV-first** (never
“optimize on test”).

Non-negotiable guardrail:
- do not worsen tail slices (`y_true <= 2.0` and `y_true >= 4.0`) without an explicit tradeoff decision.

## Context

The current single-model training setup can overfit strongly and can be high-variance given:
- a high-capacity representation (768 embeddings + handcrafted features)
- skewed label distribution (weak tail support)

Recent AES work often reports large gains from **cross-validation ensembling**; we should test a
lightweight version of that idea that is easy to reproduce and explain.

## Plan

Prereqs:
- Reusable `splits.json` exists (see dataset+splits task).
- Baseline CV metrics exist for `feature_set=combined` under both schemes.

Implementation:
- Extend the research runner so CV can train **N models per fold** (different `seed`) and ensemble
  their predictions:
  - average continuous predictions (then apply the existing half-band rounding + clipping)
  - compute metrics on the ensembled predictions
- Persist ensemble metadata and per-fold metrics so we can compare single-model vs ensemble.

Experiments:
- Run CV on ELLIPSE with:
  - `scheme=stratified_text`
  - `scheme=prompt_holdout`
- Compare `ensemble_size=1` vs `ensemble_size in {3, 5}` and pick the smallest ensemble that gives
  stable uplift on **prompt-holdout** without destabilizing `stratified_text`.

Reporting:
- Add a concise table to the CV-first story showing mean±std QWK/MAE for:
  - baseline single model
  - best ensemble setting
- Record final “best current” recommendation (ensemble size, seeds strategy) in the story.
- Require residual diagnostics artifacts for the chosen ensemble setting so tail behavior and hard
  prompts are comparable to the single-model baseline.

## Success Criteria

- CV runner supports `ensemble_size > 1` and produces a fold-aggregated report.
- We have mean±std QWK for single-model vs ensemble under both schemes.
- A decision is recorded: either “ensemble helps” (with chosen size) or “no meaningful uplift”
  (with evidence).
- Tail slices are evaluated for single vs ensemble (at minimum: MAE + mean residual for
  `y_true <= 2.0` and `y_true >= 4.0`).

## Implementation (completed 2026-02-05)

CV now supports ensembling by training N models per fold with different seeds and averaging
predictions before evaluation + residual artifacts.

- CLI: `pdm run essay-scoring-research cv --ensemble-size <N>`
- Code:
  - `scripts/ml_training/essay_scoring/cli.py` (new flag)
  - `scripts/ml_training/essay_scoring/cross_validation.py` (seed strategy + metrics payload)
  - `scripts/ml_training/essay_scoring/cv_shared.py` (fold-level ensembling)
  - `scripts/ml_training/essay_scoring/reports/cv_report.py` (prints `ensemble_size`)
- Tests: `scripts/ml_training/essay_scoring/tests/test_cv_ensembling.py`

Seed strategy (for CV selection comparability):
- Member seeds are deterministic: `base_seed + i` for `i in [0..ensemble_size-1]`.
- This preserves historical behavior for `ensemble_size=1` (matches Gate E baseline runs).

## Results (prompt_holdout; combined; drop-3; weighting+calibration; best XGB params)

Runs:
- `ensemble_size=1`: `output/essay_scoring/20260205_213805_ellipse_gate_f_cv_ensemble1_prompt_holdout_drop3_wcal_bestparams_20260205_223800/`
- `ensemble_size=3`: `output/essay_scoring/20260205_213920_ellipse_gate_f_cv_ensemble3_prompt_holdout_drop3_wcal_bestparams_20260205_223917/`
- `ensemble_size=5`: `output/essay_scoring/20260205_214118_ellipse_gate_f_cv_ensemble5_prompt_holdout_drop3_wcal_bestparams_20260205_224115/`

Summary table (computed from `artifacts/cv_metrics.json` + `artifacts/residuals_cv_val_oof.csv`):

| ensemble_size | CV QWK mean±std | CV adj_acc | CV MAE | high_tail adj_acc | high_tail MAE | high_tail mean_resid | low_tail adj_acc | low_tail MAE | mid_band adj_acc | run_dir |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.68460 ± 0.01659 | 0.86478 | 0.37946 | 0.87907 | 0.34496 | -0.24729 | 0.79577 | 0.47887 | 0.86873 | `output/essay_scoring/20260205_213805_ellipse_gate_f_cv_ensemble1_prompt_holdout_drop3_wcal_bestparams_20260205_223800` |
| 3 | 0.68573 ± 0.01755 | 0.86611 | 0.37286 | 0.83411 | 0.37054 | -0.26822 | 0.79225 | 0.48944 | 0.88245 | `output/essay_scoring/20260205_213920_ellipse_gate_f_cv_ensemble3_prompt_holdout_drop3_wcal_bestparams_20260205_223917` |
| 5 | 0.68946 ± 0.01533 | 0.87339 | 0.36783 | 0.85271 | 0.36822 | -0.26744 | 0.79930 | 0.50000 | 0.88676 | `output/essay_scoring/20260205_214118_ellipse_gate_f_cv_ensemble5_prompt_holdout_drop3_wcal_bestparams_20260205_224115` |

Decision:
- Reject ensembling for CV-first selection for now: `ensemble_size>1` increases mean QWK but
  worsens the **high-tail adjacent accuracy** slice (`y_true>=4.0`), which is a non-negotiable
  guardrail in this story phase.
- Keep `ensemble_size=1` as the best-current default until we revisit tail calibration/feature
  changes that might counteract the ensemble-induced grade compression.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Gate C: `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Tasks:
  - `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`
  - `TASKS/assessment/essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
- Research hub: `docs/reference/ref-essay-scoring-research-hub.md`
