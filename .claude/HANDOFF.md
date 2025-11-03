# Continuation-aware Optimizer - Task Handoff (2025-11-05)

## Context
- Multi-session optimization currently loads previous comparisons only for anchor coverage; historical pairs are not counted toward slot budgets or repeat limits.
- `TASKS/d_optimal_continuation_plan.md` defines the required refactor to make continuation statistically sound while exporting only newly generated comparisons.
- Prior PyInstaller/standalone work is complete; no further action unless explicitly requested.

## Required Rules & Workflows
1. Read `.claude/README_FIRST.md` and this handoff before coding; update both documents with any findings.
2. Follow coding/tooling standards: `.claude/rules/010-foundational-principles.mdc`, `050-python-coding-standards.mdc`, `080-repository-workflow-and-tooling.mdc`, `095-textual-tui-patterns.mdc`, `110.2-coding-mode.mdc`.
3. Run `pdm run lint-all` (or scoped Ruff for touched files) and `pdm run typecheck-all` before handing off.

## Current Gaps
- Baseline comparisons are discarded during optimization; repeat counters and slot limits ignore previous sessions.
- Diagnostics/log-det comparisons do not reflect combined (historical + new) schedules.
- CLI/TUI emit only new comparisons (correct) but lack messaging about historical consumption.

## Next Steps (see task plan for details)
1. Load historical comparisons into the optimizer as `DesignEntry` objects, locking them into the working design.
2. Seed repeat counts and slot usage with the baseline; validate constraints before optimization.
3. Ensure `select_design` (or a new helper) separates baseline vs new entries so CSV output remains new-only.
4. Update CLI/TUI messaging, docs, and tests to cover continuation behavior.
5. Record results in TASKS updates and refresh this handoff + README_FIRST.

## Testing Expectations
- Unit/integration tests under `scripts/bayesian_consensus_model/tests/test_redistribute.py` should cover continuation scenarios (add/extend as needed).
- Manual smoke test: run CLI and TUI with a previous-session CSV to verify new-only output and accurate combined diagnostics.
- Confirm `pdm run lint-all` / `pdm run typecheck-all` pass before completion.
