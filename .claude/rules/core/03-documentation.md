# Documentation Standards

## Task Tracking
- **Create**: `pdm run new-task --domain <domain> --title "Title"`
- **Location**: `TASKS/<domain>/<id>.md`
- **Never** create tasks manually

## Document Types

| Type | Location | Notes |
|------|----------|-------|
| Runbooks | `docs/operations/` | Requires frontmatter |
| ADRs | `docs/decisions/` | Requires frontmatter |
| How-tos | `docs/how-to/` | — |
| Reports | `.claude/work/reports/` | Research/diagnostic |

## Naming
- All files: **lowercase kebab-case**
- No spaces in filenames
- Filename must match frontmatter `id` for tasks

## Validation
```bash
pdm run new-task
pdm run validate-tasks
pdm run python scripts/docs_mgmt/validate_docs_structure.py --verbose
```
