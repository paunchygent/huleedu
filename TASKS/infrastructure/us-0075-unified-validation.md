---
id: 'us-0075-unified-validation'
title: 'US-007.5 Unified Validation'
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
# US-007.5 Unified Validation

## Objective

Create single validation entry point and integrate with `lint-fix` PDM script.

## Deliverables

### 1. `scripts/validate_all.py`
```bash
pdm run validate-all              # validates all (default)
pdm run validate-all --tasks      # tasks only
pdm run validate-all --docs       # docs only
pdm run validate-all --rules      # rules only
pdm run validate-all --verbose    # verbose output
```
- Aggregate results from all three validators
- Exit code: 0 if all pass, 1 if any fail
- Use `ValidationReporter` from shared utils

### 2. Integration with lint-fix
Update `pyproject.toml` to include `validate-all` in the `lint-fix` composite script chain.

## Success Criteria

- [ ] `validate_all.py` invokes all three validators
- [ ] Aggregated summary shows pass/fail counts per domain
- [ ] `lint-fix --unsafe-fixes` includes validation step
- [ ] Pre-commit hooks still work independently

## Related

- Depends on: US-007.1
- Validators: `validate_front_matter.py`, `validate_docs_structure.py`, `validate_claude_structure.py`
