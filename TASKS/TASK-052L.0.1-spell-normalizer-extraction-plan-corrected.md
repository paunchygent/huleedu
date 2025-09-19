# TASK-052L.0.2 — Spell Normalizer Extraction Implementation Plan (Lean Revision) ✅ COMPLETED

## Status: COMPLETED (2025-09-19)

### Implementation Summary
Successfully extracted spell correction pipeline to `libs/huleedu_nlp_shared/normalization/`. Service integration via DI working with all tests passing.

### Key Deviations from Plan:
- **`core_logic.py` deleted**: No backward compatibility wrapper retained
- **L2 dictionary loading**: Remains in service DI layer, not moved to shared lib
- **No feature flag**: Legacy pipeline completely removed, no rollback option

## Objective

Extract the existing spell correction pipeline from `services/spellchecker_service` into the shared library `libs/huleedu_nlp_shared` with the smallest possible surface area change. The new module must expose the current behaviour verbatim so runtime services and future local CLI tooling reuse exactly the same code path.

## Guiding Principles

- Pure extraction: no new features, no extra configuration layers, no behavioural changes.
- Reuse existing service dependencies (settings, whitelist, parallel processor, logging); do not duplicate them in the shared package.
- Keep startup performance identical by loading the L2 dictionary once through DI, not per-request.
- Maintain `_spellchecker_cache` caching semantics and structured logging fields.
- Make adoption incremental: service keeps the legacy wrapper so regression tests can compare both implementations.

## Phase 1: Create Shared Library Structure

### 1.1 Create Package Structure

```bash
# Create directories
mkdir -p libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization
mkdir -p libs/huleedu_nlp_shared/tests/normalization

# Create package files
touch libs/huleedu_nlp_shared/pyproject.toml
touch libs/huleedu_nlp_shared/src/huleedu_nlp_shared/__init__.py
touch libs/huleedu_nlp_shared/src/huleedu_nlp_shared/py.typed
```

### 1.2 Package Configuration

Minimal project metadata (name, version, description, build backend) so `pdm` can install the library from a local path. Dependencies stay empty at the package level; consumers provide the service components during construction.

## Phase 2: Extract Core Components

### 2.1 Files to Extract From (CORRECTED LINE NUMBERS)

#### VERIFIED SOURCE FILES

1. **`services/spellchecker_service/core_logic.py`**
   - Function: `default_perform_spell_check_algorithm` (lines 44-551)
   - Global: `_spellchecker_cache` (line 41)

2. **`services/spellchecker_service/spell_logic/l2_dictionary_loader.py`**
   - Function: `load_l2_errors` (lines 37-102)

3. **`services/spellchecker_service/spell_logic/l2_filter.py`**
   - Function: `filter_l2_entries` (line 94 onwards)
   - Class: `L2CorrectionFilter` (line 22 onwards)

4. **`services/spellchecker_service/implementations/whitelist_impl.py`**
   - Class: `DefaultWhitelist` (entire file)
   - **NOTE**: Constructor takes Settings object, not path

5. **`services/spellchecker_service/implementations/parallel_processor_impl.py`**
   - Class: `DefaultParallelProcessor` (entire file)
   - Function: `get_adaptive_edit_distance` (lines 18-36)
   - Constructor: `__init__` (lines 41-45) - initializes from settings
   - Method: `process_corrections_parallel` (lines 46-145)

6. **`services/spellchecker_service/protocols.py`**
   - Protocol: `WhitelistProtocol` (lines 69-81)
   - Protocol: `ParallelProcessorProtocol` (lines 84 onwards)

### 2.2 Core Algorithm Migration Strategy

- Create `normalization/models.py` containing `SpellNormalizationResult`, mirroring the existing `SpellcheckMetrics` fields and validation. No extra helpers (`to_feature_dict`, etc.) are added in this extraction phase.
- Implement `normalization/spell_normalizer.py` with a `SpellNormalizer` class that accepts constructor dependencies:
  - `l2_errors: dict[str, str]`
  - `whitelist: WhitelistProtocol`
  - `parallel_processor: ParallelProcessorProtocol`
  - `settings: Settings` (for logging paths and feature flags)
  - `logger: Logger`
  - Optional clock/test hooks as needed by current unit tests
- Move the algorithm from `default_perform_spell_check_algorithm` into a `normalize_text(...)` method on the class, preserving `_spellchecker_cache` as a module-level singleton (shared with the existing function via import).
- Export a thin function `normalize_text(...)` that forwards to a shared default instance when used outside DI contexts (parity with existing module-level function usage).

### 2.3 Dependency Strategy

- Do **not** duplicate dictionary loaders, whitelist implementations, or parallel processor logic inside the shared package. Instead, import the service implementations in the DI layer and hand them to `SpellNormalizer`.
- The shared package only contains the result model, the spell normalizer class, protocol definitions (if needed for typing), and the reusable algorithm body.
- Keep the existing file paths (`settings.effective_filtered_dict_path`, correction log directory) untouched by reading them from the injected `settings` object.

## Phase 3: Update Spellchecker Service (CORRECTED)

### 3.1 Dependency Injection

- In `services/spellchecker_service/di.py`, register an APP-scoped `SpellNormalizer` built from the already-provided `Settings`, `WhitelistProtocol`, and `ParallelProcessorProtocol`. Load the L2 dictionary once here (`load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)`) and pass the resulting dict into the normalizer constructor.
- Update `DefaultSpellLogic` to accept the shared normalizer as a dependency. Remove its private L2 dictionary cache and delegate to `SpellNormalizer.normalize_text(...)` while preserving existing error handling, logging, and storage steps.
- Keep `default_perform_spell_check_algorithm` as a thin wrapper that constructs a temporary `SpellNormalizer` for backwards compatibility and to support existing tests. Mark it for deprecation once the service and tooling fully adopt the shared class.

### 3.2 Service Metadata

- Append the shared library to `services/spellchecker_service/pyproject.toml` dependencies (`"huleedu-nlp-shared @ file:///${PROJECT_ROOT}/libs/huleedu_nlp_shared"`).
- Add the same editable install to the root `pyproject.toml` dev dependency group so local development picks it up automatically.

## Phase 4: Testing & Validation

### 4.1 Regression Coverage

- Add shared library unit tests that instantiate `SpellNormalizer` with service fixtures and assert equality with `default_perform_spell_check_algorithm` outputs on representative essays.
- Update existing spellchecker service tests to use the injected normalizer path (especially `test_core_logic.py`) and add a regression test ensuring the wrapper and shared class stay in lockstep.
- Ensure the new package is included in coverage reports and CI by extending the relevant `pytest-root` invocations if needed.

## Critical Implementation Checklist

### BEFORE Starting

- [ ] Verify `services/spellchecker_service/core_logic.py` lines 44-551
- [ ] Verify `services/spellchecker_service/spell_logic/l2_dictionary_loader.py` exists
- [ ] Verify `services/spellchecker_service/implementations/whitelist_impl.py` exists
- [ ] Verify `services/spellchecker_service/implementations/parallel_processor_impl.py` exists
- [ ] Confirm whitelist directory path in deployment environment

### MUST PRESERVE

- [ ] Global `_spellchecker_cache` dictionary
- [ ] Single dictionary load per process (no per-request file IO)
- [ ] Exact algorithm implementation (no optimisations, identical logging fields)
- [ ] Error handling patterns and metrics logging

### MUST NOT

- [ ] Change any algorithm logic
- [ ] Add new features or optimisations
- [ ] Modify error messages
- [ ] Introduce new configuration surfaces
- [ ] Create multiple parallel processing implementations

## Acceptance Criteria

1. **Functional Parity**: Shared normalizer produces identical output compared to `default_perform_spell_check_algorithm`.
2. **Performance**: No regression (<5% difference) in processing time across representative samples.
3. **Testing**: Updated service and shared-library test suites pass, including regression comparisons.
4. **Backward Compatibility**: Legacy wrapper remains available for transitional callers until all consumers migrate.
5. **Documentation**: Task notes and service README updated to describe the shared normalizer usage.

## Files Summary (CORRECTED)

- `libs/huleedu_nlp_shared/pyproject.toml`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/__init__.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/py.typed`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/__init__.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/models.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/spell_normalizer.py`
- `libs/huleedu_nlp_shared/tests/normalization/test_spell_normalizer.py`

### Files Modified

- `pyproject.toml` (root) — register editable dependency for the shared library
- `services/spellchecker_service/pyproject.toml` — add dependency on the shared library
- `services/spellchecker_service/core_logic.py` — refactor wrapper to delegate to shared normalizer
- `services/spellchecker_service/di.py` — provide shared normalizer instance via Dishka
- `services/spellchecker_service/implementations/spell_logic_impl.py` — inject and consume the shared normalizer
- `services/spellchecker_service/tests/` — update/extend regression coverage
