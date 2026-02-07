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
  - precision mode must be explicit and recorded in run artifacts/logs,
  - current evidence marks ROCm mixed-precision paths as unstable on this runtime,
  - gate runs must use a precision mode with finite training metrics,
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

## Launcher Hardening Snapshot (2026-02-06, Verified)

- Canonical Gate G3 launcher path kept as:
  - `pdm run g3-launch-hemma` (single execution path, fail-closed).
- Launcher robustness fixes applied in
  `scripts/ml_training/essay_scoring/g3_launch_hemma.py`:
  - fixed/standardized canonical Hemma repo root to
    `/home/paunchygent/apps/huleedu`,
  - deterministic preflight CLI contract check via
    `NO_COLOR=1 COLUMNS=240 ... transformer-finetune --help`,
  - detached command launch refactored to Bash array + `printf '%q'`
    to avoid nested shell expansion bugs around run-name injection,
  - explicit fail-fast rejection of typo root
    `/home/paunchygent/apps/huledu` before remote execution.
- Regression tests updated and executed at
  `scripts/ml_training/essay_scoring/tests/test_g3_launch_hemma.py`
  to prevent these failures from reappearing.
- Remote execution wrapper `scripts/run-hemma.sh` fixed and verified:
  - deterministic parsing for `--` and `--shell`,
  - safe remote argv transport for quoted/space-containing arguments.

## Gate G3.1 Execution Evidence (2026-02-06)

Fail-closed canonical launcher used for all attempts:
- `pdm run run-local-pdm g3-launch-hemma`

Attempt A (after peft dependency fix):
- run name:
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_232914`
- run dir:
  `output/essay_scoring/20260206_232921_ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_232914`
- driver log:
  `output/essay_scoring/ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_232914.driver.log`
- status:
  `failed` (`error_type=AcceleratorError`, `HIP error: unspecified launch failure`) while running `precision=bf16`.

Attempt B (ROCm auto precision fallback to fp16):
- run name:
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233408`
- run dir:
  `output/essay_scoring/20260206_233415_ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233408`
- driver log:
  `output/essay_scoring/ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233408.driver.log`
- status:
  `failed` (`error_type=ValueError`, `Attempting to unscale FP16 gradients.`).

Attempt C (ROCm fp16 + no GradScaler):
- run name:
  `ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233717`
- run dir:
  `output/essay_scoring/20260206_233723_ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233717`
- driver log:
  `output/essay_scoring/ellipse_gate_g3_1_transformer_lora_prompt_holdout_20260206_233717.driver.log`
- status:
  numerically unstable (`loss=nan`, `val_qwk=0.00000`, `val_mae=nan` in log output).
  This run is excluded from gate acceptance evidence.

## Hardening Update (2026-02-07)

- Launcher/runtime contract hardening implemented locally:
  - `g3-launch-hemma` default precision changed to `none` (fp32 fail-safe),
  - preflight now requires approved transformer base-image marker and validates
    HIP/Torch/Python runtime version prefixes,
  - preflight now runs a finite-value precision canary before detached launch.
- Training-loop hardening implemented locally:
  - fail fast on non-finite training loss,
  - fail fast on non-finite logits/labels/aggregated predictions.
- Transformer training runtime image defaults pinned locally to:
  `rocm/pytorch:rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.9.1`.
- Local validation status:
  - `pdm run run-local-pdm format-all` passed,
  - `pdm run run-local-pdm lint-fix --unsafe-fixes` passed,
  - `pdm run run-local-pdm typecheck-all` passed,
  - `pdm run run-local-pdm pytest-root scripts/ml_training/essay_scoring/tests/test_g3_launch_hemma.py -q` passed,
  - `pdm run run-local-pdm pytest-root scripts/ml_training/essay_scoring/tests/test_transformer_finetune.py -q` passed.
- Hemma sync/redeploy completed sequentially:
  - `pdm run run-local-pdm run-hemma -- git pull --ff-only origin main`,
  - `pdm run run-local-pdm run-hemma -- sudo docker compose ... --profile research-transformer-train up -d --build essay_transformer_train`.
