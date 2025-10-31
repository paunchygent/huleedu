# D-Optimal Pair Optimizer Rollout Plan

## Objective

Operationalize the Fisher-information optimizer for CJ pair planning with a unified dynamic intake workflow that supports multi-session optimization, eliminating CSV-based baseline loading in favor of direct parameter inputs.

## Critical Design Context

### The Locked Pairs vs Previous Comparisons Discovery

**Initial Misunderstanding:**
The first implementation treated "locked pairs" as historical data that the optimizer should build upon. This was incorrect.

**Actual Requirements:**
- **previous_comparisons**: Historical comparison data from past sessions that the optimizer analyzes to build complementary schedules
- **locked_pairs**: Hard constraints - pairs that MUST be included in the current schedule (rare, optional use case)

**Why This Matters:**

Multi-session workflow requires the optimizer to:
1. **Session 1**: Generate fresh comparisons with baseline coverage (no history)
2. **Session 2+**: Load previous session data, analyze coverage gaps, generate complementary comparisons

**Example Workflow:**

**Session 1 (no history):**
```bash
python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --student JA24 --student II24 --student ES24 \
  --total-slots 84 \
  --output-csv session1_pairs.csv
```

**Session 2 (building on Session 1):**
```bash
python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --student JA24 --student II24 --student ES24 \
  --previous-csv session1_pairs.csv \
  --total-slots 84 \
  --output-csv session2_pairs.csv
```

**Corrective Actions Taken:**
- Added `ComparisonRecord` dataclass for type-safe historical data representation
- Updated `DynamicSpec` with `previous_comparisons` field (separate from `locked_pairs`)
- Implemented `derive_required_student_anchor_pairs()` for coverage gap analysis
- Rewrote `optimize_from_dynamic_spec()` to use coverage analysis from baseline
- Added CLI `--previous-csv` flag and TUI "Previous Session CSV" field
- Preserved baseline loading functions (they were needed, not legacy bloat)

## Current Implementation Status

### ✅ Complete (as of 2025-11-01)

- **Dynamic Spec Schema**: `DynamicSpec` dataclass with students, anchors, previous_comparisons, locked_pairs, total_slots
- **CLI Redesign**: Replaced `--mode session/synthetic` with direct parameters (`--student`, `--previous-csv`, `--lock-pair`, etc.)
- **TUI Workflow**: Updated inputs for dynamic spec (student IDs, previous session CSV, locked pairs)
- **Optimizer Integration**: `optimize_from_dynamic_spec()` with coverage gap analysis
- **Previous Session Support**: Multi-session workflows via `--previous-csv` flag and CSV loader
- **Testing**: 50 tests passing (includes 11 new CSV loading tests)
- **Type Safety**: All type checks passing
- **Code Quality**: All linting issues resolved (0 errors)
- **Documentation**: README updated with previous_comparisons vs locked_pairs distinction
- **Status Filter Removal**: Removed legacy "core" vs "extra" status filtering from entire optimizer workflow
- **CSV Loading Tests**: Comprehensive test coverage for `load_students_from_csv()` with 11 test cases
- **Refactoring Plan**: Architectural analysis and refactoring recommendations documented for bloated files

## Completion Summary (2025-10-31)

### ✅ HIGH PRIORITY: TUI Simplification (COMPLETE)

**Implemented:**
- ✅ CSV student loading with case-insensitive column matching (`essay_id`, `student_id`, `id`)
- ✅ Case-insensitive column mapping implemented correctly (maps lowercase search key to original column name before row access)
- ✅ Manual comma-separated entry preserved as fallback
- ✅ Unified workflow: single "Generate Assignments" button creates both Pairs CSV and Assignments CSV
- ✅ Removed dual workflow toggle ("Optimize before assigning?")
- ✅ Removed separate "Optimize" button and keyboard binding
- ✅ Clearer field labels:
  - "Students CSV (optional - recommended for large cohorts)"
  - "Students (comma-separated - fallback if no CSV)"
  - "Anchors (optional - leave blank for default 12-anchor ladder)"
  - "Assignments CSV Path (final rater assignments)"
  - "Pairs CSV Path (optimized comparison pairs)"
  - "Total Comparison Slots" (was "Optimization Total Slots")
  - "Max Repetitions Per Pair (default: 3)" (was "Optimization Max Repeat")
- ✅ Updated instructions text to reflect unified workflow
- ✅ Log now shows both output paths (Pairs CSV + Assignments CSV)

**Files Modified:**
- `redistribute_tui.py`: Added CSV loader (now shared via `d_optimal_workflow`), unified workflow, renamed fields
- `README.md`: Updated TUI section with new workflow documentation

### ✅ BONUS: Dynamic Anchor Display (COMPLETE)

**Implemented:**
- ✅ Removed hardcoded `ANCHOR_DISPLAY` dictionary from `redistribute_core.py`
- ✅ Removed `display_a` and `display_b` properties from `Comparison` class
- ✅ Auto-generated sequential display names for all essays (anchors + students)
- ✅ Format: `essay_01`, `essay_02`, ..., `essay_N`
- ✅ Deterministic mapping (sorted by essay ID for reproducibility)
- ✅ Complete rater anonymization in Assignments CSV output

**Benefits:**
- Works with any anchor naming scheme (F+1, 1a, Grade-A-Low, etc.)
- Zero configuration needed
- Symmetric treatment of anchors and students
- No maintenance burden for different exam variants

**Files Modified:**
- `redistribute_core.py`: Removed hardcoded mapping, added auto-generation logic in `write_assignments()`
- `d_optimal_pairing_plan.md`: Updated architecture guidance to reflect dynamic display names
- `README.md`: Added "Anchor Flexibility" section

### ✅ LOW PRIORITY: Legacy Cleanup (COMPLETE)

**Findings:**
- ✅ `OptimizerMode` enum already removed (verified via grep)
- ✅ Baseline loading functions are NOT legacy - they support multi-session workflows
- ✅ No unused code found in `redistribute_pairs.py` or `d_optimal_workflow.py`

**Documentation Updates:**
- ✅ Removed "Prototype script (legacy)" section from README.md
- ✅ Updated `d_optimal_pairing_plan.md` to remove `ANCHOR_DISPLAY` references
- ✅ All documentation reflects current dynamic workflow

### 📊 Testing Results

**Regression Tests:**
- ✅ All 40 existing tests pass
- ✅ No test failures from dynamic display name changes
- ✅ Auto-generated display names are backward compatible
- ✅ Changes to `redistribute_core.py` and `redistribute_tui.py` don't break existing functionality

**Test Command:**
```bash
pdm run pytest-root scripts/bayesian_consensus_model/tests/ -v
# Result: 40 passed in 14.14s
```

**Coverage Notes:**
- CSV loading functionality works but not yet covered by automated tests
- Manual testing confirmed case-insensitive matching works correctly
- Future: Add dedicated CSV loading test cases

## Next Actions

### ✅ COMPLETE: Add CSV Loading Tests

**Completed 2025-11-01**

**What Was Done:**
Created comprehensive test coverage for the `load_students_from_csv()` helper function in `test_csv_loading.py`.

**Test Coverage (11 tests):**
1. Valid CSV with `essay_id` column (lowercase)
2. Valid CSV with `Essay_ID` column (mixed case) - verifies case-insensitive matching
3. Valid CSV with `student_id` column
4. Valid CSV with `id` column (fallback)
5. CSV with no matching columns → error message includes available columns
6. CSV with matching column but all empty values → clear error
7. Missing file → FileNotFoundError
8. Whitespace in values → properly stripped
9. Multiple valid columns → uses first match
10. Empty CSV file → appropriate error
11. CSV with only headers → appropriate error

**Files Added:**
- `scripts/bayesian_consensus_model/tests/test_csv_loading.py`

**Test Results:**
All 11 tests passing ✅

### ✅ COMPLETE: Remove Legacy "core" vs "extra" Status Filter

**Completed 2025-11-01**

**What Was Done:**
Successfully removed all status filtering logic from the optimizer workflow. The optimizer now treats all comparison pairs equally, as originally designed.

**Changes Made:**
1. **Core Module** (`redistribute_core.py`):
   - Removed `StatusSelector` enum completely
   - Removed `status` field from `Comparison` dataclass
   - Removed `filter_comparisons()` function
   - Updated `select_comparisons()` to remove `include_status` parameter
   - Updated `read_pairs()` to not require/use status column
   - Updated `write_assignments()` to remove status from output CSV

2. **Workflow Module** (`d_optimal_workflow.py`):
   - Removed `status` field from `ComparisonRecord` dataclass
   - Removed `status_filter` field from `BaselinePayload` dataclass
   - Updated all functions to remove status filtering logic
   - Updated `write_design()` to remove status parameter and column from CSV output

3. **CLI** (`redistribute_pairs.py`):
   - Removed `--include-status` flag from `redistribute` command
   - Updated command logic to use all comparisons without filtering

4. **TUI** (`redistribute_tui.py`):
   - Removed status dropdown UI element
   - Removed status handling in `_generate_assignments()` method

5. **Tests** (`test_redistribute.py`):
   - Updated all 50 tests to remove status references
   - All tests passing after status removal

6. **Documentation**:
   - Updated `README.md` to remove `--include-status` flag examples
   - Updated troubleshooting section to remove status filter references

**Design Rationale:**
The status filter was legacy from pre-dynamic-spec workflow. The correct approach is to specify the exact number of desired slots upfront via `--total-slots N`, allowing the optimizer to generate N optimal pairs treating all pairs equally. Arbitrarily filtering pairs after optimization breaks the Fisher-information design.

### 🔧 NEXT: Code Organization Refactoring

**Problem Identified:**
Two files violate the **400-500 LoC hard limit** from `.cursor/rules/015-project-structure-standards.mdc`, mixing multiple responsibilities in violation of the Single Responsibility Principle:

| File | Lines | Violation | Overage |
|------|-------|-----------|---------|
| `d_optimal_workflow.py` | 788 | ❌ **CRITICAL** | 288 lines (57%) |
| `redistribute_tui.py` | 523 | ❌ **MODERATE** | 23 lines (5%) |

#### `d_optimal_workflow.py` Analysis (788 lines)

**Current Mixed Responsibilities:**
1. **Data Loading** (CSV, JSON payload parsing) - 4 functions, ~167 lines
2. **Data Validation & Spec Building** - 1 function, ~75 lines
3. **Workflow Orchestration** (multiple optimization entry points) - 4 functions, ~251 lines
4. **Design Analysis & Diagnostics** - 2 functions, ~90 lines
5. **CSV Writing** - 1 function, ~16 lines
6. **Synthetic Data Generation** - 2 functions, ~94 lines

**Proposed Solution: Split into Focused Package**

```
scripts/bayesian_consensus_model/
├── d_optimal_workflow/              # NEW: Package structure
│   ├── __init__.py                  # Exports public API (backward compatibility)
│   ├── data_loaders.py              # ~150 lines
│   │   - load_baseline_design()
│   │   - load_baseline_payload()
│   │   - load_baseline_from_records()
│   │   - load_previous_comparisons_from_csv()
│   │   - load_dynamic_spec()
│   ├── design_analysis.py           # ~120 lines
│   │   - summarize_design()
│   │   - derive_student_anchor_requirements()
│   │   - DesignDiagnostics dataclass
│   ├── optimization_runners.py      # ~200 lines
│   │   - optimize_from_payload()
│   │   - optimize_schedule()
│   │   - optimize_from_dynamic_spec()
│   ├── synthetic_data.py            # ~100 lines
│   │   - run_synthetic_optimization()
│   │   - _build_random_design()
│   └── io_utils.py                  # ~80 lines
│       - write_design()
│       - CSV/JSON writing utilities
```

**Shared Models** (in `__init__.py` or separate `models.py`):
- `OptimizationResult`, `BaselinePayload`, `ComparisonRecord`, `DynamicSpec`
- `DEFAULT_ANCHOR_ORDER`

#### `redistribute_tui.py` Analysis (523 lines)

**Current Mixed Responsibilities:**
1. **Textual UI Definition** (app structure, widgets, layout) - ~250 lines
2. **Business Logic** (CSV loading, optimization, assignment generation) - ~150 lines
3. **Event Handling** (button clicks, form validation) - ~100 lines

**Proposed Solution: Extract Shared Utilities**

Option 1 (Minimal): Move `load_students_from_csv()` to `d_optimal_workflow/io_utils.py` (shared utility)
- Reduces `redistribute_tui.py` to ~450 lines (acceptable)
- No package restructuring needed

Option 2 (Comprehensive): Split into package if further growth expected:
```
scripts/bayesian_consensus_model/
├── tui/                             # NEW: Package structure
│   ├── __init__.py                  # Exports RedistributeApp
│   ├── app.py                       # ~200 lines (UI structure only)
│   ├── handlers.py                  # ~200 lines (event handlers, validation)
│   └── data_loaders.py              # ~100 lines (CSV parsing, error handling)
```

**Recommendation:** Start with Option 1 (move shared utility), assess if Option 2 needed later.

#### Benefits of Refactoring

1. **Adherence to Standards**: All files under 500 LoC hard limit
2. **Single Responsibility**: Each module has one clear purpose
3. **Testability**: Focused unit tests per module (easier to write and maintain)
4. **Maintainability**: Easier code review, debugging, and future enhancements
5. **Alignment**: Follows project's DDD/Clean Code principles

#### Backward Compatibility Strategy

Use `__init__.py` re-exports to maintain existing import paths:

**Before:**
```python
from scripts.bayesian_consensus_model.d_optimal_workflow import (
    optimize_from_dynamic_spec,
    load_dynamic_spec,
    write_design,
)
```

**After (with re-exports):**
```python
# Same imports work - no breaking changes
from scripts.bayesian_consensus_model.d_optimal_workflow import (
    optimize_from_dynamic_spec,  # Re-exported from optimization_runners
    load_dynamic_spec,            # Re-exported from data_loaders
    write_design,                 # Re-exported from io_utils
)
```

#### Implementation Checklist

**Phase 1: `d_optimal_workflow.py` Refactoring**
- [x] Create package directory: `d_optimal_workflow/`
- [x] Create `__init__.py` with public API re-exports
- [x] Split into 5 focused modules (data_loaders, design_analysis, optimization_runners, synthetic_data, io_utils)
- [x] Update imports in dependent files:
  - [x] `redistribute_pairs.py`
  - [x] `redistribute_tui.py`
  - [x] Removed legacy `d_optimal_prototype.py`
- [x] Run type checking: `pdm run typecheck-all` *(fails on existing SQLAlchemy `rowcount` annotations in identity_service/class_management/batch_orchestrator modules; unchanged by this refactor)*
- [x] Run regression tests: `pdm run pytest-root scripts/bayesian_consensus_model/tests/test_redistribute.py` and `pdm run pytest-root scripts/bayesian_consensus_model/tests/test_csv_loading.py`
- [x] Run linting: `pdm run ruff check scripts/bayesian_consensus_model/`

**Phase 2: `redistribute_tui.py` Cleanup**
- [x] Extract `load_students_from_csv()` to `d_optimal_workflow/io_utils.py`
- [x] Update imports in `redistribute_tui.py`
- [x] Verify line count reduction to ~500 lines (current: 492)
- [x] Run tests and validation (commands above)

**Success Criteria:**
✅ All files under 500 LoC
✅ Each module has single, clear responsibility
✅ No breaking changes to public API
✅ All 50+ tests passing
⚠️ Type checking command still reports pre-existing `rowcount` typing errors outside optimizer modules
✅ Linting passes

**Estimated Effort:**
- Phase 1: 3-4 hours
- Phase 2: 1-2 hours
- Testing & Validation: 1-2 hours
- **Total**: 5-8 hours

**Risk Assessment:** Low
- Primarily structural refactoring (moving code, not changing logic)
- Backward compatibility maintained via re-exports
- Comprehensive test coverage (50+ tests)
- Type checker will catch import issues early

### 🔮 FUTURE (Lower Priority)

- **Per-rater quota flexibility**: Accept heterogeneous per-rater counts for precise assignment control (e.g., some raters do 8 comparisons, others do 12)
