---
id: 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
title: 'essay-scoring: CV baseline (stratified_text + prompt_holdout) on ELLIPSE'
type: 'task'
status: 'proposed'
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

Run CV with Hemma backend (single tunnel):
- `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --splits-path <SPLITS_JSON> --scheme stratified_text --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_cv_combined_stratified_text`
- `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --splits-path <SPLITS_JSON> --scheme prompt_holdout --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_cv_combined_prompt_holdout`

Operational:
- First run will populate caches; subsequent runs should reuse the CV feature store to avoid
  repeated extraction.
- Capture key outputs (paths + mean±std QWK) in the story and append an experiment-log entry to
  `docs/operations/ml-nlp-runbook.md`.

## Success Criteria

- Two CV runs exist (one per scheme) with `reports/cv_report.md` and `artifacts/cv_metrics.json`.
- CV feature stores exist (`cv_feature_store/`) and are usable for ablation/sweeps without re-extraction.
- Mean±std QWK is recorded for both schemes (the baseline).

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
