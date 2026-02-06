---
type: reference
id: REF-tasks-lifecycle-v2
title: "TASKS lifecycle v2"
status: active
created: 2026-02-01
last_updated: 2026-02-01
topic: task-lifecycle
---

# TASKS lifecycle v2

## Purpose

Define a lean, agent-first workflow for work items in `TASKS/`, and keep
research/reviews as explicit documentation artifacts in `docs/`.

Note: `type: doc` is intentionally not used in `TASKS/` (docs belong under `docs/`).

<!-- BEGIN:workstream-topology:tasks-lifecycle-v2 -->
## Topology Contract (Generated)

- Manifest: `scripts/docs_mgmt/workstream_topology/tasks-lifecycle-v2.toml`
- Canonical chain:
  - Runbook: `docs/reference/ref-tasks-overview.md`
  - Epic: `docs/product/epics/dev-tooling-script-consolidation-epic.md`
  - Decision: `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`
  - Decision gate task: `TASKS/architecture/align-tasks-and-docs-lifecycle-v2.md`
  - Research: `docs/research/research-tasks-lifecycle-v2-governance-and-topology-notes.md`
- Active tracks:
  - `TASKS/architecture/align-tasks-and-docs-lifecycle-v2.md`
- Review records:
  - `docs/product/reviews/review-example-story-approval.md`
- Evidence roots:
  - `TASKS`
  - `docs/product/reviews`
<!-- END:workstream-topology:tasks-lifecycle-v2 -->

## Canonical statuses

Work item `status` is a work-state enum (not a document category):

- `proposed`
- `in_review` (stories only)
- `approved` (stories only)
- `in_progress`
- `blocked`
- `paused`
- `done`
- `archived`

## Story vs task semantics (lean)

- **Story**: requires an explicit review record before implementation.
  - `proposed → in_review → approved → in_progress|blocked → done`
- **Task**: no review gate.
  - `proposed → in_progress|blocked → done`

## Where docs live

- Research notes: `docs/research/` (`type: research`)
- Story reviews: `docs/product/reviews/` (`type: review`)
- Decisions: `docs/decisions/` (`type: decision`)

## Commands

- Create a story: `pdm run new-task --domain <domain> --type story --title "..." --status proposed`
- Create a review doc: `pdm run new-doc --type review --title "Review: ..." --story <story-id>`
- Query tasks: `pdm run tasks --status in_progress`
- Index tasks: `pdm run index-tasks`

## References

- `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`
- `TASKS/_REORGANIZATION_PROPOSAL.md`
