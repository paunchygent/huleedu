---
type: reference
id: REF-infrastructure-tasks-how-we-track-platform-work
title: Infrastructure tasks (how we track platform work)
status: active
created: '2026-02-01'
last_updated: '2026-02-01'
topic: infrastructure
---
# Infrastructure tasks (how we track platform work)

## Purpose

Define what belongs in `TASKS/infrastructure/` and how to query it without
maintaining drift-prone “current tasks” lists.

## Canonical Rules

- Directory: `TASKS/infrastructure/`
- Lifecycle: `docs/reference/ref-tasks-lifecycle-v2.md` (infrastructure tasks are *tasks*, not stories)
- Validation: `pdm run validate-tasks`

What belongs here:

- Docker/Compose changes, CI/CD changes
- observability stack wiring + runbooks
- cross-service dev tooling and scripts
- platform-level limits (rate limiting, timeouts, resource constraints)

What does not belong here:

- service-specific business logic changes (use that service’s domain)

## Examples

```bash
# In-progress infrastructure tasks
pdm run tasks --domain infrastructure --status in_progress

# Proposed infrastructure tasks (next-up)
pdm run tasks --domain infrastructure --status proposed

# Recently done infrastructure tasks
pdm run tasks --domain infrastructure --status done --updated-last-days 30
```
