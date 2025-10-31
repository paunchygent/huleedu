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
