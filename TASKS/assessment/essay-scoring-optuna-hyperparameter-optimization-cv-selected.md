---
id: 'essay-scoring-optuna-hyperparameter-optimization-cv-selected'
title: 'essay-scoring: Optuna hyperparameter optimization (CV-selected)'
type: 'task'
status: 'done'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-06'
last_updated: '2026-02-06'
related: ['improve-essay-scoring-prediction-power-ellipse-cv-first', 'essay-scoring-xgboost-hyperparameter-sweep-cv-selected', 'essay-scoring-decision-gate-for-experiment-optimization-dependencies']
labels: []
---
# essay-scoring: Optuna hyperparameter optimization (CV-selected)

## Objective

Add an Optuna-backed hyperparameter optimizer for our CV-first XGBoost training so we can:

- search more efficiently than a fixed grid,
- optimize for prompt-holdout generalization (worst-prompt-first), and
- keep selection disciplined (CV-only) with explicit guardrails (tails).

## Context

- Current sweep runner (`pdm run essay-scoring-research xgb-sweep`) uses a fixed grid.
- We already have the ingredients Optuna needs:
  - a deterministic CV runner (`scripts/ml_training/essay_scoring/cross_validation.py`)
  - per-record residual artifacts + prompt slice report (`reports/residual_diagnostics.md`)
- Risk: if we run too many trials, we can overfit to a single `splits.json` definition.

## Plan

### A) Dependency + isolation

- Add `optuna` to `dependency-groups.ml-research` only.
- Confirm no impact on offload runtime images (`dependency-groups.offload-runtime` unchanged).

### B) Implement an Optuna sweep runner (CV-first)

- Add a new CLI command, tentatively:
  - `pdm run essay-scoring-research optuna-sweep`
- Each Optuna trial:
  1) builds an XGBoost param set (subset of the existing sweep grid + any new regularization knobs),
  2) runs `run_cross_validation(...)` with `scheme=prompt_holdout` and CV feature-store reuse,
  3) parses `artifacts/residuals_cv_val_oof.csv` to compute:
     - worst-prompt QWK (with `min_prompt_n`),
     - mean QWK,
     - low/high tail slice metrics.

Objective (lexicographic):
- maximize worst-prompt QWK, then mean QWK.

Guardrails:
- reject configs that materially worsen tail slices unless explicitly allowed via a flag.

### C) Overfitting-to-splits mitigation

- Trial cap: pilot 30–50.
- Require a stability check:
  - rerun the best config under `scheme=stratified_text` (same dataset + same feature store)
  - confirm no large regression.

### D) Artifacts + reporting (must be reproducible)

Persist under a single sweep run dir:
- `artifacts/optuna_study.json` or `artifacts/optuna_trials.json`
- `artifacts/selected_params.json`
- `reports/optuna_summary.md` (sorted by worst-prompt, then mean QWK)
- `progress.json` (trial progress)

### E) Pilot run + decision

- Run one pilot on ELLIPSE prompt-holdout using the canonical splits + feature-store reuse.
- Compare against the best fixed-grid sweep result.
- Record findings in:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`

## Pilot Execution Plan (2026-02-06)

### Phase 0: Inputs + baseline freeze

1) Reuse canonical ELLIPSE artifacts and existing CV feature store:
   - `--ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
   - `--ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
   - `--splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
   - `--reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store`
2) Baseline comparator is the best current fixed-grid prompt-holdout run under weighting+calibration.
   - Baseline sweep root: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746`
   - Baseline best config: `config_id=97e84d798d`
   - Baseline best run dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d`

### Phase 1: Optuna pilot scope

- Trials: `40` (cap remains within 30–50 pilot window).
- Primary objective: maximize worst-prompt QWK with `min_prompt_n=30`.
- Secondary objective: maximize mean QWK.
- Guardrails:
  - report bottom-5 prompts by QWK (`min_prompt_n=30`),
  - reject candidate configs that materially regress high/low-tail slices unless explicitly overridden.

First runnable command (frozen paths + guardrails):

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

### Phase 2: Stability and anti-overfit checks

1) Re-run the top-1 and top-2 prompt-holdout configs under `scheme=stratified_text`.
2) Keep only configs with no material stratified-text regression relative to fixed-grid baseline.
3) Persist all trial records and selected params under one run dir.

### Phase 3: Decision handoff outputs

- Required artifacts:
  - `artifacts/optuna_trials.json`
  - `artifacts/selected_params.json`
  - `reports/optuna_summary.md`
  - `progress.json`
- Required doc updates:
  - update decision state in
    `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
  - append findings and recommendation in
    `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`

### Pilot completion criteria

- A selected Optuna config is reproducible and passes stratified-text stability.
- Prompt-holdout worst-prompt QWK (`min_prompt_n=30`) is improved or explicitly tradeoff-justified.
- Decision gate task is ready to close with accept/defer/reject for Optuna.

## Outcome (2026-02-06)

- Optuna pilot (`40` trials) completed with full artifacts and frozen-input reproducibility.
- Stratified stability pair completed and validated:
  - stable selected config: `b28c376a73`
  - rejected near-miss config: `16796accd7` (split-sensitive / higher overfit gap)
- Decision integrated into accepted ADR:
  - `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`

### Pilot result snapshot (2026-02-06)

- Run dir: `output/essay_scoring/20260206_105542_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536`
- Sweep status: completed (`40/40` trials).
- Selected trial: `#5` (`config_id=b28c376a73`), params:
  - `max_depth=3`, `min_child_weight=20`, `reg_lambda=5.0`, `reg_alpha=1.0`
- Baseline (`97e84d798d`) vs selected (`b28c376a73`) on objective guardrail metrics:
  - worst-prompt QWK: `0.48185 -> 0.50282` (improved)
  - mean QWK: `0.68460 -> 0.67940` (regressed)
  - low-tail adjacent accuracy: `0.79577 -> 0.82042` (improved)
  - high-tail adjacent accuracy: `0.87907 -> 0.86667` (regressed, within tolerance)
- Trial-space behavior:
  - `19` unique configs over `40` trials.
  - Selected config repeated `19` times, suggesting duplicate-trial inefficiency.

Implication:
- The pilot demonstrates prompt-tail robustness gains are achievable, but not yet a clear global-quality win.
- A stratified-text stability check is still required before promotion.

### Phase 2 stability result snapshot (2026-02-06)

- Stability pair completed in detached mode (`scheme=stratified_text`) using frozen
  ELLIPSE train/test/splits + reused CV feature store + Gate D drop-3/wcal controls.
- Run dirs:
  - `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_b28c376a73_20260206_185804`
  - `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_16796accd7_20260206_185804`
- CV summary:
  - `b28c376a73`: `val_qwk_mean=0.68537`, `val_adjacent_mean=0.87187`
  - `16796accd7`: `val_qwk_mean=0.67733`, `val_adjacent_mean=0.86067`
- Worst-prompt metric (`min_prompt_n=30`, `cv_val_oof`):
  - `b28c376a73`: `0.48834`
  - `16796accd7`: `0.43720`
- Overfit signal (train-vs-val QWK gap across folds):
  - `b28c376a73`: `0.15331`
  - `16796accd7`: `0.22705`

Decision implication:
- `b28c376a73` remains the stable candidate for promotion.
- `16796accd7` is not stable under split change and should remain rejected.

### Implementation update (2026-02-06)

- Implemented new CLI command:
  - `pdm run essay-scoring-research optuna-sweep`
- Implemented Optuna sweep module:
  - `scripts/ml_training/essay_scoring/optuna_sweep.py`
- Refactored CLI for SRP/maintainability:
  - `scripts/ml_training/essay_scoring/cli.py` is now a thin registration entrypoint.
  - Command ownership moved to bounded modules:
    - `scripts/ml_training/essay_scoring/commands/experiment_commands.py`
    - `scripts/ml_training/essay_scoring/commands/dataset_commands.py`
    - `scripts/ml_training/essay_scoring/commands/cv_commands.py`
    - `scripts/ml_training/essay_scoring/commands/sweep_commands.py`
    - shared helpers: `scripts/ml_training/essay_scoring/commands/common.py`
- CLI contract now supports the planned pilot flags:
  - `--n-trials`
  - `--objective worst_prompt_qwk_then_mean_qwk`
  - `--min-prompt-n`
  - `--bottom-k-prompts`
  - `--baseline-best-run-dir`
- Trial scoring and guardrails implemented:
  - primary objective: worst-prompt QWK (`min_prompt_n`)
  - secondary objective: mean QWK (lexicographic scalarization)
  - tail guardrail rejection relative to baseline best run
- Artifacts implemented per sweep run:
  - `artifacts/optuna_trials.json`
  - `artifacts/selected_params.json`
  - `reports/optuna_summary.md`
  - `progress.json`
- Unit tests added:
  - `scripts/ml_training/essay_scoring/tests/test_optuna_sweep.py`
- Canonical dependency flow executed:
  - `pdm lock -G ml-research`
  - `pdm lock --check`
  - `pdm install -G ml-research`

## Success Criteria

- Optuna sweep runs end-to-end and produces reproducible artifacts.
- The selected configuration matches or improves:
  - prompt-holdout mean QWK, and
  - worst-prompt QWK,
  without worsening tail slices without an explicit tradeoff decision.
- Decision is recorded/linked in:
  `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`

## Related

- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Decision gate:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
- ADR: `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Research notes:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
