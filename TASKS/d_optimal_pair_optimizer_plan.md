# D-Optimal Pair Optimizer Rollout Plan

## Objective

Operationalize the new Fisher-information optimizer for CJ pair planning, integrate it into existing tooling, and remediate assignment imbalances so each rater receives a balanced workload.

## Workstreams

### 1. CLI & TUI Integration

1. ✅ **Typer command**: `optimize-pairs` now lives in `redistribute_pairs.py` with session and synthetic modes, `total_slots`, `max_repeat`, and optional JSON diagnostics (`--report-json`).
2. ✅ **Textual TUI**: `redistribute_tui.py` includes optimization inputs, a dedicated Optimize action, and an "optimize before assigning" toggle.
3. ✅ **Compatibility**: Optimized CSVs reuse the legacy schema, and new smoke tests under `tests/test_redistribute.py` validate the Typer command and loader compatibility.
4. ✅ **Automation hooks**: Pipelines can call `python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs ...` directly; JSON diagnostics enable offline verification.
5. 🚧 **Shortage-aware allocation**: Plan to auto-scale per-rater quotas when the requested load exceeds the available comparison pool. Update CLI/TUI prompts with a warning banner and surface actual allocations (min/max per rater) in the success summary.
6. 🚧 **Per-rater quota flexibility**: Extend `assign_pairs` to accept heterogeneous per-rater counts so the redistribution layer can supply precise quotas after shortage reconciliation.

### 2. Documentation & Diagnostics
1. ✅ Updated `scripts/bayesian_consensus_model/README.md` and `SESSION_2_PAIRING_PLAN.md` with CLI/TUI workflows, slot guidance, and verification steps (team docs still reference this plan).
2. ✅ Added `summarize_design` plus CLI/TUI reporting of comparison mix, student-anchor coverage, and repeat counts (see `d_optimal_workflow.py`).
3. ✅ Documented troubleshooting steps in `scripts/bayesian_consensus_model/README.md` (see "Troubleshooting" subsection).

### 3. Assignment Distribution Improvements
1. ✅ Gap analysis confirmed sequential chunking caused anchor-only loads; regression test added to lock expected variety.
2. ✅ Implemented type-aware greedy balancing inside `redistribute_core.assign_pairs` ensuring every rater receives student-anchor work when available.
3. ✅ Balancing lives in the redistribution layer with `_RaterAllocation` tracking (documented via new unit test).
4. ✅ README + session plan now describe the balanced allocator; HANDOFF will summarize latest behaviour in this task update.
5. 🚧 **Scarcity tests**: Add unit + CLI tests that simulate fewer optimized pairs than requested and assert graceful down-scaling plus balanced type distribution across the adjusted assignments.

### 4. Unified Dynamic Intake (new single workflow)
1. 🚧 **Input schema definition**
   - Author a new payload schema (JSON + CLI flags) that captures:
     - `students`: arbitrarily named essay IDs to include in pairing.
     - `anchors`: ordered anchor ladder (defaults to `DEFAULT_ANCHOR_ORDER`, overridable).
     - `include_anchor_anchor`: boolean toggle (default true) controlling candidate universe generation.
     - `locked_pairs`: optional array of already-committed comparison pairs (each with `essay_a_id`, `essay_b_id`, optional `status`).
     - `total_slots`: required integer slot budget; must meet minimum inferred from adjacency + locked pairs.
   - Document schema and validation rules in `scripts/bayesian_consensus_model/README.md` and HANDOFF.

2. 🚧 **Optimizer ingestion**
   - Add a new `load_dynamic_spec()` helper that converts the schema above into:
     - Anchor list + student list.
     - Locked `DesignEntry`s (marked `locked=True`) for reuse by `select_design`.
     - Derived candidate flags (`include_student_student`, `include_anchor_anchor`).
   - Update `optimize_schedule` to accept this spec in place of CSV/legacy payloads, building the baseline internally by:
     - Adding locked pairs directly.
     - Injecting anchor adjacency constraints.
     - Deriving required student-anchor coverage targets using the same bracket logic as today.
   - Remove code paths that load baseline CSVs/JSON comparisons dumps once the new spec is wired end-to-end.

3. 🚧 **CLI redesign**
   - Replace `--pairs-csv` / `--baseline-json` options with:
     - `--student` (repeatable or comma-delimited), `--anchor` (optional override), `--total-slots`, `--include-anchor-anchor/--no-include-anchor-anchor`.
     - `--lock-pair` for pre-committed comparisons (repeatable flag).
     - Validation that `total_slots >= result.min_slots_required` before invoking the optimizer (reuse helper).
   - Maintain existing command layout and messages (Typer app structure) but point execution at dynamic spec builder.
   - Update JSON diagnostics to include the supplied dynamic spec (students, anchors, locked pairs, inclusion flags).

4. 🚧 **TUI workflow replacement**
   - Reuse the current layout (inputs, buttons, TextLog) but repurpose fields:
     - `Pairs CSV Path` → `Student Essay IDs (comma-separated)`.
     - Add dedicated input for optional anchor list override.
     - Keep per-rater/per-slot inputs and optimizer toggle (now always “yes” because optimizer is the generator).
     - Replace baseline JSON input with multi-line text entry for locked pairs (one `essay_a_id,essay_b_id` per line).
   - Adjust `_generate_assignments` to:
     - Build the dynamic spec from form fields.
     - Invoke the optimizer directly (no intermediate CSV load).
     - Pass optimized design to existing quota + assignment logic.
   - Carefully retain existing Textual widget usage (do not change widget classes or layout containers).

5. 🚧 **Legacy removal & migration**
   - Delete helpers no longer used (`read_pairs`, `load_baseline_payload`, etc.) if they are only referenced by the retired flow; migrate shared utilities (e.g., `load_comparisons_from_records`) into the dynamic path or archive them if tests require.
   - Update tests to:
     - Cover dynamic spec ingestion (unit tests for validator).
     - Exercise CLI/TUI flows via Typer/Textual harness using the new flags/inputs.
     - Remove legacy tests that reference CSV/JSON baseline inputs.
   - Refresh documentation (README, HANDOFF, session plan) to describe the streamlined workflow and removal of CSV-based paths.

## Deliverables
- Updated Typer/TUI commands capable of producing balanced, optimized schedules.
- New diagnostics/summary outputs ensuring operators can validate each run.
- Revised documentation & handoff materials reflecting the new workflow.
- Assignment balancing design ready for implementation (or implemented, per schedule).
- Dynamic intake plan aligning optimizer, CLI, TUI, and forthcoming API surface with a single, easier-to-use pipeline.

---

## Implementation Progress (2025-10-31)

### ✅ Completed Work

#### 4.1 Input Schema Definition
**Status: COMPLETE**

Created `DynamicSpec` dataclass in `d_optimal_workflow.py`:
- `students`: List of student essay IDs
- `anchors`: Ordered anchor ladder (defaults to `DEFAULT_ANCHOR_ORDER`)
- `include_anchor_anchor`: Boolean toggle for anchor-anchor comparisons
- `locked_pairs`: List of tuples `(essay_a_id, essay_b_id)`
- `total_slots`: Required integer slot budget

Implemented `load_dynamic_spec()` with full validation:
- Validates non-empty students and anchors lists
- Validates total_slots meets minimum (anchor adjacency + locked pairs)
- Validates locked pair essay IDs reference known essays
- Returns validated `DynamicSpec` object

#### 4.2 Optimizer Ingestion
**Status: COMPLETE**

Implemented `optimize_from_dynamic_spec()` bridge function:
- Converts locked pairs to `DesignEntry` objects with `locked=True` flag
- Passes `include_anchor_anchor` flag to `select_design()`
- Builds baseline design from locked pairs only (no CSV/JSON required)
- Returns full `OptimizationResult` with diagnostics

Updated `select_design()` in `d_optimal_optimizer.py`:
- Added `include_anchor_anchor` parameter
- Passes flag to `build_candidate_universe()` for proper candidate filtering

#### 4.3 CLI Redesign
**Status: COMPLETE**

Completely rewrote `optimize-pairs` command in `redistribute_pairs.py`:
- **New parameters:**
  - `--student` / `-s`: Repeatable option for student IDs (also accepts comma-delimited)
  - `--anchors` / `-a`: Optional comma-separated anchor order override
  - `--total-slots` / `-t`: Required slot budget
  - `--include-anchor-anchor` / `--no-include-anchor-anchor`: Toggle (default: true)
  - `--lock-pair` / `-l`: Repeatable option for locked pairs (format: "essay_a,essay_b")
  - `--max-repeat` / `-r`: Max repeat count (default: 3)
  - `--output-csv` / `-o`: Required output path
  - `--report-json`: Optional diagnostics report
- **Removed parameters:**
  - `--mode` (session/synthetic)
  - `--pairs-csv`
  - `--baseline-json`
  - `--include-status`
  - `--seed`

Updated `_write_report()` to include `dynamic_spec` in JSON diagnostics.

#### 4.4 TUI Workflow Replacement
**Status: COMPLETE**

Updated `redistribute_tui.py` with new input fields:
- "Student Essay IDs (comma-separated)" replaces "Pairs CSV Path"
- "Anchor Order Override (comma-separated, optional)" - new field
- "Locked Pairs (one per line: essay_a,essay_b)" replaces "Optional Baseline JSON Path"
- "Optimization Total Slots (required)" - now required instead of optional
- "Include Anchor-Anchor Comparisons" - new Yes/No selector
- Removed "Optimization Status Pool" (no longer needed)

Rewrote `_run_optimizer()` method:
- Parses student IDs from comma-separated input
- Parses optional anchor override
- Parses locked pairs from input field
- Builds `DynamicSpec` object
- Calls `optimize_from_dynamic_spec()` directly
- No CSV/JSON file dependencies

#### 4.5 Testing
**Status: COMPLETE (11 new tests, 2 legacy tests removed)**

Added comprehensive dynamic spec tests in `test_redistribute.py`:
1. `test_load_dynamic_spec_validates_empty_students` - validates error on empty students
2. `test_load_dynamic_spec_validates_total_slots` - validates minimum slots requirement
3. `test_load_dynamic_spec_validates_locked_pair_essay_ids` - validates locked pair references
4. `test_load_dynamic_spec_defaults_to_standard_anchors` - confirms default anchor order
5. `test_load_dynamic_spec_accepts_custom_anchors` - confirms custom anchor support
6. `test_optimize_from_dynamic_spec_builds_design` - validates optimizer produces valid design
7. `test_optimize_from_dynamic_spec_respects_locked_pairs` - confirms locked pairs in output
8. `test_optimize_from_dynamic_spec_respects_anchor_toggle` - validates anchor-anchor toggle
9. `test_cli_optimize_with_dynamic_spec` - CLI integration test
10. `test_cli_optimize_with_locked_pairs` - CLI with locked pairs test
11. `test_cli_optimize_with_report_includes_dynamic_spec` - validates JSON report schema

Removed incompatible legacy tests:
- `test_optimize_cli_writes_outputs` (used removed `--mode synthetic`)
- `test_optimize_cli_accepts_baseline_json` (used removed `--baseline-json`)

**All 22 tests pass.**

### ⚠️ Issues & Shortcuts Taken

#### 1. Locked Pairs Parsing Bug in TUI
**Severity: MEDIUM**

The TUI locked pairs input parsing has a bug on line 397:
```python
for line in locked_value.split(","):  # Splits on comma
    parts = [p.strip() for p in line.split(",")]  # Splits again on comma
```

This double-split logic is incorrect. Should either:
- Use newline splitting if we want multi-line input, OR
- Use a different delimiter between pairs (e.g., semicolon)

**Impact:** Locked pairs feature in TUI won't work correctly until fixed.

#### 2. Legacy Code Still Present
**Severity: LOW**

The following legacy functions remain in `d_optimal_workflow.py` and should be removed:
- `load_baseline_payload()` - line 187
- `optimize_from_payload()` - line 244
- `load_baseline_design()` - line 275
- `load_baseline_from_records()` - line 318
- `run_synthetic_optimization()` - line 575
- `_build_random_design()` - line 535
- `BaselinePayload` dataclass - line 93

**Why kept:** Avoided breaking changes during iterative development. Some may still be used by external code.

**Recommendation:** Audit usage, then remove unused functions in Phase 4 cleanup.

#### 3. Simplified Locked Pairs Input
**Severity: LOW**

Original plan called for multi-line text entry for locked pairs in TUI. Implemented as single-line comma-separated field instead.

**Reason:** Simpler widget implementation, consistent with other comma-separated inputs.

**Trade-off:** Less intuitive for many locked pairs, but acceptable for current use case (typically 0-5 locked pairs).

#### 4. Documentation Not Yet Updated
**Severity: MEDIUM**

The following documentation files need updates:
- `scripts/bayesian_consensus_model/README.md` - still references old CLI flags
- `.claude/HANDOFF.md` - needs dynamic intake workflow documentation
- This task document - needs completion status (being addressed now)

### 🚧 Remaining Work

#### Phase 4: Legacy Code Removal
- [ ] Remove unused baseline loading functions from `d_optimal_workflow.py`
- [ ] Remove `OptimizerMode` enum from `redistribute_pairs.py` (already removed, verify)
- [ ] Clean up unused imports
- [ ] Verify no external dependencies on removed code

#### Phase 6: Documentation Updates
- [ ] Update `scripts/bayesian_consensus_model/README.md` with new CLI examples
- [ ] Update `.claude/HANDOFF.md` with unified dynamic intake workflow
- [ ] Add migration guide for users of old CLI syntax
- [ ] Document locked pairs input format clearly

#### Testing & Validation
- [ ] Fix locked pairs parsing bug in TUI (`redistribute_tui.py:397`)
- [ ] Run full test suite (not just `test_redistribute.py`)
- [ ] Run `pdm run typecheck-all` to verify type safety
- [ ] Run `pdm run lint` to verify code quality
- [ ] Manual testing of TUI workflow

### 📚 Lessons Learned

1. **Incremental Migration Works Well:** Keeping legacy code initially allowed us to develop and test the new pathway without breaking existing functionality. Tests caught incompatibilities early.

2. **Test-First Approach Pays Off:** Writing comprehensive tests before removing legacy code gave confidence that the new implementation works correctly.

3. **CLI Design Clarity:** The new CLI is significantly clearer than the old `--mode session/synthetic` approach. Direct parameter names (`--student`, `--lock-pair`) are more intuitive than file-based inputs.

4. **Validation Early:** The `load_dynamic_spec()` function's thorough validation prevents downstream errors and provides clear error messages.

5. **Widget Complexity Trade-offs:** The TUI locked pairs field demonstrates the trade-off between feature richness and implementation complexity. Single-line input is simpler but less user-friendly for many pairs.

### 🚨 CRITICAL DESIGN ISSUE DISCOVERED (2025-10-31)

#### The Problem: Misunderstanding of "Locked Pairs"

**What was implemented:**
- `locked_pairs`: Pairs that MUST be included in the current schedule (hard constraints)

**What is actually needed:**
- `previous_comparisons`: Historical comparison data from past sessions that the optimizer analyzes to build complementary schedules

#### Why This Matters

The current implementation treats "locked pairs" as constraints to force into the new schedule. The **actual user need** is:

**Scenario A (Session 1):**
- No historical data
- Generate 84 fresh comparisons
- Ensure baseline coverage (every student gets anchor comparisons)

**Scenario B (Session 2+):**
- Load 84 comparisons from Session 1 as historical data
- Analyze what coverage already exists
- Generate 84 NEW comparisons that:
  - Fill gaps in student-anchor coverage
  - Complement existing data
  - Avoid unnecessary duplication
- Build on Session 1 to improve overall design

#### Current Implementation Failures

1. **No way to provide historical data**: DynamicSpec has `locked_pairs` but not `previous_comparisons`
2. **No coverage analysis**: `optimize_from_dynamic_spec()` sets `required_pairs=[]` (starts fresh every time)
3. **Would delete baseline loading**: Was planning to remove `load_baseline_design()` which is actually needed
4. **CLI/TUI don't accept previous session data**: No `--previous-csv` flag or TUI field for historical comparisons

#### Corrected Design

```python
@dataclass(frozen=True)
class ComparisonRecord:
    """A single comparison record from historical data."""
    essay_a_id: str
    essay_b_id: str
    comparison_type: str  # student_anchor, student_student, anchor_anchor
    status: str  # core, extra, etc.

@dataclass(frozen=True)
class DynamicSpec:
    """Dynamic input specification for optimizer."""
    students: Sequence[str]
    anchors: Sequence[str]
    include_anchor_anchor: bool
    previous_comparisons: Sequence[ComparisonRecord]  # NEW: Historical data
    locked_pairs: Sequence[Tuple[str, str]]  # OPTIONAL: Must-include constraints (rare)
    total_slots: int
```

#### How It Should Work

**Workflow for Session 1 (no history):**
```bash
python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --student JA24 --student II24 --student ES24 \
  --total-slots 84 \
  --output-csv session1_pairs.csv
```
- `previous_comparisons` is empty
- Optimizer ensures baseline student-anchor coverage
- Generates 84 fresh comparisons

**Workflow for Session 2 (building on Session 1):**
```bash
python -m scripts.bayesian_consensus_model.redistribute_pairs optimize-pairs \
  --student JA24 --student II24 --student ES24 \
  --previous-csv session1_pairs.csv \  # NEW FLAG
  --total-slots 84 \
  --output-csv session2_pairs.csv
```
- Loads 84 comparisons from Session 1
- Analyzes which student-anchor pairs are covered
- Identifies coverage gaps
- Generates 84 NEW comparisons that complement Session 1

**TUI Workflow:**
1. Operator enters students: `JA24, II24, ES24`
2. Operator enters previous session CSV: `session1_pairs.csv` (or leaves blank for Session 1)
3. Optimizer analyzes coverage, generates complementary schedule
4. Proceeds to assignment as before

#### Integration with Existing Code

The baseline loading functions (which I was going to delete) are **actually needed**:
- `load_baseline_design()`: Loads previous comparisons from CSV
- `load_baseline_from_records()`: Parses comparison records
- Coverage analysis in `d_optimal_optimizer.py`: Derives required pairs from baseline

**New flow in `optimize_from_dynamic_spec()`:**
```python
def optimize_from_dynamic_spec(spec: DynamicSpec, *, max_repeat: int = 3):
    # Build baseline from previous comparisons (if any)
    if spec.previous_comparisons:
        baseline_design = [
            DesignEntry(
                PairCandidate(rec.essay_a_id, rec.essay_b_id, rec.comparison_type),
                locked=False  # Historical data, not constraints
            )
            for rec in spec.previous_comparisons
        ]
    else:
        baseline_design = []

    # Derive required pairs from baseline coverage analysis
    required_pairs = derive_required_student_anchor_pairs(
        students=spec.students,
        anchors=spec.anchors,
        anchor_order=spec.anchors,
        baseline_design=baseline_design,
    )

    # Optional: Add locked pairs as hard constraints
    locked_candidates = []
    for essay_a, essay_b in spec.locked_pairs:
        comp_type = determine_comparison_type(essay_a, essay_b, spec.anchors)
        locked_candidates.append(PairCandidate(essay_a, essay_b, comp_type))

    # Run optimizer with both historical context and constraints
    optimized_design, _ = select_design(
        students=spec.students,
        anchors=spec.anchors,
        total_slots=spec.total_slots,
        anchor_order=spec.anchors,
        locked_pairs=locked_candidates,  # Hard constraints
        required_pairs=required_pairs,  # Coverage requirements from baseline
        max_repeat=max_repeat,
        include_anchor_anchor=spec.include_anchor_anchor,
    )

    # Return result with proper baseline
    return OptimizationResult(
        baseline_design=baseline_design,  # Historical data
        optimized_design=optimized_design,  # New schedule
        # ... rest of result
    )
```

### 🔧 Corrective Actions Required

#### 4.6 Add Previous Comparisons Support (NEW - CRITICAL)

**Status: ✅ COMPLETE (2025-10-31)**

1. **Define ComparisonRecord dataclass**
   - Location: `d_optimal_workflow.py`
   - Fields: `essay_a_id`, `essay_b_id`, `comparison_type`, `status`
   - Purpose: Type-safe representation of historical comparison data

2. **Update DynamicSpec**
   - Add `previous_comparisons: Sequence[ComparisonRecord]` field
   - Keep `locked_pairs` as optional constraint mechanism (separate from history)
   - Update validation in `load_dynamic_spec()` to handle both

3. **Rewrite optimize_from_dynamic_spec()**
   - Build baseline_design from previous_comparisons (NOT from locked_pairs)
   - Call `derive_required_student_anchor_pairs()` to analyze coverage
   - Pass required_pairs to select_design() (currently passes empty list)
   - Treat locked_pairs as hard constraints (separate from baseline)
   - Compute baseline_log_det from actual historical data

4. **Integrate baseline loading helpers**
   - **DO NOT DELETE** `load_baseline_design()` - needed for loading previous CSV
   - Create helper: `load_previous_comparisons_from_csv(path)` → `Sequence[ComparisonRecord]`
   - Reuse existing CSV parsing logic from `load_baseline_design()`

5. **Update CLI**
   - Add `--previous-csv` / `-p` flag: optional path to previous session CSV
   - Parse CSV into ComparisonRecords
   - Pass to `load_dynamic_spec(previous_comparisons=...)`
   - Keep `--lock-pair` as separate optional constraint
   - Update help text to clearly distinguish previous data vs constraints

6. **Update TUI**
   - Add field: "Previous Session CSV Path (optional)"
   - Placeholder: "e.g., session1_pairs.csv (leave blank for first session)"
   - Parse CSV if provided
   - Update `_run_optimizer()` to load and pass previous comparisons
   - Keep locked pairs field but clarify it's for constraints, not history

7. **Update tests**
   - Test Session 1 scenario: empty previous_comparisons
   - Test Session 2 scenario: load previous CSV, verify complementary coverage
   - Test that coverage gaps from Session 1 are filled in Session 2
   - Test locked pairs work as constraints (separate from history)
   - Verify baseline_log_det is computed from actual historical data

8. **Update documentation**
   - README: Explain Session 1 vs Session 2+ workflows
   - Clarify distinction: previous_comparisons (history) vs locked_pairs (constraints)
   - Add example: "Building Session 2 on top of Session 1"

### 🎯 Revised Next Actions

**CRITICAL (Implementation Incomplete Without This):**
1. ✅ ~~Fix locked pairs parsing bug in TUI~~ (DONE)
2. ✅ ~~Implement previous_comparisons support (sections 4.6.1-4.6.8 above)~~ (DONE 2025-10-31)
   - ComparisonRecord dataclass defined
   - DynamicSpec updated with previous_comparisons field
   - derive_required_student_anchor_pairs() function created
   - optimize_from_dynamic_spec() rewritten to use coverage analysis
   - load_previous_comparisons_from_csv() helper created
   - CLI updated with --previous-csv flag
   - TUI updated with previous session CSV input field
   - 4 new tests added (Session 1, Session 2+, CSV loading, CLI integration)
   - All 26 tests passing
   - Type checks passing

**Important (After Critical Items):**
3. Update documentation to explain previous_comparisons vs locked_pairs
4. Remove truly unused legacy code (after confirming baseline loaders are needed)
5. Update README and HANDOFF with corrected workflow

**Future Enhancements:**
1. Add scarcity handling (Workstream 3.5)
2. Add per-rater quota flexibility (Workstream 1.6)
3. Consider multi-line text widget for locked pairs in TUI
4. Add CLI example to README with real Session 2 data showing previous_comparisons
