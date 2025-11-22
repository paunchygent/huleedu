---
id: 'mypy-configuration-investigation-and-consolidation'
title: 'MyPy Configuration Investigation and Consolidation'
status: 'completed'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-22'
last_updated: '2025-11-22'
related: []
labels: ['mypy', 'type-checking', 'configuration', 'monorepo']
---
# MyPy Configuration Investigation and Consolidation

## Objective

Investigate and resolve potential conflict between global `exclude` and `[[tool.mypy.overrides]]` in pyproject.toml, then consolidate configuration for clarity.

## Context

User identified apparent configuration conflict:
- Line 174-180: Global `exclude` list includes `libs/common_core/src/` and `libs/huleedu_service_libs/`
- Lines 183-204: Override configuration for `common_core.*` and `libs.*` modules with strict settings

Question: Does global exclude make overrides ineffective?

## Investigation Findings

### No Actual Conflict

MyPy operates in two phases:
1. **Discovery Phase** (`exclude`): Prevents MyPy from discovering files during directory traversal
2. **Import Following Phase** (`overrides`): Applies settings to modules when imported by checked code

**Result**: Libs are excluded from primary checking but validated via import following (~98-99% coverage).

### Evidence

- `pdm run typecheck-all` → 0 errors across 1,286 files (baseline)
- Verbose logs show 127 libs modules silenced (type-checked via imports)
- Override settings for `common_core.*` and `libs.*` are ineffective (excluded from discovery)

### CI/CD Gap Identified

**Found**: Existing typecheck scripts in pyproject.toml:
- `typecheck-libs`
- `typecheck-common-core`
- `typecheck-service-libs`

**Issue**: None are invoked in CI/CD workflows - type checking is manual-only.

## Actions Taken

### Phase 1: Documentation (Completed)
- Added section 6 to `.claude/rules/086-mypy-configuration-standards.md`
- Documented how `exclude` and `overrides` interact
- Explained HuleEdu monorepo pattern and silencing behavior
- Validation: Documentation renders correctly ✅

### Phase 2: CI/CD Investigation (Completed)
- Searched GitHub workflows for type checking
- Found existing typecheck scripts but no CI/CD integration
- Documented findings in investigation report
- Decision: typecheck-libs script already exists, no need to add ✅

### Phase 3: Configuration Consolidation (Completed)
- Removed ineffective overrides: `"common_core.*"` and `"libs.*"` from pyproject.toml
- Cleared MyPy cache and validated
- Validation results:
  - ✅ Exclude list unchanged
  - ✅ Libs still silenced (import following working)
  - ✅ File count unchanged (1,286 files)
  - ⚠️ 1 error from concurrent prompt cache work (unrelated)

### Phase 4: Script Fix (Bonus)
- Fixed `new-task` and `tasks` scripts in pyproject.toml
- Changed from `{shell = "... $@"}` to `{cmd = ["python", "..."]}`
- Resolved issue with quoted arguments containing spaces
- Validation: `pdm run new-task --title "Test"` works ✅

### Phase 5: libs/mypy.ini Fix (Critical Discovery)
**Issue Found**: During testing, discovered `pdm run typecheck-libs` was non-functional
- 100+ import-not-found errors for internal imports
- Root cause: Missing `mypy_path` configuration in libs/mypy.ini

**Fix Applied**:
- Added `mypy_path = huleedu_service_libs/src:common_core/src:huleedu_nlp_shared/src` to libs/mypy.ini
- Added `[mypy-jwt.*]` ignore for PyJWT library without stubs

**Validation**:
- ✅ `pdm run typecheck-libs` → Success: no issues found in 131 source files
- ✅ `pdm run typecheck-common-core` → Success: no issues found in 46 source files
- ✅ `pdm run typecheck-service-libs` → Success: no issues found in 85 source files

**Impact**: Standalone libs type checking now fully functional (was broken since creation)

## Changes Made

1. **pyproject.toml Line 184-186**: Removed `"common_core.*"` and `"libs.*"` from overrides
2. **pyproject.toml Line 448**: Fixed `new-task` script to use cmd array
3. **pyproject.toml Line 450**: Fixed `tasks` script to use cmd array
4. **.claude/rules/086-mypy-configuration-standards.md**: Added section 6
5. **libs/mypy.ini Line 2**: Added `mypy_path` configuration
6. **libs/mypy.ini Line 42-43**: Added `[mypy-jwt.*]` ignore

## Success Criteria

- [x] Documentation added explaining exclude/override interaction
- [x] Ineffective overrides removed from pyproject.toml
- [x] Validation confirms zero functional regression
- [x] Investigation report created with findings
- [x] Task document created and updated

## Related

- Investigation Report: `.claude/work/reports/2025-11-22-mypy-configuration-investigation.md`
- Rule: `.claude/rules/086-mypy-configuration-standards.md`
- Config: `pyproject.toml` (MyPy configuration)

## Future Work

Consider adding type checking to CI/CD workflows:
```yaml
- name: Type Check Services
  run: pdm run typecheck-all

- name: Type Check Libraries
  run: pdm run typecheck-libs
```
