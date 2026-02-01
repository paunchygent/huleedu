---
id: improve-functional-test-harness-and-stack-ergonomics
title: Improve functional test harness and stack ergonomics
type: task
status: proposed
priority: medium
domain: infrastructure
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-11-26'
last_updated: '2026-02-01'
related: []
labels: []
---
# Improve functional test harness and stack ergonomics

## Objective

Provide a repeatable, developer-friendly functional test harness that runs against the standard dev Docker stack (deps image + dev services), with deterministic readiness, realistic env config, and reduced duplication in the functional suite. (No separate functional compose profile; reuse the dev compose flow already used day-to-day.)

## Context

- Functional tests under `tests/functional/` depend on dockerized services but currently require manual `docker compose` bring-up and ad-hoc health waits; pytest `addopts` exclude the `docker` marker by default.
- Existing dev ergonomics (deps image tagging, dev stack as default) are not leveraged by the functional harness.
- Timeouts exceed Rule 070 in several tests, hiding nondeterminism.
- Some functional tests overlap in coverage (similar pipeline/identity flows), leading to long runtimes and maintenance bloat.
- CJ registration flag removed from contracts and services; pipeline selection is driven solely by `ClientBatchPipelineRequestV1`.

## Plan

1) Reuse dev compose workflow (no separate profile)  
   - Keep using the standard dev compose/overrides and deps image tagging already in place.  
   - Optional: lightweight helper aliases/wrappers may point to dev compose but **no new compose profile**.  
   - Ensure docs/tests reference the existing dev commands, not a functional profile.

2) Deterministic readiness & hygiene  
   - Session autouse gate in `tests/functional/conftest.py` that waits for `/healthz` via `ServiceTestManager` with bounded retries; clear/skip with actionable message if not ready.  
   - Pre-create Kafka topics + Redis cleanup hook for each run; rely on existing `KafkaTestManager.ensure_topics` and a lightweight Redis key scrubber for test prefixes.  
   - Enforce ≤60s per-test timeouts; mark true long flows as `slow` instead of inflating timeouts.

3) Env realism & docs  
   - Keep env aligned with dev compose defaults (JWT secret, DB creds, internal API key) and document the required variables in `tests/README.md`.  
   - Update `tests/README.md` to reflect `docker compose` v2 syntax, existing dev commands, and marker guidance (`-m "docker and not slow"`).

4) Reduce overlapping tests  
   - Inventory functional tests by target scenario; merge/remove redundant flows (e.g., similar pipeline happy-path variants, duplicate identity threading/email flows).  
   - Keep one canonical per scenario: pipeline (regular + guest), identity/email, idempotency (Redis), Kafka monitoring, language-tool/NLP, CJ after NLP.  
   - Document decisions and prune dead coverage.

## Success Criteria

- Dev stack (existing compose + overrides) is the single path to bring up services for functional tests; no extra compose profile required.  
- Functional tests run via `pdm run pytest-root tests/functional -m "docker and not slow"` with deterministic readiness and without extra manual compose steps.  
- Per-test timeouts comply with Rule 070 (≤60s) except explicit `slow`; flakiness reduced (no startup race failures).  
- Environment variables documented alongside dev compose defaults; secrets/config match compose dev defaults.  
- Redundant functional tests removed or merged; documented mapping of scenarios to surviving tests.

## Related

- Rules: `.agent/rules/070-testing-and-quality-assurance.md`, `084-docker-containerization-standards.md`, `084.1-docker-compose-v2-command-reference.md`
- Docs: `tests/README.md`
