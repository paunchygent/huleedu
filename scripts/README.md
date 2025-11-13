# HuleEdu Scripts

This directory contains project-level scripts and utilities for the HuleEdu microservice ecosystem.

## Available Scripts

### Task Management Utilities (TASKS/)

#### `scripts/task_mgmt/*`

Utilities to keep TASKS/ organized and agent-friendly.

**Commands**:

```bash
# Create a new task with front matter
python scripts/task_mgmt/new_task.py --title "Svelte 5 + Vite CORS" --domain frontend

# Validate front matter across TASKS/ (excludes archive by default)
python scripts/task_mgmt/validate_front_matter.py --verbose

# Generate TASKS/INDEX.md (by domain/status/program)
python scripts/task_mgmt/index_tasks.py

# Archive a task to archive/YYYY/MM/{domain}/ and set status=archived
python scripts/task_mgmt/archive_task.py --path TASKS/<relative-path>.md [--git]
```

These scripts are standard-library only and harness-independent for LLM Agent use.

### Configuration Validation

#### `validate_service_config.py`

**Purpose**: Validates service configurations against docker-compose setup to catch configuration drift issues.

**Usage**:

```bash
# Basic validation
pdm run validate-config

# Strict mode (treat warnings as errors)
pdm run validate-config-strict

# Direct execution
python scripts/validate_service_config.py
python scripts/validate_service_config.py --strict
```

**What it checks**:

- ✅ JWT configuration for services using authentication
- ✅ Database environment variables
- ✅ Kafka configuration
- ✅ Port conflicts across services
- ✅ Service dependency consistency

**When to use**:

- Before committing configuration changes
- After adding JWT authentication to a service
- When adding new services
- In CI/CD pipelines to prevent config drift

**Example output**:

```
🔍 Validating Service Configurations...

✅ cj_assessment_service
✅ api_gateway_service
❌ new_service
   ERROR: Inherits JWTValidationSettings but missing NEW_SERVICE_JWT_SECRET_KEY

❌ 1 configuration error(s) found
```

### Environment Setup

#### `setup_huledu_environment.sh`

**Purpose**: Sets up the complete HuleEdu development environment for OpenAI Codex agent work.

#### `codex-exec`

**Purpose**: Enhanced codex CLI wrapper that combines your standard configuration with execution capabilities for running bash commands and files.

**Usage**:

```bash
# Basic usage with standard config (model_reasoning_effort="high")
./scripts/codex-exec "Help me analyze this Python file"

# Full automation for trusted environments
./scripts/codex-exec --full-auto "Run the test suite and fix any failures"

# Danger mode for isolated environments only
./scripts/codex-exec --danger "Install dependencies and deploy the application"

# Custom configurations
./scripts/codex-exec -c model="o3" "Optimize this algorithm"

# With images and directory changes
./scripts/codex-exec -C /path/to/project -i screenshot.png "Debug this UI issue"
```

**Execution Modes**:
- **Safe Mode (default)**: Requires approval for potentially dangerous commands
- **Full Auto Mode**: Executes most commands automatically with workspace sandboxing
- **Danger Mode**: Full system access without prompts (USE WITH CAUTION)

**Key Features**:
- Combines your standard `model_reasoning_effort="high"` configuration
- Configurable sandbox modes: `read-only`, `workspace-write`, `danger-full-access`
- Approval policies: `untrusted`, `on-failure`, `on-request`, `never`
- Support for all codex CLI arguments (model, images, config overrides, etc.)
- Dry-run mode for testing commands before execution

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

### Script Organization

Scripts are organized by purpose:

``` text
scripts/
├── task_mgmt/                     # TASKS/ management utilities
│   ├── new_task.py                # Scaffold a new task with front matter
│   ├── validate_front_matter.py   # Validate required fields/enums/dates
│   ├── index_tasks.py             # Generate TASKS/INDEX.md
│   └── archive_task.py            # Move a task to archive/YYYY/MM/{domain}
├── tests/                         # Test automation scripts
│   ├── functional_tests.sh        # Existing functional test runner
│   ├── quick_validation_test.sh   # Existing quick validation
│   ├── test_*.sh                  # Individual test scripts
│   └── trace_*.py                 # Analysis and tracing utilities
├── utils/                         # General utility scripts
│   ├── backup.sh
│   ├── maintenance.sh
│   └── cleanup.sh
├── docs/                          # Script documentation
├── setup_huledu_environment.sh   # Environment setup
└── kafka_topic_bootstrap.py      # Infrastructure setup
```

**Test Script Guidelines**:
- **Integration Tests**: Use `tests/functional/` for Python pytest-based tests
- **Shell Test Scripts**: Use `scripts/tests/` for bash-based automation
- **Test Utilities**: Use `scripts/tests/` for analysis and tracing tools

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
