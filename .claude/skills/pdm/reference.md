# PDM Migration Specialist - Detailed Reference

Comprehensive guide for migrating pyproject.toml from pre-PDM 2.0 to modern PEP-compliant syntax.

## Table of Contents

1. [Development Dependencies Migration](#development-dependencies-migration)
2. [Project Metadata Migration (PEP 621)](#project-metadata-migration-pep-621)
3. [Dependency Specification](#dependency-specification)
4. [Build Backend Migration](#build-backend-migration)
5. [Local Dependencies](#local-dependencies)
6. [Optional Dependencies](#optional-dependencies)
7. [Complete Migration Workflow](#complete-migration-workflow)
8. [Context7 Integration](#context7-integration)

---

## Development Dependencies Migration

### The Major Change: PEP 735

**Pre-PDM 2.0** used a custom `[tool.pdm.dev-dependencies]` table that was PDM-specific and not standardized.

**PDM 2.0+** adopts **PEP 735** with `[dependency-groups]`, which is a Python ecosystem standard.

### Basic Migration

**Old (Pre-2.0)**:
```toml
[tool.pdm.dev-dependencies]
test = ["pytest>=6.0", "pytest-cov"]
lint = ["flake8", "black", "mypy"]
doc = ["mkdocs", "mkdocs-material"]
```

**New (PEP 735)**:
```toml
[dependency-groups]
test = ["pytest>=6.0", "pytest-cov"]
lint = ["flake8", "black", "mypy"]
doc = ["mkdocs", "mkdocs-material"]
```

### Key Points

- **Simple rename**: `[tool.pdm.dev-dependencies]` → `[dependency-groups]`
- **Same structure**: Group names and dependency lists remain identical
- **Not in metadata**: Dependencies in `[dependency-groups]` are NOT included in package distribution metadata
- **CLI compatibility**: `pdm add -dG test pytest` works with both formats

---

## Project Metadata Migration (PEP 621)

### The Standard: PEP 621

**PEP 621** defines a standard way to specify project metadata in `pyproject.toml` using the `[project]` table.

### Basic Project Information

**Old (Legacy)**:
```toml
[tool.pdm]
name = "huleedu-content-service"
version = "1.0.0"
description = "Content management service"
author = "Your Name <you@example.com>"
license = "MIT"
```

**New (PEP 621)**:
```toml
[project]
name = "huleedu-content-service"
version = "1.0.0"
description = "Content management service"
authors = [
    {name = "Your Name", email = "you@example.com"}
]
license = {text = "MIT"}
requires-python = ">=3.11"
```

### Production Dependencies

**Old**:
```toml
[tool.pdm]
dependencies = [
    "quart>=0.19.0",
    "sqlalchemy[asyncio]>=2.0",
]
```

**New (PEP 621)**:
```toml
[project]
dependencies = [
    "quart>=0.19.0",
    "sqlalchemy[asyncio]>=2.0",
]
```

### Dynamic Fields

Some fields can be marked as "dynamic" to be read from other sources:

```toml
[project]
name = "mypackage"
dynamic = ["version"]

[tool.pdm]
version = { source = "file", path = "mypackage/__version__.py" }
```

---

## Dependency Specification

### Modern Syntax (PEP 440 & PEP 508)

**Named Requirements**:
```toml
dependencies = [
    "requests",                    # Any version
    "flask>=1.1.0",               # Minimum version
    "django>=3.0,<4.0",           # Range
    "numpy~=1.21.0",              # Compatible release
]
```

**Environment Markers (PEP 508)**:
```toml
dependencies = [
    "pywin32; sys_platform == 'win32'",
    "mock>=1.0.1; python_version < '3.4'",
]
```

**URL Requirements**:
```toml
dependencies = [
    "pip @ git+https://github.com/pypa/pip.git@20.3.1",
    "mylib @ https://example.com/mylib-1.0.tar.gz",
]
```

---

## Build Backend Migration

### From setuptools to pdm-backend

**Old (setuptools)**:
```toml
[build-system]
requires = ["setuptools>=45", "wheel", "setuptools-scm[toml]>=6.2"]
build-backend = "setuptools.build_meta"
```

**New (pdm-backend)**:
```toml
[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"
```

### Other Build Backends

PDM supports multiple backends. Common options:

**Hatchling**:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Flit**:
```toml
[build-system]
requires = ["flit_core>=3.2,<4"]
build-backend = "flit_core.buildapi"
```

**Maturin** (Rust extensions):
```toml
[build-system]
requires = ["maturin>=1.4,<2.0"]
build-backend = "maturin"
```

---

## Local Dependencies

### Modern Path Syntax

**Pre-2.0 (Relative paths)**:
```toml
dependencies = [
    "sub-package @ ./sub-package",
]
```

**Modern (file:// URI with PROJECT_ROOT)**:
```toml
[project]
dependencies = [
    "sub-package @ file:///${PROJECT_ROOT}/sub-package",
    "mywheel @ file:///${PROJECT_ROOT}/dist/mywheel-1.0.0-py3-none-any.whl",
]
```

### Backend-Specific Placeholders

**pdm-backend**:
```toml
dependencies = ["my-package @ file:///${PROJECT_ROOT}/my-package"]
```

**hatchling**:
```toml
dependencies = ["my-package @ {root:uri}/my-package"]

[tool.hatch.metadata]
allow-direct-references = true
```

### Monorepo Pattern (HuleEdu Style)

```toml
# Root pyproject.toml
[dependency-groups]
dev = [
    "-e file:///${PROJECT_ROOT}/libs/common_core",
    "-e file:///${PROJECT_ROOT}/libs/huleedu_service_libs",
    "-e file:///${PROJECT_ROOT}/services/content_service",
]
```

The `-e` prefix makes packages editable (development mode).

---

## Optional Dependencies

### Extras/Optional Groups

**Old (Various formats)**:
```toml
[tool.pdm]
extras = {
    "socks" = ["PySocks>=1.5.6"],
    "tests" = ["pytest", "mock"],
}
```

**New (PEP 621)**:
```toml
[project.optional-dependencies]
socks = ["PySocks>=1.5.6, !=1.5.7, <2"]
tests = [
    "pytest>=6.0",
    "mock>=1.0.1; python_version < '3.4'",
]
all = ["myproject[socks,tests]"]  # Combine multiple extras
```

### Installation

```bash
# Install with optional dependencies
pdm install -G socks

# Install multiple groups
pdm install -G socks -G tests

# Install all optional dependencies
pdm install -G all
```

---

## Complete Migration Workflow

### Step-by-Step Migration

**1. Backup Current File**:
```bash
cp pyproject.toml pyproject.toml.backup
```

**2. Migrate Development Dependencies**:
```toml
# Change this:
[tool.pdm.dev-dependencies]
test = ["pytest"]

# To this:
[dependency-groups]
test = ["pytest"]
```

**3. Migrate Project Metadata**:
```toml
# Change this:
[tool.pdm]
name = "myproject"
version = "1.0.0"
dependencies = ["requests"]

# To this:
[project]
name = "myproject"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = ["requests"]
```

**4. Update Build Backend** (optional but recommended):
```toml
[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"
```

**5. Test the Migration**:
```bash
# Remove existing lock file
rm pdm.lock

# Regenerate lock file with new format
pdm lock

# Install to verify
pdm install

# Run tests to ensure everything works
pdm run pytest
```

**6. Update Local Paths** (if any):
```bash
# PDM will automatically update relative paths to file:// URIs
# when you run pdm lock
```

---

## Context7 Integration

### When to Use Context7

Fetch latest PDM documentation when:
- Encountering new PDM features not covered in this reference
- Need clarification on PEP 621/735 specifications
- Troubleshooting migration issues
- Understanding new dependency specification formats
- Checking for breaking changes in newer PDM versions

### Usage Pattern

```python
# Within the skill context, use Context7 MCP tools:

# Step 1: Resolve library ID (already known: /pdm-project/pdm)
# Step 2: Fetch specific documentation

# Example topics:
# - "pyproject.toml PEP 621 migration"
# - "dependency-groups PEP 735"
# - "pdm-backend configuration"
# - "monorepo workspace setup"
# - "dependency specification syntax"
```

### Example Context7 Call

When user asks: "How do I migrate environment markers in dependencies?"

```
Use mcp__context7__get-library-docs:
- context7CompatibleLibraryID: "/pdm-project/pdm"
- topic: "environment markers PEP 508 dependency specification"
```

---

## Migration Checklist

- [ ] Rename `[tool.pdm.dev-dependencies]` to `[dependency-groups]`
- [ ] Move project metadata to `[project]` table
- [ ] Add `requires-python` field
- [ ] Convert `authors` to list of objects
- [ ] Update `license` to `{text = "..."}` format
- [ ] Move `dependencies` to `[project]` table
- [ ] Rename `extras` to `[project.optional-dependencies]`
- [ ] Update build backend to `pdm-backend` (optional)
- [ ] Convert relative paths to `file:///${PROJECT_ROOT}/` format
- [ ] Remove obsolete `[tool.pdm]` fields
- [ ] Test with `pdm lock`
- [ ] Verify with `pdm install`
- [ ] Run existing tests to confirm compatibility

---

## Common Pitfalls

### 1. Forgetting `requires-python`

**Problem**: Modern format requires Python version specification.

**Solution**:
```toml
[project]
requires-python = ">=3.11"
```

### 2. Incorrect Author Format

**Old**:
```toml
author = "Name <email>"
```

**Correct**:
```toml
authors = [
    {name = "Name", email = "email"}
]
```

### 3. Mixing Old and New Syntax

**Problem**: Having both `[tool.pdm.dev-dependencies]` and `[dependency-groups]`.

**Solution**: Choose one format (preferably new) and remove the old.

### 4. Relative Paths in Monorepo

**Problem**: Using relative paths like `./libs/common_core`.

**Solution**: Use `file:///${PROJECT_ROOT}/libs/common_core` for portability.

---

## Related Resources

- **Quick Reference**: See `SKILL.md` in this directory
- **Migration Examples**: See `examples.md` in this directory
- **PEP 621 Specification**: <https://peps.python.org/pep-0621/>
- **PEP 735 Specification**: <https://peps.python.org/pep-0735/>
- **PDM Documentation**: Use Context7 with `/pdm-project/pdm`
