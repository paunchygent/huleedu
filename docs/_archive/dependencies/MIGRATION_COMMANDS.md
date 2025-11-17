# Migration Commands

## Update PDM to Latest Version

```bash
# Update PDM itself
pdm self update

# Verify version
pdm --version  # Should show 2.24.2+
```

## Update Dependencies

```bash
# Update all dependencies to latest compatible versions
pdm update

# Update specific packages
pdm update ruff mypy pytest

# Update with new resolution strategies
pdm lock --update-reuse --strategy inherit_metadata
```

## Clean Installation

```bash
# Remove old lock file and reinstall
rm pdm.lock
pdm install

# Or force clean install
pdm install --clean
```

# New Features in 2025

## 1. UV Resolver Integration (Experimental)

```bash
# Enable UV resolver for faster dependency resolution
pdm config use_uv true

# Verify UV is being used
pdm info  # Should show "Using uv resolver"
```

## 2. Enhanced Python Management

```bash
# List available Python versions
pdm python install --list

# Install specific Python version
pdm python install 3.13.2

# Use installed Python
pdm use python3.13
```

## 3. Dependency Groups (PEP 735)

```bash
# Install specific dependency groups
pdm install -G test
pdm install -G lint
pdm install --prod  # Production only

# Install with exclusions
pdm install --without dev
```

# Performance Optimizations

## 1. Lock File Optimization

```toml
[tool.pdm.resolution]
# Faster resolution with metadata inheritance
strategy = ["inherit_metadata"]

# Respect source order for faster lookups
respect-source-order = true
```

## 2. Cache Configuration

```bash
# Configure cache location
export PDM_CACHE_DIR="$HOME/.cache/pdm"

# Enable install cache
pdm config install.cache true
```

## 3. Parallel Installation

```toml
[tool.pdm]
# Enable parallel installation
parallel = true
```

## Troubleshooting

## Common Issues and Solutions

1. **Ruff Native Server Issues**

   ```json
   {
     "ruff.nativeServer": "off"  // Fallback to Python server
   }
   ```

2. **MyPy Performance Issues**

   ```json
   {
     "mypy-type-checker.preferDaemon": true,
     "mypy-type-checker.args": ["--fast-module-lookup"]
   }
   ```

3. **PDM Lock File Conflicts**

   ```bash
   # Reset lock file
   rm pdm.lock
   pdm lock --update-all
   ```

## Best Practices for 2025

1. **Use Dependency Groups**: Organize dependencies by purpose
2. **Pin Major Versions**: Use `>=` for minor updates, `~=` for patch updates
3. **Regular Updates**: Update dependencies monthly
4. **Lock File Commits**: Always commit `pdm.lock` for reproducible builds
5. **Native Tools**: Prefer native Rust tools (ruff server) for performance
6. **Type Checking**: Enable strict MyPy settings for better code quality

## Security Considerations

### Dependency Scanning

```bash
# Check for known vulnerabilities (requires safety)
pdm add --dev safety
pdm run safety check

# Audit dependencies
pdm audit
```

### Lock File Verification

```bash
# Verify lock file integrity
pdm lock --check

# Update with security patches only
pdm update --security-only
```

## Monitoring and Maintenance

### Regular Maintenance Tasks

1. **Weekly**: Check for security updates
2. **Monthly**: Update all dependencies
3. **Quarterly**: Review and clean unused dependencies
4. **Annually**: Major version upgrades

### Automation

```yaml
# GitHub Actions example for dependency updates
name: Update Dependencies
on:
  schedule:
    - cron: '0 0 * * 1'  # Weekly on Monday
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup PDM
        uses: pdm-project/setup-pdm@v4
      - name: Update dependencies
        run: |
          pdm update
          pdm lock --check
```

## Resources

- [PDM Documentation](https://pdm-project.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [MyPy Documentation](https://mypy.readthedocs.io/)
- [PEP 735 - Dependency Groups](https://peps.python.org/pep-0735/)

---

**Last Updated**: January 2025
**PDM Version**: 2.24.2
**Ruff Version**: 0.11.11+
**Python Support**: 3.11 - 3.14
