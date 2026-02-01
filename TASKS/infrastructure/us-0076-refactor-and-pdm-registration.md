---
id: us-0076-refactor-and-pdm-registration
title: US-007.6 Refactor and PDM Registration
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
- us-0071-shared-utilities-extraction
labels:
- dev-tooling
---
# US-007.6 Refactor and PDM Registration

## Objective

Migrate existing scripts to shared utilities and register all new PDM script entries.

## Deliverables

### 1. Refactor task scripts
- `validate_front_matter.py` → use `frontmatter_utils` + `validation_reporter`
- `filter_tasks.py` → use `frontmatter_utils`
- `index_tasks.py` → use `frontmatter_utils`
- `new_task.py` → use shared utils, improve terminal hints

### 2. Refactor docs/rules validators
- `validate_docs_structure.py` → use `frontmatter_utils` + `validation_reporter`
- `validate_claude_structure.py` → use `frontmatter_utils` + `validation_reporter`

### 3. PDM script registration
Add to `pyproject.toml`:
```toml
new-doc = {cmd = ["python", "scripts/docs_mgmt/new_doc.py"]}
new-runbook = "python scripts/docs_mgmt/new_doc.py --type runbook --title"
new-adr = "python scripts/docs_mgmt/new_doc.py --type adr --title"
new-epic = "python scripts/docs_mgmt/new_doc.py --type epic --title"
index-docs = "python scripts/docs_mgmt/index_docs.py"
new-rule = {cmd = ["python", "scripts/claude_mgmt/new_rule.py"]}
index-rules = "python scripts/claude_mgmt/index_rules.py"
validate-all = "python scripts/validate_all.py --all --verbose"
```

## Success Criteria

- [ ] All existing scripts use shared utilities
- [ ] No code duplication for frontmatter parsing
- [ ] All PDM scripts registered and working
- [ ] Pre-commit hooks pass after refactor

## Related

- Depends on: US-007.1 through US-007.5
- Consolidates: Phase 6 + Phase 7 from plan
