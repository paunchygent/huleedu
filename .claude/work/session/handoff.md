# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks,
architectural decisions, and patterns live in:

- **README_FIRST.md** – Architectural overview, decisions, service status
- **Service READMEs** – Service-specific patterns, error handling, testing
- **.claude/rules/** – Implementation standards and requirements
- **docs/operations/** – Operational runbooks
- **TASKS/** – Detailed task documentation

Use this file to coordinate what the very next agent should focus on.

---

## 🎯 ACTIVE WORK (2025-11-30)

### 1. PR‑3: BT Standard Error Diagnostics & Observability (IN PROGRESS)

- Status: Implementation and tests landed; still needs follow‑up usage and
  adoption in monitoring/ops.
- What’s done (see CJ code + EPIC‑005/006 docs for details):
  - `BT_STANDARD_ERROR_MAX = 2.0` defined and applied in
    `bt_inference.compute_bt_standard_errors`.
  - Batch‑level SE summary (mean/max/min, counts, coverage stats) threaded
    into `CJBatchState.processing_metadata["bt_se_summary"]`.
  - Grade projector now exposes cohort‑level SE summaries (all/anchors/students).
  - Unit + integration tests around SE capping and metadata are in place.
- Next‑session focus:
  - Ensure dashboards/alerts actually consume `bt_se_summary` and any derived
    quality flags (see EPIC‑005/006 and CJ runbook).
  - Confirm ENG5 runners use these fields only for diagnostics (no gating).

### 2. PR‑4: CJ Scoring Core Refactor (BT inference robustness) – AWAITING REVIEW

- Status: Implementation complete and tests green; needs focused code review
  and sign‑off.
- What changed (high level, see PR‑4/task docs for details):
  - Introduced `BTScoringResult` helper and refactored
    `record_comparisons_and_update_scores` to be single‑session, single‑commit.
  - BT math isolated in a pure helper; SE diagnostics reused from PR‑3.
- Next‑session focus:
  - Perform reviewer‑level pass on scoring refactor (locking, transaction
    boundaries, error propagation).
  - Once approved, merge and confirm no regressions in CJ integration tests.

### 3. ENG5 NP Runner Refactor & Prompt-Tuning Harness – BASELINE SMOKE RUN COMPLETE

- Status: Handler architecture + tests + docs are in place; a full `anchor-align-test`
  run completed successfully via `pdm run eng5-runner` on 2025-11-30.
  - Artefact: `.claude/research/data/eng5_np_2016/assessment_run.anchor-align-test.json`
  - Report: `.claude/research/data/eng5_np_2016/anchor_align_anchor-align-baseline-20251130-011352_20251130_001406.md`
  - CJ callbacks and completion events were ingested without schema errors.
- Observed metrics from this run:
  - Total comparisons: `0` (no ENG5-specific LLM comparison callbacks hydrated).
  - Direct inversions: `0`
  - Zero-win anchors: `12`
  - Kendall’s tau: `1.00` (all anchors treated as `UNKNOWN` grade; optimistic by construction).
- Interpretation:
  - This run validates the ENG5 runner + hydrator + reporter plumbing and confirms that
    Kafka topic contamination (LLM callbacks / CJ completions) no longer crashes the
    harness.
  - Because CJ’s BT summary was available but no ENG5 comparison records were hydrated,
    the resulting alignment metrics are not yet a calibration-quality baseline against
    Batch 108; they are a smoke-test baseline only.
- Next‑session focus:
  1. Tighten ENG5 batch wiring so that ENG5 `anchor-align-test` runs also hydrate
     their *own* LLM comparison callbacks (non-zero `llm_comparisons` length) while
     still ignoring legacy traffic on shared topics.
  2. Re-run `anchor-align-test` to obtain a “true” alignment baseline with:
     - Non-zero total comparisons,
     - Expert grade map applied (no `UNKNOWN` anchor grades),
     - Meaningful inversion/zero-win counts and Kendall’s tau.
  3. Once a stable baseline is captured, start running H1–H4 prompt variants and
     record per-run metrics in the task doc.

**References**

- Task: `TASKS/assessment/anchor-alignment-prompt-tuning-experiment.md`
- Epic: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md`
- Runbook: `docs/operations/eng5-np-runbook.md`
- Design: `docs/architecture/eng5-np-runner-handler-architecture.md`
