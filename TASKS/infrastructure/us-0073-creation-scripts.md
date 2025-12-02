---
id: 'us-0073-creation-scripts'
title: 'US-007.3 Creation Scripts'
type: 'story'
status: 'completed'
priority: 'high'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-01'
last_updated: '2025-12-01'
related: ['EPIC-007', 'ADR-0019', 'us-0072-schema-consolidation']
labels: ['dev-tooling']
---
# US-007.3 Creation Scripts

## Objective

Create `new_doc.py` and `new_rule.py` with LLM-compatible single CLI invocation (no interactive prompts).

## Deliverables

### 1. `scripts/docs_mgmt/new_doc.py`
```bash
pdm run new-doc --type runbook --title "My Runbook"
pdm run new-doc --type adr --title "My Decision"
pdm run new-doc --type epic --title "My Epic"
```
- Auto-generate ADR ID (scan `docs/decisions/` for next NNNN)
- Output path based on type: `docs/operations/`, `docs/decisions/`, `docs/product/epics/`
- Print allowed values for all fields on success

### 2. `scripts/claude_mgmt/new_rule.py`
```bash
pdm run new-rule --title "My Rule" --type service --scope backend
```
- Auto-generate rule ID (scan `.claude/rules/` for next NNN prefix)
- Output to `.claude/rules/NNN-kebab-title.md`
- Print allowed values for `--type` and `--scope`

## Success Criteria

- [x] Both scripts work with single CLI invocation
- [x] Auto-increment IDs work correctly
- [x] Terminal output shows allowed enum values
- [x] Pattern mirrors `new_task.py`
- [x] All management scripts run as modules (no sys.path bootstrap)
- [x] PDM scripts registered: `new-doc`, `new-rule`

## Related

- Depends on: US-007.2
- Reference: `scripts/task_mgmt/new_task.py`
