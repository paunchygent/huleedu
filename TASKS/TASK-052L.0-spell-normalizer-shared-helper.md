# TASK-052L.0 — Shared Spell Normaliser Extraction

## Objective

Extract the three-stage spell correction pipeline (word filter → Swedish L2 lookup → PySpellChecker) into a shared library so both runtime services and offline tooling use identical logic before feature experimentation begins.

## Status: ✅ PARTIAL COMPLETION

### Completed Components

1. **Library Scaffold** ✅ COMPLETED
   - Created `libs/huleedu_nlp_shared/` with `normalization/` sub-package containing:
     - `SpellNormalizer` class with preserved algorithm and `_spellchecker_cache` singleton
     - `SpellNormalizationResult` model with metrics (corrected_text, total_corrections, l2_dictionary_corrections, spellchecker_corrections, word_count, correction_density)
     - Protocol definitions for `WhitelistProtocol`, `ParallelProcessorProtocol`, `SpellcheckerSettingsProtocol`
   - L2 dictionary loaded once via DI in service layer, passed to normalizer constructor
   - Async normalization with full parameter support (essay_id, language, correlation_id, parallel settings)

2. **Service Integration** ✅ COMPLETED
   - `DefaultSpellLogic` in `services/spellchecker_service/implementations/spell_logic_impl.py` uses injected `SpellNormalizer`
   - DI container provides APP-scoped instance via `SpellCheckerServiceProvider.provide_spell_normalizer()`
   - All service tests passing with new implementation
   - **Deviation**: `core_logic.py` deleted entirely (no backward compatibility wrapper retained)

### Pending Components

3. **CLI Preparation** ❌ NOT STARTED
   - `scripts/ml/normalize_dataset.py` not created
   - Note: `scripts/data_preparation/prepare_ielts_task2_dataset.py` exists but only does CSV→Parquet conversion
   - Directory structure `scripts/ml/` not created

4. **Testing** ⚠️ PARTIAL
   - Basic unit tests in `libs/huleedu_nlp_shared/tests/normalization/test_spell_normalizer.py`
   - Service integration tests updated and passing
   - Missing: Comprehensive edge case coverage, regression benchmarks

5. **Documentation** ❌ NOT STARTED
   - `libs/huleedu_nlp_shared/README.md` missing (violates rule 090)
   - Service README not updated with migration notes

## Acceptance Criteria Status

- ✅ **DONE**: Spellchecker Service passes all existing tests using the shared normaliser
- ❌ **NO FLAG**: Feature flag for reverting to legacy pipeline not implemented (core_logic.py deleted)
- ⚠️ **PARTIAL**: Shared package has basic tests but not ≥90% coverage or regression benchmarks
- ❌ **NOT STARTED**: CLI `scripts/ml/normalize_dataset.py` not created
- ❌ **NOT STARTED**: Documentation incomplete (missing library README, migration guide)

## Remaining Work

1. Create `scripts/ml/normalize_dataset.py` CLI tool
2. Add comprehensive test coverage with regression benchmarks
3. Create `libs/huleedu_nlp_shared/README.md` per rule 090
4. Update service documentation with migration notes
