---
description: MyPy configuration and monorepo type checking standards
globs: 
alwaysApply: false
---
# 086: MyPy Configuration Standards

## 1. Module Path Conflict Problem
PDM editable installs create dual import paths causing MyPy errors:
```
error: Source file found twice under different module names: 
"services.libs.huleedu_service_libs" and "huleedu_service_libs"
```

## 2. Solution: Dual Configuration Pattern

### 2.1. Root MyPy (`pyproject.toml`)
```toml
[tool.mypy]
exclude = [
    "services/libs/huleedu_service_libs/",  # Exclude file path version
]
```

### 2.2. Library MyPy (`services/libs/mypy.ini`)
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
cd services/libs && mypy huleedu_service_libs --show-error-codes
```

## 4. Troubleshooting

### Module Conflicts
```bash
# Clear cache after config changes
rm -rf .mypy_cache && cd services/libs && rm -rf .mypy_cache
```

### Import Verification
```bash
# Verify editable install works
python -c "from huleedu_service_libs.database import DatabaseMetrics"
```

## 5. Standards
- **MUST** exclude `services/libs/huleedu_service_libs/` in root config
- **MUST** use isolated `mypy.ini` for service libs  
- **MUST** maintain both configurations for CI/CD

---
**MyPy monorepo configuration with module conflict resolution.**
