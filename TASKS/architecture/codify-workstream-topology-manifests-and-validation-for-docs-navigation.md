---
id: 'codify-workstream-topology-manifests-and-validation-for-docs-navigation'
title: 'codify workstream topology manifests and validation for docs navigation'
type: 'task'
status: 'done'
priority: 'medium'
domain: 'architecture'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-06'
last_updated: '2026-02-06'
related: []
labels: []
---
# codify workstream topology manifests and validation for docs navigation

## Objective

Codify one maintainable docs navigation contract for essay-scoring so
documentation placement remains clean and link topology stays enforceable.

## Context

`docs/` placement is correct, but navigation has started to feel scattered due to
unbounded cross-links across research, decision, tasks, and review records.
We need a machine-validated topology that keeps one canonical entrypoint and a
stable decision path.

## Plan

1) Add a workstream topology manifest for essay-scoring.
2) Add validator logic for manifest integrity, backlinks, and generated hub freshness.
3) Add a hub renderer with marker-based generated block updates.
4) Wire validation into `pdm run validate-docs`.
5) Update docs structure spec to document the contract.

## Success Criteria

- One manifest exists and references canonical essay-scoring docs/tasks/reviews.
- `pdm run render-workstream-hubs` updates generated topology blocks.
- `pdm run validate-docs` fails on stale/missing topology links.
- `docs/DOCS_STRUCTURE_SPEC.md` documents the codified topology contract.
- All validation commands pass.

## Implementation Notes

- Added topology manifests:
  `scripts/docs_mgmt/workstream_topology/essay-scoring.toml`
  `scripts/docs_mgmt/workstream_topology/tasks-lifecycle-v2.toml`
- Added shared parser/render helpers:
  `scripts/docs_mgmt/workstream_topology_manifest.py`
- Added hub renderer:
  `scripts/docs_mgmt/render_workstream_hubs.py`
- Added topology validator:
  `scripts/docs_mgmt/validate_workstream_topology.py`
- Added tests:
  `scripts/docs_mgmt/tests/test_workstream_topology_manifest.py`
- Updated scripts:
  `pyproject.toml` (`render-workstream-hubs`, `validate-docs`)
- Updated hub/spec docs:
  `docs/reference/ref-essay-scoring-research-hub.md`
  `docs/reference/ref-tasks-lifecycle-v2.md`
  `docs/DOCS_STRUCTURE_SPEC.md`
- Added lifecycle governance research note:
  `docs/research/research-tasks-lifecycle-v2-governance-and-topology-notes.md`

## Related

- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Decision gate task:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
- ADR:
  `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
