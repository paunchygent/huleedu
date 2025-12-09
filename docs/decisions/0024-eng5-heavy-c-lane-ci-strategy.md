---
type: decision
id: ADR-0024
status: accepted
created: '2025-12-09'
last_updated: '2025-12-09'
---
# ADR-0024: ENG5 Heavy C-lane CI Strategy

## Status

Accepted

## Context

ENG5-related tests (CJ docker semantics and mock-profile parity) are:

- Computationally heavier than normal unit/integration tests.
- Sensitive to environment configuration (`LLM_PROVIDER_SERVICE_*`, `CJ_ASSESSMENT_SERVICE_*`).
- Intended to validate behaviour and observability under **specific** batching and mock profiles derived from real ENG5 runs.

Two competing implementation strategies were considered:

1. **Runtime-configurable mock modes**:
   - Introduce test-only switches in `llm_provider_service` (e.g. `POST /admin/mock-mode`, request-level `mock_scenario_id`) to change mock behaviour per test.
   - Pros:
     - Faster test cycles; no container restarts.
   - Cons:
     - Diverges from production: prod does not support such switches.
     - Introduces new mutable global state that can be misused.
     - Blurs the line between configuration and runtime behaviour.

2. **Environment-driven configuration with container restarts (Heavy C-lane)**:
   - Treat ENG5 modes (`cj_generic_batch`, `eng5_anchor_gpt51_low`, `eng5_lower5_gpt51_low`) as **deployment-time configuration**.
   - Use `.env` + `dev-recreate` to restart containers between profiles.
   - Tests treat services as immutable black boxes for the duration of a run and use `/admin/mock-mode` to verify active profile.
   - Pros:
     - Matches production behaviour (config fixed at startup).
     - Keeps test code independent of internal implementation switches.
     - Allows clear separation of fast vs heavy CI lanes.
   - Cons:
     - Slower (restart + healthcheck latency).
     - Requires careful CI orchestration to avoid polluting fast pipelines.

## Decision

We adopt **Strategy 2 – Environment-driven configuration with container restarts** for ENG5 heavy suites and formalize it as the **Heavy C-lane** CI strategy:

- ENG5 heavy suites (CJ docker semantics and ENG5 mock parity) run exclusively in a dedicated CI lane (Lane C) with:
  - `.env`-driven configuration per profile/mode.
  - Container restarts via `pdm run dev-recreate ...` as needed.
  - `/admin/mock-mode` used for introspection and drift detection.
- We **do not** add test-only runtime mock switches to `llm_provider_service` or `cj_assessment_service`.
- Fast PR and walking-skeleton pipelines remain free of `.env` mutation and heavy ENG5 harnesses.

This decision is codified in:

- `.claude/rules/101-ci-lanes-and-heavy-suites.md`
- `.github/workflows/eng5-heavy-suites.yml`
- `docs/product/epics/ci-test-lanes-and-eng5-heavy-suites.md` (EPIC-011)

## Consequences

### Positive

- **Production fidelity**:
  - Mock profiles and serial-bundle settings are selected the same way in tests as in production: via configuration at startup, not runtime toggles.
  - Reduces risk of test-only behaviour creeping into production code paths.

- **Isolation of heavy suites**:
  - Heavy ENG5 suites are cleanly separated from the fast PR pipeline.
  - Only the Heavy C-lane is allowed to:
    - Mutate `.env` for profile and batching configuration.
    - Restart containers as part of test orchestration.

- **Clear ownership and documentation**:
  - CI orchestration concerns (matrix jobs, healthcheck tuning, profile split) are owned by EPIC-011 and Rule 101, not scattered across individual tests.

### Negative

- **Longer end-to-end runtime for ENG5 lanes**:
  - Container restarts and healthchecks add latency (tens of seconds per profile).
  - Requires careful tuning (e.g. CI-only healthcheck intervals) to keep the Heavy C-lane acceptable for nightly builds.

- **Higher CI complexity**:
  - More workflows and jobs to maintain (`eng5-cj-docker-regular-and-small-net`, `eng5-profile-parity-suite`).
  - Requires clear documentation to avoid accidental usage from non-heavy lanes.

### Neutral / Follow-ups

- Future enhancements are allowed but must respect this decision:
  - **Matrix parallelization** of profiles in CI (each profile gets its own job with fixed env).
  - CI-only **healthcheck tuning** to reduce startup time without changing production defaults.
  - C-lane-specific **stability thresholds** (e.g. stricter `SCORE_STABILITY_THRESHOLD`) to make heavy suites act as a canary for subtle regressions.

Any future proposal to introduce runtime mock switching or to move ENG5 tests into the fast PR pipeline must either:

- Demonstrate that it preserves production fidelity and isolation guarantees, or
- Supersede this ADR with a new decision document.
