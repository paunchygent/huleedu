---
id: 'hemma-operations-runbooks-huleedu--gpu'
title: 'Hemma operations runbooks (HuleEdu + GPU)'
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
labels: ['operations', 'hemma', 'gpu', 'runbook']
---
# Hemma operations runbooks (HuleEdu + GPU)

## Objective

Create HuleEdu-native, repo-local runbooks for operating the Hemma server as an
infrastructure host for HuleEdu services and GPU workloads, while remaining explicitly
compatible with the existing Skriptoteket deployment on the same host.

## Context

We are offloading RAM- and GPU-heavy NLP workloads (LanguageTool, DeBERTa + spaCy /
TextDescriptives feature extraction) to Hemma to keep the local research loop fast and
predictable on a MacBook.

The existing `skriptoteket-devops` Codex skill references runbooks that are not present
in this repo; for HuleEdu work we need runbooks that live under `docs/operations/`
(normative) and match the HuleEdu service layout and Docker workflows.

## Plan

1. Add a Hemma home-server runbook under `docs/operations/`.
2. Add a GPU AI workloads runbook under `docs/operations/`.
3. Keep guidance scoped to HuleEdu needs (no generic freeze/hang recovery playbooks).
4. Cross-link to the essay-scoring offload ADR and TASKS.
5. Validate docs structure + tasks indexing.

## Success Criteria

- Runbooks exist under `docs/operations/` and follow frontmatter rules.
- Runbooks include copy-paste-ready commands for:
  - health checks, logs, restarts
  - SSH port-forwarding tunnels to localhost-bound services
  - GPU container verification steps (ROCm)
- Docs validators pass (`pdm run validate-tasks` + docs validators).

## Related

- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
- `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
- `TASKS/infrastructure/huleedu-devops-codex-skill-for-hemma-server.md`
- `TASKS/assessment/offload-deberta--spacy-features-to-hemma-binary-embedding-service.md`
