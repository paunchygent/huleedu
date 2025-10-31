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

### ✅ Complete (as of 2025-10-31)

- **Dynamic Spec Schema**: `DynamicSpec` dataclass with students, anchors, previous_comparisons, locked_pairs, total_slots
- **CLI Redesign**: Replaced `--mode session/synthetic` with direct parameters (`--student`, `--previous-csv`, `--lock-pair`, etc.)
- **TUI Workflow**: Updated inputs for dynamic spec (student IDs, previous session CSV, locked pairs)
- **Optimizer Integration**: `optimize_from_dynamic_spec()` with coverage gap analysis
- **Previous Session Support**: Multi-session workflows via `--previous-csv` flag and CSV loader
- **Testing**: 26 tests passing (Session 1, Session 2+, CLI/TUI integration, coverage analysis)
- **Type Safety**: All type checks passing
- **Documentation**: README updated with previous_comparisons vs locked_pairs distinction

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
- `redistribute_tui.py`: Added `_load_students_from_csv()` helper, unified workflow, renamed fields
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

### 🧪 HIGH PRIORITY: Add CSV Loading Tests

**Context:**
The `_load_students_from_csv()` helper function works correctly (manually verified) but lacks automated test coverage.

**Key Implementation Detail:**
Function builds `{lowercase_name: original_name}` mapping first, then uses original column name to access row data. This prevents errors with mixed-case headers like `Essay_ID`.

**Test scenarios needed in `test_redistribute.py`:**
1. Valid CSV with `essay_id` column (lowercase)
2. Valid CSV with `Essay_ID` column (mixed case) - verifies case-insensitive matching
3. Valid CSV with `student_id` column
4. Valid CSV with `id` column (fallback)
5. CSV with no matching columns → error message includes available columns
6. CSV with matching column but all empty values → clear error
7. Missing file → FileNotFoundError
8. Whitespace in values → properly stripped

**Import:**
```python
from scripts.bayesian_consensus_model.redistribute_tui import _load_students_from_csv
```

**Estimated Effort:** 1 hour

### 🔧 HIGH PRIORITY: Remove Legacy "core" vs "extra" Status Filter

**Problem Identified:**
The `StatusSelector` filter (core/all) is legacy from pre-dynamic-spec workflow and breaks optimizer design:
1. Optimizer generates N pairs with Fisher-information maximization treating ALL pairs equally
2. Arbitrarily filtering "extra" pairs (e.g., keeping only 1-84, discarding 85-140) breaks the optimized design
3. Users should specify `--total-slots 84` or `--total-slots 140` directly, not generate 140 then filter to 84

**Correct Workflow:**
- Need 84 slots? → `--total-slots 84` → optimizer generates 84 optimal pairs
- Need 140 slots? → `--total-slots 140` → optimizer generates 140 optimal pairs
- DON'T: Generate 140, mark some as "extra", filter to 84

**Investigation Needed:**
1. Trace where "core" vs "extra" status gets assigned
2. Determine if this distinction serves any valid purpose in current workflow
3. If not: Remove `StatusSelector`, remove status filtering, simplify assignment logic
4. If yes: Document the actual purpose (currently unclear)

**Files to investigate:**
- `redistribute_core.py`: `StatusSelector` enum, `filter_comparisons()`
- `d_optimal_workflow.py`: `write_design()` - all pairs get same status
- `redistribute_pairs.py` CLI: `--include-status` flag
- `redistribute_tui.py`: Status selection dropdown

**Estimated Effort:** 2-3 hours (investigation + removal if legacy)

### 🔮 FUTURE (Lower Priority)

- **Per-rater quota flexibility**: Accept heterogeneous per-rater counts for precise assignment control (e.g., some raters do 8 comparisons, others do 12)
