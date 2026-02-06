---
id: 'essay-scoring-optuna-hyperparameter-optimization-cv-selected'
title: 'essay-scoring: Optuna hyperparameter optimization (CV-selected)'
type: 'task'
status: 'proposed'
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
