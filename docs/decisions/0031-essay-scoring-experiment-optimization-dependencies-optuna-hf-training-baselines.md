---
type: decision
id: ADR-0031
status: accepted
created: '2026-02-06'
last_updated: '2026-02-06'
---
# ADR-0031: Essay scoring: experiment optimization dependencies (Optuna, HF training, baselines)

## Status

Accepted (decision gate tracked in
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

Adopt a phased dependency strategy with explicit decision gates and the following
final decision matrix.

| Dependency track | Decision | Rationale |
|---|---|---|
| Optuna (`optuna`) | Accept | Prompt-holdout pilot + stratified stability pair completed. Stable selected config (`b28c376a73`) held under `scheme=stratified_text` and outperformed near-miss (`16796accd7`) on stability metrics. |
| HF training stack (`datasets`, `accelerate`, `evaluate`, `torchmetrics`, optional `peft`) | Defer | Added implementation/runtime complexity is not yet justified before finishing current CV-first gains with accepted Optuna flow. |
| Diagnostics + alt baseline (`statsmodels`, `catboost`) | Defer | Useful but not required to unblock immediate optimization path; prioritize after Optuna hardening and next gate results. |

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

Evidence (completed):

- Prompt-holdout pilot selected `b28c376a73` with improved worst-prompt robustness.
- Stratified stability pair (`b28c376a73` vs `16796accd7`) confirmed:
  - `b28c376a73`: `val_qwk_mean=0.68537`, train-val QWK gap `0.15331`
  - `16796accd7`: `val_qwk_mean=0.67733`, train-val QWK gap `0.22705`
- Decision: promote Optuna path with `b28c376a73` as stable selected configuration.

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

## Gate G3.1 Execution Log (2026-02-06)

Canonical launcher and wrappers:
- local launcher:
  `pdm run run-local-pdm g3-launch-hemma`
- remote operations:
  `pdm run run-local-pdm run-hemma -- ...`

Observed fail-closed outcomes on Hemma:
- run
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_232914`
  failed with ROCm `AcceleratorError` under `precision=bf16`.
- run
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233408`
  failed with `ValueError: Attempting to unscale FP16 gradients`.

Changes applied during investigation:
- added `peft` to `dependency-groups.ml-research` for LoRA runtime parity,
- hardened launcher preflight with fail-closed `MISSING_MODULE:peft` check,
- adjusted ROCm precision behavior in transformer fine-tuning while diagnosing runtime failures.

Current state:
- run
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233717`
  produced non-finite training (`loss=nan`, `val_mae=nan` in driver log output).
- No gate-valid G3.1 baseline result exists yet under the current ROCm runtime profile.
- Deployed hardening now pins transformer runtime image defaults,
  enforces image/runtime preflight contracts, sets launcher default precision to fp32
  (`none`), and adds non-finite fail-fast guards in training.

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
