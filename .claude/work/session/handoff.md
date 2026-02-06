# HANDOFF: Active Session Context

## Purpose

This file contains only active, next-action context.
Detailed implementation history belongs in:

- `TASKS/` (task plans and status)
- `docs/reference/ref-essay-scoring-research-hub.md` (workstream navigation)
- `docs/operations/ml-nlp-runbook.md` (canonical run commands)
- `output/essay_scoring/` (experiment evidence)

## Current Focus (2026-02-06)

### Whitebox essay scoring: CV-first optimization decision gate

Active tasks:
- `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md` (`status: in_progress`)

Recently completed:
- `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md` (`status: done`; ADR-0031 accepted)
- `TASKS/assessment/essay-scoring-optuna-hyperparameter-optimization-cv-selected.md` (`status: done`)
- `TASKS/assessment/essay-scoring-statsmodels-diagnostics--catboost-baseline.md` (`status: done`; Gate G1 prompt-holdout failed)

Deferred follow-up track (gate-locked):
- None (transformer task promoted after Gate G1 failure)

Gate G1 strict order (completed):
1. CatBoost prompt-holdout CV completed:
   - run dir: `output/essay_scoring/20260206_185135_ellipse_gate_g1_catboost_prompt_holdout_20260206_195132`
2. CatBoost stratified-text CV completed:
   - run dir: `output/essay_scoring/20260206_185436_ellipse_gate_g1_catboost_stratified_20260206_195431`
3. Paired comparison reports completed:
   - prompt-holdout: `output/essay_scoring/20260206_190010_ellipse_gate_g1_compare_prompt_holdout_catboost_vs_b28c`
   - stratified-text: `output/essay_scoring/20260206_190014_ellipse_gate_g1_compare_stratified_catboost_vs_b28c`
4. Gate result:
   - prompt-holdout **failed** (worst-prompt and both tail guardrails regressed)
   - stratified-text **passed** (mean QWK within tolerance)
   - escalation rule triggered: transformer prompt-invariance track promoted.

### Optuna Pilot Phase 0 (frozen inputs)

Frozen dataset/splits/feature-store paths:
- Train CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
- Test CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
- Splits JSON: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
- Reused CV feature store: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store`

Frozen fixed-grid baseline comparator:
- Sweep root: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746`
- Best config id: `97e84d798d`
- Best run dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d`

### First runnable command (guardrail contract)

Runbook-aligned contract for first pilot run:
- objective: `worst_prompt_qwk_then_mean_qwk`
- prompt guardrail: `--min-prompt-n 30`
- diagnostics breadth: `--bottom-k-prompts 5`
- weighting + calibration + drop-3 kept fixed vs baseline

```bash
pdm run essay-scoring-research optuna-sweep \
  --scheme prompt_holdout \
  --feature-set combined \
  --training-mode regression \
  --grade-band-weighting sqrt_inv_freq \
  --grade-band-weight-cap 3.0 \
  --prediction-mapping qwk_cutpoints_lfo \
  --predictor-handcrafted-drop has_conclusion \
  --predictor-handcrafted-drop clause_count \
  --predictor-handcrafted-drop flesch_kincaid \
  --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json \
  --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store \
  --n-trials 40 \
  --objective worst_prompt_qwk_then_mean_qwk \
  --min-prompt-n 30 \
  --bottom-k-prompts 5 \
  --baseline-best-run-dir output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d \
  --run-name ellipse_optuna_pilot_prompt_holdout_drop3_wcal
```

Detached launch variant (canonical for long ML runs):

```bash
RUN_NAME=ellipse_optuna_pilot_prompt_holdout_drop3_wcal_$(date +%Y%m%d_%H%M%S)
LOG=output/essay_scoring/${RUN_NAME}.driver.log
mkdir -p output/essay_scoring
/usr/bin/screen -S "essay_scoring_${RUN_NAME}" -dm /bin/bash -lc \
  "cd \"$(pwd)\" && set -a && source .env && set +a && PYTHONUNBUFFERED=1 \
   pdm run essay-scoring-research optuna-sweep \
     --scheme prompt_holdout \
     --feature-set combined \
     --training-mode regression \
     --grade-band-weighting sqrt_inv_freq \
     --grade-band-weight-cap 3.0 \
     --prediction-mapping qwk_cutpoints_lfo \
     --predictor-handcrafted-drop has_conclusion \
     --predictor-handcrafted-drop clause_count \
     --predictor-handcrafted-drop flesch_kincaid \
     --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv \
     --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv \
     --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json \
     --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store \
     --n-trials 40 \
     --objective worst_prompt_qwk_then_mean_qwk \
     --min-prompt-n 30 \
     --bottom-k-prompts 5 \
     --baseline-best-run-dir output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d \
     --run-name \"${RUN_NAME}\" 2>&1 | tee -a \"${LOG}\""
echo "Screen session: essay_scoring_${RUN_NAME}"
echo "Driver log: ${LOG}"
```

Live run started (2026-02-06 11:55 local):
- Screen session: `essay_scoring_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536`
- Run dir: `output/essay_scoring/20260206_105542_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536`
- Driver log: `output/essay_scoring/ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536.driver.log`
- Progress file: `output/essay_scoring/20260206_105542_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536/progress.json`

Pilot completion snapshot (2026-02-06 12:24 local):
- `status.json` completed; selected trial `#5`, config `b28c376a73`.
- Selected params: `max_depth=3`, `min_child_weight=20`, `reg_lambda=5.0`, `reg_alpha=1.0`.
- Baseline (`97e84d798d`) vs selected (`b28c376a73`) on prompt-holdout objective metrics:
  - worst-prompt QWK: `0.48185 -> 0.50282` (improved)
  - mean QWK: `0.68460 -> 0.67940` (regressed)
  - low-tail adjacent accuracy: `0.79577 -> 0.82042` (improved)
  - high-tail adjacent accuracy: `0.87907 -> 0.86667` (regressed within tolerance)
- Sweep behavior:
  - `40` trials, `19` unique configs, `20` guardrail-rejected.
  - Strong duplicate concentration on selected config (`19` repeated trials), indicating search inefficiency.

Stratified stability pair completion snapshot (2026-02-06 18:00 local):
- Run dir (selected): `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_b28c376a73_20260206_185804`
- Run dir (near-miss): `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_16796accd7_20260206_185804`
- Both runs completed (`cv_final_train_test_eval`).
- CV summary (`stratified_text`, same frozen paths/feature-store/drop-3+wcal controls):
  - `b28c376a73`: `val_qwk_mean=0.68537`, `val_adjacent_mean=0.87187`
  - `16796accd7`: `val_qwk_mean=0.67733`, `val_adjacent_mean=0.86067`
- Bottom-5 worst-prompt metric (`min_prompt_n=30`, `cv_val_oof`):
  - `b28c376a73`: `worst_prompt_qwk=0.48834`
  - `16796accd7`: `worst_prompt_qwk=0.43720`
- Overfit signal (mean train-vs-val QWK gap across folds):
  - `b28c376a73`: `0.15331`
  - `16796accd7`: `0.22705`
- Recommendation basis for ADR-0031:
  - keep `b28c376a73` as the stable Optuna-selected config,
  - treat `16796accd7` as split-sensitive/overfit despite prompt-holdout upside.

## Recently Completed (Compressed)

### Optuna sweep command and artifact contract ✅ COMPLETED
- Landed `optuna-sweep` CLI and sweep runner with trial artifacts, selected-params output, summary report, and progress tracking.
- Paths: `scripts/ml_training/essay_scoring/optuna_sweep.py`, `scripts/ml_training/essay_scoring/commands/sweep_commands.py`.

### Essay-scoring CLI SRP refactor ✅ COMPLETED
- Replaced 1000+ LoC monolithic CLI with command modules under `scripts/ml_training/essay_scoring/commands/`.
- Root `scripts/ml_training/essay_scoring/cli.py` is now composition-only.

### Workstream topology contract (docs-as-code) ✅ COMPLETED
- Added manifest + scaffold + renderer + validator for hub topology.
- Paths: `scripts/docs_mgmt/workstream_topology_manifest.py`, `scripts/docs_mgmt/workstream_topology_scaffold.py`, `scripts/docs_mgmt/render_workstream_hubs.py`, `scripts/docs_mgmt/validate_workstream_topology.py`.

### AGENTS.md surgical compaction ✅ COMPLETED
- Reduced duplication and moved stable detail to rules/runbooks/skills while preserving core workflow behavior.

## Notes

- Completed execution logs, one-off shell transcripts, and historical run narration were intentionally removed from this handoff and are considered superseded by code, runbook contracts, and run artifacts.
