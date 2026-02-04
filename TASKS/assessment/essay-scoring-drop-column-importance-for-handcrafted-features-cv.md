---
id: 'essay-scoring-drop-column-importance-for-handcrafted-features-cv'
title: 'essay-scoring: drop-column importance for handcrafted features (CV)'
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
# essay-scoring: drop-column importance for handcrafted features (CV)

## Objective

Determine which handcrafted features add incremental value under CV, to:
- simplify the feature set,
- reduce overfitting surface area,
- and focus future work on features that matter.

## Context

Handcrafted features are interpretable and (in SHAP) appear high-impact, but the combined model
still has hundreds of embedding dimensions. Drop-column CV tells us whether each handcrafted
feature helps beyond everything else, and how stable that effect is across folds.

## Plan

Prereqs:
- a reusable `splits.json` (see dataset+splits task)
- a reusable CV feature store from a baseline `cv` run (so this doesn’t re-extract features)

Run:
- Define canonical inputs (from the prep/splits task):
  - `PREP_TRAIN_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv`
  - `PREP_TEST_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv`
  - `SPLITS_JSON=output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json`

- Run drop-column reusing the baseline CV feature store:
  - `pdm run essay-scoring-research drop-column --dataset-kind ellipse --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" --feature-set combined --splits-path "$SPLITS_JSON" --scheme stratified_text --language-tool-service-url http://127.0.0.1:18085 --embedding-service-url http://127.0.0.1:19000 --reuse-cv-feature-store-dir output/essay_scoring/<BASELINE_CV_RUN>/cv_feature_store --run-name ellipse_drop_column_combined_stratified_text`

Interpretation rubric (starting point; adjust after seeing results):
- keep if mean ΔQWK > 0 and stability ≥ 0.8 (helps in ≥80% of folds)
- drop if mean ΔQWK ≤ 0 or stability low

Operational:
- Monitor by script via `output/essay_scoring/<RUN>/progress.json`.

## Success Criteria

- `artifacts/drop_column_importance.json` exists and is referenced in the story.
- A “keep/drop” recommendation list exists for handcrafted features.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
