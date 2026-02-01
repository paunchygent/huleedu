---
id: 'huleedu-devops-codex-skill-for-hemma-server'
title: 'HuleEdu DevOps Codex skill for Hemma server'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-01'
last_updated: '2026-02-01'
related: []
labels: ['operations', 'hemma', 'gpu', 'codex-skill']
---
# HuleEdu DevOps Codex skill for Hemma server

## Objective

Create a HuleEdu-aligned Codex skill for operating Hemma as a host for:
- HuleEdu services (notably `language_tool_service`)
- GPU-backed ML/NLP workloads (notably DeBERTa + spaCy/TextDescriptives offload)
- Coexistence with Skriptoteket (SSO integration later; shared infra now)

## Context

We already have `skriptoteket-devops`, but it is tailored to Skriptoteket’s repo layout
and references runbooks that are not present in this HuleEdu repo.

For HuleEdu work we need a skill that:
- references HuleEdu-native runbooks under `docs/operations/`
- uses HuleEdu service naming and compose patterns
- explicitly supports the “offload heavy NLP to Hemma” workflow for the whitebox scorer

## Plan

1. Add a version-controlled skill source under `scripts/codex_skills/huledu-devops-hemma/`.
2. Include copy-paste SSH + Docker commands for:
   - (re)deploying selected services
   - log and health triage
   - tunnel setup for localhost-bound service exposure
   - GPU workload verification
3. Install the skill into `~/.codex/skills/huledu-devops-hemma` for local use.

## Success Criteria

- `scripts/codex_skills/huledu-devops-hemma/SKILL.md` exists and references:
  - `docs/operations/hemma-server-operations-huleedu.md`
  - `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
- The skill contains a minimal, maintainable set of commands (no generic ops bloat).
- Installation into `~/.codex/skills/` is documented and repeatable.

## Related

- `TASKS/infrastructure/hemma-operations-runbooks-huleedu--gpu.md`
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
