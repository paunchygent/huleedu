---
id: us-0071-shared-utilities-extraction
title: US-007.1 Shared Utilities Extraction
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
labels:
- dev-tooling
---
# US-007.1 Shared Utilities Extraction

## Objective

Extract common frontmatter and validation utilities to `scripts/utils/` to eliminate code duplication across task/docs/rules management scripts.

## Deliverables

### 1. `scripts/utils/frontmatter_utils.py`
- `read_front_matter(path) -> tuple[dict, str]` - parse YAML frontmatter
- `write_front_matter(path, frontmatter, body)` - write file with frontmatter
- `validate_frontmatter_against_schema(data, schema_class)` - generic Pydantic validation

### 2. `scripts/utils/validation_reporter.py`
- `ValidationReporter` class for collecting errors/warnings
- `report_file_result(path, status, message)` - consistent `[OK]`/`[ERROR]` output
- `exit_with_summary()` - aggregated summary and exit code

## Success Criteria

- [x] Both utilities created (`frontmatter_utils.py`, `validation_reporter.py`)
- [x] Pattern extracted from `scripts/task_mgmt/validate_front_matter.py`
- [x] Uses yaml.safe_load (stdlib + yaml, no new deps added)
- [x] Smoke tests pass for both utilities
- [x] Strict mypy passes for new modules

## Implementation Notes

- Used `yaml.safe_load` instead of regex-based parsing (aligns with `validate_claude_structure.py`)
- `ValidationReporter` supports verbose mode and strict mode (warnings as errors)
- Tests via smoke commands; formal unit tests deferred to US-007.6 refactoring story

## Related

- Epic: `docs/product/epics/dev-tooling-script-consolidation-epic.md`
- ADR: `docs/decisions/0019-script-management-consolidation.md`
- Plan: `.claude/plans/keen-growing-umbrella.md`
