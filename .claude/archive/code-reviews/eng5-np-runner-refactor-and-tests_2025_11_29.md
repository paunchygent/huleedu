---
title: "ENG5 NP Runner Refactor & Test Strategy Review"
date: 2025-11-29
review_target: "eng5-np-runner-refactor-and-prompt-tuning"
scope:
  - scripts/cj_experiments_runners/eng5_np/cli.py
  - scripts/cj_experiments_runners/eng5_np/protocols.py
  - scripts/cj_experiments_runners/eng5_np/handlers/*.py
  - scripts/cj_experiments_runners/eng5_np/alignment_report.py
  - scripts/cj_experiments_runners/eng5_np/tests/**
  - docs/operations/eng5-np-runbook.md
  - docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md
  - TASKS/assessment/anchor-alignment-prompt-tuning-experiment.md
summary: |
  Initial lead-dev review of the ENG5 NP runner refactor from a monolithic
  CLI to a handler-based architecture, plus the test strategy for the new
  `anchor-align-test` mode and associated alignment reporting.

  Focus areas:
  - Mode handler design and ModeHandlerProtocol compliance
  - Separation of concerns between CLI parsing, handlers, and lower-level
    helper modules (inventory, artefact_io, kafka_flow, etc.)
  - Unit tests for alignment_report.py (51 tests) and new handler/CLI tests
  - Documentation alignment across the runbook, task doc, and ENG5 runner epic
notes:
  - CLI now correctly delegates mode-specific behavior to dedicated handlers
    via HANDLER_MAP, keeping parsing concerns in `cli.py` and execution
    logic in `handlers/`. This is a clear improvement over the previous
    ~900-line monolith and aligns with the small-SRP-file rule.
  - Mode-specific validation (e.g. optional assignment_id for
    ANCHOR_ALIGN_TEST, required for EXECUTE) is centralized in CLI and
    handler helpers, which matches the documented GUEST vs DB-owned anchor
    semantics in 020.19.
  - Existing tests covered alignment_report.py thoroughly; new unit tests now
    exercise PLAN/DRY_RUN/ANCHOR_ALIGN_TEST/EXECUTE handlers and Typer CLI
    integration (argument validation + handler dispatch).
  - The ENG5 runbook has been updated to document the handler architecture and
    `anchor-align-test` usage, including prompt file wiring and alignment
    report output/metrics.
  - A dedicated ENG5 runner epic and an architecture design note now capture
    the handler contract, GUEST vs EXECUTE semantics, and alignment report
    schema to keep product/architecture documentation in sync with code.
  - Task frontmatter/doc validators and docs structure checks are passing; the
    task indexer still has a minor `relative_to` path bug when writing output
    outside the repo root (no behavior impact on ENG5 runner itself).
status:
  architecture_review: "completed"
  handler_tests: "completed"
  cli_integration_tests: "completed"
  documentation_updates: "completed"
open_questions:
  - For long term maintainability, should EXECUTE and ANCHOR_ALIGN_TEST be
    split further around shared upload/publish primitives, or is the current
    level of duplication acceptable given their distinct domain semantics?
  - How strict do we want CLI contract tests to be around log messages and
    human-facing output vs. exit codes and side effects?
