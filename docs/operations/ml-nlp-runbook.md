---
type: runbook
service: global
severity: medium
last_reviewed: '2026-02-04'
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
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme stratified_text \
  --feature-set combined \
  --language-tool-service-url http://127.0.0.1:18085 \
  --embedding-service-url http://127.0.0.1:19000 \
  --run-name ellipse_cv_combined_stratified_text
```

Outputs:
- `output/essay_scoring/<RUN>/reports/cv_report.md`
- `output/essay_scoring/<RUN>/artifacts/cv_metrics.json`
- `output/essay_scoring/<RUN>/cv_feature_store/` (reusable across sweeps)

### Reuse extracted features for fast sweeps

```bash
pdm run essay-scoring-research cv \
  --dataset-kind ellipse \
  --splits-path output/essay_scoring/<SPLITS_RUN>/artifacts/splits.json \
  --scheme stratified_text \
  --feature-set combined \
  --reuse-cv-feature-store-dir output/essay_scoring/<CV_RUN>/cv_feature_store
```

### 4) Drop-column importance (feature selection, handcrafted features)

Drop-column importance answers: “does this handcrafted feature add signal beyond everything else?”.

```bash
pdm run essay-scoring-research drop-column \
  --dataset-kind ellipse \
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

## Observability

Each run directory contains:
- `run.log` (INFO-level, full stage + progress logs)
- `status.json` (single file updated at stage start/complete with a UTC timestamp)
- `stderr.log` (captured stderr for the run; includes Python tracebacks and tool warnings)
- `fault.log` (faulthandler output: segfault traces + periodic hang stack dumps)

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
