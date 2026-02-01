---
type: reference
id: REF-tasks-overview
title: TASKS overview
status: active
created: '2026-02-01'
last_updated: '2026-02-01'
topic: task-system
---
# TASKS overview

## Purpose

`TASKS/` is the execution layer for work items (stories, tasks, programme hubs).
It is optimized for agent + developer throughput with machine-validated
frontmatter and a small work-state lifecycle.

## Canonical Rules

Source of truth:

- Structure + required frontmatter: `TASKS/_REORGANIZATION_PROPOSAL.md`
- Status semantics: `docs/reference/ref-tasks-lifecycle-v2.md`
- Schema used by tooling: `scripts/schemas/task_schema.py`

Directory taxonomy (top-level):

- `TASKS/programs/` (programme hubs)
- `TASKS/assessment/`
- `TASKS/content/`
- `TASKS/identity/`
- `TASKS/frontend/`
- `TASKS/infrastructure/`
- `TASKS/security/`
- `TASKS/integrations/`
- `TASKS/architecture/`
- `TASKS/archive/` (excluded from validation by default)

Naming:

- `id` MUST be kebab-case and MUST match the filename stem (`<id>.md`).

Docs separation:

- Work items live in `TASKS/`.
- Research notes live in `docs/research/`.
- Story approvals live in `docs/product/reviews/`.
- `type: doc` is deprecated in `TASKS/` (docs belong in `docs/`).

## Examples

```bash
# Create a task
pdm run new-task --domain assessment --type task --title "Add X"

# Create a story (review-gated)
pdm run new-task --domain frontend --type story --title "Teacher dashboard phase 6"

# Validate + index
pdm run validate-tasks
pdm run index-tasks
```
