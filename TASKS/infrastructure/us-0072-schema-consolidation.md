---
id: us-0072-schema-consolidation
title: US-007.2 Schema Consolidation
type: story
status: done
priority: high
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
- us-0071-shared-utilities-extraction
labels:
- dev-tooling
---
# US-007.2 Schema Consolidation

## Objective

Consolidate all frontmatter schemas into `scripts/schemas/` with `get_allowed_values()` helpers.

## Implementation (COMPLETED)

### Schemas Created in `scripts/schemas/`

1. **`task_schema.py`** - TaskFrontmatter, TaskStatus, TaskPriority, TaskDomain, TaskType enums
2. **`rule_schema.py`** - RuleFrontmatter, RuleType, RuleScope Literal types
3. **`docs_schema.py`** - RunbookFrontmatter, DecisionFrontmatter, EpicFrontmatter
4. **`__init__.py`** - Public exports for all schemas

### All Schemas Include `get_allowed_values()`

```python
def get_allowed_values() -> dict[str, list[str]]:
    """Return dict of field names to allowed values for CLI hints."""
```

### Import Updates

Consumer files updated to import from `scripts.schemas.*`:
- `scripts/task_mgmt/new_task.py`
- `scripts/task_mgmt/validate_front_matter.py`
- `scripts/task_mgmt/archive_task.py`
- `scripts/task_mgmt/migrate_to_spec.py`
- `scripts/claude_mgmt/validate_claude_structure.py`

### Original Files Deleted

- `scripts/task_mgmt/task_frontmatter_schema.py` - DELETED
- `scripts/claude_mgmt/rule_frontmatter_schema.py` - DELETED

## Success Criteria

- [x] `scripts/schemas/` created with consolidated schemas
- [x] All schemas have `get_allowed_values()` returning enum values
- [x] Consumer scripts import from new location
- [x] Original schema files deleted
- [x] 66 tests passing
- [x] typecheck-all passes

## Related

- Depends on: US-007.1
- Plan: `.claude/plans/steady-finding-muffin.md`
