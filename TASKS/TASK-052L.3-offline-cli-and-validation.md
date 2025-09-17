# TASK-052L.3 — Offline Feature CLI & Early Real-World Validation

## Objective
Ship an async CLI that reuses the production feature pipeline to generate training datasets, and validate the full stack against the IELTS Task 2 corpus early in development.

## Requirements
1. Implement `scripts/ml/build_nlp_features.py` (naming flexible) with:
   - Async Dishka container reuse (NLP dependencies + feature pipeline + Language Tool client).
   - Support for reading `processed/train.parquet` and `processed/test.parquet` via `pyarrow.dataset` streaming.
   - CLI options: `--dataset-dir`, `--output-path`, `--format {parquet,csv}`, `--max-tasks`, `--sample <int>` for subset runs, `--skip-grammar` for diagnostics.
   - Output schema capturing identifiers, prompt/essay metadata, IELTS band, derived CEFR label/code, and flatten feature map.
   - Integrate the shared spell-normalisation helper so CLI generates the corrected text + error counts before invoking the feature pipeline.
2. Add orchestration glue in `BatchNlpAnalysisHandler` to call the pipeline and include features in the rich event payload (guarded by feature flag if necessary).
3. Develop integration tests:
   - CLI smoke test using a trimmed fixture dataset (≤5 essays) to ensure end-to-end execution.
   - Handler-level test confirming features are produced when analyzer + grammar data are present.
4. Execute an early real-world run locally:
   ```bash
   pdm run python scripts/ml/build_nlp_features.py --dataset-dir data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation --output-path data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/processed/features.parquet --max-tasks 6 --sample 200
   ```
   Capture runtime, resource usage, and sample output statistics in the ticket notes.
5. Document CLI usage, expected outputs, and troubleshooting tips (Language Tool availability, performance tuning).

### Feature Integrity Requirements
- CLI output must contain the full 50-feature set exactly as enumerated in the master plan (no omissions, no legacy keys).
- Grammar features rely on live Language Tool responses; CLI should detect service availability and fail fast with actionable messaging.
- Include summary validation in CLI logs (e.g., per-dimension mean/std) to help spot anomalies early.

## Acceptance Criteria
- CLI script committed with comprehensive docstring, argument parsing, and logging.
- Integration tests pass and are wired into CI.
- Real-world run executed with results captured (JSON summary or metrics) and checked into `TASK-052L.3` notes section.
- NLP handler publishes events enriched with feature payloads without regressing existing tests.
