---
id: 'pdm-pyproject-toml-migration-to-pep-735'
title: 'PDM pyproject.toml Migration to PEP 735'
status: 'in_progress'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-22'
last_updated: '2025-11-22'
related: []
labels: ['pdm', 'dependencies', 'pep-735', 'migration']
---
# PDM pyproject.toml Migration to PEP 735

## Objective

Migrate legacy `[tool.pdm.dev-dependencies]` section in root `pyproject.toml` to modern PEP 735 `[dependency-groups]` format, completing the PDM 2.0+ migration.

## Context

The project currently has a **mixed state**:
- ✅ Modern `[dependency-groups]` section (line 35) with `monorepo-tools` and `dev` groups
- ❌ Legacy `[tool.pdm.dev-dependencies]` section (line 433) with editable local service installations

**Legacy Section Content** (17 editable packages):
```toml
[tool.pdm.dev-dependencies]
dev = [
    "-e file:///${PROJECT_ROOT}/libs/common_core",
    "-e file:///${PROJECT_ROOT}/libs/huleedu_service_libs",
    "-e file:///${PROJECT_ROOT}/libs/huleedu_nlp_shared",
    "-e file:///${PROJECT_ROOT}/services/content_service",
    # ... (14 services)
]
```

**Why Migrate?**:
1. PDM 2.0+ deprecated `[tool.pdm.dev-dependencies]` in favor of PEP 735 `[dependency-groups]`
2. Mixed format causes confusion and potential conflicts
3. Modern format is standard-compliant and tool-agnostic
4. Better IDE/tooling support for PEP 735

## Plan

1. **Merge Legacy to Modern**:
   - Move editable service/lib installations from `[tool.pdm.dev-dependencies]` to `[dependency-groups]`
   - Decide placement: add to existing `dev` group or create new group (e.g., `services`)

2. **Remove Legacy Section**:
   - Delete entire `[tool.pdm.dev-dependencies]` block

3. **Verify Lock File**:
   - Run `pdm lock --update-reuse` to regenerate lock file
   - Ensure all editable packages still resolved

4. **Test Installation**:
   - Fresh install: `pdm install`
   - Verify all services importable
   - Run type checks: `pdm run typecheck-all`

## Success Criteria

- [x] No `[tool.pdm.dev-dependencies]` section in pyproject.toml
- [x] All editable packages moved to `[dependency-groups]`
- [x] `pdm lock --check` passes (lock file valid)
- [x] pyproject.toml formatting passes
- [ ] All services importable in Python REPL (deferred - requires full install)
- [ ] Type checking passes: `pdm run typecheck-all` (deferred - requires full install)
- [ ] Pre-commit hooks pass

## Implementation Notes

**Completed 2025-11-22**:
- Merged 17 editable packages from `[tool.pdm.dev-dependencies].dev` into `[dependency-groups].dev`
- Removed entire legacy `[tool.pdm.dev-dependencies]` section
- Final dev group contains 21 packages (4 dev tools + 17 editable local packages)
- Lock file remains valid (no regeneration needed)

## Related

- PDM Skill: `.claude/skills/pdm/`
- PEP 735: Dependency Groups for Python
- PEP 621: Python Project Metadata
