---
id: 'eng5-heavy-ci-matrix-and-healthcheck-tuning'
title: 'ENG5 Heavy CI Matrix and Healthcheck Tuning'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: 'eng5'
created: '2025-12-09'
last_updated: '2025-12-09'
related: ['EPIC-011', 'EPIC-005', 'EPIC-008']
labels: ['ci', 'eng5', 'heavy-lane']
---
# ENG5 Heavy CI Matrix and Healthcheck Tuning

## Objective

Design and implement CI orchestration improvements for the ENG5 Heavy C-lane so that:

- ENG5 docker/profile suites run in parallel where safe (per profile) instead of serializing across modes.
- Container startup latency for heavy jobs is reduced via CI-specific healthcheck tuning.
- The fast PR pipeline remains unaffected, and heavy-lane behaviour is fully aligned with ADR-0024 and Rule 101.

## Context

- ADR-0024 (ENG5 Heavy C-lane CI Strategy) and Rule 101 (CI Lanes and Heavy Suites) define:
  - Lane C as the dedicated home for ENG5 docker semantics and mock profile parity tests.
  - `.env`-driven configuration and container restarts as the accepted orchestration mechanism for ENG5 heavy suites.
- Current `eng5-heavy-suites.yml` implementation runs:
  - `eng5-cj-docker-regular-and-small-net` and `eng5-profile-parity-suite` jobs.
  - Profiles for parity tests are executed serially via `.env` edits + `pdm run llm-mock-profile <profile>`.
- This task formalises and optimises the CI orchestration for these heavy jobs without changing the underlying service architecture.

## Plan

1. **Baseline heavy-lane runtime and resource usage**
   - Measure wall-clock time and container startup latency for:
     - `eng5-cj-docker-regular-and-small-net`
     - `eng5-profile-parity-suite`
   - Record baseline CPU/memory during heavy suites using existing observability (e.g. `container_cpu_usage_seconds_total`).

2. **Introduce CI matrix for ENG5 mock profiles**
   - Convert `eng5-profile-parity-suite` into a matrix over `profile ∈ {cj-generic, eng5-anchor, eng5-lower5}`.
   - For each matrix entry:
     - Set `LLM_PROVIDER_SERVICE_MOCK_MODE` and other required env vars for its profile.
     - Run `pdm run llm-mock-profile <profile>`.
   - Ensure all matrix entries:
     - Respect Heavy C-lane rules (no impact on fast PR pipeline).
     - Share a consistent `.env` template but override profile-specific values in job env.

3. **Tune CI-only healthchecks for heavy jobs**
   - Introduce a CI-specific override (compose or env) for:
     - `llm_provider_service` and `cj_assessment_service` healthcheck intervals/start periods.
   - Target significantly reduced startup detection time compared to production defaults while keeping tests reliable.

4. **Document orchestration pattern**
   - Update:
     - `docs/product/epics/ci-test-lanes-and-eng5-heavy-suites.md` (EPIC-011).
     - `docs/operations/eng5-np-runbook.md` CI/validation section.
     - `.claude/rules/101-ci-lanes-and-heavy-suites.md` (if needed) with a short note on matrix usage.
   - Ensure TASKS for ENG5 serial-bundle and parity work (`cj-llm-serial-bundle-validation-fixes`, `llm-mock-provider-cj-behavioural-parity-tests`) reference this task where appropriate.

## Success Criteria

- Heavy C-lane jobs for ENG5 run successfully and remain stable under:
  - Matrix-based `eng5-profile-parity-suite`.
  - Tuned CI-only healthchecks.
- Overall heavy-lane wall-clock time is reduced (e.g. profiles running in parallel instead of sequentially).
- Fast PR and walking-skeleton pipelines remain unchanged and unaffected by heavy-lane orchestration.
- Docs/rules clearly describe:
  - Which workflows belong to Lane C.
  - How ENG5 heavy suites are parallelised and how they rely on `.env` and container restarts.

## Related

- ADR-0024: `docs/decisions/0024-eng5-heavy-c-lane-ci-strategy.md`
- Rule 101: `.claude/rules/101-ci-lanes-and-heavy-suites.md`
- EPIC-011: `docs/product/epics/ci-test-lanes-and-eng5-heavy-suites.md`
- ENG5 runbook: `docs/operations/eng5-np-runbook.md`
- Related TASKS:
  - `TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`
  - `TASKS/infrastructure/llm-mock-provider-cj-behavioural-parity-tests.md`
