---
id: 'essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse'
title: 'essay-scoring: ablation (handcrafted vs embeddings vs combined) on ELLIPSE'
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
# essay-scoring: ablation (handcrafted vs embeddings vs combined) on ELLIPSE

## Objective

Quantify the incremental value of each feature set on ELLIPSE:
- handcrafted-only
- embeddings-only
- combined

Run under CV (not a single split) so we can make robust decisions about what to invest in.

## Context

We need to know whether LanguageTool/spaCy handcrafted features materially improve generalization
once embeddings are present. This determines whether future effort should prioritize:
- scaling/optimizing LanguageTool capacity (if it matters), or
- embedding model/representation work (if handcrafted adds little), or
- both (if combined consistently wins).

## Plan

Prereq: baseline CV splits exist (see `essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words`).

Option A (preferred, explicit CV per feature set):
- Run three CV jobs with the same `splits.json` and `scheme`:
  - `--feature-set handcrafted`
  - `--feature-set embeddings`
  - `--feature-set combined`

Recommended command pattern (per feature set):

- Define canonical inputs (from the prep/splits task):
  - `PREP_TRAIN_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv`
  - `PREP_TEST_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv`
  - `SPLITS_JSON=output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json`

- For each `FEATURE_SET` in `{handcrafted,embeddings,combined}`:
  1) Run `scheme=stratified_text` first (creates the CV feature store for that feature set):
     - `pdm run essay-scoring-research cv --dataset-kind ellipse --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" --splits-path "$SPLITS_JSON" --scheme stratified_text --feature-set "$FEATURE_SET" --language-tool-service-url http://127.0.0.1:18085 --embedding-service-url http://127.0.0.1:19000 --run-name ellipse_cv_${FEATURE_SET}_stratified_text`
  2) Run `scheme=prompt_holdout` reusing that store (avoids re-extraction):
     - `pdm run essay-scoring-research cv --dataset-kind ellipse --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" --splits-path "$SPLITS_JSON" --scheme prompt_holdout --feature-set "$FEATURE_SET" --reuse-cv-feature-store-dir output/essay_scoring/<STRAT_CV_RUN_FOR_FEATURE_SET>/cv_feature_store --run-name ellipse_cv_${FEATURE_SET}_prompt_holdout`

Operational:
- Monitor by script via `output/essay_scoring/<RUN>/progress.json`.

Option B (only if you explicitly want single-run ablation):
- `pdm run essay-scoring-research ablation --dataset-kind ellipse --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_ablation_hemma_single_split`

Deliverable reporting:
- Add a short comparison table (mean±std QWK per feature set per scheme) to the story and append to
  `.claude/work/reports/essay-scoring/2026-02-04-ellipse-full-hemma-post-run-analysis.md`.

## Success Criteria

- For each scheme (`stratified_text`, `prompt_holdout`), we have:
  - CV mean±std QWK for each feature set
  - a clear winner and effect size (ΔQWK vs baseline)
- Decision-ready conclusion: is `combined` worth the extra feature extraction cost?

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
