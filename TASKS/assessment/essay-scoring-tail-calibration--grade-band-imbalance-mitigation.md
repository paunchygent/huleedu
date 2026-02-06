---
id: 'essay-scoring-tail-calibration--grade-band-imbalance-mitigation'
title: 'essay-scoring: tail calibration + grade-band imbalance mitigation'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-05'
related:
  - 'improve-essay-scoring-prediction-power-ellipse-cv-first'
  - 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
  - 'essay-scoring-ordinal-custom-objective-experiments-qwk'
labels: []
---
# essay-scoring: tail calibration + grade-band imbalance mitigation

## Objective

Reduce the model’s **grade-band compression** and systematic tail bias:
- stop consistently **overpredicting** low-score essays, and
- stop consistently **underpredicting** high-score essays,
while keeping `scheme=prompt_holdout` CV mean±std QWK stable (allowing a small within-noise tradeoff
if tail slice accuracy improves).

## Context

Gate C residual diagnostics show a strong “regression-to-the-mean” shape:
- predictions cluster around `3.0–3.5` and almost never hit `4.5/5.0`
- low tail is overpredicted, high tail is underpredicted

Baseline reference (combined + prompt_holdout, feature-store reuse):
- Current best baseline (pruned predictor; validated under prompt_holdout):
  - Run: `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
  - Residual report: `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/reports/residual_diagnostics.md`
  - Predictor pruning: drop `has_conclusion`, `clause_count`, `flesch_kincaid`

## Plan

Guardrails:
- Do not change ELLIPSE exclusions or the 200–1000 word window in this task.
- Always reuse the CV feature store (`--reuse-cv-feature-store-dir .../cv_feature_store`).
- Keep the predictor definition fixed across comparisons (include the predictor prune flags for “best current”):
  - `--predictor-handcrafted-drop has_conclusion`
  - `--predictor-handcrafted-drop clause_count`
  - `--predictor-handcrafted-drop flesch_kincaid`

### Tail slices (must be explicit in selection)

1) Make the **tail slices** explicit in reporting/selection:
   - low tail slice: `y_true <= 2.0`
   - high tail slice: `y_true >= 4.0`
   - For each slice, report at least: MAE, mean residual, adjacent accuracy.

### Gate D experiment matrix (exact)

Common inputs (locked for Gate D; do not change without a new task/decision):
- Train CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
- Test CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
- Splits JSON: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
- Reuse CV feature store (canonical): `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store`

Common args (must be identical across all variants below):
- `--dataset-kind ellipse`
- `--feature-set combined`
- `--scheme prompt_holdout`
- Fold count is defined by `splits.json`; do not regenerate splits in this task.
- `--training-mode regression`
- `--ellipse-train-path <train_csv>`
- `--ellipse-test-path <test_csv>`
- `--splits-path <splits_json>`
- `--reuse-cv-feature-store-dir <cv_feature_store>`
- predictor prune flags (drop-3):
  - `--predictor-handcrafted-drop has_conclusion`
  - `--predictor-handcrafted-drop clause_count`
  - `--predictor-handcrafted-drop flesch_kincaid`

Variants (A–D):

**A) Baseline (no weighting, no calibration)**
- Purpose: reference point; confirms we can reproduce tail metrics with feature-store reuse.
- Command (system terminal):
  - `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode regression --ellipse-train-path <train_csv> --ellipse-test-path <test_csv> --splits-path <splits_json> --reuse-cv-feature-store-dir <cv_feature_store> --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --run-name ellipse_gate_d_baseline_prompt_holdout_drop3_<timestamp>`

**B) Weighting only (grade-band weighting; no calibration)**
- Purpose: reduce grade-band compression by increasing the influence of rare high/low bands during training.
- Implementation required (CV pipeline + trainer):
  - Add a grade-band weighting option that produces `sample_weight` for XGBoost training:
    - `--grade-band-weighting sqrt_inv_freq` (default `none`)
    - `--grade-band-weight-cap 3.0` (caps extreme weights; prevents the tiny 1.0/1.5 bands dominating)
- Command (system terminal; after implementation):
  - Same as (A) + `--grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0`
  - Run name: `ellipse_gate_d_weighting_prompt_holdout_drop3_<timestamp>`

**C) Calibration only (post-hoc monotone cutpoints; no weighting)**
- Purpose: improve tail classification without changing the underlying regressor.
- Implementation required (CV evaluation + artifacts):
  - Add an optional post-hoc mapping mode for converting `y_pred_raw -> y_pred`:
    - `--prediction-mapping qwk_cutpoints_lfo` (default `round_half_band`)
  - Leakage guardrail (mandatory): calibration must be **leave-one-fold-out** within CV:
    - for fold `k`, fit cutpoints using `cv_val_oof` rows where `fold != k`,
      then apply to fold `k` predictions (no access to fold `k` labels when fitting).
  - Persist calibration artifacts under `artifacts/`:
    - `artifacts/calibration_cutpoints_by_fold.json`
    - `artifacts/calibration_summary.json` (mode + bands + constraints)
- Command (system terminal; after implementation):
  - Same as (A) + `--prediction-mapping qwk_cutpoints_lfo`
  - Run name: `ellipse_gate_d_calibration_prompt_holdout_drop3_<timestamp>`

**D) Weighting + calibration (both enabled)**
- Purpose: fix compression at the source (weighting) + refine tails at output (calibration).
- Command (system terminal; after implementation):
  - Same as (A) + `--grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0 --prediction-mapping qwk_cutpoints_lfo`
  - Run name: `ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_<timestamp>`

### Acceptance check table (fill from `artifacts/` outputs)

How to fill:
- QWK mean±std: `artifacts/cv_metrics.json` → `summary.val_qwk_mean` / `summary.val_qwk_std`
- Tail slice metrics: compute from `artifacts/residuals_cv_val_oof.csv` (low: `y_true<=2.0`, high: `y_true>=4.0`)
- Locked test sanity check: confirm the direction of tail changes in `reports/residual_diagnostics.md`

Baseline reference (A) metrics (prompt_holdout CV, regression, drop-3):
- Run: `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`

| Variant | Run dir | QWK mean±std | OOF global MAE | Low tail MAE | Low tail mean residual | Low tail adjacent_acc | High tail MAE | High tail mean residual | High tail adjacent_acc | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A baseline | `output/essay_scoring/20260205_163458_ellipse_gate_d_baseline_prompt_holdout_drop3_20260205_173454/` | 0.62210 ± 0.01743 | 0.34516 | 0.64965 | +0.64965 | 0.64437 | 0.53488 | -0.53178 | 0.77674 | baseline |
| B weighting | `output/essay_scoring/20260205_170701_ellipse_gate_d_weighting_prompt_holdout_drop3_20260205_180657/` | 0.63516 ± 0.01650 | 0.34660 | 0.63028 | +0.63028 | 0.66901 | 0.51163 | -0.50543 | 0.79225 | improves tails + QWK; keep as optional lever |
| C calibration | `output/essay_scoring/20260205_170843_ellipse_gate_d_calibration_prompt_holdout_drop3_20260205_180838/` | 0.68615 ± 0.01029 | 0.38294 | 0.51232 | +0.26585 | 0.78873 | 0.41783 | -0.29535 | 0.79225 | runner-up (best QWK; strong tail bias reduction) |
| D weighting+calibration | `output/essay_scoring/20260205_171050_ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_20260205_181046/` | 0.68360 ± 0.01470 | 0.37820 | 0.47359 | +0.35035 | 0.77465 | 0.40543 | -0.26434 | 0.82481 | **default** (best high-tail adjacent_acc; QWK within noise vs C) |

Selection rule (Gate D):
- Global yardstick remains prompt-holdout CV mean±std QWK, but a small within-noise tradeoff is
  acceptable (allow up to `~0.005` mean QWK drop) when it buys meaningful tail slice improvements.
- Primary slice yardstick (selection): **high-tail adjacent accuracy** (`y_true>=4.0`), then high-tail MAE.
- Secondary (guardrail): tail mean residual should move toward 0 or at least not worsen materially; treat
  mean residual as a **noisy-label proxy**, not an absolute truth signal.
- Note (important tradeoff): calibration variants can reduce mid-band adjacent accuracy; monitor the
  mid slice (`2.5<=y_true<=3.5`) and explicitly record the tradeoff when selecting a default.

4) Decision:
   - Prefer the variant that improves **tail slices** without regressing prompt-holdout mean QWK.
   - Record the chosen default (or “no change”) back into the CV-first story.

Current Gate D decision (2026-02-05):
- Adopt **weighting + calibration** as the default for CV-first selection:
  - `--grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0`
  - `--prediction-mapping qwk_cutpoints_lfo`
  Reason: best OOF **high-tail adjacent accuracy** with prompt-holdout mean QWK still within fold
  noise vs calibration-only.
- Keep **calibration-only** (`--prediction-mapping qwk_cutpoints_lfo`) as the runner-up when we want
  the highest mean QWK / lowest tail bias without training-time weighting.

## Success Criteria

- We have CV evidence (prompt_holdout mean±std) for baseline vs at least one mitigation variant.
- Tail slices (`y_true <= 2.0`, `y_true >= 4.0`) improve (or at minimum do not worsen) under the
  selected variant.
- A decision is recorded in the story with paths to the comparison runs.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Gate C: `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Gate D (objective variants): `TASKS/assessment/essay-scoring-ordinal-custom-objective-experiments-qwk.md`
- Research hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
