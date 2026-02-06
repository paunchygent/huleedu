---
type: decision
id: ADR-0031
status: proposed
created: '2026-02-06'
last_updated: '2026-02-06'
---
# ADR-0031: Essay scoring: experiment optimization dependencies (Optuna, HF training, baselines)

## Status

Proposed (decision gate tracked in
`TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`).

## Context

We are improving the whitebox essay scoring research pipeline with a CV-first workflow:

- Primary selection yardstick: `scheme=prompt_holdout` CV mean±std QWK on ELLIPSE (unseen prompt
  generalization).
- Guardrails: feature-store reuse, tail-slice monitoring, residual diagnostics reporting.

Current state:

- We can improve QWK via tail calibration + grade-band weighting (Gate D), and via XGBoost
  regularization sweeps (Gate E), but we are still far from the target of ~0.85 prompt-holdout
  QWK.
- The current hyperparameter search uses a small fixed grid (`xgb-sweep`). As we iterate, we risk
  either:
  - spending too long on manual grids, or
  - overfitting our choices to a single `splits.json` through excessive search.

We want to decide whether to expand the `ml-research` dependency group with tools that enable:

1) smarter hyperparameter optimization (Optuna),
2) transformer fine-tuning / adversarial prompt-invariance constraints (Hugging Face training stack),
3) stronger diagnostics + alternate baselines (statsmodels, CatBoost).

Non-goals:

- These dependencies must not affect production/offload runtime images. All additions must live in
  `dependency-groups.ml-research` only.

## Decision

Adopt a phased dependency strategy with explicit decision gates.

### 1) Add Optuna (recommended first; small/low-risk)

We intend to add `optuna` to `ml-research` and implement an `optuna-sweep` runner that uses the
existing CV runner.

Selection objective (lexicographic):

- Primary: maximize **worst-prompt QWK** on `cv_val_oof` (with a `min_prompt_n` safeguard), because
  prompt-holdout generalization is the target.
- Secondary: maximize overall CV mean QWK.
- Guardrails: do not materially worsen tail slices (`y_true <= 2.0` and `y_true >= 4.0`) without an
  explicit tradeoff note.

Overfitting-to-splits mitigation:

- Cap trial count (pilot 30–50) and require a stability check under `scheme=stratified_text` for the
  top configs.
- Persist sweep artifacts (definition, trial results, and selected config) for reproducibility.

### 2) Add statsmodels + CatBoost (optional; diagnostic/baseline)

We may add:

- `statsmodels` to support more formal model comparison and slice diagnostics (paired/bootstrap
  comparisons across folds; covariate analyses),
- `catboost` as an alternative GBM baseline on the same feature matrices.

This is optional and should be prioritized only if it improves decision quality (e.g., clarifies
whether observed deltas are noise) or establishes a meaningful baseline.

### 3) Defer HF training stack until a “representation ceiling” gate is met

Adding the Hugging Face training stack (`datasets`, `accelerate`, `evaluate`, `torchmetrics`,
optional `peft`) is a major increase in dependency weight and implementation scope.

We will defer this until after:

- the best current XGBoost params (Gate E) are selected, and
- CV ensembling and prompt-invariance-without-fine-tuning experiments are evaluated (prompt-balanced
  weighting + dropping prompt-sim features).

If still far from target, we proceed with a minimal fine-tuning prototype:

- baseline fine-tuning without invariance,
- then add prompt-invariance constraints (adversarial prompt classifier / gradient reversal or a
  simpler group-robust objective),
- all evaluated under prompt-holdout CV using the existing splits and residual diagnostics.

## Consequences

Pros:

- Faster, more principled search (Optuna) with reproducible artifacts.
- Better decision hygiene (formal comparison tools and alternate baselines).
- A clear escalation path if frozen-embedding + tree models are insufficient.

Cons / risks:

- Search-induced overfitting to fixed splits if trial counts are uncontrolled.
- Heavier dependency footprint (especially HF stack) and longer install times.
- Fine-tuning can overfit quickly on small datasets and may require GPU/Hemma scheduling discipline.

## Related

- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Story hub: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Decision gate task:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
- Optuna task: `TASKS/assessment/essay-scoring-optuna-hyperparameter-optimization-cv-selected.md`
- Fine-tuning task:
  `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md`
- Diagnostics/baselines task:
  `TASKS/assessment/essay-scoring-statsmodels-diagnostics--catboost-baseline.md`
- Review records:
  - `docs/product/reviews/review-transformer-fine-tuning-prompt-invariance-dependencies.md`
  - `docs/product/reviews/review-statsmodels-diagnostics-catboost-baseline-dependencies.md`
- Research notes:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
