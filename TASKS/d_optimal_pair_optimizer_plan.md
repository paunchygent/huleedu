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

## Current Implementation Status (2025-11-01)

### ✅ Complete

**Core Features:**
- Dynamic Spec Schema with students, anchors, previous_comparisons, locked_pairs, total_slots
- CLI with direct parameters (`--student`, `--previous-csv`, `--lock-pair`)
- TUI with unified workflow (single "Generate Assignments" button)
- Multi-session support via previous comparisons CSV loading
- CSV student loading with case-insensitive column matching
- Dynamic anchor display (auto-generated essay_01, essay_02, etc.)
- Status filter removal (legacy "core" vs "extra" filtering eliminated)

**Quality Metrics:**
- 50+ tests passing (includes 11 CSV loading tests)
- Type checks passing
- Linting clean (0 errors)
- Code organization: All files under 500 LoC after refactoring

**Documentation:**
- README updated with current workflow
- CSV loading test coverage documented
- Previous_comparisons vs locked_pairs distinction clarified

## Completed Work Summary

### ✅ TUI Simplification
- CSV student loading with fallback to manual entry
- Unified workflow: single button generates both pairs and assignments
- Clearer field labels and instructions
- Dynamic anchor display (no hardcoded mappings)

### ✅ Status Filter Removal
- Removed `StatusSelector` enum, `status` field from `Comparison`, `filter_comparisons()` function
- Updated all modules: `redistribute_core.py`, `d_optimal_workflow`, CLI, TUI
- Design rationale: Status filtering breaks Fisher-information design; specify exact slots upfront instead

### ✅ Code Organization Refactoring
- Split bloated `d_optimal_workflow.py` (788 lines) into focused package:
  - `data_loaders.py`, `design_analysis.py`, `optimization_runners.py`, `synthetic_data.py`, `io_utils.py`
- Moved `load_students_from_csv()` to shared utilities
- All modules now under 500 LoC hard limit
- Backward compatibility maintained via `__init__.py` re-exports

### ✅ CSV Loading Tests
- 11 comprehensive test cases covering column matching, error handling, whitespace normalization, empty file detection
- All tests passing

## Completed Tasks (2025-11-01 Session)

### ✅ Auto-Calculate Total Slots from Rater Settings

**Completed:** 2025-11-01

**Implementation Summary:**
- Removed "Total Comparison Slots" input field from TUI
- Auto-calculate `total_slots = num_raters × per_rater` in `_run_optimizer()`
- Updated instructions text to reflect simplified workflow
- Removed orphaned `DEFAULT_PAIRS` constant

**Files Modified:**
- `redistribute_tui.py`: Removed manual slots input, added auto-calculation (498 LoC)
- Tests: All 47 tests passing

**Results:**
- ✅ UI simplified (one less confusing input)
- ✅ Optimizer generates exact pairs needed for rater assignments
- ✅ No shortage/excess warnings in normal workflow
- ✅ File size: 498 LoC (under 500 LoC limit)

---

### ✅ Dead Code Removal: Legacy Baseline Workflow

**Completed:** 2025-11-01

**Implementation Summary:**
Removed all legacy baseline CSV workflow code that was replaced by dynamic spec workflow.

**Removed from `d_optimal_workflow/__init__.py`:**
- 12 unused exports (60% reduction: 20 → 8 exports)
- Legacy functions: `load_baseline_design`, `load_baseline_from_records`, `load_baseline_payload`, `optimize_from_payload`
- Internal-only functions: `optimize_schedule`, `derive_student_anchor_requirements`, `summarize_design`, `unique_pair_count`, `run_synthetic_optimization`
- Test-only types: `DEFAULT_ANCHOR_ORDER`, `ComparisonRecord`, `BaselinePayload`

**Removed from `test_redistribute.py`:**
- 3 legacy test functions (~70 lines)
- Inlined test-only constants for remaining tests

**Files Modified:**
- `d_optimal_workflow/__init__.py`: Cleaned public API to 8 exports
- `test_redistribute.py`: Removed 3 legacy tests (50 → 47 tests)

**Results:**
- ✅ All 47 tests passing
- ✅ Clean public API (only actively used exports)
- ✅ Type checking passes
- ✅ Linting passes

---

### ✅ Import Structure Simplification

**Completed:** 2025-11-01

**Implementation Summary:**
Removed complex try/except import blocks and sys.path hacks, replaced with clean absolute imports matching project standards.

**Before (58 lines):**
```python
import sys
if __package__ in (None, ""):
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from .d_optimal_workflow import (...)
    from .redistribute_core import (...)
except ImportError:
    from scripts.bayesian_consensus_model.d_optimal_workflow import (...)
    from scripts.bayesian_consensus_model.redistribute_core import (...)
```

**After (27 lines):**
```python
from pathlib import Path
from typing import Optional

from scripts.bayesian_consensus_model.d_optimal_workflow import (...)
from scripts.bayesian_consensus_model.redistribute_core import (...)
```

**Files Modified:**
- `redistribute_tui.py`: Removed 31 lines of import complexity
- `redistribute_pairs.py`: Removed 31 lines of import complexity

**Results:**
- ✅ All 47 tests passing
- ✅ CLI works: `pdm run python -m scripts.bayesian_consensus_model.redistribute_pairs --help`
- ✅ TUI imports successfully
- ✅ No sys.path hacks
- ✅ Consistent with project standards
- ✅ Type checking passes
- ✅ Linting passes

---

## Active Tasks

### 🔧 NEXT: PyInstaller Standalone Executables (Optional Enhancement)

**Status:** Plan created in `TASKS/pyinstaller_standalone_executables_plan.md`

**Objective:**
Create standalone executable binaries for `redistribute-tui` and `redistribute-pairs` using PyInstaller `--onefile` mode.

**Benefits:**
- True standalone executables (no Python installation required)
- Single-file distribution (~25-35MB per executable)
- Copy to `/usr/local/bin/` or distribute to non-developers
- 1-3 second startup time (acceptable for interactive tools)

**See:** `TASKS/pyinstaller_standalone_executables_plan.md` for complete implementation guide.

**Estimated Effort:** ~60 minutes

