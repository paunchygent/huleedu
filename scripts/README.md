# HuleEdu Scripts

This directory contains project-level scripts and utilities for the HuleEdu microservice ecosystem.

## Available Scripts

### Environment Setup

#### `setup_huledu_environment.sh`
**Purpose**: Sets up the complete HuleEdu development environment for OpenAI Codex agent work.

**Usage**:
```bash
# From project root
./scripts/setup_huledu_environment.sh

# Or make it executable and run directly
chmod +x scripts/setup_huledu_environment.sh
./scripts/setup_huledu_environment.sh
```

**What it does**:
- ✅ Verifies project structure and location
- ✅ Installs PDM (Python Dependency Manager) if not present
- ✅ Installs all monorepo tools (Black, isort, flake8, mypy, pytest)
- ✅ Installs all microservices in editable development mode
- ✅ Provides summary of available development commands

**Requirements**:
- Python 3.11+
- pip (for PDM installation)
- Internet connection for package downloads

**Target Environment**: 
- OpenAI Codex browser-based sandbox environments
- Local development environments
- CI/CD environments

## Script Documentation

Detailed documentation for each script is available in the [`docs/`](./docs/) directory:

- [Setup Guide](./docs/SETUP_GUIDE.md) - Comprehensive setup and usage documentation

## Development Guidelines

### Adding New Scripts

When adding new scripts to this directory:

1. **Script Placement**: Place executable scripts directly in `scripts/`
2. **Documentation**: Create corresponding documentation in `scripts/docs/`
3. **Naming**: Use descriptive names with appropriate extensions (`.sh`, `.py`, etc.)
4. **Permissions**: Ensure scripts are executable (`chmod +x script_name.sh`)
5. **Error Handling**: Include proper error handling and informative output

### Script Standards

All scripts in this directory should:

- Include proper shebang lines (`#!/usr/bin/env bash` or `#!/usr/bin/env python3`)
- Use set -e for bash scripts to exit on errors
- Provide colored output for better user experience
- Include usage documentation in comments
- Handle both sandbox and local environments appropriately

### Utility Scripts

For utility scripts that don't warrant top-level placement, use the `utils/` subdirectory:

```
scripts/
├── utils/
│   ├── backup.sh
│   ├── maintenance.sh
│   └── cleanup.sh
└── main_script.sh
```

## Integration with PDM

These scripts complement the PDM-based development workflow defined in the root `pyproject.toml`. While PDM scripts handle code quality and testing tasks, these scripts handle environment setup and deployment tasks.

**PDM Scripts** (run with `pdm run <script>`):
- `format-all` - Code formatting
- `lint-all` - Code linting  
- `typecheck-all` - Type checking
- `test-all` - Test execution
- `docker-*` - Docker operations

**Project Scripts** (run directly):
- Environment setup
- Deployment automation
- Maintenance tasks
- Backup operations

## Support

For questions about scripts or to report issues:

1. Check the documentation in `scripts/docs/`
2. Review the script source code for inline comments
3. Consult the project's main documentation in the root `README.md`
4. Check the `.cursor/rules/` directory for development standards 