# TASK-052L.2 — Feature Bundles & Comprehensive Testing

## Objective
Implement the 50-signal specification as cohesive extractor bundles with exhaustive automated coverage.

## Deliverables
1. Bundle layout under `libs/huleedu_nlp_shared/feature_pipeline/` (each module <500 LoC), exposed to both services and CLI, with ability to register/unregister bundles individually for experimentation:
   - `lexical_diversity.py`
   - `syntax_complexity.py`
   - `cohesion.py`
   - `prompt_alignment.py`
   - `grammar_quality.py` (consumes Language Tool analysis)
   - `readability.py`
   - `metadata_features.py`
   - Additional files as needed to keep each module <500 LoC.
2. Each bundle exports one or more concrete `FeatureExtractorProtocol` implementations registered via the pipeline registry.
3. Shared helpers (token filters, n-gram stats, normalization utilities) live in `features/helpers/` and include unit coverage.
4. Feature names follow a consistent naming convention (`nlp_<group>_<metric>`), documented centrally; provide lightweight stubs (returning `None` or `0.0`) for bundles still under evaluation so CLI can emit complete schemas while experiments are in-progress.

### Spell-Normalised Text Usage
- All bundles consume the spell-normalised text provided by the shared helper. Store the reference in the feature context once to avoid duplicated corrections.
- Grammar bundle combines Language Tool rates with Spellchecker error counts (per 100 words) rather than re-running detection on raw text.
- Tests must include fixtures for: raw text, normalised text, and error count metadata to ensure helper parity across environments.

## Target Feature Set (must match master plan)
- **Grammar & Mechanics (10)** — `grammar_quality.py`
  - `grammar_error_rate_p100w`, `spelling_error_rate_p100w`, `punctuation_error_rate_p100w`, `capitalization_error_rate_p100w`, `agreement_error_rate_p100w`, `tense_misuse_rate_p100w`, `sentence_fragment_rate`, `run_on_rate`, `quote_mismatch_count`, `non_alnum_symbol_rate`
- **Vocabulary Range (8)** — `lexical_diversity.py`
  - `mtld`, `hdd`, `ttr_lemma`, `content_word_ratio`, `avg_zipf`, `pct_zipf_lt3`, `noun_verb_ratio`, `adj_adv_ratio`
- **Syntactic Complexity (10)** — `syntax_complexity.py`
  - `mean_sentence_length_words`, `sentence_length_cv`, `clauses_per_sentence`, `subordination_ratio`, `mean_tunit_length_words`, `passive_voice_rate`, `dependency_distance_mean`, `coordination_rate`, `parse_depth_mean`, `left_branching_ratio`
- **Cohesion & Flow (8)** — `cohesion.py`
  - `entity_grid_coherence`, `adjacent_sent_sim_variance`, `adjacent_sent_low_sim_rate`, `lexical_overlap_prev_sent_mean`, `lexical_overlap_prev_sent_var`, `paragraph_thematic_overlap_mean`, `paragraph_boundary_drop_mean`, `doc_sent_drift_var`
- **Readability & Length (8)** — `readability.py`
  - `fkgl`, `fre`, `smog`, `ari`, `avg_syllables_per_word`, `total_words`, `total_sentences`, `total_paragraphs`
- **Task Alignment (6)** — `prompt_alignment.py`
  - `roberta_cos_to_prompt`, `tfidf_cos_to_prompt`, `keyword_coverage_prompt`, `entity_overlap_prompt`, `off_topic_indicator`, `prompt_alignment_var`

Deprecated metrics (`transition_count`, `stance_modality_index`, `nli_neutrality_to_prompt`, etc.) must remain removed.

## Testing Strategy
- Unit tests per bundle verifying:
  - Correct handling of typical vs. edge cases (empty essay, short essay, non-English text).
  - Deterministic output given fixed analyzer/grammar fixtures.
- Grammar features must rely on the Language Tool Service client’s DTOs; build fixtures from real responses to avoid diverging schemas.
- Integration test for the pipeline that loads a minimal mock context (real analyzer outputs captured from dev run) and asserts combined feature map ordering and values.
- Property-style test where applicable (e.g., monotonicity of ratios) to catch regressions.
- Dataset-backed smoke test: run pipeline against a handful of rows sampled from `processed/train.parquet` to ensure real essays exercise every signal.
- For features still flagged as experimental, ensure tests assert graceful disabling (e.g., pipeline returns empty map when bundle is skipped).

## Acceptance Criteria
- All feature modules implemented with docstrings and type hints.
- New tests pass via `pdm run pytest-root services/nlp_service/tests/features` (create directory if needed).
- Coverage demonstrates every feature is exercised; add snapshot / golden-file assertions if numeric stability is critical.
- Documentation entry summarising available features and bundles (link from master ticket doc).
