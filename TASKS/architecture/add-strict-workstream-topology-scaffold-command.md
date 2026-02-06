---
id: 'add-strict-workstream-topology-scaffold-command'
title: 'add strict workstream-topology-scaffold command'
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
# add strict workstream-topology-scaffold command

## Objective

Add a strict `workstream-topology-scaffold` command so topology manifests
and hub markers are created with one canonical workflow and predictable shape.

## Context

Topology contracts were working, but creating new manifests required manual file
authoring. That invites drift and inconsistent shape over time.

We need one dependable scaffold command that enforces:
- stable manifest schema,
- required path existence,
- marker generation on the target hub,
- no ambiguous/duplicate list inputs.

## Plan

1) Implement `scripts/docs_mgmt/workstream_topology_scaffold.py`.
2) Add `pdm` alias: `workstream-topology-scaffold`.
3) Add tests for deterministic scaffold behavior and strict input validation.
4) Update docs command guidance to keep one canonical command surface.

## Success Criteria

- `pdm run workstream-topology-scaffold --help` works.
- Scaffold command writes manifest + hub markers in one run.
- Duplicate repeatable args are rejected.
- `pdm run validate-docs` continues to enforce topology invariants.
- Full validation suite passes.

## Implementation Notes

- Added scaffold command module:
  `scripts/docs_mgmt/workstream_topology_scaffold.py`
- Added PDM alias:
  `workstream-topology-scaffold` in `pyproject.toml`
- Added tests:
  `scripts/docs_mgmt/tests/test_workstream_topology_scaffold.py`
- Expanded topology manifest tests:
  `scripts/docs_mgmt/tests/test_workstream_topology_manifest.py`
- Updated command guidance:
  `scripts/docs_mgmt/README.md`
  `docs/DOCS_STRUCTURE_SPEC.md`
  `.claude/work/session/readme-first.md`
  `.claude/work/session/handoff.md`

## Related

- `TASKS/architecture/codify-workstream-topology-manifests-and-validation-for-docs-navigation.md`
- `scripts/docs_mgmt/workstream_topology_manifest.py`
- `scripts/docs_mgmt/validate_workstream_topology.py`
- `scripts/docs_mgmt/render_workstream_hubs.py`
