---
id: us-0074-indexing-scripts
title: US-007.4 Indexing Scripts
type: story
status: proposed
priority: medium
domain: infrastructure
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-12-01'
last_updated: '2026-02-01'
related:
- EPIC-007
- ADR-0019
- us-0072-schema-consolidation
labels:
- dev-tooling
---
# US-007.4 Indexing Scripts

## Objective

Create index generation scripts for docs and rules, mirroring `index_tasks.py` pattern.

## Deliverables

### 1. `scripts/docs_mgmt/index_docs.py`
- Generate `docs/INDEX.md`
- Group by type: Runbooks, ADRs, Epics, How-tos
- Include: title, status, created date
- CLI: `pdm run index-docs`

### 2. `scripts/claude_mgmt/index_rules.py`
- Generate `.agent/rules/INDEX.md`
- Group by type and scope
- Include: ID, title, type, scope
- Show parent/child relationships
- CLI: `pdm run index-rules`

## Success Criteria

- [ ] `index_docs.py` generates valid markdown index
- [ ] `index_rules.py` generates valid markdown index with hierarchy
- [ ] Both use `frontmatter_utils.py` for parsing

## Related

- Depends on: US-007.1, US-007.2
- Reference: `scripts/task_mgmt/index_tasks.py`
