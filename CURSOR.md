# HuleEdu – Cursor Agent Reference

## Standard Test Runner

- Use the root-aware runner for all pytest executions to ensure consistent config and path resolution across the monorepo.

```bash
# From repo root
pdm run pytest-root <path-or-nodeid> [pytest args]

# Anywhere (recommended helpers)
source scripts/dev-aliases.sh
pyp <path-or-nodeid> [args]                 # run tests via root-aware wrapper
pdmr pytest-root <path-or-nodeid> [args]    # force PDM to use repo root

# Optional global shim (no PDM project discovery)
pytest-root <path-or-nodeid> [args]
```

Notes
- The wrapper passes `-m ""` by default so all markers are included unless you specify `-m`.
- Supports node-ids (including parametrized cases with spaces) and rewrites paths relative to the repository root.
- Prefer this over `pdm run pytest` to avoid subproject resolution issues.

## Debugging
- Append `-s` to the standard runner for debug output, e.g. `pdm run pytest-root -s <path>`.

## Type Checking
- Always run from root: `pdm run typecheck-all`.

