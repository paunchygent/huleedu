---
type: epic
id: EPIC-011
title: CI Test Lanes and ENG5 Heavy Suites
status: draft
phase: 1
sprint_target: null
created: '2025-12-09'
last_updated: '2025-12-09'
---
# EPIC-011: CI Test Lanes and ENG5 Heavy Suites

## Summary

Define and implement clear CI lanes (fast PR, walking skeleton, ENG5 heavy) and orchestrate ENG5 docker/profile suites in a dedicated **Heavy C-lane** that:

- Preserves fast feedback for day-to-day PRs.
- Validates ENG5 serial-bundle semantics and mock-provider parity under realistic configurations.
- Avoids introducing test-only runtime toggles into production services.

This epic owns ADR-0024 (ENG5 Heavy C-lane CI Strategy) and Rule 101 (CI Lanes and Heavy Suites).

## Deliverables

- **D1 – CI lane taxonomy and rules**
  - `docs/decisions/0024-eng5-heavy-c-lane-ci-strategy.md` (ADR-0024) accepted and referenced.
  - `.claude/rules/101-ci-lanes-and-heavy-suites.md` describing:
    - Lane A (Fast PR).
    - Lane B (Walking Skeleton / Infra Smoke).
    - Lane C (ENG5 Heavy Suites).
  - `070-testing-and-quality-assurance.md` updated to reference CI lane rules.

- **D2 – ENG5 heavy workflow and orchestration**
  - `.github/workflows/eng5-heavy-suites.yml` with:
    - `eng5-cj-docker-regular-and-small-net` job for CJ docker semantics (serial_bundle + hints).
    - `eng5-profile-parity-suite` job for ENG5 mock profile parity.
  - CI-specific documentation in `docs/operations/eng5-np-runbook.md` describing:
    - Which jobs run the heavy suites.
    - Exact commands used and how to reproduce them locally.

- **D3 – Optimized and stable heavy lane**
  - Optional but recommended:
    - Matrix-based parallelization of ENG5 profiles in `eng5-profile-parity-suite`.
    - CI-only healthcheck tuning for `llm_provider_service` and `cj_assessment_service`.
    - C-lane-specific stability thresholds for CJ to surface subtle regressions early.

- **D4 – Task-linked stories for implementation**
  - Story-level TASKS for:
    - Heavy-lane metrics assertions in CJ docker tests (C-lane only).
    - Richer ENG5 parity metrics in `tests/eng5_profiles/*` (C-lane only).
  - TASK frontmatter includes `related: ['EPIC-011', 'EPIC-005', 'EPIC-008']` where applicable.

## User Stories

- **US-011.1 – As a developer**, I want a fast, deterministic PR pipeline that never gets blocked by ENG5-heavy tests, so I can iterate on everyday changes quickly.
- **US-011.2 – As a release owner**, I want a separate ENG5 heavy lane that validates CJ ↔ LPS serial bundling and ENG5 mock parity under production-like configs, so I can trust that complex changes don’t regress high-stakes flows.
- **US-011.3 – As an SRE**, I want CI rules that clearly specify where `.env` mutation and container restarts are allowed, so we avoid accidental cross-contamination between test lanes and keep infra predictable.
- **US-011.4 – As an architect**, I want ENG5 tests to treat services as black boxes configured at startup, so test behaviour remains aligned with production deployment semantics and we don’t add hidden test-only switches.

## References

- ADR-0024: `docs/decisions/0024-eng5-heavy-c-lane-ci-strategy.md`
- Rule 101: `.claude/rules/101-ci-lanes-and-heavy-suites.md`
- Testing rules: `.claude/rules/070-testing-and-quality-assurance.md`
- ENG5 runbook: `docs/operations/eng5-np-runbook.md`
- ENG5 epic: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md`
