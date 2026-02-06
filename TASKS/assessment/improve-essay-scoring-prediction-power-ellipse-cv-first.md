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
last_updated: '2026-02-06'
related:
  - 'essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
  - 'essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse'
  - 'essay-scoring-drop-column-importance-for-handcrafted-features-cv'
  - 'essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout'
  - 'essay-scoring-xgboost-hyperparameter-sweep-cv-selected'
  - 'essay-scoring-decision-gate-for-experiment-optimization-dependencies'
  - 'essay-scoring-optuna-hyperparameter-optimization-cv-selected'
  - 'essay-scoring-transformer-fine-tuning--prompt-invariance-experiments'
  - 'essay-scoring-statsmodels-diagnostics--catboost-baseline'
  - 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
  - 'essay-scoring-tail-calibration--grade-band-imbalance-mitigation'
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

Structure work as **tracks**, each with a single decision axis, so we don’t explode the
combinatorics (features × objective × hyperparams × ensemble × new features).

Locked defaults (guardrails):
- Construct scope: argumentative/discussion essay discourse (no genre broadening).
- Inputs: prepared ELLIPSE CSVs + `splits.json` (200–1000 words policy; exclusions unchanged).
- Primary yardstick: `scheme=prompt_holdout` CV val QWK mean±std (unseen prompt generalization).
- Feature-store reuse mandatory for follow-ups (avoid accidental re-extraction drift).

### Track 0 — Foundations (done)
- Dataset prep + reusable splits: `essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words`
- Baselines (`combined`) under `stratified_text` + `prompt_holdout`:
  `essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse`

### Track 1 — Feature-set choice (done; Gate A)
- Ablation across feature sets: `essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse`
- Gate A outcome: keep `combined` as current “best”.

### Track 2 — Failure modes + slice gates (Gate C)
- Residual diagnostics by prompt + grade band + covariates:
  `essay-scoring-residual-diagnostics-by-prompt-and-grade-band`
- Gate C outcome drives the next lever (tail calibration vs objective vs features).

### Track 3 — Handcrafted feature discipline (Gate B → prompt-holdout validation)
- Drop-column importance shortlist (done): `essay-scoring-drop-column-importance-for-handcrafted-features-cv`
- Validate a pruned handcrafted predictor subset under `prompt_holdout` before we drop features
  (use Gate C tail slices as acceptance criteria):
  `essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout`

### Track 4 — Tail calibration + objective alignment (Gate D, but *slice-aware*)
- Address grade-band compression / imbalance first (cheap, targeted):
  `essay-scoring-tail-calibration--grade-band-imbalance-mitigation`
- Then (if still needed) try ordinal/custom training modes:
  `essay-scoring-ordinal-custom-objective-experiments-qwk`

### Track 5 — Hyperparams + variance reduction (after objective is chosen)
- CV-select XGBoost params (prompt_holdout-first): `essay-scoring-xgboost-hyperparameter-sweep-cv-selected`
- CV-time ensembling (bagging across seeds per fold): `essay-scoring-cv-ensembling-ellipse-cv-first`

### Track 6 — Construct validity + candidate features (after “best current” is stable)
- Audit + candidate features: `essay-scoring-construct-validity-audit--feature-candidates`

## Shared artifacts (for this story)

Created 2026-02-04 (ELLIPSE Overall, 200–1000 words, excluded prompts unchanged):

- Prepared dataset run dir: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/`
  - Train CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
  - Test CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
  - Integrity report: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/reports/dataset_integrity_report.md`
- Splits run dir: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/`
  - Splits JSON: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
  - Splits report: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/reports/splits_report.md`

Baseline CV runs (feature_set=combined):

- `scheme=stratified_text` run dir: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/`
  - Metrics: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/artifacts/cv_metrics.json`
  - Report: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/reports/cv_report.md`
  - Val QWK (mean±std): **0.62623 ± 0.01793**
- `scheme=prompt_holdout` run dir: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/`
  - Metrics: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/artifacts/cv_metrics.json`
  - Report: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/reports/cv_report.md`
  - Val QWK (mean±std): **0.61832 ± 0.02396** (PRIMARY yardstick)

Notes:
- The `final_train_val_test.test.qwk` value is the same across schemes because it is not fold-based;
  do not treat it as “prompt-holdout test performance”. Use CV val mean±std for selection.

CV ablation (feature_set in {embeddings, handcrafted, combined}) completed 2026-02-04:

- `embeddings`:
  - `scheme=stratified_text`: Val QWK (mean±std) **0.55198 ± 0.02148**
    - Run: `output/essay_scoring/20260204_164449_ellipse_cv_embeddings_stratified_text_20260204_174445/`
  - `scheme=prompt_holdout`: Val QWK (mean±std) **0.54465 ± 0.02199**
    - Run: `output/essay_scoring/20260204_165648_ellipse_cv_embeddings_prompt_holdout_20260204_175630/`
- `handcrafted`:
  - `scheme=stratified_text`: Val QWK (mean±std) **0.57372 ± 0.01393**
    - Run: `output/essay_scoring/20260204_180119_ellipse_cv_handcrafted_stratified_text_20260204_190101/`
  - `scheme=prompt_holdout`: Val QWK (mean±std) **0.56444 ± 0.01887**
    - Run: `output/essay_scoring/20260204_180303_ellipse_cv_handcrafted_prompt_holdout_20260204_190248/`
- `combined` (baseline above): Val QWK (mean±std) **0.61832 ± 0.02396** (prompt_holdout)

Decision gate A outcome:
- Keep `combined` as the current “best” feature set. Next: drop-column to prune/validate the
  handcrafted set (Gate B), then residual diagnostics (Gate C).

Drop-column (Gate B) completed 2026-02-04 (scheme=`stratified_text`, feature_set=`combined`):

- Run dir: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/`
  - Metrics: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/artifacts/drop_column_importance.json`
  - Report: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/reports/drop_column_importance.md`
- Baseline (CV val mean±std): **0.6262 ± 0.0179** (matches the baseline stratified-text CV run)
- Candidate handcrafted features evaluated: `25` (Tier1–Tier3)

Gate B synthesis (for *predictor input*; auditor/XAI surface can be broader):
- Strong keep (largest + stable ΔQWK): `grammar_errors_per_100_words`, `spelling_errors_per_100_words`,
  `parse_tree_depth`, `smog`, `avg_word_length`, `ttr`.
- Suggested drop (ΔQWK ≤ 0 within noise): `has_conclusion`, `clause_count`, `flesch_kincaid`.
- Weak/unstable signals (keep only if construct-audit needs them inside the predictor): `has_intro`,
  `sent_similarity_variance`, `paragraph_count`, `min_para_relevance`, `lexical_overlap`,
  `pronoun_noun_ratio`.

Next-step implication:
- Before we treat “drop these from the predictor” as truth for prompt generalization, we should
  **validate** the pruned-vs-full handcrafted subset under `scheme=prompt_holdout` (primary yardstick).
  The drop-column run is still a very useful shortlist for what to test first.
- Implementation note: use `pdm run essay-scoring-research cv` with repeatable
  `--predictor-handcrafted-keep <feature_name>` (allowlist) or `--predictor-handcrafted-drop <feature_name>`
  (denylist) flags (column filtering; no re-extraction) and confirm
  `artifacts/predictor_feature_selection.json`.

Gate B prompt-holdout validation (completed 2026-02-04):
- Pruned predictor (drop 3 handcrafted): `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
  - CV val QWK mean±std: `0.62210 ± 0.01743`
  - Decision: drop `has_conclusion`, `clause_count`, `flesch_kincaid` from the predictor going forward.
- Pruned predictor (drop 9 handcrafted; tested, not adopted): `output/essay_scoring/20260204_204456_ellipse_cv_combined_prompt_holdout_pruned_handcrafted_20260204_214450/`
  - CV val QWK mean±std: `0.61122 ± 0.02462` (regressed)

Residual diagnostics (Gate C) implementation (2026-02-04):
- CV runs now also persist per-record prediction rows + a report:
  - `artifacts/residuals_cv_val_oof.csv` + `.jsonl` (OOF val predictions across folds)
  - `artifacts/residuals_locked_test.csv` + `.jsonl` (locked test from final fit)
  - `reports/residual_diagnostics.md` (by prompt, grade band, covariates)

Gate C baseline residual diagnostics run (combined + prompt_holdout, feature-store reuse):
- Run dir: `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/`
  - Residual report: `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/reports/residual_diagnostics.md`
  - Per-record rows:
    - `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/artifacts/residuals_locked_test.csv`
    - `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/artifacts/residuals_cv_val_oof.csv`

Gate C findings (high-level):
- Strong **grade compression** (rarely predicts 4.5/5.0; high tail underpredicted; low tail overpredicted).
- Some prompts are consistently hard (e.g. “Places to visit”) and should be audited for construct fit.
- Covariates in the current report do not explain much variance in residuals → likely missing “excellent vs good”
  signals once mechanics are already clean.

Track 4 (objective alignment) — Step 1 minimal ordinal check (completed 2026-02-05):
- Goal: see if ordinal-as-multiclass reduces tail bias / grade compression before Gate D.
- Runs (all `scheme=prompt_holdout`, combined, predictor fixed to drop-3, feature-store reuse):
  - Regression baseline (drop-3): `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
    - CV val QWK mean±std: `0.62210 ± 0.01743`
  - Ordinal multiclass (expected-value decode): `output/essay_scoring/20260205_145529_ellipse_cv_combined_prompt_holdout_ordinal_expected_20260205_155521/`
    - CV val QWK mean±std: `0.58728 ± 0.01729` (ΔQWK: `-0.03482`)
  - Ordinal multiclass (argmax decode): `output/essay_scoring/20260205_145529_ellipse_cv_combined_prompt_holdout_ordinal_argmax_20260205_155521/`
    - CV val QWK mean±std: `0.54047 ± 0.02357` (ΔQWK: `-0.08163`)
- Tail slices regressed in both ordinal variants (high tail MAE/adjacent_acc worsened vs regression baseline).
- Decision: keep regression as “best current” and proceed to Gate D tail calibration / imbalance mitigation.

Track 4 (Gate D) — Tail calibration + grade-band imbalance mitigation (completed 2026-02-05):
- Task: `essay-scoring-tail-calibration--grade-band-imbalance-mitigation`
- New CV flags introduced (for Gate D + later sweeps):
  - `--grade-band-weighting {none,sqrt_inv_freq}` + `--grade-band-weight-cap <float>`
  - `--prediction-mapping {round_half_band,qwk_cutpoints_lfo}` (leave-one-fold-out cutpoints; leak-safe)
  - Calibration artifacts are persisted under `artifacts/` when enabled:
    - `artifacts/calibration_cutpoints_by_fold.json`
    - `artifacts/calibration_summary.json`

Gate D experiment matrix (all `scheme=prompt_holdout`, combined, predictor fixed to drop-3, feature-store reuse):
- A baseline:
  - Run: `output/essay_scoring/20260205_163458_ellipse_gate_d_baseline_prompt_holdout_drop3_20260205_173454/`
  - CV val QWK mean±std: `0.62210 ± 0.01743`
- B weighting-only (`sqrt_inv_freq`, cap=3.0):
  - Run: `output/essay_scoring/20260205_170701_ellipse_gate_d_weighting_prompt_holdout_drop3_20260205_180657/`
  - CV val QWK mean±std: `0.63516 ± 0.01650`
- C calibration-only (`qwk_cutpoints_lfo`):
  - Run: `output/essay_scoring/20260205_170843_ellipse_gate_d_calibration_prompt_holdout_drop3_20260205_180838/`
  - CV val QWK mean±std: `0.68615 ± 0.01029`
- D weighting + calibration:
  - Run: `output/essay_scoring/20260205_171050_ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_20260205_181046/`
  - CV val QWK mean±std: `0.68360 ± 0.01470`

Gate D decision (for CV-first selection):
- Adopt **weighting + calibration** as the default evaluation setup going forward:
  - `--grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0`
  - `--prediction-mapping qwk_cutpoints_lfo`
  Rationale: best OOF **high-tail adjacent accuracy** (primary for our noisy-label setting) with mean QWK still
  within fold noise vs calibration-only.
- Keep **calibration-only** as the runner-up when we want max mean QWK / lowest tail bias without adding
  training-time weighting.

Track 5 (Gate E) — XGBoost hyperparameter sweep (completed 2026-02-05):
- Task: `essay-scoring-xgboost-hyperparameter-sweep-cv-selected`
- Prompt-holdout sweep (combined; drop-3; weighting+calibration; feature-store reuse):
  - Sweep dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/`
  - Summary: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/reports/sweep_summary.md`
  - Best config: `config_id=97e84d798d`
    - Params: `max_depth=4`, `min_child_weight=20`, `reg_lambda=2.0`, `reg_alpha=0.0`
    - Run dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d/`
    - CV val QWK mean±std: `0.68460 ± 0.01659`
    - High tail adjacent_acc (`y_true>=4.0`): `0.87907` (improved vs Gate D baseline D `0.82481`)
- Stratified_text stability check (same best config):
  - Run: `output/essay_scoring/20260205_202126_ellipse_gate_e_xgb_bestparams_stratified_text_20260205_212122/`
  - CV val QWK mean±std: `0.68509 ± 0.01969`
- Decision: adopt `max_depth=4`, `min_child_weight=20` as “best current” training params for follow-up gates
  (still using drop-3 handcrafted prune + weighting+calibration mapping).

Track 5 (Gate F) — CV ensembling (completed 2026-02-05):
- Task: `essay-scoring-cv-ensembling-ellipse-cv-first`
- Implementation: `pdm run essay-scoring-research cv --ensemble-size <N>` trains N models per fold (seed ensemble)
  and averages predictions before CV metrics + residual diagnostics.
- Runs (all `scheme=prompt_holdout`, combined, predictor fixed to drop-3, weighting+calibration, feature-store reuse):
  - `ensemble_size=1` (baseline, matches Gate E best config):
    - Run: `output/essay_scoring/20260205_213805_ellipse_gate_f_cv_ensemble1_prompt_holdout_drop3_wcal_bestparams_20260205_223800/`
    - CV val QWK mean±std: `0.68460 ± 0.01659`
    - High tail adjacent_acc (`y_true>=4.0`): `0.87907`
  - `ensemble_size=3`:
    - Run: `output/essay_scoring/20260205_213920_ellipse_gate_f_cv_ensemble3_prompt_holdout_drop3_wcal_bestparams_20260205_223917/`
    - CV val QWK mean±std: `0.68573 ± 0.01755`
    - High tail adjacent_acc (`y_true>=4.0`): `0.83411` (regression)
  - `ensemble_size=5`:
    - Run: `output/essay_scoring/20260205_214118_ellipse_gate_f_cv_ensemble5_prompt_holdout_drop3_wcal_bestparams_20260205_224115/`
    - CV val QWK mean±std: `0.68946 ± 0.01533`
    - High tail adjacent_acc (`y_true>=4.0`): `0.85271` (regression)
- Decision: reject ensembling for CV-first selection for now. While mean QWK improves, the high-tail slice degrades,
  violating the current tail guardrail / primary yardstick for noisy-label selection.

## Success Criteria

- Baseline CV metrics exist (mean±std QWK) for `combined` under both schemes.
- A documented “best current” configuration exists selected by CV (not by test), prioritized by:
  - `prompt_holdout` mean QWK first, then
  - stability check via `stratified_text` (avoid regressions / high variance).
- A concrete shortlist of next improvements exists, backed by:
  - ablation deltas (what feature sets matter)
  - drop-column results (what handcrafted features matter)
  - prompt/band residual diagnostics (where the model fails)
- Tail slices are explicitly monitored for “best current” candidates:
  - low tail: `y_true <= 2.0`
  - high tail: `y_true >= 4.0`
  (do not accept global QWK gains that worsen these slices without an explicit tradeoff decision)

## Acceptance Criteria (XAI + Construct Validity)

Non-negotiable: regardless of whether the CV-best *predictor* ends up being `embeddings`, `handcrafted`,
or `combined`, the workflow MUST preserve an explicit **construct-validity audit** surface and a
teacher-meaningful XAI surface.

### A. Construct audit artifacts must exist for every “best current” candidate

For any configuration we intend to treat as “best current” (i.e. a candidate we would ship as the
current scorer in research demos), we MUST produce and store:

- Prompt/band/slice residual diagnostics (see task `essay-scoring-residual-diagnostics-by-prompt-and-grade-band`).
- A construct-focused audit report that explicitly checks for shortcut signals (length-only, mechanics-only proxies)
  and documents failure slices and mitigations.

If `embeddings` wins under prompt-holdout CV, the above artifacts remain REQUIRED; in that case, the
handcrafted feature pack becomes an **auditor/explainer** surface (may be computed but not fed into
the predictor).

### B. Interpretation standards (teacher-facing)

- Do **not** treat “embedding dimension importance” as teacher-facing XAI.
- Teacher-facing explanations MUST be grounded in construct-relevant signals (mechanics, readability,
  discourse structure, cohesion/syntax, etc.) and/or example-based/counterfactual analyses that are
  intelligible in classroom terms.

### C. Handcrafted feature set is versioned; “hybrid doesn’t help” conclusions are scoped

The current LanguageTool + spaCy feature set is a **v1 iteration**, not an exhaustive representation
of “handcrafted features”.

Therefore:
- Ablation conclusions are scoped to the exact handcrafted set and feature definitions used in that run.
- If we change handcrafted features materially (add/remove/rename/normalize), we MUST treat this as a
  new feature-set version and re-run the ablation under `scheme=prompt_holdout` before concluding
  anything about hybrid uplift.
- Any changes to exclusions or the word-window policy (200–1000) remain guarded: do not change them
  without a new task/decision and a new set of prepared artifacts + splits.

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
