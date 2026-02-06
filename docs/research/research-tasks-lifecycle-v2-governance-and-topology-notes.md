---
type: research
id: RES-tasks-lifecycle-v2-governance-and-topology-notes
title: TASKS lifecycle v2 governance and topology notes
status: active
created: '2026-02-06'
last_updated: '2026-02-06'
---
# TASKS lifecycle v2 governance and topology notes

## Question

How do we keep TASKS/docs lifecycle navigation enforceable as the number of
stories, review records, and helper docs grows?

## Findings

- Hub-first navigation is the stable contract:
  `docs/reference/ref-tasks-lifecycle-v2.md`
- Decision source of truth remains:
  `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`
- Work execution for this lifecycle stream has one canonical implementation task:
  `TASKS/architecture/align-tasks-and-docs-lifecycle-v2.md`
- Review records are docs-as-code artifacts under:
  `docs/product/reviews/`

## Decision / Next Steps

- Keep this stream codified through the topology manifest:
  `scripts/docs_mgmt/workstream_topology/tasks-lifecycle-v2.toml`
- Validate as part of the default docs pipeline:
  `pdm run validate-docs`
- Render generated hub topology blocks when manifest content changes:
  `pdm run render-workstream-hubs`
