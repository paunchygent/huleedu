---
id: nlp-lang-tool-whitebox-essay-scoring-pr
title: NLP LangTool whitebox essay scoring PR
type: task
status: proposed
priority: medium
domain: assessment
service: nlp_service
owner_team: agents
owner: ''
program: ''
created: '2026-01-31'
last_updated: '2026-02-01'
related:
- docs/product/epics/ml-essay-scoring-pipeline.md
- docs/decisions/0021-ml-scoring-integration-in-nlp-service.md
- .agent/rules/020.15-nlp-service-architecture.md
- TASKS/assessment/nlp-phase2-command-handler-skeleton-plan.md
- services/language_tool_service/README.md
- TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md
labels:
- nlp
- essay-scoring
- whitebox
- languagetool
- features
---
# NLP LangTool whitebox essay scoring PR

## Objective

Define and implement the LanguageTool-backed Tier 1 error-density features for the
whitebox essay scoring pipeline in `nlp_service`, aligned with EPIC-010 and ADR-0021,
while respecting NLP service constraints (Kafka worker, batch-level only, outbox).

## Context

EPIC-010 requires tiered hand-rolled features with LanguageTool as the highest-signal
error-density source. This PR focuses on the NLP Service integration and feature
extraction pathway so that the whitebox scorer can compute deterministic, interpretable
error signals alongside embeddings and other tiers.

NLP Service architecture mandates batch-level processing, no HTTP API exposure, and
outbox-based publishing. LanguageTool is already a dedicated internal service; this work
integrates it via a client protocol, with explicit error handling and observability.

This PR is cross-linked to EPIC-010 and should be treated as the Tier 1 feature
implementation slice for the whitebox scorer.

## Scope

In scope:
- LanguageTool client protocol + implementation in NLP Service
- Tier 1 error-density feature extractor (grammar, spelling, punctuation) normalized
  per 100 words
- Wiring into the essay-scoring feature pipeline and combined feature schema
- Metrics and failure handling (timeouts, partial failures)
- Unit tests with protocol mocks (no real LanguageTool in unit tests)

Out of scope:
- Research build (experiments, training scripts, data loaders, ablations). See
  `TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md`.
- Swedish grade mapping or psychometric calibration (covered by grade-scale report)
- Embedding extraction or XGBoost training (covered by EPIC-010 phases)
- UI-facing explanations or SHAP rendering

## Plan

1. Define protocol + settings
   - Add `LanguageToolClientProtocol` and settings (endpoint, timeout, retry policy).
   - Register in Dishka container for `nlp_service`.

2. Implement Tier 1 extractor
   - New module: `services/nlp_service/features/essay_scoring/extractors/tier1_error_readability.py`.
   - Compute error counts from LanguageTool response.
   - Normalize to densities per 100 words and return Pydantic feature model.

3. Integrate into feature pipeline
   - Extend `EssayFeatures` / tier models and the feature combiner.
   - Ensure batch-level processing with concurrency control (semaphore).
   - Return per-essay error markers on failure, not hard-fail batch.

4. Observability + resilience
   - Metrics: request count, error count, latency histogram.
   - Structured logging with essay_id and batch_id correlation.
   - Graceful fallback to zeroed features when LanguageTool is unavailable.

5. Tests
   - Unit tests for density math and error handling using protocol mocks.
   - Integration test wiring in `nlp_service` (no external LT dependency).

6. Docs and alignment
   - Update `services/language_tool_service/README.md` (if needed) with usage contract.
   - Confirm EPIC-010 alignment and cross-link to this task.

## Success Criteria

- Tier 1 LanguageTool features are computed and included in the essay feature vector.
- NLP Service handles LanguageTool failures without batch failure (partial errors only).
- Feature extraction is deterministic and normalized (per 100 words).
- Unit tests cover density math, error normalization, and failure paths.
- Metrics and logs are visible for LanguageTool calls.
- Links and alignment confirmed with EPIC-010 and ADR-0021.

## Related

- `docs/product/epics/ml-essay-scoring-pipeline.md`
- `docs/decisions/0021-ml-scoring-integration-in-nlp-service.md`
- `.agent/rules/020.15-nlp-service-architecture.md`
- `TASKS/assessment/nlp-phase2-command-handler-skeleton-plan.md`
- `services/language_tool_service/README.md`
- `TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md`
