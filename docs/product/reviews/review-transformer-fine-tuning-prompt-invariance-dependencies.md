---
type: review
id: REV-transformer-fine-tuning-prompt-invariance-dependencies
title: 'Review: essay scoring transformer fine tuning and prompt invariance dependencies'
status: pending
created: '2026-02-06'
last_updated: '2026-02-06'
story: essay-scoring-transformer-fine-tuning--prompt-invariance-experiments
reviewer: agents
---
# Review: essay scoring transformer fine tuning and prompt invariance dependencies

## TL;DR

Track a formal review gate before adding the Hugging Face training stack and starting
fine-tuning work. Keep decision criteria tied to prompt-holdout CV performance and
worst-prompt slice behavior.

## Problem Statement

The project needs to decide whether a heavier training stack (`datasets`,
`accelerate`, `evaluate`, `torchmetrics`, optional `peft`) is justified now. This is
high potential, but it also carries implementation complexity and overfitting risk on
ELLIPSE if we skip strict invariance and CV-first discipline.

## Proposed Solution

Use a staged review:

- Define a minimal fine-tuning baseline that reuses current ELLIPSE prepared CSVs and
  `splits.json`.
- Require apples-to-apples comparison against the best current XGBoost configuration
  under `scheme=prompt_holdout`.
- Add one explicit invariance variant (adversarial prompt classifier or group-robust
  worst-prompt penalty) and compare with residual diagnostics.

## Scope

- In scope:
  - dependency decision for HF training stack in `ml-research`,
  - minimal experiment design and acceptance criteria,
  - evidence checklist for accept/defer decision.
- Out of scope:
  - full productionization of fine-tuning,
  - replacing existing CV reporting artifacts.

## Risks / Unknowns

- Search/training overfit on fixed splits if trial/epoch budgets are not capped.
- Prompt leakage via representation shortcuts if invariance constraints are weak.
- Compute and reproducibility complexity (GPU scheduling, deterministic seeds, artifact
  completeness).

## Verdict

**Reviewer:** `agents`
**Date:** `2026-02-06`

### Decision Checklist

- [ ] Baseline fine-tuning run completed with prompt-holdout CV + residual diagnostics.
- [ ] Invariance variant run completed with same splits and comparable artifacts.
- [ ] Worst-prompt slices and mean QWK reviewed against current XGB baseline.
- [ ] Recommendation recorded in ADR-0031 and dependency research doc.

**Status:** `pending`

### Execution Evidence (2026-02-06)

- Attempt
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_232914`
  failed on ROCm with `AcceleratorError` under bf16.
- Attempt
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233408`
  failed on ROCm fp16 with `ValueError: Attempting to unscale FP16 gradients`.
- Stabilization changes shipped:
  - LoRA runtime dependency parity (`peft`) in `ml-research`,
  - fail-closed launcher preflight module check for `peft`,
  - ROCm precision policy adjusted to fp16 without grad scaling for `auto`.
- Current baseline run:
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233717`
  is running detached on Hemma; final artifact review is pending completion.

## Links

- Story:
  `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md`
- Hub:
  `docs/reference/ref-essay-scoring-research-hub.md`
- Decision gate:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
- ADR:
  `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Research:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
