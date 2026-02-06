---
id: 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
title: 'essay-scoring: residual diagnostics by prompt and grade band'
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
related:
  - 'improve-essay-scoring-prediction-power-ellipse-cv-first'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
labels: []
---
# essay-scoring: residual diagnostics by prompt and grade band

## Objective

Add diagnostics that show *where* the model fails:
- by prompt (topic)
- by grade band (tails vs middle)
- by key covariates (length / grammar error rate / prompt similarity)

## Context

Aggregate metrics (QWK/MAE) hide important failure modes:
- prompt-specific drift (common in prompt-based writing datasets)
- tail underperformance (rare labels)
- systematic biases (length effects, grammar density effects)

These diagnostics should guide which changes will actually improve prediction power instead of
just moving global averages slightly.

## Plan

Implementation (code + report):
- Persist per-essay predictions and residuals for evaluation splits (at least test; ideally per CV fold):
  - `record_id`, `prompt`, `y_true`, `y_pred`, `residual`, and a few key features (word_count, etc.)
- Add a report generator that outputs:
  - per-prompt MAE/QWK (top N prompts by volume)
  - per-band MAE
  - residual vs word_count scatter summary (and correlation)
  - “worst prompts” list with sample size safeguards

Target outputs:
- `reports/residual_diagnostics.md` under the run directory for single-run and CV runs.

## Success Criteria

- A run directory contains per-record predictions + a residual diagnostics report.
- The report is referenced from the story with a short “what to do next” section.

## Implementation (2026-02-04)

Code:
- CV fold predictions + locked-test predictions are persisted by `cv` runs:
  - `scripts/ml_training/essay_scoring/cv_shared.py` (`run_fold_with_predictions`)
  - `scripts/ml_training/essay_scoring/cross_validation.py` (writes artifacts + report)
- Report generator:
  - `scripts/ml_training/essay_scoring/reports/residual_diagnostics.py`

Artifacts written under the CV run directory:
- Per-record rows:
  - `artifacts/residuals_cv_val_oof.csv` + `.jsonl` (OOF val predictions across folds)
  - `artifacts/residuals_locked_test.csv` + `.jsonl` (locked test from the final fit)
- Report:
  - `reports/residual_diagnostics.md`

How to run (feature-store reuse; Gate C baseline):
- Run `pdm run essay-scoring-research cv --scheme prompt_holdout --reuse-cv-feature-store-dir <CV_RUN_DIR_OR_cv_feature_store_DIR> ...`
- Verify the run dir contains `reports/residual_diagnostics.md` and the `artifacts/residuals_*.{csv,jsonl}` files.

## Results (2026-02-04)

Baseline residual diagnostics run (combined + prompt_holdout, feature-store reuse):
- Run dir: `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/`
  - Residual report: `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/reports/residual_diagnostics.md`
  - Artifacts:
    - `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/artifacts/residuals_locked_test.csv`
    - `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/artifacts/residuals_cv_val_oof.csv`

Key takeaways (high-level):
- Strong tail bias / grade compression (rarely predicts 4.5/5.0; high tail underpredicted; low tail overpredicted).
- A small set of prompts repeatedly underperform and should be construct-audited.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
