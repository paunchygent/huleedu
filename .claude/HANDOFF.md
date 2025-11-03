# Continuation-aware Optimizer - Task Handoff (2025-11-05)

## Context
- Multi-session optimization now seeds historical comparisons directly into the working design so slot budgets, repeat guards, and log-det metrics operate over the combined baseline + new schedule.
- `TASKS/d_optimal_continuation_plan.md` defines the required refactor to make continuation statistically sound while exporting only newly generated comparisons.
- Prior PyInstaller/standalone work is complete; no further action unless explicitly requested.

## Required Rules & Workflows
1. Read `.claude/README_FIRST.md` and this handoff before coding; update both documents with any findings.
2. Follow coding/tooling standards: `.claude/rules/010-foundational-principles.mdc`, `050-python-coding-standards.mdc`, `080-repository-workflow-and-tooling.mdc`, `095-textual-tui-patterns.mdc`, `110.2-coding-mode.mdc`.
3. Run `pdm run lint-all` (or scoped Ruff for touched files) and `pdm run typecheck-all` before handing off.

## Current Gaps
- Manual smoke runs (CLI + Textual) still recommended to validate the refreshed messaging and CSV output against real data sets.
- Global `pdm run lint-all` continues to fail on pre-existing long lines outside the optimizer scope (e.g., `libs/huleedu_nlp_shared/...`, `tui/help_screen.py`). No fixes attempted in this pass.

## Recent Updates (2025-11-05)
- Baseline comparisons canonicalized and locked into `select_design`; the optimizer now treats `total_slots` as the number of new comparisons for the current session while `min_slots_required` reports mandatory new slots (adjacency, locked, coverage) separate from the historical baseline.
- CLI/TUI now write only newly scheduled comparisons while summaries/report JSON describe combined totals, baseline consumption, and added constraints.
- Added canonicalization guardrails for previous comparison records and expanded test coverage (`test_load_dynamic_spec_canonicalizes_previous_comparisons`, multi-session assertions on `new_design`).

## Next Steps
1. Run manual multi-session CLI/TUI workflows to confirm UX messaging and CSV/new-only export match stakeholder expectations.
2. Coordinate with docs team to fold continuation semantics into Textual help content (`tui/help_screen.py`) once lint backlog is addressed.
3. Monitor downstream consumers of optimizer reports for assumptions about `optimized_design` vs `new_design` to ensure integrations read the correct field.

## Testing Expectations
- Unit/integration tests under `scripts/bayesian_consensus_model/tests/test_redistribute.py` should cover continuation scenarios (add/extend as needed).
- Manual smoke test: run CLI and TUI with a previous-session CSV to verify new-only output and accurate combined diagnostics.
- Confirm `pdm run lint-all` / `pdm run typecheck-all` pass before completion.
