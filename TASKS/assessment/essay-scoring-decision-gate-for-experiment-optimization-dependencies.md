---
id: 'essay-scoring-decision-gate-for-experiment-optimization-dependencies'
title: 'essay-scoring: decision gate for experiment optimization dependencies'
type: 'task'
status: 'proposed'
priority: 'high'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-06'
last_updated: '2026-02-06'
related: ['improve-essay-scoring-prediction-power-ellipse-cv-first', 'essay-scoring-xgboost-hyperparameter-sweep-cv-selected', 'essay-scoring-optuna-hyperparameter-optimization-cv-selected', 'essay-scoring-transformer-fine-tuning--prompt-invariance-experiments', 'essay-scoring-statsmodels-diagnostics--catboost-baseline']
labels: []
---
# essay-scoring: decision gate for experiment optimization dependencies

## Objective

Make a CV-first, evidence-backed decision on whether to expand `dependency-groups.ml-research` with:

1) Optuna (smarter hyperparameter optimization than a fixed grid),
2) Hugging Face training stack (transformer fine-tuning + adversarial prompt invariance),
3) statsmodels + CatBoost (formal diagnostics + alt GBM baseline).

The decision must be documented in `ADR-0031` and integrated into the CV-first story workflow.

## Context

- CV-first story hub (current focus): `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- We have a working sweep runner (`xgb-sweep`) and a residual diagnostics report that already slices
  by prompt and tails.
- Adding dependencies increases lockfile churn and install time, so we need to justify the ROI.
- We must avoid search-induced overfitting to the fixed `splits.json` definition (a real risk when
  adding Bayesian optimization / large trial counts).

## Plan

### A) Guardrails (must be explicit before accepting new deps)

- All new dependencies MUST be added to `dependency-groups.ml-research` only (no runtime/offload
  impact).
- CV-first selection discipline remains unchanged:
  - never select on locked test,
  - prompt-holdout CV is the primary yardstick.
- Search-induced overfitting mitigation:
  - strict trial caps (Optuna),
  - stability check under `scheme=stratified_text` for the top configs,
  - record/report worst-prompt and tail-slice behavior (not just global QWK).

### B) Evidence to produce (before “accept”)

1) **Optuna pilot**
   - 30–50 trials, prompt-holdout scheme.
   - Objective: worst-prompt QWK primary, mean QWK secondary, tail slices as guardrails.
   - Output: a sweep report with the selected params + a stability check run.
2) **Diagnostics/baselines pilot**
   - Decide whether `statsmodels` improves decision quality (noise vs signal) enough to justify.
   - Decide whether CatBoost is competitive as a baseline on our existing feature matrices.
3) **HF fine-tuning feasibility check**
   - Confirm the minimum viable training plan and compute plan (Hemma GPU vs local).
   - Confirm evaluation discipline (prompt-holdout CV, residual diagnostics artifacts).
   - Decide whether we proceed now or defer until we hit a “representation ceiling” gate.

### C) Decision + documentation

- Update ADR status + outcome:
  `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Write findings to:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
- Update the CV-first story hub with the decided next steps.

## Success Criteria

- ADR-0031 records a clear decision per option: accept / defer / reject (with rationale).
- The research doc contains concrete, repo-grounded findings (trial caps, expected ROI, risks).
- Exactly one follow-up implementation task is promoted to `in_progress` with explicit acceptance
  criteria.

## Related

- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- ADR: `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Research: `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
- Review records:
  - `docs/product/reviews/review-transformer-fine-tuning-prompt-invariance-dependencies.md`
  - `docs/product/reviews/review-statsmodels-diagnostics-catboost-baseline-dependencies.md`
- Tasks:
  - `TASKS/assessment/essay-scoring-optuna-hyperparameter-optimization-cv-selected.md`
  - `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md`
  - `TASKS/assessment/essay-scoring-statsmodels-diagnostics--catboost-baseline.md`
