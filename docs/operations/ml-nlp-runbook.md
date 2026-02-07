---
type: runbook
service: global
severity: medium
last_reviewed: '2026-02-06'
---
# ML/NLP Research Runbook (Essay Scoring)

## Purpose

Canonical reference for **whitebox essay scoring research** runs:
- dataset choices and trust policy
- stable train/test + CV split methodology
- Hemma offload prerequisites
- experiment logging conventions (reproducible, leak-safe)

Start here for the full navigation chain (runbook → epic → story hubs → tasks → artifacts):
- `docs/reference/ref-essay-scoring-research-hub.md`

## Canonical dataset policy

### Canonical (current)

- **ELLIPSE train/test** (Overall target) in `data/ELLIPSE_TRAIN_TEST/`
- Standard filters for research comparability:
  - word window: **200–1000 words** (inclusive)
  - drop **letter-dominated prompts** (prompt-level exclusions; do not “detect letters” per essay)
    - configured by `ExperimentConfig.ellipse_excluded_prompts` in `scripts/ml_training/essay_scoring/config.py`

### Construct scope (do not ignore)

This research targets **L2 English discourse essay writing ability** (argumentative/discussion
essays). Do not mix in other communication genres (letters, narratives, creative writing, etc.)
unless you can explicitly filter/tag them and justify the scope change.

For ELLIPSE we approximate this scope via:
- prompt-level exclusions for letter-dominated prompts
- the 200–1000 word window

When the Swedish essay database becomes available, prompt-specific evaluation and explicit genre
scope enforcement should become first-class (dataset-driven, not “best guess”).

### Blocked (do not use for claims)

- **IELTS dataset** in `data/cefr_ielts_datasets/ielts_writing_dataset.csv` is **blocked** until the source and licensing are validated.
  - Allowed use: local smoke tests only (no reported metrics, no decisions based on results).

## Gold-standard experiment workflow (ELLIPSE, Overall)

### 0) Prereqs

Install ML research deps:
```bash
pdm install -G ml-research
```

If using Hemma offload (recommended on macOS to avoid local torch/transformers crashes):
```bash
~/bin/hemma-huleedu-tunnel status
curl -fsS http://127.0.0.1:18085/healthz
curl -fsS http://127.0.0.1:19000/healthz
```

Long runs: run from a real terminal session (not inside an agent tool runner).

If you need “detached” execution on macOS, prefer `screen` so the process survives terminal/tool
session teardown:
```bash
RUN_NAME=ellipse_full_hemma_$(date +%Y%m%d_%H%M%S)
LOG=output/essay_scoring/${RUN_NAME}.driver.log
mkdir -p output/essay_scoring
/usr/bin/screen -S "essay_scoring_${RUN_NAME}" -dm /bin/bash -lc \
  "cd \"$(pwd)\" && set -a && source .env && set +a && PYTHONUNBUFFERED=1 \
   pdm run essay-scoring-research run --dataset-kind ellipse --feature-set combined \
     --backend hemma --offload-service-url http://127.0.0.1:19000 \
     --skip-shap --skip-grade-scale-report --run-name \"${RUN_NAME}\" 2>&1 \
   | tee -a \"${LOG}\""
tail -f "$LOG"
```

### Gate G3 transformer fine-tuning (Hemma GPU; local orchestrator)

For Gate G3 runs, CPU fallback is invalid. Run transformer fine-tuning inside the dedicated Hemma
GPU training service (`essay_transformer_train`) and keep local machine as the orchestrator.

Start the training runtime on Hemma:
```bash
pdm run run-hemma -- sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-transformer-train up -d --build essay_transformer_train
```

Canonical launch command (local orchestrator; fail-closed preflight + detached launch):
```bash
pdm run run-local-pdm g3-launch-hemma
```

Dry-run (prints exact remote preflight/launch scripts without executing):
```bash
pdm run run-local-pdm essay-scoring-research g3-launch-hemma --dry-run
```

The canonical launcher validates, then launches:
- remote repo root and frozen input paths exist,
- `huleedu_essay_transformer_train` container is running,
- training image declares an approved ROCm base-image label
  (`org.huleedu.transformer_train.base_image`),
- ROCm/PyTorch/Python runtime versions match the approved contract in preflight,
- a short in-container precision canary completes with finite values before detached launch,
- `transformer-finetune` CLI contract includes `--chunk-overlap-tokens` and `--require-gpu`,
- no stale detached screen session matches the G3 run prefix.

Default G3 launcher precision is fail-safe (`--mixed-precision none`). Any AMP mode
(`bf16`, `fp16`, `auto`) should be treated as explicit opt-in and validated with run evidence.

Persistent tunnel setup lives in:
- `docs/operations/hemma-alpha-rollout-days-1-3.md`

### 1) Prepare dataset artifacts + integrity report

```bash
pdm run essay-scoring-research prepare-dataset \
  --dataset-kind ellipse \
  --min-words 200 \
  --max-words 1000 \
  --run-name ellipse_prep_200_1000
```

Outputs:
- prepared CSVs under `output/essay_scoring/<RUN>/artifacts/datasets/`
- dataset integrity report under `output/essay_scoring/<RUN>/reports/`

### 2) Generate reusable split definitions (CV + prompt holdout)

```bash
pdm run essay-scoring-research make-splits \
  --dataset-kind ellipse \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --min-words 200 \
  --max-words 1000 \
  --n-splits 5 \
  --run-name ellipse_splits_200_1000
```

Outputs:
- `output/essay_scoring/<RUN>/artifacts/splits.json`
- `output/essay_scoring/<RUN>/reports/splits_report.md`

Split schemes:
- `stratified_text`: stratified by Overall, grouped by essay hash (leakage guard)
- `prompt_holdout`: prompt-grouped folds (unseen-prompt generalization)

### 3) Run CV (feature-set=combined) against Hemma offload

```bash
pdm run essay-scoring-research cv \
  --dataset-kind ellipse \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme stratified_text \
  --feature-set combined \
  --language-tool-service-url http://127.0.0.1:18085 \
  --embedding-service-url http://127.0.0.1:19000 \
  --run-name ellipse_cv_combined_stratified_text
```

Outputs:
- `output/essay_scoring/<RUN>/reports/cv_report.md`
- `output/essay_scoring/<RUN>/reports/residual_diagnostics.md` (by prompt, grade band, covariates)
- `output/essay_scoring/<RUN>/artifacts/cv_metrics.json`
- `output/essay_scoring/<RUN>/artifacts/residuals_cv_val_oof.csv` + `.jsonl`
- `output/essay_scoring/<RUN>/artifacts/residuals_locked_test.csv` + `.jsonl`
- `output/essay_scoring/<RUN>/cv_feature_store/` (reusable across sweeps)

Optional (objective experiments):
- `--training-mode regression` (default)
- `--training-mode ordinal_multiclass_expected` (train `multi:softprob`, decode via expected value)
- `--training-mode ordinal_multiclass_argmax` (train `multi:softprob`, decode via argmax band)

### Reuse extracted features for fast sweeps

```bash
pdm run essay-scoring-research cv \
  --dataset-kind ellipse \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme stratified_text \
  --feature-set combined \
  --reuse-cv-feature-store-dir output/essay_scoring/<CV_RUN>/cv_feature_store
```

### XGBoost hyperparameter sweep (Gate E)

When Gate D is locked, prefer `xgb-sweep` over ad-hoc manual loops. It reuses the CV feature store,
records tail slices, and writes a single sweep summary table.

Example (prompt-holdout; combined; drop-3; weighting+calibration):

```bash
pdm run essay-scoring-research xgb-sweep \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme prompt_holdout \
  --feature-set combined \
  --training-mode regression \
  --grade-band-weighting sqrt_inv_freq \
  --grade-band-weight-cap 3.0 \
  --prediction-mapping qwk_cutpoints_lfo \
  --predictor-handcrafted-drop has_conclusion \
  --predictor-handcrafted-drop clause_count \
  --predictor-handcrafted-drop flesch_kincaid \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --reuse-cv-feature-store-dir output/essay_scoring/<BASELINE_CV_RUN>/cv_feature_store \
  --run-name ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_weighting_calibration
```

Outputs:
- `output/essay_scoring/<SWEEP>/reports/sweep_summary.md` (sorted by high-tail adjacent accuracy, then mean QWK)
- `output/essay_scoring/<SWEEP>/artifacts/sweep_results.json` (incremental; safe to monitor)
- `output/essay_scoring/<SWEEP>/progress.json`
- Per-configuration CV runs under `output/essay_scoring/<SWEEP>/variants/`

### Optuna sweep pilot (decision gate)

Use `optuna-sweep` when you want trial-budgeted optimization with explicit prompt/tail guardrails.

Example (prompt-holdout; combined; drop-3; weighting+calibration; frozen ELLIPSE inputs):

```bash
pdm run essay-scoring-research optuna-sweep \
  --scheme prompt_holdout \
  --feature-set combined \
  --training-mode regression \
  --grade-band-weighting sqrt_inv_freq \
  --grade-band-weight-cap 3.0 \
  --prediction-mapping qwk_cutpoints_lfo \
  --predictor-handcrafted-drop has_conclusion \
  --predictor-handcrafted-drop clause_count \
  --predictor-handcrafted-drop flesch_kincaid \
  --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json \
  --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store \
  --n-trials 40 \
  --objective worst_prompt_qwk_then_mean_qwk \
  --min-prompt-n 30 \
  --bottom-k-prompts 5 \
  --baseline-best-run-dir output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d \
  --run-name ellipse_optuna_pilot_prompt_holdout_drop3_wcal
```

Outputs:
- `output/essay_scoring/<SWEEP>/artifacts/optuna_trials.json`
- `output/essay_scoring/<SWEEP>/artifacts/selected_params.json`
- `output/essay_scoring/<SWEEP>/reports/optuna_summary.md`
- `output/essay_scoring/<SWEEP>/progress.json`
- Per-trial CV runs under `output/essay_scoring/<SWEEP>/variants/`

### Paired gate comparison (fold-paired + bootstrap CI)

Compare candidate vs reference CV runs with paired-fold bootstrap CIs and strict thresholds:

```bash
pdm run essay-scoring-research compare-cv-runs \
  --reference-run-dir output/essay_scoring/<REFERENCE_XGB_RUN_DIR> \
  --candidate-run-dir output/essay_scoring/<CANDIDATE_XGB_RUN_DIR> \
  --gate-profile prompt_holdout_primary \
  --min-prompt-n 30 \
  --bottom-k-prompts 5
```

Outputs:
- `output/essay_scoring/<COMPARE_RUN>/artifacts/cv_comparison.json`
- `output/essay_scoring/<COMPARE_RUN>/reports/cv_comparison.md`

### CV ensembling (Gate F)

CV supports simple seed ensembling per fold:
- Flag: `--ensemble-size <N>` (default: `1`)
- Behavior: trains N XGBoost models per fold (different random seeds), averages raw predictions, then runs the
  usual rounding/mapping + residual diagnostics.

Important selection note:
- Do not accept global QWK gains that worsen tail slices unless you explicitly decide to trade them off.

Example (prompt-holdout; combined; drop-3; weighting+calibration; feature-store reuse):

```bash
pdm run essay-scoring-research cv \
  --dataset-kind ellipse \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme prompt_holdout \
  --feature-set combined \
  --ensemble-size 5 \
  --reuse-cv-feature-store-dir output/essay_scoring/<BASELINE_CV_RUN>/cv_feature_store \
  --grade-band-weighting sqrt_inv_freq \
  --grade-band-weight-cap 3.0 \
  --prediction-mapping qwk_cutpoints_lfo \
  --predictor-handcrafted-drop has_conclusion \
  --predictor-handcrafted-drop clause_count \
  --predictor-handcrafted-drop flesch_kincaid \
  --run-name ellipse_gate_f_cv_ensemble5_prompt_holdout
```

Decision (2026-02-05, ELLIPSE CV-first):
- On the current best baseline (prompt_holdout, drop-3, weighting+calibration, best XGB params),
  `ensemble_size>1` increased mean QWK but degraded **high-tail adjacent accuracy** (`y_true>=4.0`).
  Keep `ensemble_size=1` as best-current until tail behavior is improved via other levers.

### 4) Drop-column importance (feature selection, handcrafted features)

Drop-column importance answers: “does this handcrafted feature add signal beyond everything else?”.

```bash
pdm run essay-scoring-research drop-column \
  --dataset-kind ellipse \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme stratified_text \
  --feature-set combined \
  --language-tool-service-url http://127.0.0.1:18085 \
  --embedding-service-url http://127.0.0.1:19000 \
  --reuse-cv-feature-store-dir output/essay_scoring/<CV_RUN>/cv_feature_store \
  --run-name ellipse_drop_column_combined_stratified_text
```

Outputs:
- `output/essay_scoring/<RUN>/artifacts/drop_column_importance.json`
- `output/essay_scoring/<RUN>/reports/drop_column_importance.md`

Decision heuristic (starting point; tune after you see results):
- Keep if mean ΔQWK > 0 and stability ≥ 0.8 (helps in ≥80% of folds).
- Drop if mean ΔQWK ≤ 0 or stability is low (likely noisy / redundant).

### 5) CV-first follow-ups (post Gate C baseline)

After you have a prompt-holdout CV run with residual diagnostics (`reports/residual_diagnostics.md`),
use the story hub to pick the next lever (avoid ad-hoc tuning):
- Story hub: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`

Recommended next tasks (in order):
1) Validate a pruned handcrafted predictor subset under prompt-holdout (Gate B → prompt generalization):
   - `TASKS/assessment/essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout.md`
2) Address grade compression / tail bias before heavy sweeps (Gate D, slice-aware):
   - `TASKS/assessment/essay-scoring-tail-calibration--grade-band-imbalance-mitigation.md`
3) Only then move to objective variants / hyperparam sweeps / ensembling:
   - `TASKS/assessment/essay-scoring-ordinal-custom-objective-experiments-qwk.md`
   - `TASKS/assessment/essay-scoring-xgboost-hyperparameter-sweep-cv-selected.md`
   - `TASKS/assessment/essay-scoring-cv-ensembling-ellipse-cv-first.md`

Example: prompt-holdout CV with a pruned handcrafted predictor denylist (embeddings always kept):

```bash
pdm run essay-scoring-research cv \
  --dataset-kind ellipse \
  --ellipse-train-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_train_prepared.csv \
  --ellipse-test-path output/essay_scoring/<PREP_RUN>/artifacts/datasets/ellipse_test_prepared.csv \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme prompt_holdout \
  --feature-set combined \
  --reuse-cv-feature-store-dir output/essay_scoring/<BASELINE_CV_RUN>/cv_feature_store \
  --predictor-handcrafted-drop has_conclusion \
  --predictor-handcrafted-drop clause_count \
  --predictor-handcrafted-drop flesch_kincaid \
  --run-name ellipse_cv_combined_prompt_holdout_pruned_handcrafted
```

Note: `--predictor-handcrafted-keep <feature_name>` also exists for “strong keep only” experiments,
but the denylist tends to be more ergonomic when you are only dropping a small number of features.

Selection artifacts:
- `output/essay_scoring/<RUN>/artifacts/predictor_feature_selection.json`
- `output/essay_scoring/<RUN>/artifacts/cv_metrics.json` includes `predictor_feature_selection`
- `output/essay_scoring/<RUN>/reports/cv_report.md` includes predictor selection summary lines

## Observability

Each run directory contains:
- `run.log` (INFO-level, full stage + progress logs)
- `status.json` (single file updated at stage start/complete with a UTC timestamp)
- `progress.json` (single file updated during long stages with **substage** processed/total + ETA)
- `stderr.log` (captured stderr for the run; includes Python tracebacks and tool warnings)
- `fault.log` (faulthandler output: segfault traces + periodic hang stack dumps)

### Monitor progress without log tailing

For runs started after `progress.json` was added, prefer monitoring this file instead of parsing logs:

```bash
RUN_DIR=output/essay_scoring/<RUN>/
cat "${RUN_DIR}/progress.json"
```

If you have `jq` installed:
```bash
cat "${RUN_DIR}/progress.json" | jq
```

Important:
- `fault.log` is not “a crash file” by default: the research runner enables periodic
  stack dumps (every 10 minutes). Lines like `Timeout (0:10:00)!` can be normal when
  a stage is slow (it is a thread snapshot, not a failure).

Tier logging notes:
- Tier 1 logs per-item progress and whether it is running with local vs tunneled LanguageTool.
- Tier 2 logs:
  - **stage1** parse/syntactic progress (pre-embeddings; this was previously a common “silent gap”)
  - **stage2** unique-text collection progress (builds the deduped embed batch)
  - embedding start/complete + per-100 progress in stage3
- Tier 3 logs per-item progress.

## Caching + performance notes

### LanguageTool (Tier 1 error counts)

- When `--language-tool-service-url` is set, the client uses a **Mac-side disk cache**:
  - `output/essay_scoring/.cache/offload_language_tool/`
- Each cache entry stores:
  - `derived_counts` (grammar/spelling/punctuation)
  - full `response` (raw errors) for later analysis
- Cache key includes:
  - language, normalized text (whitespace-normalized), LanguageTool base URL
  - request timeout + request options payload
- Tier 1 error features are computed as **densities per 100 words** (word tokens; punctuation excluded).

### Embeddings offload (Tier 2)

- When `--embedding-service-url` is set, Tier 2 embeddings are offloaded to Hemma (no local torch).
- Hemma-side batching is controlled by:
  - `OFFLOAD_EMBEDDING_BATCH_SIZE` in `docker-compose.hemma.research.yml`
    - default: `32`

### Offload performance metrics (GPU + latency tuning)

Each run that performs feature extraction writes:
- `output/essay_scoring/<RUN>/artifacts/offload_metrics.json`

This file is the canonical source for throughput + stability tuning:
- `benchmarks[].essays_per_second` (headline metric)
- per-service request latency:
  - For Hemma `--backend hemma` runs (single-tunnel `/v1/extract`), use
    `offload.extract.requests.latency_s` (p50/p95/p99).
  - `offload.embedding.requests.*` and `offload.language_tool.requests.*` may be zero in this
    mode because the client is not calling the legacy `/v1/embed` or LanguageTool directly.
- cache effectiveness: `offload.*.cache.hit_rate`
- error budgets: `requests_timeout`, `requests_http_error`, `requests_connection_error`

Hemma-side metrics:
- The offload server exposes a Prometheus-style endpoint with **GPU memory + request latency**:
  - `curl -fsS http://127.0.0.1:19000/metrics | head`

Best-practice tuning loop:
- tune **one knob at a time** (batch size, payload chunking, concurrency)
- run the same benchmark 3× and compare medians
- stop when p95 latency or error rate rises faster than essays/sec improves

## Experiment log (append-only)

Add a new entry for every run you care about comparing:
- command (exact)
- dataset + filters (200–1000 words, excluded prompts list)
- split scheme + splits.json path
- offload URLs + tunnel status
- metrics summary (mean±std QWK for CV) + output dir

### Template

```text
YYYY-MM-DD: <run-name>
- command:
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: [...]
- splits: <path/to/splits.json> (scheme=stratified_text|prompt_holdout)
- feature_set: combined|handcrafted|embeddings
- offload: lt=http://127.0.0.1:18085 embed=http://127.0.0.1:19000
- output: output/essay_scoring/<RUN>/
- results:
  - QWK (CV mean±std):
  - notes:
```

### Example (completed run, Hemma backend, ELLIPSE full)

2026-02-04: `ellipse_full_hemma_20260204_071238`
- output: `output/essay_scoring/20260204_061242_ellipse_full_hemma_20260204_071238/`
- QWK:
  - train: 0.99295
  - val: 0.64241
  - test: 0.65552
- feature extraction throughput (from `artifacts/offload_metrics.json`):
  - total: 4.04 essays/s (6168 essays in 1525.40s)
- offload extract latency (97 requests, no timeouts):
  - mean: 31.19s, p95: 34.05s, p99: 45.66s

2026-02-04: `ellipse_prep_200_1000`
- command: `pdm run essay-scoring-research prepare-dataset --dataset-kind ellipse --min-words 200 --max-words 1000 --run-name ellipse_prep_200_1000`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- output: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/`
- results:
  - notes:
    - Train CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
    - Test CSV: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
    - Integrity report: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/reports/dataset_integrity_report.md`

2026-02-04: `ellipse_splits_200_1000`
- command: `pdm run essay-scoring-research make-splits --dataset-kind ellipse --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --min-words 200 --max-words 1000 --n-splits 5 --run-name ellipse_splits_200_1000`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=stratified_text|prompt_holdout)
- output: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/`
- results:
  - notes:
    - Splits report: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/reports/splits_report.md`

2026-02-04: `ellipse_cv_combined_stratified_text_20260204_150321`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --scheme stratified_text --feature-set combined --language-tool-service-url http://127.0.0.1:18085 --embedding-service-url http://127.0.0.1:19000 --run-name ellipse_cv_combined_stratified_text_20260204_150321`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=stratified_text)
- output: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/`
- results:
  - QWK (CV val mean±std): 0.62623 ± 0.01793
  - notes:
    - CV feature store: `output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/cv_feature_store`

2026-02-04: `ellipse_cv_combined_prompt_holdout_20260204_150321`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --scheme prompt_holdout --feature-set combined --language-tool-service-url http://127.0.0.1:18085 --embedding-service-url http://127.0.0.1:19000 --run-name ellipse_cv_combined_prompt_holdout_20260204_150321`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=prompt_holdout)
- output: `output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/`
- results:
  - QWK (CV val mean±std): 0.61832 ± 0.02396
  - notes:
    - Primary yardstick for CV-first selection (unseen prompt generalization).
    - Future runs: prefer `--reuse-cv-feature-store-dir output/essay_scoring/<STRAT_CV_RUN>/cv_feature_store` to avoid re-extraction.

2026-02-04: `ellipse_cv_embeddings_stratified_text_20260204_174445`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set embeddings --scheme stratified_text --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_cv_embeddings_stratified_text_20260204_174445`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=stratified_text)
- output: `output/essay_scoring/20260204_164449_ellipse_cv_embeddings_stratified_text_20260204_174445/`
- results:
  - QWK (CV val mean±std): 0.55198 ± 0.02148
  - notes:
    - CV feature store: `output/essay_scoring/20260204_164449_ellipse_cv_embeddings_stratified_text_20260204_174445/cv_feature_store`

2026-02-04: `ellipse_cv_embeddings_prompt_holdout_20260204_175630`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set embeddings --scheme prompt_holdout --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_164449_ellipse_cv_embeddings_stratified_text_20260204_174445/cv_feature_store --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_cv_embeddings_prompt_holdout_20260204_175630`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=prompt_holdout)
- output: `output/essay_scoring/20260204_165648_ellipse_cv_embeddings_prompt_holdout_20260204_175630/`
- results:
  - QWK (CV val mean±std): 0.54465 ± 0.02199

2026-02-04: `ellipse_cv_handcrafted_stratified_text_20260204_190101`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set handcrafted --scheme stratified_text --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_cv_handcrafted_stratified_text_20260204_190101`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=stratified_text)
- output: `output/essay_scoring/20260204_180119_ellipse_cv_handcrafted_stratified_text_20260204_190101/`
- results:
  - QWK (CV val mean±std): 0.57372 ± 0.01393
  - notes:
    - CV feature store: `output/essay_scoring/20260204_180119_ellipse_cv_handcrafted_stratified_text_20260204_190101/cv_feature_store`

2026-02-04: `ellipse_cv_handcrafted_prompt_holdout_20260204_190248`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set handcrafted --scheme prompt_holdout --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_180119_ellipse_cv_handcrafted_stratified_text_20260204_190101/cv_feature_store --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_cv_handcrafted_prompt_holdout_20260204_190248`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=prompt_holdout)
- output: `output/essay_scoring/20260204_180303_ellipse_cv_handcrafted_prompt_holdout_20260204_190248/`
- results:
  - QWK (CV val mean±std): 0.56444 ± 0.01887

2026-02-04: `ellipse_drop_column_combined_stratified_text_20260204_190546`
- command: `pdm run essay-scoring-research drop-column --dataset-kind ellipse --feature-set combined --scheme stratified_text --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_140326_ellipse_cv_combined_stratified_text_20260204_150321/cv_feature_store --run-name ellipse_drop_column_combined_stratified_text_20260204_190546`
- dataset: ELLIPSE (train/test), 200–1000 words, excluded prompts: (see `ExperimentConfig.ellipse_excluded_prompts`)
- splits: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json` (scheme=stratified_text)
- feature_set: combined (drop-column evaluates Tier1–Tier3 features only)
- output: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/`
- results:
  - Baseline (CV val QWK mean±std): 0.6262 ± 0.0179
  - Top deltas (ΔQWK mean): grammar_errors_per_100_words (+0.0261), spelling_errors_per_100_words (+0.0211), parse_tree_depth (+0.0134)
  - Suggested drop from predictor input (ΔQWK ≤ 0): has_conclusion (-0.0024), clause_count (-0.0014), flesch_kincaid (-0.0002)

2026-02-04: `ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --run-name ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922`
- output: `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
- results:
  - QWK (CV val mean±std): 0.62210 ± 0.01743
- notes:
  - “Drop-3” handcrafted prune adopted for the predictor going forward.

2026-02-05: `ellipse_cv_combined_prompt_holdout_ordinal_expected_20260205_155521`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode ordinal_multiclass_expected --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --run-name ellipse_cv_combined_prompt_holdout_ordinal_expected_20260205_155521`
- output: `output/essay_scoring/20260205_145529_ellipse_cv_combined_prompt_holdout_ordinal_expected_20260205_155521/`
- results:
  - QWK (CV val mean±std): 0.58728 ± 0.01729
- notes:
  - Regressed vs regression baseline; do not adopt as “best current” on ELLIPSE.

2026-02-05: `ellipse_cv_combined_prompt_holdout_ordinal_argmax_20260205_155521`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode ordinal_multiclass_argmax --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --run-name ellipse_cv_combined_prompt_holdout_ordinal_argmax_20260205_155521`
- output: `output/essay_scoring/20260205_145529_ellipse_cv_combined_prompt_holdout_ordinal_argmax_20260205_155521/`
- results:
  - QWK (CV val mean±std): 0.54047 ± 0.02357
- notes:
  - Much worse than regression; avoid for ELLIPSE objective experiments.

2026-02-05: `ellipse_gate_d_baseline_prompt_holdout_drop3_20260205_173454`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode regression --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --run-name ellipse_gate_d_baseline_prompt_holdout_drop3_20260205_173454`
- output: `output/essay_scoring/20260205_163458_ellipse_gate_d_baseline_prompt_holdout_drop3_20260205_173454/`
- results:
  - QWK (CV val mean±std): 0.62210 ± 0.01743
- notes:
  - Gate D baseline for tail calibration + imbalance mitigation.

2026-02-05: `ellipse_gate_d_weighting_prompt_holdout_drop3_20260205_180657`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode regression --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0 --run-name ellipse_gate_d_weighting_prompt_holdout_drop3_20260205_180657`
- output: `output/essay_scoring/20260205_170701_ellipse_gate_d_weighting_prompt_holdout_drop3_20260205_180657/`
- results:
  - QWK (CV val mean±std): 0.63516 ± 0.01650
- notes:
  - Training-time weighting improves tails modestly and improves mean QWK.

2026-02-05: `ellipse_gate_d_calibration_prompt_holdout_drop3_20260205_180838`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode regression --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --prediction-mapping qwk_cutpoints_lfo --run-name ellipse_gate_d_calibration_prompt_holdout_drop3_20260205_180838`
- output: `output/essay_scoring/20260205_170843_ellipse_gate_d_calibration_prompt_holdout_drop3_20260205_180838/`
- results:
  - QWK (CV val mean±std): 0.68615 ± 0.01029
- notes:
  - Post-hoc cutpoint mapping (leave-one-fold-out) persists:
    - `artifacts/calibration_cutpoints_by_fold.json`
    - `artifacts/calibration_summary.json`

2026-02-05: `ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_20260205_181046`
- command: `pdm run essay-scoring-research cv --dataset-kind ellipse --feature-set combined --scheme prompt_holdout --training-mode regression --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0 --prediction-mapping qwk_cutpoints_lfo --run-name ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_20260205_181046`
- output: `output/essay_scoring/20260205_171050_ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_20260205_181046/`
- results:
  - QWK (CV val mean±std): 0.68360 ± 0.01470
- notes:
  - Weighting + calibration improves high-tail adjacent accuracy most (OOF) with mean QWK still
    within fold noise vs calibration-only; adopt as the default when tail adjacent accuracy is the
    primary yardstick (noisy-label setting). Calibration-only remains the runner-up for max QWK /
    bias reduction (see Gate D task decision).

2026-02-05: `ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746`
- command: `pdm run essay-scoring-research xgb-sweep --splits-path output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json --scheme prompt_holdout --feature-set combined --training-mode regression --grade-band-weighting sqrt_inv_freq --grade-band-weight-cap 3.0 --prediction-mapping qwk_cutpoints_lfo --predictor-handcrafted-drop has_conclusion --predictor-handcrafted-drop clause_count --predictor-handcrafted-drop flesch_kincaid --ellipse-train-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv --ellipse-test-path output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv --reuse-cv-feature-store-dir output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/cv_feature_store --run-name ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746`
- output: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/`
- results:
  - Best config: `97e84d798d` (max_depth=4, min_child_weight=20, reg_lambda=2.0, reg_alpha=0.0)
  - Best run: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d/`
  - CV val QWK mean±std: `0.68460 ± 0.01659`
  - High tail adjacent_acc (`y_true>=4.0`): `0.87907`
- notes:
  - Sweep summary: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/reports/sweep_summary.md`
  - Variants live under: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/`

2026-02-05: `ellipse_gate_e_xgb_bestparams_stratified_text_20260205_212122`
- command: (same as Gate E `xgb-sweep` above, but with `--scheme stratified_text` and a one-config
  grid containing only the selected best params: max_depth=4, min_child_weight=20, reg_lambda=2.0,
  reg_alpha=0.0)
- output: `output/essay_scoring/20260205_202126_ellipse_gate_e_xgb_bestparams_stratified_text_20260205_212122/`
- results:
  - CV val QWK mean±std: `0.68509 ± 0.01969`
