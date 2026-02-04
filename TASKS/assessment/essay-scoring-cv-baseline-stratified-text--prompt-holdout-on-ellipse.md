---
id: 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
title: 'essay-scoring: CV baseline (stratified_text + prompt_holdout) on ELLIPSE'
type: 'task'
status: 'done'
priority: 'high'
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
labels: []
---
# essay-scoring: CV baseline (stratified_text + prompt_holdout) on ELLIPSE

## Objective

Establish CV baselines for ELLIPSE using `feature_set=combined` under both:
- `scheme=stratified_text` (standard CV with leak guard)
- `scheme=prompt_holdout` (unseen-prompt generalization)

These baselines become the yardstick for all later improvements.

## Context

Single train/val/test runs are not sufficient for selecting improvements (high variance; easy to
overfit). We need CV mean±std and prompt-holdout performance to understand whether changes improve
generalization rather than memorization.

## Plan

Prereq: have a reusable `splits.json` from:
- `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`

Run CV baselines (recommended: create feature store once, then reuse it for the second scheme):

- Define canonical inputs (from the prep/splits task):
  - `PREP_TRAIN_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv`
  - `PREP_TEST_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv`
  - `SPLITS_JSON=output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json`

- Run `scheme=stratified_text` first (creates `cv_feature_store/`):
  - `pdm run essay-scoring-research cv --dataset-kind ellipse --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" --splits-path "$SPLITS_JSON" --scheme stratified_text --feature-set combined --language-tool-service-url http://127.0.0.1:18085 --embedding-service-url http://127.0.0.1:19000 --run-name ellipse_cv_combined_stratified_text`

- Run `scheme=prompt_holdout` second (reuses the feature store; avoids re-extraction):
  - `pdm run essay-scoring-research cv --dataset-kind ellipse --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" --splits-path "$SPLITS_JSON" --scheme prompt_holdout --feature-set combined --reuse-cv-feature-store-dir output/essay_scoring/<STRAT_CV_RUN>/cv_feature_store --run-name ellipse_cv_combined_prompt_holdout`

Important:
- `cv` does **not** compute SHAP artifacts (SHAP is run-level explainability, not a fold-level CV artifact).
- For SHAP, run a dedicated `run` after baselines (or reuse an existing SHAP-enabled run), e.g.:
  - `pdm run essay-scoring-research run --dataset-kind ellipse --feature-set combined --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_run_combined_with_shap`
  - (Do **not** pass `--skip-shap`.)

Operational:
- First run will populate caches; subsequent runs should reuse the CV feature store to avoid
  repeated extraction.
- Monitor by script via `output/essay_scoring/<RUN>/progress.json` (machine-readable processed/total + ETA), not log parsing.
- Capture key outputs (paths + mean±std QWK) in the story and append an experiment-log entry to
  `docs/operations/ml-nlp-runbook.md`.

## Success Criteria

- Two CV runs exist (one per scheme) with `reports/cv_report.md` and `artifacts/cv_metrics.json`.
- CV feature stores exist (`cv_feature_store/`) and are usable for ablation/sweeps without re-extraction.
- Mean±std QWK is recorded for both schemes (the baseline).

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
