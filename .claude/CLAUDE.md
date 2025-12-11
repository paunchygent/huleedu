# HuleEdu - Claude Code Memory

Rules are auto-loaded from `.claude/rules/`:
- `core/` — Golden rules, workflow, documentation, testing
- `backend/` — Architecture, services, database, events, docker
- `frontend/` — Overview, design system, Svelte patterns, integration

## Quick Reference

### Detailed Rules
For comprehensive guidance: `.agent/rules/000-rule-index.md`

### Session Context
- Handoff: `.claude/work/session/handoff.md`
- Tasks: `TASKS/<domain>/<id>.md`

### Common Commands
```bash
./scripts/dev-shell.sh              # Start env-aware shell
pdm run pytest-root <path>          # Run tests
pdm run format-all && pdm run lint-fix --unsafe-fixes
pdm run new-task --domain <d> --title "T"
```
