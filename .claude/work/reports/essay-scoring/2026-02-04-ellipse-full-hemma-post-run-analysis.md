# Post-run analysis: ELLIPSE full (Hemma backend, combined) — 2026-02-04

## Scope

This report analyzes the completed ELLIPSE full run using the Hemma combined offload backend
(`POST /v1/extract`) and `feature_set=combined`.

Primary goals:
- Summarize model metrics (train/val/test) and failure modes.
- Summarize performance/throughput and where time is spent.
- Extract actionable feature-importance signals to guide next experiments.
- Identify what artifacts are missing for deeper analysis (SHAP, residuals, prompt-level drilldowns)
  and propose concrete follow-up runs.

## Run identity

- run name: `ellipse_full_hemma_20260204_071238`
- output dir: `output/essay_scoring/20260204_061242_ellipse_full_hemma_20260204_071238/`
- git sha (runner recorded): `1d59125b9c15f3334a757cb1032d87fafd82604b`
- dataset:
  - train: `data/ELLIPSE_TRAIN_TEST/ELLIPSE_Final_github_train.csv`
  - test: `data/ELLIPSE_TRAIN_TEST/ELLIPSE_Final_github_test.csv`
  - excluded prompts: `['Cell phones at school', 'Community service', 'Grades for extracurricular activities', 'Letter to employer']`
- counts: total `6168`, train `3079`, val `659`, test `2430`
- label scale recorded: `1.0–5.0`

Notes:
- The splitter logged: `Assigning rare labels to train: [1.0]` (so `1.0` is effectively absent in val).
- `reports/` and `shap/` are empty because the run was executed with `--skip-shap --skip-grade-scale-report`.

## Model configuration (training)

Model: XGBoost regressor on 793 features (768 DeBERTa + 25 handcrafted).

Embedding:
- model: `microsoft/deberta-v3-base`
- dim: `768`

XGBoost params (from `artifacts/metadata.json`):
- objective: `reg:squarederror`
- max_depth: `6`
- learning_rate: `0.03`
- min_child_weight: `5`
- subsample: `0.8`
- colsample_bytree: `0.6`
- reg_lambda: `2.0`
- num_boost_round: `1500`
- early_stopping_rounds: `100`
- best_iteration: `281`

Interpretation:
- `best_iteration=281` indicates early stopping triggered well before the maximum rounds.
- Training is not compute-bound (training ~10 seconds). Generalization/robustness (splits/CV) is
  the key lever, not GPU acceleration.

## Performance / throughput (processing)

### Stage timing (from `run.log`)

| stage | records | seconds | essays/s |
|---|---:|---:|---:|
| feature_extraction_train | 3079 | 759.44 | 4.05 |
| feature_extraction_val | 659 | 169.15 | 3.90 |
| feature_extraction_test | 2430 | 596.81 | 4.07 |
| feature_extraction_total | 6168 | 1525.40 | 4.04 |
| training_xgboost | 3079 | 9.68 | — |
| evaluation | 2430 | 0.06 | — |

Takeaway:
- Feature extraction dominates wall-clock (≈25.4 minutes out of ≈25.6 minutes).
- Training/eval are negligible at current data size.

### Hemma offload request stats (from `artifacts/offload_metrics.json`)

`/v1/extract` behavior:
- requests: `97` total, `97` ok, `0` timeouts
- request size: mean `63.34` essays per request (target batch size is 64, with tail batches smaller)
- latency: mean `31.19s`, p95 `34.05s`, p99 `45.66s`

Throughput reconciliation (useful for bottleneck reasoning):
- per-request throughput estimate: `63.34 / 31.19 ≈ 2.03 essays/s`
- headline throughput: `4.04 essays/s`
- implied sustained in-flight `/v1/extract` concurrency: `4.04 / 2.03 ≈ 1.99` (≈2)

Cache behavior (first full run):
- extract cache hit rate: `0.39%` (24 hits / 6168 total)
- next runs should be strongly cache-hit dominated and can be used for fast sweeps (ablation/CV),
  as long as the cache key stays stable (same offload fingerprint + config).

## Evaluation results (train/val/test)

### Headline metrics (from `artifacts/metrics.json`)

- QWK:
  - train: `0.99295`
  - val: `0.64241`
  - test: `0.65552`
- MAE:
  - train: `0.01169`
  - val: `0.32853`
  - test: `0.32860`
- Adjacent accuracy (|pred−true| ≤ 0.5):
  - train: `1.000`
  - val: `0.894`
  - test: `0.915`

Interpretation:
- Train vs val/test gap is large (train QWK ≈ 0.99 vs test ≈ 0.66), indicating strong
  overfitting under the current split. This is expected when:
  - many embedding dimensions are available (768), and
  - labels are heavily concentrated in the middle bands (see distributions below).
- Val and test are close (0.642 vs 0.656), suggesting the holdout split is reasonably consistent.

### Label distribution (from confusion matrices)

Val (n=659):
- 3.0: 230
- 3.5: 134
- 2.5: 117
- 4.0: 95
- 2.0: 57
- 4.5: 17
- 5.0: 5
- 1.5: 4

Test (n=2430):
- 3.0: 881
- 3.5: 493
- 2.5: 422
- 4.0: 348
- 2.0: 209
- 4.5: 55
- 5.0: 12
- 1.5: 9
- 1.0: 1

Implication for next-step evaluation:
- The tails (≤2.0 and ≥4.5) have low support; per-band MAE there will be noisy and error bars large.
- A prompt-holdout CV scheme is still needed to claim “generalization” beyond this single split.

## Feature importance analysis

This run did not generate SHAP artifacts. The available importance signal is XGBoost split gain,
which is useful for directional decisions but is not a substitute for SHAP.

Naming note:
- Tier 1 error-rate feature names were later updated to include units (per 100 words) via
  `docs/decisions/0030-essay-scoring-tier1-error-rate-feature-names-include-units.md`.
  Older runs may show `grammar_density` etc in their saved artifacts/logs.

### Feature importance (XGBoost gain)

Note: “gain” is XGBoost split gain; it is not SHAP and is not directly comparable across model families.

**Gain by tier (used features only):**
- embedding: 90.8%
- tier1: 7.1%
- tier2: 1.5%
- tier3: 0.6%

**Top handcrafted features (gain):**

| rank | feature | tier | gain |
|---:|---|---|---:|
| 1 | grammar_errors_per_100_words | tier1 | 21.8734 |
| 2 | spelling_errors_per_100_words | tier1 | 7.9259 |
| 3 | parse_tree_depth | tier2 | 3.8626 |
| 4 | avg_sentence_length | tier1 | 2.7035 |
| 5 | avg_word_length | tier1 | 2.4926 |
| 6 | word_count | tier1 | 2.4423 |
| 7 | dep_distance | tier2 | 2.3468 |
| 8 | paragraph_count | tier3 | 1.6281 |
| 9 | flesch_kincaid | tier1 | 1.5886 |
| 10 | coleman_liau | tier1 | 1.3864 |
| 11 | has_conclusion | tier3 | 1.2769 |
| 12 | punctuation_errors_per_100_words | tier1 | 1.2350 |
| 13 | ttr | tier1 | 1.1880 |
| 14 | ari | tier1 | 1.1410 |
| 15 | sent_similarity_variance | tier2 | 0.8149 |

**Top features overall (gain):**

| rank | feature | tier | gain |
|---:|---|---|---:|
| 1 | grammar_errors_per_100_words | tier1 | 21.8734 |
| 2 | embedding_542 | embedding | 9.6343 |
| 3 | embedding_254 | embedding | 8.4703 |
| 4 | spelling_errors_per_100_words | tier1 | 7.9259 |
| 5 | embedding_649 | embedding | 5.4980 |
| 6 | embedding_705 | embedding | 5.2212 |
| 7 | embedding_519 | embedding | 5.2094 |
| 8 | embedding_682 | embedding | 5.1245 |
| 9 | embedding_533 | embedding | 5.0231 |
| 10 | embedding_720 | embedding | 4.9671 |
| 11 | embedding_242 | embedding | 4.2176 |
| 12 | parse_tree_depth | tier2 | 3.8626 |
| 13 | embedding_431 | embedding | 3.7774 |
| 14 | embedding_564 | embedding | 3.6291 |
| 15 | embedding_128 | embedding | 3.3584 |

Actionable interpretation:
- Even with strong embeddings, the most “valuable” non-embedding signal is still Tier 1 grammar/spelling
  densities. That supports continued investment in LanguageTool capacity/latency.
- Tier 2/Tier 3 handcrafted features contribute, but much less than Tier 1 + embeddings. This is a
  candidate area for drop-column confirmation (to keep only features that matter and simplify the system).

## What’s missing for “full” analysis (and how to get it)

### SHAP

Status: generated in a follow-up run reusing the feature store (see addendum below).

Fastest way to get SHAP without re-extracting features repeatedly:
1) Persist features once:
```bash
pdm run essay-scoring-research featurize \\
  --dataset-kind ellipse --feature-set combined \\
  --backend hemma --offload-service-url http://127.0.0.1:19000 \\
  --run-name ellipse_features_combined_hemma
```
2) Run training+eval with SHAP enabled, reusing the feature store:
```bash
pdm run essay-scoring-research run \\
  --dataset-kind ellipse --feature-set combined \\
  --reuse-feature-store-dir output/essay_scoring/<FEATURIZE_RUN_DIR> \\
  --run-name ellipse_full_hemma_with_shap
```

Expected outputs:
- `shap/` summary plots and/or tables (depending on the runner config).
- `reports/grade_scale_report.md` (if not skipped).

### Cross-regression / ablation across feature sets

This repo has a built-in `ablation` command, but we do not have a comparable ELLIPSE baseline yet.

Recommended:
```bash
pdm run essay-scoring-research ablation \\
  --dataset-kind ellipse \\
  --backend hemma --offload-service-url http://127.0.0.1:19000 \\
  --run-name ellipse_ablation_hemma
```

This gives an apples-to-apples comparison of:
- handcrafted-only vs embeddings-only vs combined
…and tells us whether LanguageTool is still a “must-have” feature set once embeddings are present.

### Handcrafted feature importance (drop-column)

For interpretability and to reduce clutter, run drop-column CV for handcrafted features:
- Generate splits once (`make-splits`), then run `drop-column`.
- This isolates which handcrafted features add incremental value beyond embeddings.

## Next steps (highest leverage)

1) Generate a feature store + SHAP artifacts (using `featurize` + `run --reuse-feature-store-dir`).
2) Run ELLIPSE ablation to quantify feature-set contributions under the same setup.
3) Run CV with `prompt_holdout` to measure unseen-prompt generalization.
4) Run `drop-column` to validate which handcrafted features are worth keeping.

## Addendum: SHAP follow-up run (reused feature store)

Follow-up run:
- output dir: `output/essay_scoring/20260204_072318_ellipse_full_hemma_with_shap_20260204_082316/`
- reused feature store: `output/essay_scoring/20260204_072305_ellipse_features_combined_hemma_20260204_082300/feature_store` (logged in `run.log`)

Headline metrics (QWK; `artifacts/metrics.json`):
- train: `0.99990`
- val: `0.65355`
- test: `0.64797`

SHAP artifacts written:
- `shap/shap_summary.png`
- `shap/shap_summary_bar.png`
- `shap/shap_values.npy` (shape `(500, 793)`; sampled rows)
- `shap/shap_base_values.npy`

Grade-scale report written:
- `reports/grade_scale_report.md`

Top features by mean(|SHAP|) (computed from `shap_values.npy`):
1) `grammar_errors_per_100_words` (Tier 1)
2) `spelling_errors_per_100_words` (Tier 1)
3) `parse_tree_depth` (Tier 2)
4) `embedding_720` (embedding)
5) `avg_word_length` (Tier 1)
6) `embedding_649` (embedding)
7) `dep_distance` (Tier 2)
8) `embedding_254` (embedding)
9) `embedding_519` (embedding)
10) `word_count` (Tier 1)

Mean(|SHAP|) mass by tier (sampled rows):
- embedding: `74.0%`
- tier1: `21.0%`
- tier2: `3.9%`
- tier3: `1.0%`

## Addendum: Full-test-set SHAP (default behavior)

Decision: `docs/decisions/0029-essay-scoring-shap-uses-full-test-set-by-default.md`

After changing the SHAP helper default from “sample 500 rows” to “no sampling”, a SHAP-enabled
run reusing the cached feature store produces full-test SHAP values by default:

- output dir: `output/essay_scoring/20260204_072809_ellipse_full_hemma_with_shap_full_20260204_082806/`
- `shap/shap_values.npy` shape: `(2430, 793)` (full ELLIPSE test split)
