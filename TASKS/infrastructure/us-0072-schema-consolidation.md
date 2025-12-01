---
id: 'us-0072-schema-consolidation'
title: 'US-007.2 Schema Consolidation'
type: 'story'
status: 'research'
priority: 'high'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-01'
last_updated: '2025-12-01'
related: ['EPIC-007', 'ADR-0019', 'us-0071-shared-utilities-extraction']
labels: ['dev-tooling']
---
# US-007.2 Schema Consolidation

## Objective

Create docs frontmatter schema and add `get_allowed_values()` helpers to all schemas for CLI hints.

## Deliverables

### 1. `scripts/docs_mgmt/docs_frontmatter_schema.py`
Extract from `validate_docs_structure.py`:
- `RunbookFrontmatter` - runbook schema
- `ADRFrontmatter` - decision record schema
- `EpicFrontmatter` - epic schema
- `DocType` enum: runbook, adr, epic
- `get_allowed_values()` - returns dict of field -> allowed values

### 2. Update existing schemas
- `task_frontmatter_schema.py`: Add `get_allowed_values()`
- `rule_frontmatter_schema.py`: Add `get_allowed_values()`

## Success Criteria

- [ ] `docs_frontmatter_schema.py` created with Pydantic models
- [ ] All three schemas have `get_allowed_values()` returning enum values
- [ ] `validate_docs_structure.py` imports schema instead of hardcoded rules

## Related

- Depends on: US-007.1
- Plan: `.claude/plans/keen-growing-umbrella.md`
