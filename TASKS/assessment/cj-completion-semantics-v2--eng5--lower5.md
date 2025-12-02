---
id: 'cj-completion-semantics-v2--eng5--lower5'
title: 'CJ completion semantics v2 – ENG5 & LOWER5'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-02'
last_updated: '2025-12-02'
related: []
labels: []
---
# CJ completion semantics v2 – ENG5 & LOWER5

## Objective

Apply the CJ completion semantics v2 model (budget-first denominator +
explicit small-net coverage) to ENG5 LOWER5 and full-anchor experiments so
that:

- LOWER5 runs (5 anchors) can use their full configured comparison budgets and
  small-net Phase-2 resampling, instead of capping at `C(5,2)=10` comparisons.
- Full-anchor runs share the same budget/coverage semantics and remain stable.
- The ENG5 epic and program tasks reflect the new behaviour and make it easy
  to reason about “how many comparisons we actually did and why”.

## Context

For ENG5 LOWER5 experiments, we currently configure CJ via:

- Docker/env: `MAX_PAIRWISE_COMPARISONS` (e.g. 60), `MIN_COMPARISONS_FOR_STABILITY_CHECK`,
  `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`, etc.
- ENG5 runner: guest-mode anchor-align runs with overrides for prompts, model,
  and (eventually) comparison budget.

Observed behaviour for LOWER5:

- `expected_essay_count = 5` → `nC2 = 10`.
- Even with a 60-comparison budget configured, `completion_denominator()` uses
  `min(total_budget, nC2) = 10`.
- Batches finalize after a single coverage wave:
  - `Total comparisons (successful) = 10`.
  - Status `COMPLETE_STABLE`.
  - No Phase-2 resampling; budget cap and small-net resampling settings are
    effectively ignored.

ADR-0020 defines the desired global semantics (budget-based denominator,
explicit coverage). This story focuses on:

- Ensuring ENG5 guest flows populate `total_budget` correctly from experiment
  configs.
- Making sure LOWER5 and full-anchor runs exercise the new semantics and
  documenting the impact in ENG5 program tasks and epics.

## Plan

- Wire budget settings for ENG5 runs:
  - Confirm how ENG5 anchor-align requests carry comparison budget hints (if
    any) into CJ (e.g. `comparison_budget.max_pairs_requested` in metadata).
  - Ensure CJ batch creation for ENG5 guest flows sets `total_budget` from:
    - the ENG5-provided override when present, else
    - `Settings.MAX_PAIRWISE_COMPARISONS`.
  - Avoid per-experiment Docker overrides for budgets where possible; favour
    per-request overrides from the ENG5 runner.
- Validate LOWER5 small-net behaviour under completion semantics v2:
  - Run a fresh LOWER5 experiment (5 anchors, budget=60, reasonable small-net
    resampling cap) with:
    - 006/006 and 007/006 system/rubric pairs.
    - `reasoning_effort` in `{"low", "none"}`.
  - Confirm via DB and logs that:
    - `CJBatchState.total_budget == 60`.
    - `completion_denominator() == 60`.
    - `max_possible_pairs == 10` (coverage_cap), but:
      - callbacks exceed 10 as resampling waves are scheduled.
      - `resampling_pass_count` increments up to the configured cap.
  - Generate DB reports (`db_alignment_report`) for these runs, record:
    - Batch IDs (runner labels, `bos_batch_id`, `cj_batch_id`).
    - Total comparisons, tau, inversion counts, and tail justifications.
- Validate full-anchor behaviour under completion semantics v2:
  - Restart CJ without LOWER5 overrides and run a full-anchor ENG5 experiment
    using:
    - system 006, rubric 007, `reasoning_effort="low"`, GPT‑5.1.
  - Confirm:
    - `total_budget` and denominator reflect the intended budget.
    - No regressions in convergence behaviour vs pre-v2 runs.
  - Generate DB reports and compare:
    - LOWER5 tail behaviour vs full ladder behaviour (especially E-/F+ pairs).
- Update ENG5 program tasks and epics:
  - `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`:
    - Document the new LOWER5 and full-anchor behaviour under completion
      semantics v2 (budgets, effective comparisons, resampling).
  - `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`:
    - Clarify ENG5 assumptions around budgets and completion, referencing
      ADR-0020.
  - Add a short “NONE vs LOW behaviour at LOWER5 tail under v2 semantics”
    summary to the ENG5 epic.

## Success Criteria

- [ ] ENG5 guest CJ batches have `total_budget` set deterministically from
      ENG5 config (override or `MAX_PAIRWISE_COMPARISONS`), with no reliance
      on Docker overrides for experiment budgets.
- [ ] LOWER5 runs:
      - Show `total_budget`/`completion_denominator` equal to the configured
        budget (e.g. 60).
      - Perform more than 10 comparisons (multiple resampling waves) when
        budget and resampling caps allow.
      - Produce DB reports that reflect the expanded comparison set (and
        updated tau/inversion stats).
- [ ] Full-anchor ENG5 runs remain stable under v2 semantics, with no
      regressions in convergence or completion behaviour.
- [ ] ENG5 program tasks and epic text are updated to describe completion
      semantics v2 and how ENG5 budgets are set and applied (including
      LOWER5 vs full-anchor scenarios).

## Related

- ADR-0020 `docs/decisions/0020-cj-assessment-completion-semantics-v2.md`
- `TASKS/assessment/cj-completion-semantics-v2--budget-vs-coverage.md`
- `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
- `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`
