---
id: 'fix-ci-docker-compose-v2-in-scripts'
title: 'fix ci docker compose v2 in scripts'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-12'
last_updated: '2025-12-12'
related: []
labels: []
---
# fix ci docker compose v2 in scripts

## Objective

Ensure all repo scripts and test harness entrypoints use **Docker Compose v2**
(`docker compose`) rather than the legacy `docker-compose` binary, so the
ENG5 Heavy C-lane workflows run on GitHub Actions runners without early failure.

## Context

The `ENG5 Heavy CJ/ENG5 Suites` workflow (`.github/workflows/eng5-heavy-suites.yml`)
failed with exit code `127` because `pdm run dev-recreate ...` shells out to
`docker-compose`, which is not available on standard GitHub hosted runners.

Rule reference:
- `.agent/rules/084.1-docker-compose-v2-command-reference.md`

## Plan

- Replace `docker-compose ...` calls with `docker compose ...` in repo scripts invoked via `pdm run`.
- Ensure no tests or scripts require the legacy `docker-compose` binary.
- Re-run the heavy workflow and confirm it reaches and passes the batch_api steps.

## Success Criteria

- `ENG5 Heavy CJ/ENG5 Suites` workflow completes green (including batch_api steps).
- No executable scripts in the repo invoke `docker-compose`.

## Related

- `.agent/rules/084.1-docker-compose-v2-command-reference.md`
- `.github/workflows/eng5-heavy-suites.yml`
