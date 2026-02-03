---
type: runbook
service: global
severity: medium
last_reviewed: '2026-02-03'
---
# ML/NLP Research Runbook (Essay Scoring)

## Purpose

Canonical reference for **whitebox essay scoring research** runs:
- dataset choices and trust policy
- stable train/test + CV split methodology
- Hemma offload prerequisites
- experiment logging conventions (reproducible, leak-safe)

## Canonical dataset policy

### Canonical (current)

- **ELLIPSE train/test** (Overall target) in `data/ELLIPSE_TRAIN_TEST/`
- Standard filters for research comparability:
  - word window: **200–1000 words** (inclusive)
  - drop **letter-dominated prompts** (prompt-level exclusions; do not “detect letters” per essay)
    - configured by `ExperimentConfig.ellipse_excluded_prompts` in `scripts/ml_training/essay_scoring/config.py`

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
- per-service request latency: `offload.embedding.requests.latency_s` and
  `offload.language_tool.requests.latency_s` (p50/p95/p99)
- cache effectiveness: `offload.*.cache.hit_rate`
- error budgets: `requests_timeout`, `requests_http_error`, `requests_connection_error`

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
