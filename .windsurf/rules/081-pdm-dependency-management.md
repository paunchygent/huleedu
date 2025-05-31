---
trigger: model_decision
description: "PDM dependency management standards. Follow when adding, updating, or removing Python dependencies to ensure consistency and reproducibility."
---

---
description: MUST READ whenever working on or discussing pdm resolution, versioning, and .toml files
globs: 
alwaysApply: false
---
# 081: PDM Dependency Management Standards

## 1. PDM Configuration Standards

### 1.1. Minimal Configuration
**MUST** use minimal PDM configuration:

```toml
[tool.pdm]
distribution = false  # Application/library, not distributable package
```

### 1.2. No Custom Resolution Settings
**FORBIDDEN**: Custom resolution settings. PDM defaults are optimal:
- `strategy.inherit_metadata = True` (DEFAULT)
- `strategy.resolve_max_rounds = 10000` (DEFAULT)
- `strategy.save = minimum` (DEFAULT)
- `strategy.update = reuse` (DEFAULT)

## 2. Dependency Version Strategy

### 2.1. Let PDM Handle Versions
**REQUIRED**: Use unconstrained dependency specifications:

```toml
[dependency-groups]
monorepo-tools = [
    "ruff",           # ✅ No version constraints
    "mypy",
    "pytest",
    "pytest-cov",
    "pytest-asyncio",
    "pre-commit"
]
```

PDM resolves latest compatible versions and locks them in `pdm.lock`.

### 2.2. Version Constraints Only When Necessary
Only add version constraints for:
- Breaking changes in major versions
- Known incompatibilities
- Security requirements

## 3. Validation Commands

### 3.1. Regular Validation
**MUST** run these commands to validate configuration:

```bash
# Check lock file is current
pdm lock --check

# Update to latest compatible versions
pdm update

# Verify installation works
pdm install
```

## 4. Scripts Configuration

### 4.1. Standard Scripts
**REQUIRED** scripts for monorepo management:

```toml
[tool.pdm.scripts]
format-all = "ruff format --force-exclude ."
lint-all = "ruff check --force-exclude ."
lint-fix = "ruff check --fix --force-exclude ."
typecheck-all = "mypy --config-file pyproject.toml ."
test-all = "pytest -n auto"
```