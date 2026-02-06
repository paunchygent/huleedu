---
id: 'essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse'
title: 'essay-scoring: ablation (handcrafted vs embeddings vs combined) on ELLIPSE'
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

## Results (2026-02-04)

Canonical inputs (200–1000 words; exclusions unchanged; shared splits):
- `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
- `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
- `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`

Runs:
- `embeddings`:
  - `scheme=stratified_text`: `output/essay_scoring/20260204_164449_ellipse_cv_embeddings_stratified_text_20260204_174445/`
  - `scheme=prompt_holdout` (reuse store): `output/essay_scoring/20260204_165648_ellipse_cv_embeddings_prompt_holdout_20260204_175630/`
- `handcrafted`:
  - `scheme=stratified_text`: `output/essay_scoring/20260204_180119_ellipse_cv_handcrafted_stratified_text_20260204_190101/`
  - `scheme=prompt_holdout` (reuse store): `output/essay_scoring/20260204_180303_ellipse_cv_handcrafted_prompt_holdout_20260204_190248/`
- `combined` (baseline already recorded in the story hub):
  - `scheme=stratified_text`: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/`
  - `scheme=prompt_holdout`: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/`

CV val QWK (mean±std):

| feature_set | stratified_text | prompt_holdout |
| --- | --- | --- |
| `embeddings` | 0.5520 ± 0.0215 | 0.5447 ± 0.0220 |
| `handcrafted` | 0.5737 ± 0.0139 | 0.5644 ± 0.0189 |
| `combined` | 0.6262 ± 0.0179 | 0.6183 ± 0.0240 |

Effect sizes (prompt-holdout; primary yardstick):
- `combined` vs `embeddings`: **+0.0737 QWK**
- `combined` vs `handcrafted`: **+0.0539 QWK**

Conclusion:
- `combined` is decisively better than either feature family alone under prompt-holdout CV.
- Proceed to Gate B: drop-column importance (to prune/validate the handcrafted set), then Gate C:
  residual diagnostics by prompt + grade band before trying objective/ensembling changes.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
