---
type: epic
id: EPIC-008
title: ENG5 NP Runner Refactor & Prompt Tuning
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-29
last_updated: 2025-11-30
---

# EPIC-008: ENG5 NP Runner Refactor & Prompt Tuning

## Summary

Refactor the ENG5 NP batch runner into a handler-based architecture and add an
isolated prompt-tuning harness (`anchor-align-test` mode) so that ENG5 anchor
alignment experiments can run safely and repeatably without impacting
production CJ behavior.

**Business Value**: Faster iteration on ENG5 prompt/rubric variants, clear
alignment metrics versus expert anchors, and a maintainable, testable runner
surface for future CJ experiments.

## Scope Boundaries

- **In Scope**
  - Refactor `scripts/cj_experiments_runners/eng5_np/cli.py` into
    small, mode-specific handlers implementing `ModeHandlerProtocol`.
  - Introduce `ANCHOR_ALIGN_TEST` mode (`anchor-align-test`) with GUEST
    semantics (no DB-owned anchors, no grade projection).
  - Implement `alignment_report.py` and reporting pipeline from ENG5 artefacts.
  - Provide unit tests for handlers and Typer CLI integration.
  - Update ENG5 runbook and design documentation for the new modes.
- **Out of Scope**
  - Changes to CJ assessment core convergence or projection logic
    (covered by EPIC-005/EPIC-006).
  - New LLM providers or model selection strategies (covered by the
    LLM Provider epics/ADRs).

## User Stories

### US-008.1: Handler-Based ENG5 Runner

**As a** developer running ENG5 experiments  
**I want** the CLI to delegate to small, testable handlers per mode  
**So that** changes to one mode do not risk regressions in others.

**Acceptance Criteria**
- [ ] `cli.py` uses a `HANDLER_MAP` from `RunnerMode` → handler class.
- [ ] All handlers implement `execute(settings, inventory, paths) -> int` and
      are `isinstance(handler, ModeHandlerProtocol) == True`.
- [ ] PLAN and DRY_RUN handlers perform no network I/O and no Kafka publish.
- [ ] EXECUTE handler:
  - [ ] Validates presence of anchors, students, prompt, and `CJ_SERVICE_URL`.
  - [ ] Registers anchors with CJ and aborts cleanly on registration errors.
  - [ ] Uploads essays + prompt to Content Service and publishes a request
        envelope to Kafka (or logs a clear message when `--no-kafka` is set).

### US-008.2: Anchor Alignment Prompt-Tuning Harness

**As a** researcher tuning ENG5 prompts  
**I want** a dedicated `anchor-align-test` mode and report  
**So that** I can quantify LLM–expert alignment on anchors only.

**Acceptance Criteria**
- [ ] `--mode anchor-align-test`:
  - [ ] Uses `assignment_id=None` (GUEST flow) and does not rely on DB-owned
        anchors or grade projection.
  - [ ] Treats all anchor essays as students in the CJ request.
  - [ ] Accepts `--system-prompt` and `--rubric` file paths and threads their
        contents via `LLMConfigOverrides`.
- [ ] On `--await-completion`, the runner:
  - [ ] Hydrates ENG5 results into an artefact.
  - [ ] Generates an `anchor_align_{batch_id}_{timestamp}.md` report under the
        ENG5 research output directory.
- [ ] The report includes:
  - [ ] Per-anchor BT scores, ranks, expert grades, and win/loss counts.
  - [ ] Direct inversion list (lower grade beating higher grade).
  - [ ] Zero-win anchor count.
  - [ ] Kendall's tau between expected and actual ranks.

### US-008.3: ENG5 Runner Developer & Ops Experience

**As a** developer or SRE  
**I want** clear ENG5 runner docs and tests  
**So that** I can safely run experiments and change code.

**Acceptance Criteria**
- [ ] Epic is linked from `docs/product/epics/INDEX.md` with status and scope.
- [ ] `docs/operations/eng5-np-runbook.md`:
  - [ ] Documents handler-based architecture at a high level.
  - [ ] Adds an `ANCHOR_ALIGN_TEST` section with prerequisites, example
        commands, and troubleshooting notes (including shell background job
        caveats for `--batch-id`).
  - [ ] References the alignment report location and key metrics.
- [ ] A design/spec document exists under `docs/architecture/` describing:
  - [ ] `ModeHandlerProtocol` and handler responsibilities.
  - [ ] GUEST vs EXECUTE flows and `assignment_id=None` semantics.
  - [ ] Alignment report schema and metric definitions.
- [ ] Unit tests exist for:
  - [ ] PLAN, DRY_RUN, ANCHOR_ALIGN_TEST, and EXECUTE handlers (happy-path +
        key failure modes with mocked dependencies).
  - [ ] Typer CLI integration for at least PLAN, DRY_RUN, and argument
        validation in EXECUTE.

### US-008.4: Controlled Grade Boundary Testing

**As a** researcher tuning ENG5 prompts
**I want** to run repeated comparisons of specific grade boundary pairs with position control
**So that** I can measure prompt discrimination at critical grade boundaries with statistical confidence.

**Acceptance Criteria**
- [ ] CJ service accepts `pre_specified_comparisons` field (bypasses pair generation).
  - [ ] New `PreSpecifiedComparison` model in event contract.
  - [ ] Pair generation bypass logic in `pair_generation.py`.
  - [ ] No position randomization when pre-specified (caller controls).
- [ ] BOUNDARY_TEST mode in runner:
  - [ ] `--boundary-pairs` CLI option (format: `HIGHER:LOWER,HIGHER:LOWER`).
  - [ ] `--boundary-iterations` CLI option (default: 10).
  - [ ] Builds `pre_specified_comparisons` list with position swapping.
  - [ ] Single CJ batch submission for all comparisons.
- [ ] Statistical report includes:
  - [ ] Win rate (% times higher-grade essay wins).
  - [ ] Mean confidence with 95% CI.
  - [ ] Position bias (A-position win rate vs 50%).
  - [ ] Agreement rate across iterations.

**Related ADR**: ADR-0018 (CJ Pre-Specified Comparisons)

## Success Metrics (Experiment Outcomes)

Baseline reference: ENG5 batch 108 (Role Models anchors).

| Metric            | Baseline (Batch 108) | Target |
|-------------------|----------------------|--------|
| Direct inversions | 5                    | ≤1     |
| Zero-win anchors  | 1 (ANCHOR_7)         | 0      |
| Kendall's tau     | ~0.82                | ≥0.90  |
| A/B regression    | 0                    | 0      |

These metrics are computed from the alignment report and used to compare
prompt/rubric variants.

## Technical Acceptance

- [ ] All new handler and CLI tests passing.
- [ ] `pdm run typecheck-all` clean.
- [ ] `pdm run format-all` and `pdm run lint-fix --unsafe-fixes` clean.
- [ ] ENG5 baseline `anchor-align-test` run produces a valid alignment report
      and artefact.
- [ ] Runbook and design docs updated and validated via
      `scripts/docs_mgmt/validate_docs_structure.py`.

## Relationships

- **Related Epics**
  - EPIC-005: CJ Stability & Reliability (uses ENG5 runs for diagnostics).
  - EPIC-006: Grade Projection Quality & Anchors.
  - EPIC-007: Developer Experience & Testing (ENG5 runner is a key dev tool).

- **Primary Task**
  - `TASKS/assessment/anchor-alignment-prompt-tuning-experiment.md`
