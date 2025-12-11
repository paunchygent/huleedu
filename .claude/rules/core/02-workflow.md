# Core Workflow

## Initial Setup
```bash
./scripts/dev-shell.sh  # Load .env before any pdm run commands
```

## Essential PDM Commands
```bash
# Quality
pdm run format-all                    # Ruff format
pdm run lint-fix --unsafe-fixes       # Auto-fix lints
pdm run typecheck-all                 # MyPy from root

# Testing  
pdm run pytest-root <path>            # Run tests
pdm run pytest-root <path> -s         # Debug mode

# Tasks & Docs
pdm run new-task --domain <d> --title "T"
pdm run new-doc --type <t> --title "T"
pdm run validate-tasks

# Docker
pdm run dev-start [service]
pdm run dev-logs [service]
```

## Task Execution
1. Read `.claude/work/session/handoff.md` for cross-service context
2. Select mode via `.agent/rules/110-ai-agent-interaction-modes.md`
3. Consult `.agent/rules/000-rule-index.md` for relevant rules and
docs/ for relevant code maps and runbooks to avoid assumptions
4. Update `.claude/work/session/handoff.md` after each task phase to document progress and decisions and the task/story/epic each
session to keep docs from going stale.

## Error Resolution
1. **Investigate first** — Check implementation before proposing changes
2. **Follow patterns** — Use existing code patterns over new abstractions
3. **Root cause** — Fix immediate issues before redesigning
