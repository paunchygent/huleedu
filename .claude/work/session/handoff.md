# HANDOFF: Active Session Context

## Purpose

This file contains only active, next-action context.
Detailed implementation history belongs in:

- `TASKS/` (task plans and status)
- `docs/reference/ref-essay-scoring-research-hub.md` (workstream navigation)
- `docs/operations/ml-nlp-runbook.md` (canonical run commands)
- `output/essay_scoring/` (experiment evidence)

## Current Focus (2026-02-06)

### Whitebox essay scoring: CV-first optimization decision gate

Active tasks:
- `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md` (`status: in_progress`)

Recently completed:
- `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md` (`status: done`; ADR-0031 accepted)
- `TASKS/assessment/essay-scoring-optuna-hyperparameter-optimization-cv-selected.md` (`status: done`)
- `TASKS/assessment/essay-scoring-statsmodels-diagnostics--catboost-baseline.md` (`status: done`; Gate G1 prompt-holdout failed)

Deferred follow-up track (gate-locked):
- None (transformer task promoted after Gate G1 failure)

Gate G1 strict order (completed):
1. CatBoost prompt-holdout CV completed:
   - run dir: `output/essay_scoring/20260206_185135_ellipse_gate_g1_catboost_prompt_holdout_20260206_195132`
2. CatBoost stratified-text CV completed:
   - run dir: `output/essay_scoring/20260206_185436_ellipse_gate_g1_catboost_stratified_20260206_195431`
3. Paired comparison reports completed:
   - prompt-holdout: `output/essay_scoring/20260206_190010_ellipse_gate_g1_compare_prompt_holdout_catboost_vs_b28c`
   - stratified-text: `output/essay_scoring/20260206_190014_ellipse_gate_g1_compare_stratified_catboost_vs_b28c`
4. Gate result:
   - prompt-holdout **failed** (worst-prompt and both tail guardrails regressed)
   - stratified-text **passed** (mean QWK within tolerance)
   - escalation rule triggered: transformer prompt-invariance track promoted.

### Transformer Gate G3 (active canonical contract)

Frozen inputs (must be reused):
- Train CSV:
  `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
- Test CSV:
  `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
- Splits JSON:
  `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
- Reused CV feature store:
  `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store`

Stable comparator (fixed):
- Config id: `b28c376a73`
- Prompt-holdout reference run:
  `output/essay_scoring/20260206_105542_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536/variants/20260206_110018_ellipse_optuna_pilot_prompt_holdout_drop3_wcal_20260206_115536_b28c376a73_trial005`
- Stratified stability reference run:
  `output/essay_scoring/20260206_175815_ellipse_optuna_stability_stratified_b28c376a73_20260206_185804`

Strict execution order:
- `G3.1`: LoRA baseline transformer fine-tune (no invariance).
- `G3.2`: prompt-invariance variant (same backbone/hparams; adversarial prompt head + GRL).
- `G3.3`: GroupDRO-style worst-prompt objective only if `G3.2` is unstable or fails thresholds.

Mandatory mechanics:
- Run detached via `/usr/bin/screen` and persist driver log under `output/essay_scoring/`.
- Transformer fine-tuning must run on Hemma GPU; local fine-tuning runs are out-of-contract.
- Use dynamic padding + length bucketing.
- Use anti-truncation chunking with overlap and essay-level pooling.
- Truncation-only runs are invalid for gate acceptance.
- Hemma GPU profile requirements:
  - mixed precision `bf16` when supported (fallback `fp16`),
  - gradient checkpointing enabled,
  - gradient accumulation for effective batch size `32-64`.

Acceptance thresholds (relative to `b28c376a73`):
- Prompt-holdout (`min_prompt_n=30`, `bottom_k=5`):
  - worst-prompt QWK delta `>= +0.010`
  - mean QWK delta `>= -0.003`
  - low-tail adjacent-accuracy delta `>= -0.010`
  - high-tail adjacent-accuracy delta `>= -0.010`
- Stratified stability:
  - mean QWK delta `>= -0.005`

Required artifacts and decision outputs:
- `artifacts/cv_metrics.json`
- `reports/residual_diagnostics.md`
- `artifacts/residuals_cv_val_oof.csv` + `.jsonl`
- `artifacts/truncation_coverage.json` with:
  - `pct_essays_exceeding_max_length`
  - `avg_tokens_truncated_before_chunking`
  - `avg_chunks_per_essay`
  - `p95_chunks_per_essay`
- Record outcome in:
  - `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md`
  - `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
  - `docs/product/reviews/review-transformer-fine-tuning-prompt-invariance-dependencies.md`

Historical Optuna/CatBoost execution detail is retained in task/ADR/research artifacts and is not
duplicated in this handoff.

## Recently Completed (Compressed)

### Optuna sweep command and artifact contract ✅ COMPLETED
- Landed `optuna-sweep` CLI and sweep runner with trial artifacts, selected-params output, summary report, and progress tracking.
- Paths: `scripts/ml_training/essay_scoring/optuna_sweep.py`, `scripts/ml_training/essay_scoring/commands/sweep_commands.py`.

### Essay-scoring CLI SRP refactor ✅ COMPLETED
- Replaced 1000+ LoC monolithic CLI with command modules under `scripts/ml_training/essay_scoring/commands/`.
- Root `scripts/ml_training/essay_scoring/cli.py` is now composition-only.

### Workstream topology contract (docs-as-code) ✅ COMPLETED
- Added manifest + scaffold + renderer + validator for hub topology.
- Paths: `scripts/docs_mgmt/workstream_topology_manifest.py`, `scripts/docs_mgmt/workstream_topology_scaffold.py`, `scripts/docs_mgmt/render_workstream_hubs.py`, `scripts/docs_mgmt/validate_workstream_topology.py`.

### AGENTS.md surgical compaction ✅ COMPLETED
- Reduced duplication and moved stable detail to rules/runbooks/skills while preserving core workflow behavior.

## Notes

- Completed execution logs, one-off shell transcripts, and historical run narration were intentionally removed from this handoff and are considered superseded by code, runbook contracts, and run artifacts.
