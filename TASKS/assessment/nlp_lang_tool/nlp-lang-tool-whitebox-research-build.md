---
id: 'nlp-lang-tool-whitebox-research-build'
title: 'NLP LangTool whitebox research build'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: 'nlp_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2026-01-31'
last_updated: '2026-02-01'
related: ['docs/product/epics/ml-essay-scoring-pipeline.md', 'docs/decisions/0021-ml-scoring-integration-in-nlp-service.md', 'TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-essay-scoring-pr.md', 'docs/research/epic-010-ml-essay-scoring-source-traceability.md']
labels: ['nlp', 'essay-scoring', 'whitebox', 'research', 'training']
---
# NLP LangTool whitebox research build

## Objective

Build a standalone research/experimentation pipeline for the whitebox essay scorer
(datasets, feature extraction, training, evaluation, and explainability) that runs
outside the HuleEdu production flow, so experiments and training can iterate without
Kafka/outbox/service wiring.

## Context

EPIC-010 requires a full training and evaluation pipeline (IELTS now, Swedish NAFS
later). The production NLP Service is a Kafka worker with strict batch-only constraints,
which is not suitable for rapid experimentation. This task creates a separate research
build so we can run experiments, ablations, and training scripts without touching the
production service runtime.

This research build remains aligned with ADR-0021 and the EPIC-010 feature architecture,
but intentionally avoids any production deployment wiring. Once validated, the outputs
become inputs to the PR task for service integration.

## Scope

In scope:
- Data loaders (IELTS CSV now; NAFS adapters later)
- Standalone feature extraction pipeline (tiers + embeddings)
- Train/validation/test splits + cross-validation utilities
- Training scripts for XGBoost ordinal regression (including QWK metrics)
- Evaluation + SHAP explainability outputs
- Ablation experiments (handcrafted-only vs embeddings-only vs combined)
- Grade-scale behavior report template execution (assumption-light analysis)

Out of scope:
- Kafka worker integration, outbox publishing, or service DI
- Production inference runtime
- Model serving, hot-reload, or deployment automation

## Plan

1. Define research entrypoints
   - CLI scripts or notebook-friendly modules for data load → features → train → eval.
   - Keep paths under a research-friendly location (not `services/` runtime).

2. Implement data loaders
   - IELTS CSV loader with schema validation.
   - Placeholder NAFS adapter interface (no data assumptions).

3. Feature extraction pipeline
   - Reuse tiered feature architecture and embedding extractor.
   - Ensure feature schema matches EPIC-010 contracts for later service ingestion.

4. Training + evaluation
   - XGBoost regressor with QWK evaluation.
   - Report metrics (QWK, adjacent accuracy, per-band errors).
   - Generate SHAP outputs for interpretability checks.

5. Experiment tracking
   - Store configs, metrics, and artifacts in a structured output directory.
   - Record hyperparameters and dataset version in metadata.

6. Grade-scale behavior report
   - Run the assumption-light grade-scale checks on dataset distributions.
   - Document findings before any Swedish mapping work.

## Progress (2026-02-01)

- Added modular research pipeline under `scripts/ml_training/essay_scoring/` with
  dataset loader, stratified splitter, tiered feature extractors, embedding extractor,
  feature combiner, XGBoost training, evaluation, SHAP artifacts, and grade-scale report.
- Added CLI entrypoint and PDM script `essay-scoring-research` for reproducible runs.
- Added focused unit tests for feature math and pipeline wiring.
- Added `ml-research` dependency group (xgboost, transformers/torch, shap, spacy, etc.).
- Mirrored NLP service spaCy plugins (textdescriptives, wordfreq, lexical-diversity,
  langdetect, gensim) and removed `textstat` from research deps.
- Swapped Tier 1 readability metrics to TextDescriptives and wired a shared spaCy
  pipeline through `FeaturePipeline` for Tier 1 + Tier 2 extractors.
- Aligned EPIC/ADR docs to reference TextDescriptives for readability indices.
- Added a writable Matplotlib cache under `output/essay_scoring/.cache/matplotlib`
  (auto-configured via environment helper).
- `pdm run essay-scoring-research run` currently fails on stratified split when a
  band class has only one sample (needs split strategy decision).
- Added Rich logging for long-running research runs (console + per-run log file).
- Added `tiktoken` + `sentencepiece` to `ml-research` deps for DeBERTa tokenizer support.
- Ran ablation on `/tmp/ielts_small_ablation.csv` end-to-end; outputs:
  - `output/essay_scoring/20260201_091815_handcrafted`
  - `output/essay_scoring/20260201_092125_embeddings`
  - `output/essay_scoring/20260201_092230_combined` (SHAP PNGs + grade report generated)

## Success Criteria

- Research pipeline runs end-to-end without Kafka/outbox/service wiring.
- IELTS dataset training and evaluation produce reproducible metrics.
- Ablation outputs compare handcrafted vs embeddings vs combined.
- SHAP artifacts are produced for interpretability analysis.
- Grade-scale behavior report is generated and reviewed.
- Outputs are reusable by the production PR task without schema drift.

## Related

- `docs/product/epics/ml-essay-scoring-pipeline.md`
- `docs/decisions/0021-ml-scoring-integration-in-nlp-service.md`
- `docs/research/epic-010-ml-essay-scoring-source-traceability.md`
- `TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-essay-scoring-pr.md`
