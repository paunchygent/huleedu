---
id: 'essay-scoring-transformer-fine-tuning--prompt-invariance-experiments'
title: 'essay-scoring: transformer fine-tuning + prompt invariance experiments'
type: 'task'
status: 'in_progress'
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

### Gate G3 Execution Order (strict)

- G3.1 baseline transformer fine-tune (LoRA, no invariance).
- G3.2 prompt-invariance variant (same backbone/hparams; add adversarial prompt head + GRL).
- G3.3 fallback variant (GroupDRO-style worst-prompt penalty) only if G3.2 is unstable or fails
  to meet thresholds.

### Canonical Inputs and Reference

- Reuse frozen ELLIPSE train/test/splits and CV feature-store paths from handoff.
- Reference comparator remains stable XGB config `b28c376a73`:
  - prompt-holdout reference run dir:
    `output/essay_scoring/20260206_105542_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536/variants/20260206_110018_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536_b28c376a73_trial005`
  - stratified stability reference run dir:
    `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_b28c376a73_20260206_185804`

### Mandatory Run Mechanics (no exceptions)

- Detached execution required (`/usr/bin/screen`) with driver log in `output/essay_scoring/`.
- Hemma GPU is mandatory for all transformer fine-tuning runs in this task.
- Hemma GPU profile requirements:
  - mixed precision (`bf16` when supported, otherwise `fp16`),
  - gradient checkpointing enabled,
  - gradient accumulation tuned to an effective batch size in the `32-64` range.
- Dynamic padding + length bucketing required.
- Anti-truncation required: chunk long essays with overlap and pool to essay-level prediction.
- Silent truncation-only runs are invalid for gate acceptance.
- Non-Hemma transformer fine-tuning runs are invalid for gate acceptance.

### Required Telemetry and Artifacts

- Existing CV artifacts must be emitted unchanged:
  - `artifacts/cv_metrics.json`
  - `reports/residual_diagnostics.md`
  - `artifacts/residuals_cv_val_oof.csv` + `.jsonl`
- Add transformer-specific run telemetry artifact:
  - `artifacts/truncation_coverage.json` containing at least:
    - `pct_essays_exceeding_max_length`
    - `avg_tokens_truncated_before_chunking`
    - `avg_chunks_per_essay`
    - `p95_chunks_per_essay`

### Gate Acceptance Thresholds (relative to b28c376a73)

- Prompt-holdout primary (`min_prompt_n=30`, `bottom_k=5`):
  - worst-prompt QWK delta `>= +0.010`
  - mean QWK delta `>= -0.003`
  - low-tail adjacent-accuracy delta `>= -0.010`
  - high-tail adjacent-accuracy delta `>= -0.010`
- Stratified stability:
  - mean QWK delta `>= -0.005`

### Decision Branch

- If thresholds pass: continue transformer track with one constrained tuning round.
- If thresholds fail: record “no justified uplift” and defer/close track with evidence links.

## Frozen Invalid Attempts (Do Not Use for Gate Evidence)

1. CLI boolean contract error (invalid launch):
   - driver log:
     `output/essay_scoring/ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_214141.driver.log`
   - failure: passed positional `true true` values to Typer boolean flags.
2. CPU runtime + tokenizer compatibility crash (invalid launch):
   - driver log:
     `output/essay_scoring/ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_214215.driver.log`
   - run dir:
     `output/essay_scoring/20260206_214222_ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_214215`
   - failures:
     - runtime resolved to `device=cpu` (out-of-contract for G3),
     - tokenizer method mismatch (`DebertaV2Tokenizer` missing `build_inputs_with_special_tokens`).

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

## Gate Unlock (2026-02-06)

This task is promoted after Gate G1 (`statsmodels + CatBoost`) failed the
prompt-holdout primary thresholds while passing only stratified stability.

Unlock evidence:
- prompt-holdout comparison (failed):
  `output/essay_scoring/20260206_190010_ellipse_gate_g1_compare_prompt_holdout_catboost_vs_b28c`
- stratified stability comparison (passed):
  `output/essay_scoring/20260206_190014_ellipse_gate_g1_compare_stratified_catboost_vs_b28c`

## Validation Snapshot (2026-02-06)

- Reviewed transformer loop semantics against current upstream docs for:
  - `/huggingface/transformers` (sequence-classification fine-tune loop expectations)
  - `/pytorch/pytorch` (AMP/autocast/GradScaler modern API)
- Modernized AMP usage in
  `scripts/ml_training/essay_scoring/transformer_finetune.py`:
  - `torch.cuda.amp.GradScaler` -> `torch.amp.GradScaler("cuda", ...)`
  - `torch.autocast` -> `torch.amp.autocast`
- Added deterministic module tests in
  `scripts/ml_training/essay_scoring/tests/test_transformer_finetune.py` for:
  - chunk span generation,
  - truncation coverage telemetry,
  - precision runtime selection,
  - finetune config validation guards.
- Validation + tests executed from repo root via `./scripts/dev-shell.sh`:
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`
  - `pdm run pytest-root scripts/ml_training/essay_scoring/tests -q`
- Result: all checks passed (`46 passed`).
