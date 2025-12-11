---
id: "086-mypy-configuration-standards"
type: "standards"
created: 2025-07-07
last_updated: 2025-11-22
scope: "all"
---
# 086: MyPy Configuration Standards

## 1. Module Path Conflict Problem
PDM editable installs create dual import paths causing MyPy errors:
```
error: Source file found twice under different module names: 
"libs.huleedu_service_libs" and "huleedu_service_libs"
```

## 2. Solution: Dual Configuration Pattern

### 2.1. Root MyPy (`pyproject.toml`)
```toml
[tool.mypy]
exclude = [
    "libs/huleedu_service_libs/",  # Exclude file path version
]
```

### 2.2. Library MyPy (`libs/mypy.ini`)
```ini
[mypy]
python_version = 3.11
explicit_package_bases = true
namespace_packages = true
no_site_packages = true

[mypy-aiokafka.*]
ignore_missing_imports = true
[mypy-redis.*]
ignore_missing_imports = true
[mypy-prometheus_client.*]
ignore_missing_imports = true
[mypy-structlog.*]
ignore_missing_imports = true
[mypy-opentelemetry.*]
ignore_missing_imports = true
[mypy-sqlalchemy.*]
ignore_missing_imports = true
[mypy-pydantic.*]
ignore_missing_imports = true
[mypy-quart.*]
ignore_missing_imports = true
[mypy-fastapi.*]
ignore_missing_imports = true
[mypy-pytest.*]
ignore_missing_imports = true
[mypy-huleedu_common_core.*]
ignore_missing_imports = true
```

## 3. Usage Commands
```bash
# Root monorepo checking
pdm run typecheck-all

# Service libs checking  
cd libs && mypy huleedu_service_libs --show-error-codes
```

## 4. Troubleshooting

### Module Conflicts
```bash
# Clear cache after config changes
rm -rf .mypy_cache && cd libs && rm -rf .mypy_cache
```

### Import Verification
```bash
# Verify editable install works
python -c "from huleedu_service_libs.database import DatabaseMetrics"
```

## 5. Standards
- **MUST** exclude `libs/huleedu_service_libs/` in root config
- **MUST** use isolated `mypy.ini` for service libs
- **MUST** maintain both configurations for CI/CD

## 6. How Exclude and Overrides Interact

### 6.1. Discovery Phase vs Import Following

MyPy operates in two distinct phases that use different configuration settings:

**Discovery Phase** (controlled by `exclude`):
- MyPy walks the filesystem to find Python files to check
- `exclude` patterns prevent MyPy from **discovering** files during traversal
- Files matching exclude patterns are never **primary check targets**
- They will not appear in standalone error reports

**Import Following Phase** (controlled by `[[tool.mypy.overrides]]`):
- When non-excluded code imports excluded modules, MyPy follows the import
- These modules are **silenced** (type-checked but errors not reported)
- The module is validated to ensure it doesn't break the importing code
- Override settings apply to **module names** (e.g., `common_core.*`), not file paths

### 6.2. HuleEdu Monorepo Pattern

In the HuleEdu monorepo, this two-phase behavior works as follows:

1. **Root `typecheck-all` command**:
   ```bash
   mypy --config-file pyproject.toml --follow-imports=silent services tests
   ```
   - Only scans `services/` and `tests/` directories
   - Libs are excluded from discovery via `exclude = ["libs/common_core/src/", "libs/huleedu_service_libs/"]`

2. **When services import libs**:
   ```python
   from common_core import EventEnvelope  # Service imports lib
   ```
   - MyPy follows the import to `libs/common_core/src/common_core/`
   - Module is silenced (checked but not reported as primary target)
   - ~98-99% of libs code is validated via import following
   - Libs errors only surface if they break importing service code

3. **Standalone libs checking**:
   ```bash
   cd libs && mypy huleedu_service_libs --config-file mypy.ini
   ```
   - Uses separate `libs/mypy.ini` configuration
   - Libs become **primary check targets** (errors reported)
   - Required for comprehensive libs validation

### 6.3. Override Configuration Best Practices

**DO NOT** create overrides for excluded module patterns:
```toml
# ❌ INEFFECTIVE: Overrides for excluded paths have no effect on primary checking
exclude = ["libs/"]
[[tool.mypy.overrides]]
module = ["libs.*"]  # ← Won't apply to primary check targets
```

**DO** create overrides for discovered modules:
```toml
# ✅ EFFECTIVE: Overrides for service modules
exclude = ["libs/"]
[[tool.mypy.overrides]]
module = [
    "services.content_service.*",  # ← Applies to discovered modules
    "services.spellchecker_service.*",
]
disallow_untyped_defs = true
```

### 6.4. Verification

To verify the two-phase behavior:
```bash
# Run with verbose output
pdm run typecheck-all --verbose 2>&1 | grep -E "^LOG:"

# Check what's excluded
pdm run typecheck-all --verbose 2>&1 | grep "Exclude"

# Check what's silenced (imported but not primary targets)
pdm run typecheck-all --verbose 2>&1 | grep "Silencing.*libs"
```

Expected output:
- Exclude list shows `libs/common_core/src/`, `libs/huleedu_service_libs/`
- Silencing logs show ~127 libs modules being checked via imports
- Success message shows ~1,286 files checked (services + tests + silenced imports)

---
**MyPy monorepo configuration with module conflict resolution.**
