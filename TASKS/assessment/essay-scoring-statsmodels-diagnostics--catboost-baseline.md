---
id: 'essay-scoring-statsmodels-diagnostics--catboost-baseline'
title: 'essay-scoring: statsmodels diagnostics + CatBoost baseline'
type: 'task'
status: 'done'
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

## Gate G1 Threshold Contract (2026-02-06)

Primary gate (`scheme=prompt_holdout`, `min_prompt_n=30`, `bottom_k=5`) relative to the
stable XGBoost reference config `b28c376a73`:

- worst-prompt QWK delta must be `>= +0.010`.
- mean QWK delta must be `>= -0.003`.
- low-tail adjacent-accuracy delta must be `>= -0.010`.
- high-tail adjacent-accuracy delta must be `>= -0.010`.

Stability gate (`scheme=stratified_text`):

- mean QWK delta must be `>= -0.005`.

Gate sequencing:

1. Run CatBoost parity CV on frozen ELLIPSE train/test/splits + reused CV feature store.
2. Run CatBoost stratified-text stability CV on the same frozen artifacts.
3. Run paired-fold + bootstrap comparison reports.
4. Promote transformer prompt-invariance task only if CatBoost fails the above thresholds.

## Outcome (2026-02-06)

Completed with frozen-input CatBoost parity + paired comparison artifacts.

Prompt-holdout gate (`prompt_holdout_primary`) result: **failed**.

- reference run: `output/essay_scoring/20260206_105542_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536/variants/20260206_110018_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536_b28c376a73_trial005`
- candidate run: `output/essay_scoring/20260206_185135_ellipse_gate_g1_catboost_prompt_holdout_20260206_195132`
- comparison: `output/essay_scoring/20260206_190010_ellipse_gate_g1_compare_prompt_holdout_catboost_vs_b28c`
- key deltas (candidate - reference):
  - `mean_qwk`: `+0.00025` (passes tolerance)
  - `worst_prompt_qwk`: `-0.01498` (**fails**; required `>= +0.010`)
  - `low_tail_adjacent_accuracy`: `-0.03521` (**fails**; required `>= -0.010`)
  - `high_tail_adjacent_accuracy`: `-0.03101` (**fails**; required `>= -0.010`)

Stratified stability gate (`stratified_stability`) result: **passed**.

- reference run: `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_b28c376a73_20260206_185804`
- candidate run: `output/essay_scoring/20260206_185436_ellipse_gate_g1_catboost_stratified_20260206_195431`
- comparison: `output/essay_scoring/20260206_190014_ellipse_gate_g1_compare_stratified_catboost_vs_b28c`
- key delta:
  - `mean_qwk`: `-0.00149` (passes stability tolerance `>= -0.005`)

Gate implication:
- CatBoost does not satisfy the primary prompt-holdout quality contract.
- Promote transformer prompt-invariance experiments as the next active track.

## Related

- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- ADR: `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Research notes:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
- Review record:
  `docs/product/reviews/review-statsmodels-diagnostics-catboost-baseline-dependencies.md`
