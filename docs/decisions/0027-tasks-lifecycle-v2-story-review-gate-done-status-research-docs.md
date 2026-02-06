---
type: decision
id: ADR-0027
status: accepted
created: '2026-02-01'
last_updated: '2026-02-01'
---
# ADR-0027: TASKS lifecycle v2 (story review gate, done status, research docs)

## Status

Accepted (2026-02-01)

## Context

HuleEdu uses `TASKS/` as the execution layer for agents and developers. Over time,
we overloaded the `status` field with `research`, which conflated:

- work state (is a work item started / blocked / done?)
- artifact type (is this a work item vs a research note?)

This creates ambiguity, makes tooling harder to reason about, and encourages
mixing planning/reference content into work tracking.

## Decision

### 1) Work items use a work-state lifecycle (no `research` status)

`TASKS/` frontmatter status is now one of:

- `proposed`
- `in_review` (stories only)
- `approved` (stories only)
- `in_progress`
- `blocked`
- `paused`
- `done`
- `archived`

### 2) Stories have an explicit review gate; tasks stay lean

- **Stories** may flow: `proposed → in_review → approved → in_progress|blocked → done`
- **Tasks** skip review and may flow: `proposed → in_progress|blocked → done`

### 3) Research is a documentation artifact, not a TASKS status

Research notes live in `docs/research/` with `type: research` frontmatter.

### 4) Reviews are explicit docs-as-code artifacts

Story approval is recorded in `docs/product/reviews/` as `type: review`.
This is the canonical record for moving a story from `in_review` to `approved`.

## Consequences

- **Clearer semantics**: status now means “work state”, not “document category”.
- **Lower cognitive load**: tasks remain low-ceremony; only stories require review.
- **Better tooling**: validators and query scripts can rely on YAML frontmatter and
  stable enums.

Migration notes:
- Existing `status: research` and `status: completed` were migrated to
  `proposed` and `done` respectively.

## Related

- Hub: `docs/reference/ref-tasks-lifecycle-v2.md`
- Research:
  `docs/research/research-tasks-lifecycle-v2-governance-and-topology-notes.md`
- Implementation task:
  `TASKS/architecture/align-tasks-and-docs-lifecycle-v2.md`
