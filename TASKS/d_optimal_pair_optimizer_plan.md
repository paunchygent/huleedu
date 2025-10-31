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

### 4. Dynamic Essay Intake & API Enablement
1. 🚧 **Optimizer inputs**: Design minimal changes to `d_optimal_optimizer.select_design`/`optimize_schedule` so callers can inject dynamic student/anchor essay IDs (e.g., via API payload) instead of relying solely on CSV introspection.
2. 🚧 **Web interface compatibility**: Specify a thin adapter layer that accepts JSON payloads from the forthcoming web interface, persists optional baseline snapshots, and feeds normalized essay IDs + constraints into the optimizer.
3. 🚧 **TUI/CLI bridging**: Update CLI/TUI to optionally consume essay lists provided at runtime (flags or interactive mode) while maintaining CSV compatibility for batch operations.
4. 🚧 **Documentation & validation**: Extend README + session pairing plan with instructions for dynamic intake, expected payload schema, and validation steps for operators.

## Deliverables
- Updated Typer/TUI commands capable of producing balanced, optimized schedules.
- New diagnostics/summary outputs ensuring operators can validate each run.
- Revised documentation & handoff materials reflecting the new workflow.
- Assignment balancing design ready for implementation (or implemented, per schedule).
- Dynamic intake plan aligning optimizer, CLI, TUI, and forthcoming API surface.
