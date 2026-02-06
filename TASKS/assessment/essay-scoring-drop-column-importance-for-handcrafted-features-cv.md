---
id: 'essay-scoring-drop-column-importance-for-handcrafted-features-cv'
title: 'essay-scoring: drop-column importance for handcrafted features (CV)'
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
- Drop-column currently does **not** emit a `progress.json` counter (unlike `run`/`cv`).
  If you need a coarse progress gauge, count XGBoost “model starts” in the driver log:
  - `rg -c '^\\[0\\]\\ttrain-qwk' output/essay_scoring/<RUN_NAME>.driver.log`
  - expected total model fits: `n_splits * (1 + n_candidate_features)`

## Success Criteria

- `artifacts/drop_column_importance.json` exists and is referenced in the story.
- A “keep/drop” recommendation list exists for handcrafted features.

## Results (2026-02-04)

Run:
- output dir: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/`
- metrics: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/artifacts/drop_column_importance.json`
- report: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/reports/drop_column_importance.md`
- reused CV feature store: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/cv_feature_store`

Baseline (CV val, scheme=`stratified_text`, feature_set=`combined`):
- QWK mean±std: `0.6262 ± 0.0179`
- MAE mean±std: `0.3420 ± 0.0113`

Candidate handcrafted features evaluated: `25` (Tier1–Tier3 names present in the combined feature store).

Keep / drop recommendations (predictor input only; auditor/XAI features may be broader):

Keep (high confidence; ΔQWK mean > 0 and stability ≥ 0.8):
- `grammar_errors_per_100_words` (ΔQWK `+0.0261 ± 0.0079`, stability `1.00`)
- `spelling_errors_per_100_words` (ΔQWK `+0.0211 ± 0.0135`, stability `1.00`)
- `parse_tree_depth` (ΔQWK `+0.0134 ± 0.0078`, stability `0.80`)
- `smog` (ΔQWK `+0.0094 ± 0.0069`, stability `1.00`)
- `avg_word_length` (ΔQWK `+0.0085 ± 0.0057`, stability `1.00`)
- `ttr` (ΔQWK `+0.0084 ± 0.0082`, stability `0.80`)
- `dep_distance` (ΔQWK `+0.0067 ± 0.0043`, stability `0.80`)
- `punctuation_errors_per_100_words` (ΔQWK `+0.0059 ± 0.0096`, stability `0.80`)
- `word_count` (ΔQWK `+0.0053 ± 0.0046`, stability `0.80`)
- `coleman_liau` (ΔQWK `+0.0051 ± 0.0051`, stability `0.80`)
- `intro_prompt_sim` (ΔQWK `+0.0046 ± 0.0053`, stability `0.80`)
- `passive_ratio` (ΔQWK `+0.0043 ± 0.0074`, stability `0.80`) (note: MAE stability is weak)
- `connective_diversity` (ΔQWK `+0.0042 ± 0.0043`, stability `0.80`)
- `avg_sentence_length` (ΔQWK `+0.0030 ± 0.0059`, stability `0.80`)
- `prompt_similarity` (ΔQWK `+0.0023 ± 0.0058`, stability `0.80`)
- `ari` (ΔQWK `+0.0022 ± 0.0066`, stability `0.80`) (note: MAE stability is weak)

Review (weak or unstable; keep only if construct-validity wants the signal as predictor input):
- `pronoun_noun_ratio` (stability `0.60`)
- `lexical_overlap` (stability `0.60`)
- `min_para_relevance` (stability `0.60`)
- `paragraph_count` (stability `0.60`)
- `has_intro` (stability `0.40`)
- `sent_similarity_variance` (stability `0.40`)

Drop (removing helps or is neutral within noise; start by excluding from predictor input):
- `has_conclusion` (ΔQWK `-0.0024 ± 0.0045`)
- `clause_count` (ΔQWK `-0.0014 ± 0.0092`)
- `flesch_kincaid` (ΔQWK `-0.0002 ± 0.0049`)

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
