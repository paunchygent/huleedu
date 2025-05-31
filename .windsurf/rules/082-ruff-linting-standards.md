---
trigger: model_decision
description: "Ruff linting standards. Follow when writing or reviewing Python code to ensure code quality and consistency through automated style enforcement."
---

---
description: Read whenever discussing linter settings
globs: 
alwaysApply: false
---
# 082: Ruff Linting Standards

## 1. Ruff Configuration

### 1.1. Core Settings
**REQUIRED** Ruff configuration in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
exclude = [
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".pdm-python",
    ".pdm-build",
    "common_core/.venv",
]
```

### 1.2. Lint Rules Selection
**REQUIRED** lint rules:

```toml
[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
]
ignore = [
    "E203",  # whitespace before ':' (conflicts with black)
]
```

### 1.3. Format Settings
**REQUIRED** format configuration:

```toml
[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

## 2. Per-File Ignores

### 2.1. Service Entry Points
**ALLOWED** imports after `load_dotenv()`:

```toml
[tool.ruff.lint.per-file-ignores]
"services/*/app.py" = ["E402"]
"services/*/worker.py" = ["E402"]
```

## 3. VS Code Integration

### 3.1. Modern VS Code Settings
**REQUIRED** VS Code settings for 2025:

```json
{
  "ruff.nativeServer": "auto",
  "ruff.lineLength": 100,
  "ruff.lint.select": ["E", "W", "F", "I"],
  "ruff.lint.ignore": ["E203"],
  "ruff.organizeImports": true,
  "ruff.logLevel": "info"
}
```

### 3.2. Deprecated Settings
**FORBIDDEN** deprecated VS Code settings:
- `ruff.format.args` (handled automatically)
- `ruff.lint.args` (handled automatically)
- `ruff.showNotifications` (use `ruff.logLevel`)