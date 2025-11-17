---
id: 'TASK-052L-FEATURE-PIPELINE-INTEGRATION-MASTER'
title: 'TASK-052L — NLP Feature Pipeline Integration Master Plan'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'integrations'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-20'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-052L — NLP Feature Pipeline Integration Master Plan

## Status: IN PROGRESS (Updated 2025-09-20)

### Progress Summary
- **Phase 1**: ✅ COMPLETED - Spell Normalizer extracted, CLI tooling implemented
- **Phase 2-3**: ❌ NOT STARTED - Feature pipeline and CLI validation

## Objective

Coordinate the end-to-end rollout of the modular NLP feature pipeline so that:

- Feature extraction inside the Phase 2 NLP handler uses a shared, testable `FeaturePipeline` abstraction.
- Offline experimentation and model training leverage the exact same feature code via an async CLI runner.
- Grammar-oriented features rely on the existing Language Tool Service client (no duplicate integrations).

## Scope

This master ticket tracks three tightly coupled workstreams:

1. Scaffolding (`feature_context`, `FeaturePipeline`, Dishka provider wiring).
2. Feature bundle implementation with comprehensive unit/integration tests.
3. Offline CLI + early real-world validation against the processed IELTS dataset.

### Execution Footprint

- Core NLP logic (spell normaliser, feature pipeline) lives in shared libraries under `libs/` (`huleedu_nlp_shared`) so production services and tooling use identical algorithms.
- Offline tooling consists of lightweight scripts under `scripts/ml/` that import from `huleedu_nlp_shared`; no new root-level module is created.
- NLP Service imports the shared libs only; it does **not** depend on CLI scripts. CLI and future notebooks consume the same libs to guarantee parity while keeping platform code lean.

### Incremental Delivery Strategy

1. **Spell Normaliser Extraction** – First milestone is extracting and packaging the three-stage spell correction helper so both services and tooling share it.
2. **CLI Prototyping with Selectable Bundles** – Bring up the CLI quickly with feature toggles (per-dimension enable/disable) so we can generate datasets, inspect correlations, and prune redundant metrics before committing to the full feature list.
3. **Iterative Feature Hardening** – Implement and promote feature bundles into shared libs as they prove useful during experiments. Only register “production ready” extractors in NLP Service once validated.

### Spell Normalisation Strategy

- Adopt a **single canonical text** for downstream NLP: all spaCy, RoBERTa, and Language Tool calls operate on spell-normalised text produced by the Spellchecker algorithm.
- Grammar features remain accurate by augmenting Language Tool counts with Spellchecker error tallies (no recomputation on raw text).
- Extract the combined L2/PySpellChecker logic into a reusable helper module (shared library) so runtime services and offline tooling use identical corrections.
- Keep raw text for auditing/teacher display; feature pipeline consumes the normalised text while retaining original error counts for analytics.

## Feature Dimensions & Signals (50 total)

All teams must implement and persist the following six dimensions. Naming shown here is canonical; every extractor and downstream artifact **must** use these keys.

- **Grammar & Mechanics (10)** — powered by existing Language Tool Service outputs
  - `grammar_error_rate_p100w`
  - `spelling_error_rate_p100w`
  - `punctuation_error_rate_p100w`
  - `capitalization_error_rate_p100w`
  - `agreement_error_rate_p100w`
  - `tense_misuse_rate_p100w`
  - `sentence_fragment_rate`
  - `run_on_rate`
  - `quote_mismatch_count`
  - `non_alnum_symbol_rate`

- **Vocabulary Range (8)**
  - `mtld`
  - `hdd`
  - `ttr_lemma`
  - `content_word_ratio`
  - `avg_zipf`
  - `pct_zipf_lt3`
  - `noun_verb_ratio`
  - `adj_adv_ratio`

- **Syntactic Complexity (10)**
  - `mean_sentence_length_words`
  - `sentence_length_cv`
  - `clauses_per_sentence`
  - `subordination_ratio`
  - `mean_tunit_length_words`
  - `passive_voice_rate`
  - `dependency_distance_mean`
  - `coordination_rate`
  - `parse_depth_mean`
  - `left_branching_ratio`

- **Cohesion & Flow (8)**
  - `entity_grid_coherence`
  - `adjacent_sent_sim_variance`
  - `adjacent_sent_low_sim_rate`
  - `lexical_overlap_prev_sent_mean`
  - `lexical_overlap_prev_sent_var`
  - `paragraph_thematic_overlap_mean`
  - `paragraph_boundary_drop_mean`
  - `doc_sent_drift_var`

- **Readability & Length (8)**
  - `fkgl`
  - `fre`
  - `smog`
  - `ari`
  - `avg_syllables_per_word`
  - `total_words`
  - `total_sentences`
  - `total_paragraphs`

- **Task Alignment (6)**
  - `roberta_cos_to_prompt`
  - `tfidf_cos_to_prompt`
  - `keyword_coverage_prompt`
  - `entity_overlap_prompt`
  - `off_topic_indicator`
  - `prompt_alignment_var`

> **Note:** Previously used stance/NLI cues (e.g., `transition_count`, `stance_modality_index`, `nli_neutrality_to_prompt`) are deprecated and must not reappear in new implementations.

## Deliverables

- New modular feature packages (<500 LoC each) grouped by signal family (lexical, syntax, cohesion, prompt alignment, grammar, readability, metadata, etc.).
- Shared DI wiring that exposes the feature pipeline to the Phase 2 command handler and to out-of-process tooling.
- Passing test suite covering individual extractors and an end-to-end CLI run on a representative subset of the IELTS dataset.
- Documentation updates summarising feature groups, testing strategy, and CLI usage.

## Success Criteria

- Feature extraction inside `BatchNlpAnalysisHandler` uses the shared pipeline and produces deterministic outputs for every essay.
- Offline CLI processes the authoritative dataset (`processed/train.parquet`, `processed/test.parquet`) without failure and emits a tracked feature table.
- At least one real-world run (`pdm run python scripts/ml/build_nlp_features.py --sample 200`) completes successfully, providing early validation for downstream modeling.
- Test coverage includes:
  - Unit tests for each feature bundle.
  - Integration test for the pipeline (mocked analyzer + language tool).
  - CLI smoke test exercising actual IO paths.

## Dependencies

- Processed IELTS dataset (`documentation/OPERATIONS/IELTS-task2-dataset-preparation.md`).
- Language Tool Service client for grammar metrics (existing implementation).
- TASK-052K (model integration plan) for downstream requirements.

## Subtasks Status

- `TASK-052L.0-spell-normalizer-shared-helper.md` ✅ **COMPLETED**
  - Library extraction complete, service integration working
  - CLI tooling (`scripts/ml/normalize_dataset.py`) implemented and tested
  - Documentation complete (comprehensive README exists)

- `TASK-052L.1-feature-pipeline-scaffolding.md` ❌ **NOT STARTED**
  - Feature pipeline abstraction not created
  - DI wiring not implemented

- `TASK-052L.2-feature-bundles-and-tests.md` ❌ **NOT STARTED**
  - No feature extractors implemented
  - 50-feature set not built

- `TASK-052L.3-offline-cli-and-validation.md` ❌ **NOT STARTED**
  - `scripts/ml/build_nlp_features.py` not created
  - Note: `scripts/data_preparation/prepare_ielts_task2_dataset.py` exists for CSV→Parquet only

## Critical Path Issues

✅ All critical path issues resolved:
- Directory structure aligned (`scripts/ml/` created, scripts moved)
- Normalization CLI implemented and tested
- Documentation complete

## Next Steps

1. Proceed with feature pipeline scaffolding (TASK-052L.1)
2. Implement 50-feature extraction system (TASK-052L.2)
3. Create `build_nlp_features.py` for offline CLI validation (TASK-052L.3)
