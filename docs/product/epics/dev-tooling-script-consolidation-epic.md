---
type: epic
id: EPIC-007
title: Dev Tooling Script Consolidation
status: draft
phase: 1
sprint_target: TBD
created: 2025-12-01
last_updated: 2025-12-01
---

# EPIC-007: Dev Tooling Script Consolidation

## Summary

Consolidate and extend the documentation/task/rules management scripts to achieve tooling parity across all three domains, with unified validation and improved developer ergonomics.

**Business Value**: Enable LLM agents and developers to create docs/rules programmatically with consistent patterns, reduce code duplication, and streamline validation workflows.

**Scope Boundaries**:
- **In Scope**: Shared utilities, schema consolidation, creation scripts, indexing scripts, unified validation
- **Out of Scope**: Query/filter scripts for docs/rules (future enhancement)

**Decision**: ADR-0019

## Deliverables

| Domain | Create | Validate | Index | Schema |
|--------|--------|----------|-------|--------|
| Tasks | `new_task.py` (exists) | `validate_front_matter.py` | `index_tasks.py` | `task_frontmatter_schema.py` |
| Docs | `new_doc.py` (new) | `validate_docs_structure.py` | `index_docs.py` (new) | `docs_frontmatter_schema.py` (new) |
| Rules | `new_rule.py` (new) | `validate_claude_structure.py` | `index_rules.py` (new) | `rule_frontmatter_schema.py` |

Plus:
- `scripts/utils/frontmatter_utils.py` - shared frontmatter parsing/writing
- `scripts/utils/validation_reporter.py` - unified validation reporting
- `scripts/validate_all.py` - single validation entry point

## User Stories

### US-007.1: Shared Utilities Extraction
Extract common frontmatter and validation utilities to `scripts/utils/`.

### US-007.2: Schema Consolidation
Create `docs_frontmatter_schema.py` and add `get_allowed_values()` to all schemas.

### US-007.3: Creation Scripts
Create `new_doc.py` and `new_rule.py` with LLM-compatible single CLI invocation.

### US-007.4: Indexing Scripts
Create `index_docs.py` and `index_rules.py` for index generation.

### US-007.5: Unified Validation
Create `validate_all.py` and integrate with `lint-fix` PDM script.

### US-007.6: Refactor & Registration
Migrate existing scripts to shared utils and register all PDM script entries.

## References

- Plan: `.claude/plans/keen-growing-umbrella.md`
- ADR: `docs/decisions/0019-script-management-consolidation.md`
