---
id: 'essay-scoring-ordinal-custom-objective-experiments-qwk'
title: 'essay-scoring: ordinal/custom objective experiments (QWK)'
type: 'task'
status: 'proposed'
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
labels: []
---
# essay-scoring: ordinal/custom objective experiments (QWK)

## Objective

Test whether training objectives that better match the **ordinal, half-band** nature of essay
scores improve **CV QWK**, with **prompt-holdout mean QWK** as the primary yardstick for selection,
and reduce tail failure modes, without reducing feature quality.

Secondary (non-negotiable) success condition:
- do not worsen tail slices (`y_true <= 2.0` and `y_true >= 4.0`) without an explicit tradeoff decision.

## Context

We currently optimize a regression objective (`reg:squarederror`) and select by QWK early stopping.
That is a sensible baseline, but it may leave performance on the table because:
- QWK depends on **discrete half-band** agreement, not continuous MSE.
- Score labels are ordered (ordinal) and class imbalance is strong in the tails.

We want a small, controlled set of experiments that can be compared apples-to-apples under the
CV-first story.

Gate C reminder:
- The current baseline shows strong grade compression / tail bias; objective changes must be evaluated
  against tail slices using residual diagnostics (not just mean QWK).

## Plan

Prereqs:
- Reusable `splits.json` exists (see dataset+splits task).
- Baseline CV metrics exist for `feature_set=combined` under both schemes.

### Step 1 (minimal ordinal check, before Gate D)

Goal: answer **“does ordinal multiclass reduce tail bias / grade compression in our setting?”**
without changing anything else (feature store, predictor selection, splits).

Implementation (done):
- `pdm run essay-scoring-research cv` now supports `--training-mode`:
  - `regression` (default)
  - `ordinal_multiclass_expected` (train `multi:softprob`, decode via expected value)
  - `ordinal_multiclass_argmax` (train `multi:softprob`, decode via argmax band)
- Code: `scripts/ml_training/essay_scoring/training/training_modes.py`,
  `scripts/ml_training/essay_scoring/training/trainer.py`,
  `scripts/ml_training/essay_scoring/cv_shared.py`,
  `scripts/ml_training/essay_scoring/cross_validation.py`,
  `scripts/ml_training/essay_scoring/cli.py`

Runs (System Terminal, detached; feature-store reuse; predictor fixed):
- Compare against the current best regression baseline (combined + prompt_holdout + drop-3 prune):
  `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
- Run two ordinal variants under `scheme=prompt_holdout`:
  1) `--training-mode ordinal_multiclass_expected`
  2) `--training-mode ordinal_multiclass_argmax`

Selection rule for Step 1:
- We treat this as an **information gate**, not a “must win on mean QWK” gate.
- Adoption as “best current” is allowed if:
  - prompt-holdout mean QWK drop is within ~`0.003–0.005`, **and**
  - the **high tail** (`y_true >= 4.0`) improves materially (MAE/bias/adjacent acc),
    with no obvious regression in the low tail (`y_true <= 2.0`).

### Results (Step 1, 2026-02-05)

Runs (all `scheme=prompt_holdout`, combined, predictor fixed to drop-3, feature-store reuse):

- Regression baseline (drop-3):
  - Run: `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
  - CV val QWK mean±std: `0.62210 ± 0.01743`
- Ordinal multiclass (expected-value decode):
  - Run: `output/essay_scoring/20260205_145529_ellipse_cv_combined_prompt_holdout_ordinal_expected_20260205_155521/`
  - CV val QWK mean±std: `0.58728 ± 0.01729` (ΔQWK vs baseline: `-0.03482`)
- Ordinal multiclass (argmax decode):
  - Run: `output/essay_scoring/20260205_145529_ellipse_cv_combined_prompt_holdout_ordinal_argmax_20260205_155521/`
  - CV val QWK mean±std: `0.54047 ± 0.02357` (ΔQWK vs baseline: `-0.08163`)

Tail slices (CV val OOF, from `artifacts/residuals_cv_val_oof.csv`):

- High tail (`y_true >= 4.0`):
  - Regression baseline: MAE `0.5349`, adjacent_acc `0.7767`
  - Ordinal expected: MAE `0.5899`, adjacent_acc `0.7147`
  - Ordinal argmax: MAE `0.6031`, adjacent_acc `0.5814`
- Low tail (`y_true <= 2.0`):
  - Regression baseline: MAE `0.6496`, adjacent_acc `0.6444`
  - Ordinal expected: MAE `0.6831`, adjacent_acc `0.5951`
  - Ordinal argmax: MAE `0.7042`, adjacent_acc `0.4754`

Decision (Step 1):
- Do **not** adopt ordinal multiclass (`multi:softprob`) as “best current” on ELLIPSE.
  It regresses prompt-holdout CV QWK well beyond the “noise tolerance” band and worsens both tails.
- Proceed to Gate D tail calibration / imbalance mitigation on the regression baseline.

Experiments:
- Run CV comparisons on ELLIPSE under:
  - `scheme=stratified_text`
  - `scheme=prompt_holdout`
- Use identical feature stores and split definitions for comparability.
- Require residual diagnostics artifacts on each CV run so prompt slices + tails are comparable.

Reporting:
- Produce a small comparison table:
  - objective/training mode → mean±std QWK, MAE, and a short “when it helps” note (if any).
- Record a decision in the CV-first story: keep baseline regression or switch modes.

## Success Criteria

- We have CV results for the baseline objective and at least one ordinal/custom variant under both
  schemes.
- A decision is recorded with evidence (improvement on prompt-holdout or “no win, keep baseline”).

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Tasks:
  - `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`
  - `TASKS/assessment/essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse.md`
- Gate C: `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Tail mitigation: `TASKS/assessment/essay-scoring-tail-calibration--grade-band-imbalance-mitigation.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
- Research hub: `docs/reference/ref-essay-scoring-research-hub.md`
