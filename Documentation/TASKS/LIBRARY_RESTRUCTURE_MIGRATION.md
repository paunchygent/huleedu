# Library Restructure Migration: From services/libs to libs/

## Task ID: ARCH-001
## Status: READY FOR EXECUTION
## Priority: MEDIUM
## Risk Level: LOW

---

## 1. Executive Summary

Restructure the HuleEdu monorepo to improve architectural clarity by moving shared libraries from `services/libs/` to a top-level `libs/` directory. This organizational change maintains all existing functionality while providing clearer separation between deployable services and shared libraries.

### Key Benefits
- **Architectural clarity**: Clear distinction between deployable services and shared libraries
- **Tool compatibility**: Standard structure recognized by Python tooling
- **Future scalability**: Clean location for new shared libraries
- **Zero code impact**: Package-based imports remain unchanged

---

## 2. Current State Analysis

### 2.1 Current Directory Structure
```
huledu-reboot/
├── common_core/                    # Shared data contracts (already at root)
├── services/
│   ├── libs/                       # ISSUE: Shared libraries under services/
│   │   └── huleedu_service_libs/  # Infrastructure utilities
│   ├── batch_orchestrator_service/
│   ├── essay_lifecycle_service/
│   └── [other services]/
```

### 2.2 Import Patterns
- Services use package imports: `from huleedu_service_libs import ...`
- Common core imports: `from common_core import ...`
- Service internals use full paths: `from services.service_name import ...`

### 2.3 Docker Configuration
```dockerfile
COPY common_core/ /app/common_core/
COPY services/libs/ /app/services/libs/
ENV PYTHONPATH=/app
```

### 2.4 PDM Configuration
```toml
# Root pyproject.toml
dev = [
    "-e file:///${PROJECT_ROOT}/common_core",
    "-e file:///${PROJECT_ROOT}/services/libs",
]

# Service pyproject.toml overrides
[tool.pdm.resolution.overrides]
huleedu-common-core = "file:///app/common_core"
huleedu-service-libs = "file:///app/services/libs"
```

---

## 3. Target State

### 3.1 New Directory Structure
```
huledu-reboot/
├── libs/                           # NEW: All shared libraries
│   ├── common_core/               # MOVED: From root
│   └── huleedu_service_libs/      # MOVED: From services/libs/
├── services/                       # ONLY deployable microservices
│   ├── batch_orchestrator_service/
│   ├── essay_lifecycle_service/
│   └── [other services]/
```

### 3.2 Updated Configuration Targets
- Docker: Update COPY paths to `libs/` structure
- PDM: Update editable install paths and resolution overrides
- MyPy: Update exclusion paths
- Ruff: Verify src paths include `libs/`

---

## 4. Migration Plan

### 4.1 Pre-Migration Checklist

```bash
# 1. Create feature branch
git checkout -b feature/library-restructure

# 2. Audit current references (save output for reference)
grep -r "common_core" --include="*.yml" --include="*.yaml" --include="Dockerfile*" . > ~/pre-migration-common-core-refs.txt
grep -r "services/libs" --include="*.yml" --include="*.yaml" --include="Dockerfile*" . > ~/pre-migration-services-libs-refs.txt

# 3. Run full test suite to establish baseline
pdm run test-all > ~/pre-migration-test-results.txt

# 4. Build all services to verify current state
docker compose build --no-cache
```

### 4.2 Migration Script

```bash
#!/bin/bash
# migration-script.sh
set -euo pipefail

echo "=== HuleEdu Library Restructure Migration ==="
echo "This script will move shared libraries to libs/ directory"
echo "Press Ctrl+C to abort, or Enter to continue..."
read -r

# 1. Create new structure
echo "Creating libs directory..."
mkdir -p libs

# 2. Move libraries (preserves git history)
echo "Moving common_core to libs/..."
git mv common_core libs/
echo "Moving services/libs/huleedu_service_libs to libs/..."
git mv services/libs/huleedu_service_libs libs/
rmdir services/libs

# 3. Update all Dockerfiles
echo "Updating Dockerfiles..."
find services -name "Dockerfile" -type f | while read -r file; do
    echo "  Updating: $file"
    sed -i.bak \
        -e 's|COPY common_core/ /app/common_core/|COPY libs/common_core/ /app/libs/common_core/|' \
        -e 's|COPY services/libs/ /app/services/libs/|COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/|' \
        "$file"
done

# 4. Update PDM overrides in service pyproject.toml files
echo "Updating service pyproject.toml files..."
find services -name "pyproject.toml" -type f | while read -r file; do
    echo "  Updating: $file"
    sed -i.bak \
        -e 's|"file:///app/common_core"|"file:///app/libs/common_core"|' \
        -e 's|"file:///app/services/libs"|"file:///app/libs/huleedu_service_libs"|' \
        "$file"
done

# 5. Update root pyproject.toml
echo "Updating root pyproject.toml..."
sed -i.bak \
    -e 's|${PROJECT_ROOT}/common_core|${PROJECT_ROOT}/libs/common_core|' \
    -e 's|${PROJECT_ROOT}/services/libs|${PROJECT_ROOT}/libs/huleedu_service_libs|' \
    pyproject.toml

# 6. Update MyPy exclusions
echo "Updating MyPy configuration..."
sed -i.bak \
    -e 's|"common_core/src/"|"libs/common_core/src/"|' \
    -e 's|"services/libs/huleedu_service_libs/"|"libs/huleedu_service_libs/"|' \
    pyproject.toml

# 7. Clean up backup files
echo "Cleaning up backup files..."
find . -name "*.bak" -type f -delete

echo "=== Migration Complete ==="
echo "Next steps:"
echo "1. Run: pdm install"
echo "2. Run: pdm run python -c 'import common_core; import huleedu_service_libs; print(\"✓ Imports working\")'"
echo "3. Run: pdm run test-all"
echo "4. Run: docker compose build --no-cache"
```

### 4.3 Post-Migration Validation

```bash
# 1. Reinstall dependencies
pdm install

# 2. Verify imports work
pdm run python -c "
import common_core
import huleedu_service_libs
from common_core import EventEnvelope
from huleedu_service_libs import KafkaBus
print('✓ All imports working correctly')
"

# 3. Run linting
pdm run lint-all

# 4. Run type checking
pdm run typecheck-all

# 5. Run test suite
pdm run test-all

# 6. Build Docker images
docker compose build --no-cache

# 7. Start services and verify health
docker compose up -d
sleep 30
docker compose ps

# 8. Run integration tests if available
pdm run test-expensive
```

---

## 5. Rollback Plan

If issues arise during migration:

```bash
# 1. Revert all changes
git checkout -- .
git clean -fd

# 2. Restore original structure
git mv libs/common_core common_core
git mv libs/huleedu_service_libs services/libs/
rmdir libs

# 3. Reinstall
pdm install
```

---

## 6. Risk Mitigation

### 6.1 Identified Risks
1. **Docker build failures**: Mitigated by comprehensive Dockerfile updates
2. **Import resolution issues**: Mitigated by PDM's package-based approach
3. **CI/CD pipeline breaks**: Requires separate CI/CD audit and updates

### 6.2 Safety Measures
- Feature branch development
- Comprehensive pre/post validation
- Automated migration script reduces human error
- Clear rollback procedure

---

## 7. Success Criteria

Migration is considered successful when:
- [ ] All imports continue to work without code changes
- [ ] All tests pass (`pdm run test-all`)
- [ ] All services build successfully in Docker
- [ ] All services start and pass health checks
- [ ] Type checking passes (`pdm run typecheck-all`)
- [ ] Linting passes (`pdm run lint-all`)

---

## 8. Long-Term Benefits

1. **Clearer mental model**: Developers immediately understand `libs/` = shared, `services/` = deployable
2. **Tool compatibility**: Standard structure works better with IDEs and analysis tools
3. **Future growth**: Clear location for new shared libraries (e.g., `libs/auth_utils/`)
4. **Reduced confusion**: No more explaining why libraries live under services

---

## 9. Implementation Timeline

- **Duration**: 2-4 hours
- **Complexity**: Low (mostly configuration updates)
- **Team Impact**: Minimal (no code changes required)
- **Recommended timing**: During low-activity period

---

## 10. Post-Migration Tasks

After successful migration:

1. Update development documentation
2. Notify team of new structure
3. Update CI/CD pipelines if needed
4. Consider creating `libs/README.md` explaining the libs structure

---

## Approval and Sign-off

- [ ] Architecture team approval
- [ ] DevOps review of Docker changes
- [ ] Team notification sent
- [ ] Migration completed
- [ ] Post-migration validation passed

---

**Note**: This migration maintains all existing functionality while improving organizational clarity. No application code changes are required.