---
description: 
globs: 
alwaysApply: true
---
===
# 050: Python Coding Standards

## 1. Core Philosophy
- Readability first. Explicit over implicit. Simple over complex.
- SOLID, DRY, YAGNI principles.

## 2. Tooling & Formatting

### 2.1. Ruff (Formatting and Linting)
- **Commands**: `pdm run format-all`, `pdm run lint-fix --unsafe-fixes`
- **Auto-fix**: `ruff check --fix --force-exclude .`
- **Configuration**: `pyproject.toml` under `[tool.ruff]`
- **MUST** use `--force-exclude` flag
- **MUST** be Ruff compliant

## 3. Static Typing (Mypy)

### 3.1. Type Hinting Rules
- **MUST** type-annotate all public functions, methods, class attributes
- **MUST** use `from __future__ import annotations`
- **MUST** prefer precise types over `typing.Any`
- **MUST** pass `typecheck all` (run from repository root to catch complex multi-level issues)
- **FORBIDDEN**: `typing.Any` where precise type possible

### 3.2. Execution Patterns
**MUST** run mypy from repository root:

```bash
# ✅ CORRECT
pdm run mypy        # Standard command
pdm run mypy services/       # Check services

### 3.3. Missing Type Stubs
- **FORBIDDEN**: Creating `py.typed` marker files for internal modules
- **REQUIRED**: Add modules without type stubs to `pyproject.toml` MyPy overrides
- **Pattern**: Add to external libraries section with `ignore_missing_imports = true`

### 3.4. Protocol Implementation Patterns
- **MUST** use explicit protocol inheritance to resolve DI type issues
- **PATTERN**: Use `TYPE_CHECKING` imports for protocol type aliases when needed

```python
# ✅ CORRECT - Explicit protocol implementation
from services.my_service.protocols import MyProtocol

class ConcreteImpl(MyProtocol):
    # Implementation methods

# ✅ CORRECT - TYPE_CHECKING pattern for type aliases
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.my_service.protocols import MyProtocol as ProtocolMyProtocol

class ConcreteImpl:
    def method(self) -> ConcreteMyType:  # Returns concrete type
        # MyPy accepts this as implementing ProtocolMyProtocol
```

### 3.5. Dependency Injection Principle
- Business logic **MUST** depend on abstractions (`typing.Protocol`), not concrete implementations.
- **MUST** use Dishka DI framework; every provider lives in `<service>/di.py`
- HTTP services **MUST** use `quart-dishka` integration with `@inject` decorator
- **FORBIDDEN**: Direct imports of concrete classes in business logic

## 4. Documentation

### 4.1. Google-Style Docstrings
- **MUST** have docstrings for all public modules, classes, functions, methods
- **Content**: Purpose, Args, Returns, Raises
- **MUST** be Google-style format

### 4.2. Inline Comments
- Use for non-obvious logic or "why" (not "what")

## 5. Naming Conventions
- Modules/Packages: `snake_case.py`
- Classes/Exceptions: `PascalCase` (Exceptions end with `Error`)
- Functions/Methods/Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_private_member`

## 6. Code Structure
- **Error Handling**: Catch specific exceptions, use domain-specific exceptions
- **Line Length**: Max 100 characters (hard limit enforced by CI where possible).
- **File Size Limits**:
  - **Production Code**: HARD LIMIT 400-500 LoC per file
    - **Rationale**: Enforces Single Responsibility Principle (SRP), improves maintainability and testability
    - **When approaching limit**: Extract helper functions, split by feature/domain, create subdirectory for related files
    - **Enforcement**: CI checks via `scripts/loc_guard.sh` where possible
  - **Test Files**: SOFT LIMIT 800 LoC, HARD LIMIT 1,200 LoC per file
    - **Rationale**: Test files naturally contain repetitive setup/assertions; multiple test cases for single component belong together
    - **When approaching 800 LoC**: Consider extracting shared fixtures to test utilities
    - **When approaching 1,000 LoC**: Consider splitting by feature or test category
    - **When exceeding 1,200 LoC**: MUST refactor - split test suite
    - **Exception**: Integration/E2E test suites may exceed limits if testing comprehensive workflows
- **Blank Lines**: Per PEP 8
- **Imports**: Prefer consistent patterns within services; actual import failures are usually service configuration issues

## 7. Service Configuration Priority

**When debugging import errors, prioritize service setup over import patterns**:
- Verify `PYTHONPATH=/app` in Dockerfiles
- Check DI container usage vs manual instantiation  
- Validate framework configuration methods
- Confirm environment variable alignment

See [044-service-debugging-and-troubleshooting.md](mdc:044-service-debugging-and-troubleshooting.md) for systematic debugging approach
===
