# TASK-052L.0 — Shared Spell Normaliser Extraction

## Objective
Extract the three-stage spell correction pipeline (word filter → Swedish L2 lookup → PySpellChecker) into a shared library so both runtime services and offline tooling use identical logic before feature experimentation begins.

## Deliverables
- New shared package `libs/huleedu_nlp_shared/` providing a `SpellNormalizer` facade and typed `SpellNormalizationResult` output.
- L2 dictionary loader, whitelist helper, and PySpell caching logic migrated from Spellchecker Service into the shared module.
- Spellchecker Service refactored to consume the shared helper without changing public behaviour.
- CLI scaffolding (to be built in later phases) prepared to import the same helper for dataset normalisation.
- Comprehensive unit tests for the helper and regression tests confirming service parity.
- Documentation updates describing usage and configuration.

## Work Breakdown
1. **Library Scaffold**
   - Create shared package `libs/huleedu_nlp_shared/` with `normalization/` sub-package (facade, models, L2 logic, whitelist, spellchecker wrappers, config dataclass with env overrides).
   - Implement `SpellNormalizationResult` dataclass (corrected text, per-stage counts, detailed corrections, word count, density, stage timings) plus helpers (e.g., `to_feature_dict`).
   - Migrate `load_l2_errors`, `apply_l2_corrections`, whitelist loader, and adaptive SpellChecker cache into this package; parameterise paths via `NormalizationConfig` / environment variables.
   - Provide `SpellNormalizer` facade supporting dependency injection (dictionary loader, whitelist manager, spell checker factory) and async normalisation.
2. **Service Integration**
   - Update `services/spellchecker_service/implementations/spell_logic_impl.py` to instantiate the shared normaliser (APP scope) and rely on it for corrections.
   - Preserve logging, metrics, and event payload shapes; ensure parallel processor hooks still function.
3. **CLI Preparation**
   - Under `scripts/ml/`, add `normalize_dataset.py` that imports the shared normaliser, normalises essays, and outputs corrected text + correction stats (foundation for later feature extraction). Ensure CLI supports env-configurable resource paths and bundle toggles in later phases.
4. **Testing**
   - Add unit tests in the shared module for dictionary replacement edge cases, whitelist behaviour, and SpellChecker corrections.
   - Add regression test comparing old vs. new normaliser outputs on fixture essays within the Spellchecker Service test suite.
   - Optional CLI smoke test normalising a tiny dataset slice.
5. **Documentation**
   - Update relevant task docs/READMEs describing how to configure and use the shared normaliser (paths, language settings, whitelist handling).

## Acceptance Criteria
- Spellchecker Service passes all existing tests using the shared normaliser; a feature flag allows reverting to the legacy pipeline during rollout.
- Shared package achieves ≥90% test coverage (dictionary/whitelist logic, spell corrections, configuration) and includes a regression benchmark showing <5% performance regression versus the current implementation on a 100-essay sample.
- CLI groundwork verified by running `scripts/ml/normalize_dataset.py` over a sample dataset (e.g., 100 essays) within <30 seconds, using the shared normaliser and resource paths resolved correctly in Docker/dev environments.
- Task documentation reflects the new shared architecture, configuration (including env overrides), and usage guidance.
