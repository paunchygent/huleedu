---
id: 'align-tasks-and-docs-lifecycle-v2'
title: 'Align TASKS and docs lifecycle v2'
type: 'task'
status: 'done'
priority: 'high'
domain: 'architecture'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-01'
last_updated: '2026-02-01'
related:
  - 'docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md'
  - 'docs/reference/ref-tasks-lifecycle-v2.md'
labels:
  - 'workflow'
  - 'task-system'
---
# Align TASKS and docs lifecycle v2

## Objective

Make work tracking (`TASKS/`) and documentation (`docs/`) unambiguous:

- `TASKS/` status means work state (no `research` status).
- Stories have a review gate (`in_review` → `approved`).
- Research and review artifacts live in `docs/`.

## Context

The previous `status: research` blurred the line between “this is a work item” and
“this is exploratory documentation”, creating inconsistent semantics and noisy
filters/indexes.

## Plan

- Update `TaskStatus` enum and validation.
- Update `new-task` defaults and fix programme hub scaffolding.
- Extend `new-doc` to create `review`/`reference`/`research` docs.
- Migrate existing TASKS frontmatter and regenerate indexes.

## Success Criteria

- `pdm run validate-tasks` passes.
- `pdm run validate-docs` passes.
- No remaining `status: research` / `status: completed` in TASKS frontmatter.

## Related

- `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`
- `docs/reference/ref-tasks-lifecycle-v2.md`
