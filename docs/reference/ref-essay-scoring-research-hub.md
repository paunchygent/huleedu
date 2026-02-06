---
type: reference
id: REF-essay-scoring-research-hub
title: Essay scoring research hub
status: active
created: '2026-02-04'
last_updated: '2026-02-06'
topic: essay-scoring
---
# Essay scoring research hub

## Purpose

Single entrypoint for developers working on **whitebox essay scoring**.

This hub defines the canonical navigation chain:
`runbook → epic → story hub(s) → tasks → run artifacts → decisions`.

Use it to:
- find “what to run next” (ops/runbook)
- find “why we’re building it” (epic/ADR)
- find “what we’re improving now” (story/task hubs)
- avoid making decisions without the required evidence (CV, ablations, diagnostics)

## Start Here (Navigation)

1) **How to run experiments (canonical)**:
   - `docs/operations/ml-nlp-runbook.md`
2) **Why/what we’re building (product/architecture)**:
   - `docs/product/epics/ml-essay-scoring-pipeline.md` (EPIC-010)
   - `docs/decisions/0021-ml-scoring-integration-in-nlp-service.md` (ADR-0021)
3) **What we’re improving now (decision-ready work)**:
   - `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md` (CV-first story hub)
   - Decision gate (experiment optimization deps): `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
4) **Latest completed run analysis (evidence)**:
   - `.claude/work/reports/essay-scoring/2026-02-04-ellipse-full-hemma-post-run-analysis.md`

## Research Scope Boundaries (PhD scope)

This workstream targets **L2 English writing ability** within the **classic essay discourse genre**
(broadly: argumentative / discussion essays). The goal is *not* “writing in general”.

In practice, this means we must avoid mixing in other communication genres that muddy the construct:
- letters/emails
- narrative/story writing
- short-form messaging
- creative writing
- procedural/instructional texts

Current ELLIPSE guardrails (imperfect but deliberate):
- prompt-level exclusions for letter-dominated prompts
- word-window filtering (200–1000 words)

Future: when the Swedish essay database is available, we must enforce **genre scope explicitly**
via dataset metadata or validated heuristics before making claims or selecting model changes.

## Workstreams (“Spokes”) and Decision Gates

### Spoke A: Prediction power (CV-first)

Hub story:
- `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`

Decision gates (evidence required before choosing levers):
- **Gate A (signal vs cost)**: CV ablation across feature sets.
- **Gate B (feature discipline)**: drop-column CV for handcrafted features.
- **Gate C (failure modes)**: residual diagnostics by prompt and grade band.
- **Gate D (model lever)**: tail calibration/imbalance mitigation → objective alignment → tuning/ensembling.
- **Gate E (construct validity)**: audit + candidate features under prompt-holdout.

Primary selection rule (applies across gates):
- Prefer **`prompt_holdout` mean±std QWK** as the primary yardstick (general L2 writing construct
  generalization across prompts), with `stratified_text` as a stability / leakage-guard check.

Secondary evaluation regime (important, but deferred):
- **Prompt-specific training/evaluation** (within a single yearly assignment prompt) is critical for
  later product validation and anchor alignment, but should be prioritized once the Swedish essay
  database (and its prompt metadata) exists.

Immediate next steps (post Gate C baseline):
- Validate a pruned handcrafted predictor subset under prompt-holdout:
  `TASKS/assessment/essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout.md`
- Address tail calibration / grade-band imbalance:
  `TASKS/assessment/essay-scoring-tail-calibration--grade-band-imbalance-mitigation.md`

### Spoke B: Offload performance + stability (Hemma)

Operational reference:
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`

Tracking tasks:
- `TASKS/assessment/optimize-hemma-offload-throughput.md`
- `TASKS/assessment/essay-scoring-sensible-progress-logs-for-feature-extraction.md`
- `TASKS/assessment/essay-scoring-progressjson-counters-for-long-runs.md`

Decision gate:
- Only optimize throughput after you can attribute time to a concrete bottleneck (LT vs embeddings vs IO),
  using `artifacts/offload_metrics.json` and service-level logs.

### Spoke C: Explainability + teacher-meaningful semantics

Key decisions:
- `docs/decisions/0029-essay-scoring-shap-uses-full-test-set-by-default.md`
- `docs/decisions/0030-essay-scoring-tier1-error-rate-feature-names-include-units.md`

Tracking tasks:
- `TASKS/assessment/essay-scoring-shap-default-full-test-set.md`
- `TASKS/assessment/essay-scoring-tier1-error-rates-per-100-words-naming.md`

Decision gate:
- Do not present “feature importance” conclusions based on XGBoost gain alone; prefer SHAP for global
  and slice-based reasoning.

### Spoke D: Integration path (research → service)

Architecture decision:
- `docs/decisions/0021-ml-scoring-integration-in-nlp-service.md`

Platform tracking:
- `TASKS/infrastructure/ml-training-pipeline-for-essay-scoring-models.md`
- `TASKS/infrastructure/ml-model-serving-infrastructure-for-essay-scoring.md`

Decision gate:
- Move into NLP Service only after we have a stable, CV-selected “best current” model configuration
  (and a repeatable training pipeline).

## Artifact Map (Where evidence lives)

All research runs write to: `output/essay_scoring/<RUN_DIR>/`

Common “evidence” files:
- `output/essay_scoring/<RUN_DIR>/run.log` (stage timings + key metrics summary)
- `output/essay_scoring/<RUN_DIR>/artifacts/metrics.json` (train/val/test)
- `output/essay_scoring/<RUN_DIR>/artifacts/offload_metrics.json` (Hemma `/v1/extract` timing/throughput)
- `output/essay_scoring/<RUN_DIR>/artifacts/metadata.json` (config fingerprint)
- `output/essay_scoring/<RUN_DIR>/shap/` (SHAP values/plots; if enabled)
- `output/essay_scoring/<RUN_DIR>/reports/` (human-readable reports)

CV runs add:
- `output/essay_scoring/<RUN_DIR>/artifacts/cv_metrics.json`
- `output/essay_scoring/<RUN_DIR>/artifacts/predictor_feature_selection.json` (if feature filtering is used)
- `output/essay_scoring/<RUN_DIR>/reports/cv_report.md`
- `output/essay_scoring/<RUN_DIR>/reports/residual_diagnostics.md` (Gate C)
- `output/essay_scoring/<RUN_DIR>/cv_feature_store/` (reuse this for sweeps)

## Examples

### “I want to improve prediction power without fooling myself”

Start with the CV-first story hub:
- `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`

Then follow the runbook commands:
- `docs/operations/ml-nlp-runbook.md`
