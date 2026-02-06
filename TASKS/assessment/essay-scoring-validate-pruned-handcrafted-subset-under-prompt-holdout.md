---
id: 'essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout'
title: 'essay-scoring: validate pruned handcrafted subset under prompt_holdout'
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
  - 'essay-scoring-drop-column-importance-for-handcrafted-features-cv'
  - 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
labels: []
---
# essay-scoring: validate pruned handcrafted subset under prompt_holdout

## Objective

Validate whether a **pruned handcrafted predictor subset** (based on Gate B drop-column results)
improves or maintains:
- `scheme=prompt_holdout` CV mean±std QWK (primary yardstick), and
- tail-slice behavior (low tail vs high tail),
before we treat “drop-column says drop X” as safe for prompt generalization.

## Context

Gate B drop-column importance was run under `scheme=stratified_text` (leak-safe, but not the
primary prompt generalization yardstick). We need a prompt-holdout validation step because:
- some handcrafted features may help specifically on unseen prompts (or vice versa),
- pruning can shift tail behavior (and Gate C shows tails are already the dominant failure mode).

References:
- Gate B results: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/artifacts/drop_column_importance.json`
- Gate C baseline residuals (prompt_holdout): `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/reports/residual_diagnostics.md`

## Plan

Guardrails:
- Keep construct scope fixed (argumentative/discussion essay discourse).
- Reuse the same prompt-holdout `cv_feature_store` for apples-to-apples comparisons.

1) Define the pruned handcrafted subset:
   - Use Gate B “keep (high confidence)” as the default predictor subset.
   - Keep “review/unstable” features only if they are needed for construct/XAI reasons (explicitly
     documented) or if they help prompt-holdout.

2) Implement selection support (training-time, using the existing feature store):
   - Allow `combined` training to include:
     - all embedding dimensions, plus
     - either (a) full handcrafted set or (b) a curated handcrafted subset.
   - Ensure this is a **column filter** on the feature matrix (no feature re-extraction).
   - Implementation detail: `pdm run essay-scoring-research cv` supports:
     - `--predictor-handcrafted-keep <feature_name>` (repeatable)
     - `--predictor-handcrafted-drop <feature_name>` (repeatable)
     - Writes `artifacts/predictor_feature_selection.json` for reproducibility.

3) Run prompt-holdout CV comparisons (feature-store reuse):
   - Full handcrafted set (baseline)
   - Pruned handcrafted subset
   - Persist residual diagnostics for both runs (so we can compare prompt slices + tails).

   Recommended pruned subset (validated under `prompt_holdout`):
   - Drop from predictor: `has_conclusion`, `clause_count`, `flesch_kincaid`.
   - Keep the remaining handcrafted features (until a construct audit says otherwise).

   Optional follow-up (only if evidence supports it): try dropping these “unstable/construct-review”
   features too: `has_intro`, `sent_similarity_variance`, `paragraph_count`, `min_para_relevance`,
   `lexical_overlap`, `pronoun_noun_ratio`.

4) Decision:
   - Prefer the pruned subset only if it is non-regressing on prompt-holdout mean QWK and does not
     worsen tail slices (`y_true <= 2.0` and `y_true >= 4.0`).
   - Record the chosen predictor input definition back into the CV-first story.

## Success Criteria

- A prompt-holdout CV run exists for full vs pruned handcrafted predictor inputs (same CV feature store).
- We have a clear keep/drop decision for predictor input handcrafted features under prompt generalization.
- The story hub includes the run paths + a short rationale for the decision.
- The run artifacts include `artifacts/predictor_feature_selection.json` and `reports/cv_report.md`
  shows the predictor feature selection mode.

## Implementation (2026-02-04)

Context (fixed inputs):
- Prepared CSVs: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_{train,test}_prepared.csv`
- Splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
- Reused CV feature store: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store`

Runs (feature_set=`combined`, scheme=`prompt_holdout`):

- Baseline (no filtering): `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/`
  - CV val QWK mean±std: `0.61832 ± 0.02396`
  - Locked-test tail slices:
    - low tail (`y_true<=2.0`) MAE: `0.5806`, adjacent_acc: `0.7151`
    - high tail (`y_true>=4.0`) MAE: `0.5224`, adjacent_acc: `0.7930`
- Prune v1 (drop 9 handcrafted): `output/essay_scoring/20260204_204456_ellipse_cv_combined_prompt_holdout_pruned_handcrafted_20260204_214450/`
  - CV val QWK mean±std: `0.61122 ± 0.02462` (regressed)
- Prune (drop 3 handcrafted): `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
  - CV val QWK mean±std: `0.62210 ± 0.01743` (improved)
  - Locked-test tail slices:
    - low tail (`y_true<=2.0`) MAE: `0.5726`, adjacent_acc: `0.7204`
    - high tail (`y_true>=4.0`) MAE: `0.5100`, adjacent_acc: `0.7980`

Decision:
- Adopt “drop 3” as the current pruned handcrafted predictor definition:
  `has_conclusion`, `clause_count`, `flesch_kincaid`.
- Do **not** drop the broader “unstable/construct-review” set by default based on current evidence
  (revisit later if construct audit or additional prompt-holdout evidence supports it).

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Gate B shortlist: `TASKS/assessment/essay-scoring-drop-column-importance-for-handcrafted-features-cv.md`
- Gate C diagnostics: `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Research hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
