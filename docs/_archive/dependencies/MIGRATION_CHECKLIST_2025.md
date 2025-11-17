# HuleEdu 2025 Migration Checklist

## Pre-Migration Preparation

### ✅ Backup Current State

- [ ] Commit all current changes to git
- [ ] Create backup branch: `git checkout -b backup-pre-2025-migration`
- [ ] Document current versions: `pdm list > pre-migration-versions.txt`
- [ ] Export current settings: Copy `.vscode/settings.json` to backup

### ✅ Environment Verification

- [ ] Verify Python version: `python --version` (should be 3.11+)
- [ ] Check PDM version: `pdm --version`
- [ ] Verify git status is clean: `git status`

## Step 1: Update PDM

### ✅ PDM Self-Update

```bash
# Update PDM to latest version
pdm self update

# Verify version (should be 2.24.2+)
pdm --version
```

### ✅ Verify PDM Features

- [ ] Check if UV resolver is available: `pdm config use_uv true`
- [ ] Test dependency groups: `pdm install --help | grep -E "(-G|--group)"`

## Step 2: Update VS Code Extensions

### ✅ Extension Updates

- [ ] Update Ruff extension to v2025.22.0+
- [ ] Update MyPy extension to latest
- [ ] Update Python extension to latest
- [ ] Restart VS Code after updates

### ✅ Remove Deprecated Settings

Remove these from `.vscode/settings.json`:

- [ ] `"ruff.format.args": ["--force-exclude"]`
- [ ] `"ruff.lint.args": ["--force-exclude"]`
- [ ] `"ruff.showNotifications": "onError"`

### ✅ Add Modern Settings

Add these to `.vscode/settings.json`:

- [ ] `"ruff.nativeServer": "auto"`
- [ ] `"ruff.logLevel": "info"`
- [ ] `"mypy-type-checker.preferDaemon": true`

## Step 3: Update Dependencies

### ✅ Core Dependencies Update

```bash
# Update all dependencies
pdm update

# Specifically update key packages
pdm update ruff mypy pytest pydantic quart
```

### ✅ Verify Key Versions

Check these minimum versions:

- [ ] `ruff>=0.11.11`
- [ ] `mypy>=1.15.0`
- [ ] `pytest>=8.3.5`
- [ ] `pydantic>=2.11.5`
- [ ] `quart>=0.20.0`

### ✅ Lock File Regeneration

```bash
# Clean regenerate lock file
rm pdm.lock
pdm lock
pdm install
```

## Step 4: Configuration Updates

### ✅ pyproject.toml Enhancements

Add these sections if missing:

```toml
[tool.pdm]
package-type = "application"

[tool.pdm.resolution]
strategy = ["inherit_metadata"]
respect-source-order = true

[dependency-groups]
dev = [
    "ruff>=0.11.11",
    "mypy>=1.15.0",
    "pytest>=8.3.5",
    "pytest-asyncio>=0.26.0",
    "pytest-cov>=6.1.1",
]
```

### ✅ Script Updates

Verify these scripts in `pyproject.toml`:

- [ ] `format-all = "ruff format --force-exclude ."`
- [ ] `lint-all = "ruff check --force-exclude ."`
- [ ] `lint-fix = "ruff check --fix --force-exclude ."`
- [ ] `typecheck-all = "mypy ."`

## Step 5: Testing & Verification

### ✅ Linting & Formatting Tests

```bash
# Test formatting
pdm run format-all

# Test linting
pdm run lint-all

# Test type checking
pdm run typecheck-all
```

### ✅ IDE Integration Tests

- [ ] Open Python file in VS Code
- [ ] Verify Ruff formatting on save
- [ ] Check MyPy error highlighting
- [ ] Test import organization
- [ ] Verify status bar shows "Ruff (native)"

### ✅ Service Tests

```bash
# Test each service
pdm run -p services/content_service test
pdm run -p services/batch_service test
pdm run -p services/spellchecker_service test
```

### ✅ Full Test Suite

```bash
# Run complete test suite
pdm run test-all
```

## Step 6: Performance Verification

### ✅ Ruff Performance

- [ ] Verify native server is active (status bar shows "Ruff (native)")
- [ ] Test formatting speed on large files
- [ ] Check linting response time

### ✅ MyPy Performance

- [ ] Enable daemon mode: `"mypy-type-checker.preferDaemon": true`
- [ ] Test type checking speed
- [ ] Verify incremental checking works

### ✅ PDM Performance

```bash
# Test dependency resolution speed
time pdm lock --check

# Test installation speed
time pdm install --clean
```

## Step 7: Documentation Updates

### ✅ Update Documentation

- [ ] Update README.md with new versions
- [ ] Update AGENTS.md with latest extension versions
- [ ] Update setup guides with 2025 settings
- [ ] Document any breaking changes

### ✅ Team Communication

- [ ] Notify team of migration
- [ ] Share updated setup instructions
- [ ] Document any workflow changes

## Step 8: Rollback Plan

### ✅ Rollback Preparation

If issues arise, rollback steps:

```bash
# Restore previous state
git checkout backup-pre-2025-migration

# Restore previous dependencies
git checkout HEAD~1 -- pdm.lock pyproject.toml
pdm install

# Restore VS Code settings
git checkout HEAD~1 -- .vscode/settings.json
```

## Post-Migration Validation

### ✅ 24-Hour Monitoring

- [ ] Monitor CI/CD pipeline for failures
- [ ] Check team feedback on IDE performance
- [ ] Verify no regression in code quality
- [ ] Monitor for any new linting errors

### ✅ Performance Metrics

- [ ] Compare linting speed before/after
- [ ] Measure type checking performance
- [ ] Check dependency resolution time
- [ ] Verify memory usage in IDE

## Troubleshooting Common Issues

### Issue: Ruff Native Server Not Working

**Solution:**

```json
{
  "ruff.nativeServer": "off"  // Fallback to Python server
}
```

### Issue: MyPy Daemon Issues

**Solution:**

```bash
# Restart MyPy daemon
pdm run mypy --dmypy-restart
```

### Issue: PDM Lock File Conflicts

**Solution:**

```bash
# Reset lock file
rm pdm.lock
pdm lock --update-all
```

### Issue: Extension Conflicts

**Solution:**

- Disable conflicting extensions
- Clear VS Code workspace cache
- Restart VS Code

## Success Criteria

### ✅ Migration Complete When

- [ ] All tests pass
- [ ] IDE shows no deprecated setting warnings
- [ ] Ruff native server is active
- [ ] MyPy daemon is working
- [ ] Team can develop without issues
- [ ] CI/CD pipeline is green
- [ ] Performance is equal or better than before

---

**Migration Date**: ___________
**Completed By**: ___________
**Issues Encountered**: ___________
**Rollback Required**: [ ] Yes [ ] No

## Resources

- [Dependency Management Guide 2025](./DEPENDENCY_MANAGEMENT_2025.md)
- [Cursor IDE Setup Guide](../CURSOR_IDE_SETUP_GUIDE.md)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [PDM Documentation](https://pdm-project.org/)
