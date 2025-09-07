# HuleEdu – Codex Agent Reference

## Test Runner (Go-To)

- Preferred: use the root-aware runner so file paths work from anywhere and all markers are included by default.

```bash
# From repo root
pdm run pytest-root <path-or-nodeid> [pytest args]

# Examples
pdm run pytest-root services/class_management_service/tests/test_core_logic.py
pdm run pytest-root 'services/.../test_file.py::TestClass::test_case'
pdm run pytest-root services/... -k 'expr'         # select tests by expression
pdm run pytest-root services/... -m 'unit'         # override markers (defaults to all)

# From any subdirectory
bash "$(git rev-parse --show-toplevel)"/scripts/pytest-root.sh <path-or-nodeid> [args]

# Optional alias: source once per shell
source scripts/dev-aliases.sh
pyp <path-or-nodeid> [args]

# Force PDM to use root project from any dir
source scripts/dev-aliases.sh
pdmr pytest-root <path-or-nodeid> [args]
```

Notes
- The wrapper calls pytest with the repo `pyproject.toml` and `-m ""` so all markers are included unless you set `-m` yourself.
- It rewrites relative paths to absolute paths under the repo root and supports node ids like `path::Class::test` and parametrized ids.

## Other Useful Commands

```bash
# Whole-suite shortcuts (from repo root)
pdm run test-all            # full suite
pdm run test-parallel       # run with xdist
pdm run test-sequential     # single-process (deterministic ordering)
```

## Prototype Codebase Guardrails (No Legacy Policy)

- No legacy shims: do not keep backward-compatibility wrappers when evolving protocols or APIs in the prototype.
- No aliases or pass-through methods that duplicate intent; rename or replace and update all call sites.
- Prefer clear, explicit contracts over transitional indirection; update dependent tests promptly.
- Rationale: aligning early prevents spaghetti, drift, and hidden behavior. Changes should be surgical, explicit, and type-safe.

## Optional Global Convenience

Create a system-wide shim so `pytest-root` works from any directory without PDM project discovery:

```bash
mkdir -p "$HOME/.local/bin"
ln -sf "$(git rev-parse --show-toplevel)/scripts/pytest-root.sh" "$HOME/.local/bin/pytest-root"
chmod +x "$HOME/.local/bin/pytest-root"
# Ensure ~/.local/bin is on PATH (add to your shell rc if needed)
export PATH="$HOME/.local/bin:$PATH"

# Usage from anywhere
pytest-root services/.../tests/test_file.py -k 'expr'
```
