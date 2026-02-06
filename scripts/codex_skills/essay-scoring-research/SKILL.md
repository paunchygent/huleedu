---
id: "codex-skill-essay-scoring-research"
type: "skill"
created: "2026-02-04"
last_updated: "2026-02-04"
scope: "repo"
---
# Codex Skill: Essay Scoring Research (ML)

## Purpose

Run ELLIPSE essay-scoring research experiments reliably (detached execution, repeatable inputs),
and avoid wasting time by re-extracting features unnecessarily.

Canonical reference: `docs/operations/ml-nlp-runbook.md`.

## Mandatory defaults (do not skip)

- Use an env-aware shell: `./scripts/dev-shell.sh` (loads `.env`).
- Long runs MUST be detached (prefer `/usr/bin/screen`) and write a driver log under
  `output/essay_scoring/`.
- After the first successful run creates a feature store, all follow-up runs MUST reuse it:
  - `run`: `--reuse-feature-store-dir output/essay_scoring/<RUN>/feature_store`
  - `cv`/sweeps: `--reuse-cv-feature-store-dir output/essay_scoring/<CV_RUN>/cv_feature_store`
- Monitor progress by script via `output/essay_scoring/<RUN>/progress.json` (not log parsing).
- CV runs MUST produce residual diagnostics (`reports/residual_diagnostics.md`) plus per-record rows
  under `artifacts/residuals_*.{csv,jsonl}` (Gate C).

## ELLIPSE CV-first: canonical inputs

Always use the prepared dataset artifacts + matching `splits.json`:

```bash
PREP_TRAIN_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv
PREP_TEST_CSV=output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv
SPLITS_JSON=output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json
```

## Baseline CV (combined)

```bash
# 1) stratified_text creates the CV feature store
pdm run essay-scoring-research cv --dataset-kind ellipse \
  --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" \
  --splits-path "$SPLITS_JSON" --scheme stratified_text --feature-set combined \
  --language-tool-service-url http://127.0.0.1:18085 \
  --embedding-service-url http://127.0.0.1:19000 \
  --run-name ellipse_cv_combined_stratified_text

# 2) prompt_holdout reuses it (avoid re-extraction)
pdm run essay-scoring-research cv --dataset-kind ellipse \
  --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" \
  --splits-path "$SPLITS_JSON" --scheme prompt_holdout --feature-set combined \
  --reuse-cv-feature-store-dir output/essay_scoring/<STRAT_CV_RUN>/cv_feature_store \
  --run-name ellipse_cv_combined_prompt_holdout
```

Note: `cv` does not compute SHAP. Run SHAP via `pdm run essay-scoring-research run` (do not pass
`--skip-shap`).

## Pruned handcrafted predictor subset (combined)

Use this to test a pruned handcrafted predictor set under `scheme=prompt_holdout`
(Gate B → prompt generalization) **without re-extracting features**
(column filtering only).

```bash
pdm run essay-scoring-research cv --dataset-kind ellipse \
  --ellipse-train-path "$PREP_TRAIN_CSV" --ellipse-test-path "$PREP_TEST_CSV" \
  --splits-path "$SPLITS_JSON" --scheme prompt_holdout --feature-set combined \
  --reuse-cv-feature-store-dir output/essay_scoring/<PROMPT_HOLDOUT_BASELINE_RUN>/cv_feature_store \
  --predictor-handcrafted-drop has_conclusion \
  --predictor-handcrafted-drop clause_count \
  --predictor-handcrafted-drop flesch_kincaid \
  --run-name ellipse_cv_combined_prompt_holdout_pruned_handcrafted
```

Note: `--predictor-handcrafted-keep <feature_name>` also exists for “strong keep only” experiments.

Selection artifacts:
- `output/essay_scoring/<RUN>/artifacts/predictor_feature_selection.json`
- `output/essay_scoring/<RUN>/reports/cv_report.md` includes predictor selection summary
