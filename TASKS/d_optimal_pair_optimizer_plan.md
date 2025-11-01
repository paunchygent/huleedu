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

## Active Tasks

### 🔧 NEXT: Auto-Calculate Total Slots from Rater Settings

**Problem:**
The TUI has two independent inputs that users must manually sync:
- "Total Comparison Slots" (optimizer input) - default: 24
- "Number of Raters" × "Comparisons Per Rater" (assignment inputs) - default: 14 × 10 = 140

This creates confusion and mismatch potential. The optimizer generates pairs based on "Total Slots" regardless of rater settings.

**Current Workflow:**
1. `_run_optimizer()` reads "Total Comparison Slots" → generates N pairs
2. `_generate_assignments()` reads rater settings → expects M pairs
3. If N ≠ M, shortage/excess handling kicks in (unintended)

**Root Cause:**
Lines 392-396 in `redistribute_tui.py`:
```python
slots_raw = self.query_one("#optimizer_slots_input", Input).value.strip()
if not slots_raw:
    raise ValueError("Total slots is required for optimization.")
total_slots = int(slots_raw)
```

The optimizer receives a manual `total_slots` value instead of deriving it from rater configuration.

**Solution: Auto-Calculate from Rater Settings**

Remove "Total Comparison Slots" input and calculate automatically:
```
total_slots = Number of Raters × Comparisons Per Rater
```

**Benefits:**
- Eliminates duplicate/conflicting inputs
- Prevents user confusion and sync errors
- Simplifies UI (one less field)
- Follows DRY principle (derive, don't duplicate)
- Users can still adjust via rater settings if needed

**Implementation Plan:**

**1. UI Changes (`redistribute_tui.py`)**

Remove:
- Lines 202-208: "Total Comparison Slots" input field and label
- Line 256: Reset value for slots field in `_reset_form()`
- Lines 392-396: Manual slots reading in `_run_optimizer()`

Add (in `_run_optimizer()`, before building spec):
```python
# Calculate total slots from rater configuration
names_raw = self.query_one("#rater_names_input", Input).value.strip()
count_raw = self.query_one("#rater_count_input", Input).value.strip()
per_rater_raw = self.query_one("#per_rater_input", Input).value.strip()

per_rater = int(per_rater_raw) if per_rater_raw else 10
if per_rater <= 0:
    raise ValueError("Comparisons per rater must be positive.")

if names_raw:
    names = build_rater_list(None, [names_raw])
else:
    if not count_raw:
        raise ValueError("Provide a rater count or explicit rater names.")
    count = int(count_raw)
    names = build_rater_list(count, None)

total_slots = len(names) * per_rater
log_widget.write(f"Generating {total_slots} pairs for {len(names)} raters × {per_rater} comparisons")
```

**2. Legacy Code Cleanup**

Remove all references to manual total_slots input:
- DEFAULT constant if only used for slots field
- Any helper text or documentation mentioning "Total Comparison Slots"
- Validation logic for manual slots value

**3. Update Instructions Text**

Lines 225-229: Update instructions to remove mention of "Total Slots":
```python
yield Static(
    "Load students via CSV (recommended) or comma-separated entry. "
    "Set rater count and comparisons per rater. "
    "Generate Assignments runs the optimizer to create comparison pairs, "
    "then distributes them to raters. Outputs: Pairs CSV + Assignments CSV.",
    id="instructions",
)
```

**4. Testing Validation**

Before:
- User sets slots=24, raters=14, per_rater=10
- Optimizer generates 24 pairs
- Assignment phase expects 140 pairs → shortage warning

After:
- User sets raters=14, per_rater=10
- Optimizer automatically generates 140 pairs
- Assignment phase gets exactly 140 pairs → no shortage

**Files Modified:**
- `redistribute_tui.py`: Remove slots input, add auto-calculation logic
- `README.md`: Update TUI documentation to reflect new workflow

**Success Criteria:**
- ✅ "Total Comparison Slots" field removed from UI
- ✅ Optimizer generates exactly `num_raters × per_rater` pairs
- ✅ No shortage/excess warnings in normal workflow
- ✅ All existing tests still pass
- ✅ Manual testing confirms correct pair count generation
- ✅ Code remains under 500 LoC limit
- ✅ No orphaned constants or validation logic

**Estimated Effort:** 1-2 hours

**Risk Assessment:** Low
- Straightforward calculation replacement
- No complex logic changes
- Existing tests validate optimizer behavior
- User-facing simplification (fewer inputs = less error-prone)
