# TASK-052L.1 — Feature Pipeline Scaffolding & DI Wiring

## Objective
Establish the shared abstractions and dependency injection plumbing required to compute NLP features across both runtime and offline contexts.

## Requirements
1. Create `feature_context.py` with a typed context object encapsulating prompt, essay text, identifiers, CEFR helpers, `NlpMetrics`, `GrammarAnalysis`, token caches, and correlation metadata.
2. Define `FeatureExtractorProtocol` (async, returns mapping of `{feature_name: float | int | str}`) and a `FeaturePipelineProtocol` that orchestrates multiple extractors and emits both ordered vectors and keyed dicts.
3. Implement `pipeline.py` with a configurable registry of extractor instances, deterministic ordering, and memoisation hooks for expensive shared computations.
4. Extend Dishka providers (`di_nlp_dependencies.py` or new module) to expose the feature pipeline at `Scope.APP`, enabling reuse in `BatchNlpAnalysisHandler` and external scripts.
5. Update service wiring so Phase 2 handler requests `FeaturePipelineProtocol` and passes it the analyzer + language tool outputs (no business logic in handler beyond orchestration).
6. Document the new abstractions in `services/nlp_service/README.md` (or dedicated doc) with diagrams illustrating where the pipeline plugs into the command handler.

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

## Acceptance Criteria
- New context/pipeline modules committed with full type hints and docstrings.
- DI container returns a working pipeline instance in unit tests (e.g., `test_feature_pipeline_scaffolding.py`).
- Phase 2 handler imports-only updated (no feature logic yet), compiling successfully with new provider wiring.
