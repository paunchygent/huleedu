---
type: research
id: RES-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines
title: 'Essay scoring: dependency decision research (Optuna, HF fine-tuning, baselines)'
status: active
created: '2026-02-06'
last_updated: '2026-02-06'
---
# Essay scoring: dependency decision research (Optuna, HF fine-tuning, baselines)

## Question

What is the minimum dependency expansion that materially improves:

- iteration speed (less manual grid management),
- decision quality (avoid "noise wins" and CV leakage),
- prompt-holdout generalization (prompt-invariant construct learning),

…without destabilizing the repo (install times, lockfile churn) or confusing the CV-first workflow?

## Findings

### Current decision context (as of 2026-02-06)

- CV-first story hub: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Gate D (tail bias mitigation) is implemented and improved prompt-holdout CV QWK materially.
- Gate E (XGBoost sweep) exists and produces a ranked sweep report.

### Option 1: Optuna

Why it might help:
- We currently use a fixed grid. Optuna can spend trials where the metric improves and stop early
  (pruning).
- We can optimize for the metric we actually care about: prompt-holdout generalization (e.g.
  worst-prompt QWK).

Risks / unknowns:
- Search-induced overfitting to a single `splits.json` if we run too many trials.
- Objective definition: worst-prompt QWK must be computed consistently with a `min_prompt_n`
  safeguard and should be based on OOF (`cv_val_oof`) only.

Mitigations:
- Strict trial caps (pilot 30–50).
- Require a stability check on `scheme=stratified_text` for top configurations.
- Persist all trial artifacts + selected params.

### Option 2: HF fine-tuning stack (+ prompt invariance)

Why it might help:
- Frozen embeddings + tree models may hit a representation ceiling on prompt-holdout, especially
  when essays exceed the encoder max length (truncation) or when the model needs to learn
  prompt-invariant representations.

Risks / unknowns:
- Implementation scope is large (dataset builders, training loops, GPU scheduling, reproducibility).
- ELLIPSE is comparatively small; naive fine-tuning can overfit quickly and amplify prompt/topic
  shortcuts unless we add explicit invariance constraints.

Mitigations:
- Gate it behind "best current" XGB (Gate E) + ensembling + prompt invariance without fine-tuning.
- Prefer parameter-efficient fine-tuning (LoRA via `peft`) if we proceed.
- Keep evaluation CV-first and prompt-holdout-first (reuse splits + residual diagnostics).

### Option 3: statsmodels + CatBoost

Why it might help:
- statsmodels can formalize comparisons (paired tests / bootstrap summaries) to avoid chasing noise.
- CatBoost provides a strong alternative GBM baseline (often competitive with XGBoost) and can act as
  a sanity check.

Risks / unknowns:
- Extra deps without direct QWK uplift; might be “nice to have” rather than “must have”.
- CatBoost adds binary wheels and may increase install/lock complexity.

## Decision / Next Steps

Decision tracking:
- ADR: `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Decision gate task:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`

Proposed next steps (ordered by ROI):
1) Run an Optuna pilot with strict trial caps and a worst-prompt-first objective.
2) If Optuna proves useful, adopt it and make it the default for future XGB sweeps.
3) Add statsmodels/CatBoost only if it improves decision reliability or baseline confidence.
4) Defer HF fine-tuning until we can justify it with a representation ceiling / target gap analysis.
