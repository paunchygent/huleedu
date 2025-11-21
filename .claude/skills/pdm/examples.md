# PDM Migration Examples

Quick before/after patterns for migrating pyproject.toml from pre-2.0 to modern syntax.

---

## Core Migration Pattern

### Before (Pre-2.0)
```toml
[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"

[tool.pdm]
name = "myproject"
version = "1.0.0"
dependencies = ["requests>=2.28.0"]

[tool.pdm.dev-dependencies]
test = ["pytest>=7.0"]
lint = ["ruff>=0.1.0"]
```

### After (Modern)
```toml
[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"

[project]
name = "myproject"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.28.0"]

[dependency-groups]
test = ["pytest>=7.0"]
lint = ["ruff>=0.1.0"]
```

---

## Author/License Fields

### Before
```toml
[tool.pdm]
author = "John Doe <john@example.com>"
license = "MIT"
```

### After
```toml
[project]
authors = [{name = "John Doe", email = "john@example.com"}]
license = {text = "MIT"}
```

---

## Optional Dependencies (Extras)

### Before
```toml
[tool.pdm]
extras = {
    "socks" = ["PySocks>=1.5.6"],
    "all" = ["PySocks>=1.5.6", "requests>=2.0"],
}
```

### After
```toml
[project.optional-dependencies]
socks = ["PySocks>=1.5.6"]
all = ["myproject[socks]", "requests>=2.0"]
```

---

## Local Dependencies (Monorepo)

### Before
```toml
[tool.pdm]
dependencies = ["./libs/common_core"]

[tool.pdm.dev-dependencies]
dev = ["./services/content_service"]
```

### After
```toml
[project]
dependencies = ["common-core @ file:///${PROJECT_ROOT}/libs/common_core"]

[dependency-groups]
dev = ["-e file:///${PROJECT_ROOT}/services/content_service"]
```

---

## Quick Checklist

```diff
- [tool.pdm]                           + [project]
- [tool.pdm.dev-dependencies]          + [dependency-groups]
- author = "Name <email>"              + authors = [{name = "Name", email = "email"}]
- license = "MIT"                      + license = {text = "MIT"}
- ./relative/path                      + file:///${PROJECT_ROOT}/relative/path
- (no requires-python)                 + requires-python = ">=3.11"
```
