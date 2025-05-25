---
description: "Python coding standards for HuleEdu. Ensures consistent, maintainable, and high-quality Python code."
globs: 
  - "**/*.py"
alwaysApply: true
---
# 050: Python Coding Standards

## 1. Core Principles
- **Readability First**: Clear, explicit, simple code
- **SOLID/DRY/YAGNI**: Follow these design principles
- **Type Safety**: Strict static typing with MyPy
- **Consistency**: Follow standards across all Python code

## 2. Tooling (Ruff + MyPy)

### 2.1. Ruff (Formatting & Linting)
- **Config**: `pyproject.toml` under `[tool.ruff]`
- **Commands**:
  - Format: `pdm run format-all`
  - Lint: `pdm run lint-all`
  - Fix: `ruff check --fix --force-exclude .`
- **Critical**: Always use `--force-exclude` flag

### 2.2. Type Checking (MyPy)
- **Requirement**: All public APIs must be typed
- **File Header**: `from __future__ import annotations`
- **Precision**:
  - Use specific types (`Protocol`, `Union`, `Optional`)
  - Avoid `typing.Any` in public interfaces
  - Use `TypedDict` for dictionaries with fixed schemas
- **Check**: `pdm run typecheck`

## 3. Code Style

### 3.1. Naming
- Modules: `snake_case.py`
- Classes: `PascalCase` (exceptions end with `Error`)
- Functions/Vars: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_private_member`

### 3.2. Structure
- Line length: 100 chars
- Imports: Absolute imports only
- Error Handling: Catch specific exceptions
- Resources: Use `with` or `try/finally`

## 4. Documentation

### 4.1. Docstrings (Google Style)
```python
"""Module-level docstring.

Public API overview and usage examples.
"""

def example(param: str) -> bool:
    """Brief description.

    Args:
        param: Description of parameter
              (type in signature)

    Returns:
        bool: Description of return value

    Raises:
        ValueError: When input is invalid
    """
```

### 4.2. Inline Comments
- Explain "why" not "what"
- Keep comments current with code
- Remove obsolete comments

## 5. Best Practices
- **Immutability**: Prefer `dataclass(frozen=True)`
- **Type Hints**: Required for all public APIs
- **Error Handling**: Use custom exceptions
- **Testing**: Write unit tests for all public functions
- **Dependencies**: Keep them minimal and well-documented
