---
id: 'improve-essay-scoring-prediction-power-ellipse-cv-first'
title: 'improve essay-scoring prediction power (ELLIPSE, CV-first)'
type: 'story'
status: 'in_review'
priority: 'high'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-04'
related:
  - 'essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
  - 'essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse'
  - 'essay-scoring-drop-column-importance-for-handcrafted-features-cv'
  - 'essay-scoring-xgboost-hyperparameter-sweep-cv-selected'
  - 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
  - 'essay-scoring-cv-ensembling-ellipse-cv-first'
  - 'essay-scoring-ordinal-custom-objective-experiments-qwk'
  - 'essay-scoring-construct-validity-audit--feature-candidates'
labels: []
---
# improve essay-scoring prediction power (ELLIPSE, CV-first)

## Objective

Improve **out-of-sample** essay score prediction on ELLIPSE using a CV-first workflow, with the
primary success metric being **prompt-holdout cross-validated QWK** (unseen prompt generalization),
while keeping feature quality intact (no “make it faster by removing signal” shortcuts).

Scope note (important):
- This story is about generalizing within the **essay discourse genre** (argumentative/discussion
  essays), not “writing in general” across mixed communication genres.

## Context

We have a working Hemma offload pipeline and a completed ELLIPSE run with strong throughput and
useful artifacts (including full-test SHAP). However, single-split train metrics are near-perfect
while test QWK is ~0.65, indicating overfitting and that **CV discipline** is the next lever for
real prediction improvements.

This story defines a repeatable research loop:
- stable dataset preparation + splits
- CV baselines (stratified + prompt-holdout)
- targeted experiments (ablation, drop-column, hyperparam sweep)
- diagnostics (prompt/band residuals) to guide feature + model changes

Primary references:
- Runbook: `docs/operations/ml-nlp-runbook.md`
- Navigation hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Post-run report: `.claude/work/reports/essay-scoring/2026-02-04-ellipse-full-hemma-post-run-analysis.md`

## Plan

Execute the linked tasks in dependency order, with explicit decision gates so we don’t “wander”
between orthogonal levers:

1) Prepare stable dataset + reusable CV splits (200–1000 words policy).
   - Task: `essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words`

2) Establish CV baselines for `feature_set=combined` under both generalization regimes:
   - `scheme=stratified_text` (leakage guard via hash grouping)
   - `scheme=prompt_holdout` (unseen prompt generalization; **primary yardstick** for selection)
   - Task: `essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse`

Decision gate A (signal vs cost): do handcrafted features meaningfully help under CV?
3) Run CV ablation across feature sets (handcrafted vs embeddings vs combined).
   - Task: `essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse`

Decision gate B (feature set discipline): if we keep handcrafted/combined, which handcrafted
features are actually worth carrying?
4) Run drop-column CV importance for handcrafted features (reusing the CV feature store).
   - Task: `essay-scoring-drop-column-importance-for-handcrafted-features-cv`

Decision gate C (where are the failures?): identify prompt/band/slice failure modes *before*
adding features or changing objectives.
5) Add residual diagnostics by prompt and grade band (and key covariates).
   - Task: `essay-scoring-residual-diagnostics-by-prompt-and-grade-band`

Decision gate D (modeling lever): do we get more reliable uplift from tuning objective/regularization,
or from ensembling, or from adding construct features?
6) CV-select better XGBoost hyperparameters (prompt_holdout-first), reusing the CV feature store.
   - Task: `essay-scoring-xgboost-hyperparameter-sweep-cv-selected`
7) Try ordinal/custom training modes (QWK-aligned) under CV.
   - Task: `essay-scoring-ordinal-custom-objective-experiments-qwk`
8) Try simple CV-time ensembling (bagging across seeds per fold) under CV.
   - Task: `essay-scoring-cv-ensembling-ellipse-cv-first`

Decision gate E (construct validity): after we have a “best current” baseline, audit for shortcut
signals and then test a small set of construct-aligned feature candidates under CV.
9) Construct validity audit + candidate features (evaluate under prompt_holdout).
   - Task: `essay-scoring-construct-validity-audit--feature-candidates`

## Shared artifacts (for this story)

Created 2026-02-04 (ELLIPSE Overall, 200–1000 words, excluded prompts unchanged):

- Prepared dataset run dir: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/`
  - Train CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
  - Test CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
  - Integrity report: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/reports/dataset_integrity_report.md`
- Splits run dir: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/`
  - Splits JSON: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
  - Splits report: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/reports/splits_report.md`

## Success Criteria

- Baseline CV metrics exist (mean±std QWK) for `combined` under both schemes.
- A documented “best current” configuration exists selected by CV (not by test), prioritized by:
  - `prompt_holdout` mean QWK first, then
  - stability check via `stratified_text` (avoid regressions / high variance).
- A concrete shortlist of next improvements exists, backed by:
  - ablation deltas (what feature sets matter)
  - drop-column results (what handcrafted features matter)
  - prompt/band residual diagnostics (where the model fails)

## Related

- Tasks:
  - `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`
  - `TASKS/assessment/essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse.md`
  - `TASKS/assessment/essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse.md`
  - `TASKS/assessment/essay-scoring-drop-column-importance-for-handcrafted-features-cv.md`
  - `TASKS/assessment/essay-scoring-xgboost-hyperparameter-sweep-cv-selected.md`
  - `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
  - `TASKS/assessment/essay-scoring-cv-ensembling-ellipse-cv-first.md`
  - `TASKS/assessment/essay-scoring-ordinal-custom-objective-experiments-qwk.md`
  - `TASKS/assessment/essay-scoring-construct-validity-audit--feature-candidates.md`
- Decisions:
  - `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
  - `docs/decisions/0029-essay-scoring-shap-uses-full-test-set-by-default.md`
  - `docs/decisions/0030-essay-scoring-tier1-error-rate-feature-names-include-units.md`
- Runbook:
  - `docs/operations/ml-nlp-runbook.md`
