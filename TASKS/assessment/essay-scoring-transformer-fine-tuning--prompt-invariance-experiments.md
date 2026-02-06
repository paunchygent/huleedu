---
id: 'essay-scoring-transformer-fine-tuning--prompt-invariance-experiments'
title: 'essay-scoring: transformer fine-tuning + prompt invariance experiments'
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
related: ['improve-essay-scoring-prediction-power-ellipse-cv-first', 'essay-scoring-decision-gate-for-experiment-optimization-dependencies']
labels: []
---
# essay-scoring: transformer fine-tuning + prompt invariance experiments

## Objective

Evaluate whether end-to-end transformer fine-tuning (and explicit prompt-invariance constraints)
can materially improve `scheme=prompt_holdout` CV QWK beyond the frozen-embedding + GBM baseline.

This is an escalation path if we hit a “representation ceiling”.

## Context

- Current pipeline uses frozen embeddings + XGBoost. It can overfit and may rely on topic/prompt
  shortcuts, which harms prompt-holdout generalization.
- Fine-tuning might learn a representation better aligned to the scoring construct, but it is a
  larger implementation and dependency footprint.
- Prompt invariance is the key requirement: naive fine-tuning can make prompt/topic shortcuts worse
  unless we explicitly constrain them.

## Plan

### A) Dependencies (decision-gated)

If accepted in ADR-0031, add to `dependency-groups.ml-research`:
- `datasets`, `accelerate`, `evaluate`, `torchmetrics`
- optional: `peft` (LoRA-style parameter-efficient fine-tuning)

### B) Minimal fine-tuning prototype (CV-first)

Scope: a smallest-possible prototype that still respects CV discipline.

1) Dataset + splits
   - Use the prepared ELLIPSE CSVs + existing `splits.json`.
   - Train/eval under `scheme=prompt_holdout` with identical reporting artifacts (cv_metrics +
     residual diagnostics).
2) Model + objective
   - Start with a single encoder model (DeBERTa-v3 or RoBERTa) with a regression head.
   - Keep the score scale consistent with our half-band evaluation (no label remapping).
3) Baselines
   - Fine-tune without invariance constraints first (to establish a truthful baseline).

### C) Add prompt-invariance constraints (core experiment)

Implement and compare one of:
- Adversarial prompt classifier (gradient reversal): optimize score prediction while making prompt
  identity hard to predict from the representation.
- A simpler group-robust objective: penalize worst-prompt loss (group DRO-like behavior).

### D) Compute + run discipline

- If GPU is needed, run on Hemma with detached execution and write driver logs to
  `output/essay_scoring/<RUN>/` per runbook (`docs/operations/ml-nlp-runbook.md`).
- Ensure reproducibility:
  - fixed seeds,
  - persisted configs/artifacts,
  - no selection on locked test.

## Success Criteria

- We have a minimal fine-tuning baseline with prompt-holdout CV metrics and residual diagnostics.
- We have at least one prompt-invariance variant evaluated apples-to-apples.
- A decision is recorded: proceed (with evidence) or defer/stop (cost/benefit not justified).

## Related

- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- ADR: `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Decision gate:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
- Review record:
  `docs/product/reviews/review-transformer-fine-tuning-prompt-invariance-dependencies.md`
