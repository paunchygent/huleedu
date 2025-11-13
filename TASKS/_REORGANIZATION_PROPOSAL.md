# HuleEdu TASKS Reorganization Proposal

Date: YYYY-MM-DD
Author: Lead Architect (Cascade)

## Executive Summary

- Purpose: Establish a maintainable, agent-friendly structure for TASKS/ that supports discovery, automation, and a high-churn LLM-driven workflow.
- Selected approach: Domain-based + Programmes (Option B+) with status in metadata (front matter), not in paths.
- Archive policy: Archive by year/month under `TASKS/archive/YYYY/MM/<domain>/`; defer mass archiving unless obviously legacy.

## Final Taxonomy (≤10 top-level)

- programmes/
- assessment/
- content/
- identity/
- frontend/
- infrastructure/
- security/
- integrations/
- architecture/
- archive/

## "Belongs Here" Criteria

- programmes/
  - Multi-team initiatives with a hub doc and related tasks.
  - Example: `programmes/cj_confidence/PHASE3_CJ_CONFIDENCE_HUB.md`
- assessment/
  - CJ, NLP, grading, rubrics, result aggregation, runners.
  - Example: `assessment/nlp_lang_tool/*`
- content/
  - Content Service, prompt references, storage by reference.
- identity/
  - Auth/JWT/roles/API Gateway auth flows and rollout tasks.
  - Example: `identity/TASK-IDENTITY-RS256-JWT-ROLLOUT.md`
- frontend/
  - SPA integration, websockets, upload UX, Svelte 5.
  - Example: `frontend/SVELTE5_CORS_AND_DEV_UTILITIES.md`
- infrastructure/
  - DevOps/CI/CD/docker/compose/observability/scripts. Keep existing folder name.
- security/
  - AppSec, threat models, secrets, audits.
- integrations/
  - External APIs/providers, contracts, quotas.
- architecture/
  - Cross-domain standards, ADRs, patterns.
- archive/
  - `archive/YYYY/MM/<domain>/` for completed/legacy items.

## Status Handling

- Keep status in front matter (machine-readable), not in folder names.
- Allowed statuses: `research | blocked | in_progress | completed | paused | archived`.

## Ownership & Teams

- Default `owner_team: agents` (you + LLM agents). Optional `owner: "@username"` per task.
- Enforced via validation script and pre-commit/CI in follow-up.

## Programmes

- Programme hubs live at `programmes/<name>/HUB.md` and link to related tasks across domains.
- Example: `programmes/cj_confidence/PHASE3_CJ_CONFIDENCE_HUB.md`.

## Archive Policy

- Path: `archive/YYYY/MM/<domain>/`.
- Defer bulk archiving unless an item is obviously legacy; mark as `archived` in front matter when moved.

## Mapping From Current Structure

- `TASKS/phase3_cj_confidence/*` → `TASKS/programmes/cj_confidence/`
- `TASKS/nlp_lang_tool/*` → `TASKS/assessment/nlp_lang_tool/`
- `TASKS/SVELTE5_CORS_AND_DEV_UTILITIES.md` → `TASKS/frontend/`
- Keep `TASKS/infrastructure/` as-is (name, scope, README) to avoid churn.

## Pilot Moves (Low Risk)

- Only move the three mappings above.
- Run validation and regenerate index after moves.

## Automation & Enforcement

- Minimal YAML front matter (validated by script) on each task:

```yaml
---
id: TASK-XXXX
title: Example Title
status: research
priority: medium
domain: assessment
service: ""
owner_team: agents
owner: ""
program: ""
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
related: []
labels: []
---
```

- Scripts (standard library only, harness-independent):
  - `scripts/task_mgmt/new_task.py` – scaffold new tasks with front matter
  - `scripts/task_mgmt/validate_front_matter.py` – validate required fields/enums
  - `scripts/task_mgmt/index_tasks.py` – generate `TASKS/INDEX.md`
  - `scripts/task_mgmt/archive_task.py` – move tasks to archive and update status

## Alternatives Considered

- Option A (Responsibility/Team-based): unclear for LLM agents; ownership shifts often.
- Option C (Status-based folders): noisy PR churn as tasks change state; poor history and discoverability.

## Approval Checklist

- [ ] Confirm taxonomy and domains
- [ ] Approve archive policy (`YYYY/MM/{domain}`)
- [ ] Approve default `owner_team: agents`
- [ ] Approve pilot moves and immediate doc updates (smoketest design revision, docker lock review, Phase 3.2 compression, AI Feedback plan update)
- [ ] Approve adding the 4 scripts and CI validation in follow-up

## Next Steps (Upon Approval)

1. Create missing folders and run pilot moves.
2. Add front matter to all tasks (script-assisted) and validate.
3. Generate `TASKS/INDEX.md` and commit.
4. Update `TASKS/README.md` and `.claude/HANDOFF.md` references.
