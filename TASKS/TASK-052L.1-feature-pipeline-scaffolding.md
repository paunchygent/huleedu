# TASK-052L.1 — Feature Pipeline Scaffolding & DI Wiring

## Objective

Establish the shared abstractions and dependency injection plumbing required to compute NLP features across both runtime and offline contexts.

## Requirements

1. Create `feature_context.py` within `libs/huleedu_nlp_shared/feature_pipeline/` with a typed context object encapsulating prompt, essay text, identifiers, CEFR helpers, `NlpMetrics`, `GrammarAnalysis`, token caches, and correlation metadata.
2. Define `FeatureExtractorProtocol` (async, returns mapping of `{feature_name: float | int | str}`) and a `FeaturePipelineProtocol` that orchestrates multiple extractors and emits both ordered vectors and keyed dicts.
3. Implement `pipeline.py` with a configurable registry of extractor instances, deterministic ordering, and memoisation hooks for expensive shared computations.
4. Extend Dishka providers (`di_nlp_dependencies.py` or new module) to expose the feature pipeline at `Scope.APP`, enabling reuse in `BatchNlpAnalysisHandler` and external scripts.
5. Update service wiring so Phase 2 handler requests `FeaturePipelineProtocol` and passes it the analyzer + language tool outputs (no business logic in handler beyond orchestration).
6. Document the new abstractions in `services/nlp_service/README.md` (or dedicated doc) with diagrams illustrating where the pipeline plugs into the command handler.

## Execution Plan (2025‑10‑07)

1. **Scaffold shared module** – Stand up `libs/huleedu_nlp_shared/feature_pipeline/feature_context.py`, `protocols.py`, and `pipeline.py` with Google-style docstrings, complete typing, and ULTRATHINK cross-links. `FeatureContext` will expose raw/normalized text, `SpellNormalizationResult`, cached spaCy docs, Language Tool `GrammarAnalysis`, embeddings, CEFR helpers, prompt metadata, word counts, correlation data, and feature-toggle state. Lazy properties will prevent repeated analyzer calls.
2. **Protocol contracts** – Define and unit-test `FeatureExtractorProtocol` and `FeaturePipelineProtocol` so each extractor is an async component returning `{feature_name: FeatureValue}`. The pipeline will enforce deterministic registration order, optional bundle toggles, and shared-computation memoisation while honouring `.claude/rules/042` DI expectations.
3. **Initial extractors** – Implement a `NormalizationFeaturesExtractor` (SpellNormalizer + Language Tool SPELLING aggregation feeding `spelling_error_rate_p100w` plus related metrics) and a stub grammar bundle placeholder to validate orchestration without front-running TASK-052L.2. These extractors consume the context’s cached artifacts instead of recomputing.
4. **Dependency injection wiring** – Extend the Dishka provider layer (likely `services/nlp_service/di.py`) to expose `FeaturePipelineProtocol` at `Scope.APP`, composing existing SpellNormalizer, Language Tool client, analyzer, embedding clients, and config toggles. Provide a factory usable both by the service and by offline tooling.
5. **Handler integration** – Refactor `services/nlp_service/command_handlers/batch_nlp_analysis_handler.py` to depend on `FeaturePipelineProtocol`. The handler will fetch essay text, populate a `FeatureContext`, invoke `pipeline.extract_features`, and forward the normalized text + aggregated feature map to existing outbox publishers while preserving current structured error handling, correlation IDs, and logging.
6. **Tooling alignment** – Update `scripts/ml/normalize_dataset.py` (or rename to `prepare_normalized_dataset.py`) and create `scripts/ml/build_nlp_features.py` so both boot the Dishka container, resolve the shared pipeline, and write normalized text + features. Maintain the established CLI error-handling pattern and ensure Language Tool runs on normalized text only once per essay.
7. **Documentation & verification** – Document the pipeline architecture, data flow, and feature ownership in `services/nlp_service/README.md` (diagram + ULTRATHINK references). Add unit tests for pipeline registration, context lazy-loading, and spelling aggregation; plan broader bundle and CLI tests for TASK-052L.2/3. Validate changes with `pdm run typecheck-all` and targeted `pdm run pytest-root` suites before requesting review.

## Progress Update (2025‑10‑07)

- Shared pipeline scaffolding is in place (`feature_context`, `protocols`, `pipeline`, extractors) with unit coverage.
- NLP DI wiring, handler integration, and CLI tooling now consume the pipeline, and `EssayNlpCompletedV1` carries the aggregated feature map.
- ELS propagates `SpellcheckResultV1` metrics into `EssayProcessingInputRefV1`, so Phase 2 receives canonical spell correction counts without recomputation.
- Documentation refreshed in `services/nlp_service/README.md`; further architectural diagrams will follow once the remaining feature bundles (TASK‑052L.2) are implemented.

### Context Data Requirements (supports 50-signal spec)

- Cached spaCy `Doc`, sentences, lemma/token lists, and counts.
- RoBERTa embeddings for document, sentences, and prompt (for cohesion/alignment metrics).
- TF-IDF vectoriser handle + prompt vector (for `tfidf_cos_to_prompt`).
- Language Tool `GrammarAnalysis` object and any per-error category aggregates (for the 10 grammar features).
- Readability helpers (e.g., textstat) should operate on the spell-normalised text to match runtime behaviour; retain raw text for auditing metrics where necessary.
- Metadata: essay/prompt IDs, IELTS band, derived CEFR code/label, batch identifiers.
- Spell-normalisation helper output (corrected text + per-category error counts) is considered canonical for feature extraction; retain reference to original text for persistence.

## Constraints & Notes

- Keep each file <500 LoC; prefer small helper modules under `services/nlp_service/features/helpers/` for common utilities.
- Do not bypass existing Language Tool client; grammar metrics arrive via the injected pipeline context.
- Preserve current batch processing semantics—scaffolding should not yet change storage formats or event contracts.
- Registry should support feature toggles (e.g., via config or CLI flags) so experiments can enable subsets of bundles without code changes.

## Acceptance Criteria

- New context/pipeline modules committed with full type hints and docstrings.
- DI container returns a working pipeline instance in unit tests (e.g., `test_feature_pipeline_scaffolding.py`).
- Phase 2 handler imports-only updated (no feature logic yet), compiling successfully with new provider wiring.
