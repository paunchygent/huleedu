---
id: d-optimal-continuation-plan
title: Continuation-aware Optimizer Plan
type: task
status: proposed
priority: medium
domain: assessment
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-11-03'
last_updated: '2026-02-01'
related: []
labels: []
---
## Objective

Extend the D-optimal pair optimizer so that multi-session runs truly continue from previous sessions: historical comparisons influence slot usage, repeat limits, and information gain. The output for the current session must contain only newly scheduled comparisons, while diagnostics reflect the combined (historical + new) design.

## Current Behavior

- Previous session CSV is parsed into `ComparisonRecord` entries, but only the coverage analysis consumes them. Historical pair counts do **not** reduce available slots or contribute to repeat limits.
- Baseline comparisons are excluded from the new CSV output and do not affect pair selection beyond minimal coverage requirements.
- CLI/TUI messaging reports historical coverage but the generated design is essentially fresh each run.

## Goals

1. Treat baseline comparisons as part of the design state when optimizing:
   - Lock them into the working design.
   - Apply repeat and slot constraints across baseline + new pairs.
2. Ensure new schedule builds on historical information (avoid reusing exhausted pairs, target new comparisons).
3. Output only the new comparisons while reporting combined diagnostics.
4. Detect invalid baselines (e.g., exceeding `max_repeat` or `total_slots`) and surface informative errors.

## Plan

### 1. Requirements Review

- Re-read `TASKS/d_optimal_pair_optimizer_plan.md` and `scripts/bayesian_consensus_model/HANDOFF.md` sections on multi-session optimization.
- Audit existing tests (`scripts/bayesian_consensus_model/tests/test_redistribute.py`) to capture current expectations.

### 2. Model & Loader Updates

- Update `DynamicSpec` and `load_dynamic_spec` to carry both the parsed `ComparisonRecord` list and a concrete `baseline_design` (list of `DesignEntry`) so downstream logic can operate on actual pairs.
- Confirm `ComparisonRecord` includes comparison types sufficient to reconstruct `DesignEntry` objects with correct semantics.

### 3. Optimizer Refactor

- Modify `optimize_from_dynamic_spec`:
  - Convert baseline records into `DesignEntry` instances and insert them into a working design (`locked=True`).
  - Seed repeat counters with baseline usage.
  - Reduce `total_slots` by the number of baseline comparisons (or validate that requested slots cover baseline + desired additions).
  - Only add coverage requirements for students still missing anchor exposure after accounting for the baseline.
- Adjust `select_design` (or create an extended variant) to accept:
  - A pre-existing design list and repeat counts.
  - A mechanism to separate baseline vs new entries for CSV output.
- Ensure anchor adjacency constraints and locked pair logic interact correctly with pre-populated designs (no duplicate insertions).

### 4. Output & Workflow Integration

- Update CLI (`redistribute_pairs.py`) and TUI workflow to:
  - Write only the new comparisons to disk.
  - Optionally provide a combined diagnostic report (baseline + new) for transparency.
  - Log counts of historical vs newly scheduled comparisons.

### 5. Statistical Validation

- Confirm log-det improvement uses the combined design (`baseline_design + optimized_design`).
- Enforce `max_repeat` against historical usage (e.g., if a pair already occurs `max_repeat` times in baseline, block new occurrences).
- Validate totals: if baseline pairs already consume all slots or exceed constraints, raise a clear `ValueError`.

### 6. Testing

- Expand unit tests (`test_redistribute.py`) to cover:
  - Baseline with full anchor coverage (no redundant anchor requirements).
  - Baseline near `max_repeat` thresholds.
  - Mixed comparison types (student/student, anchor/anchor) carried through.
- Add CLI regression test verifying that new CSV contains only fresh comparisons but log output references combined counts.
- Add TUI workflow test (if feasible) or document manual QA checklist for multi-session runs.

### 7. Documentation & Rules

- Update `scripts/bayesian_consensus_model/tui/README.md` and CLI help text to describe continuation behavior.
- Note optimizer changes in `TASKS/d_optimal_pair_optimizer_plan.md` and `.claude/work/session/handoff.md`.
- If Textual patterns change (e.g., instructions referencing continuation), update `.agent/rules/095-textual-tui-patterns.md`.

### 8. Verification

- Run `pdm run format-all` (if necessary), `pdm run lint-fix --unsafe-fixes` (or scoped Ruff) and `pdm run typecheck-all`.
- Manual smoke test:
  - Baseline CSV with multiple comparison types.
  - Run CLI (`redistribute_pairs optimize-pairs`) and TUI to verify diagnostics and CSV output.

## Risks & Mitigations

- **Historical duplicates exceeding limits**: enforce validation before optimization; provide actionable error messages.
- **Large baselines**: ensure seeding logic is efficient (avoid quadratic operations when initializing repeat counts).
- **Breaking existing workflows**: maintain backward compatibility by defaulting to current behavior when no previous CSV is provided.

## Deliverables

1. Updated optimizer pipeline (`d_optimal_workflow`, `d_optimal_optimizer`).
2. CLI/TUI behavior that honors continuation semantics (new-only output, combined diagnostics).
3. Extended test coverage for multi-session scenarios.
4. Documentation, rule updates, and lint/type checks passing.
