# HuleEdu Development Environment Setup Guide

## For OpenAI Codex Agent Environments

This guide explains how to set up the HuleEdu microservice development environment, specifically designed for OpenAI Codex agent work in browser-based sandbox environments.

## Quick Start

### 1. Run the Setup Script

```bash
./setup_huledu_environment.sh
```

This script will:

- ✅ Verify you're in the correct HuleEdu project directory
- ✅ Install PDM (Python Dependency Manager) if not present
- ✅ Install all monorepo tools (Black, isort, flake8, mypy, pytest)
- ✅ Install all microservices in editable development mode
- ✅ Provide a summary of available development commands

### 2. Verify Installation

After the script completes, you can verify the setup:

```bash
# Check that all services are installed
pdm list

# Run a quick test to ensure everything works
pdm run typecheck-all
```

## Project Structure Overview

HuleEdu is a sophisticated microservice ecosystem built with:

### 🏗️ Architecture

- **Domain-Driven Design (DDD)**: Each service owns its bounded context
- **Event-Driven Architecture**: Asynchronous communication via Kafka events
- **Explicit Contracts**: Pydantic models for all inter-service communication
- **Service Autonomy**: Independent deployment and scaling

### 🔧 Technology Stack

- **Python 3.11+**: Modern Python with full type hints
- **PDM**: Monorepo dependency management
- **Quart**: Async web framework
- **Pydantic**: Data validation and serialization
- **Kafka**: Event streaming platform
- **Docker**: Containerization and orchestration

### 📦 Microservices

| Service | Location | Purpose |
|---------|----------|---------|
| **Batch Orchestration** | `services/batch_service/` | Manages essay batch processing workflows |
| **Content Service** | `services/content_service/` | Handles content storage and retrieval |
| **Spell Checker** | `services/spell_checker_service/` | Performs spell checking on essays |
| **Essay Service** | `services/essay_service/` | 🚧 *Placeholder - Not yet implemented* |
| **Common Core** | `common_core/` | Shared models, events, and utilities |
| **Service Libraries** | `services/libs/` | Common service infrastructure |

## Development Commands

After setup, you have access to these PDM scripts:

### 🔧 Code Quality

```bash
pdm run format-all      # Format code with Ruff
pdm run lint-all        # Lint with Ruff
pdm run typecheck-all   # Type check with mypy
pdm run test-all        # Run all tests with pytest
```

### 🐳 Docker Operations

```bash
pdm run docker-build   # Build all service containers
pdm run docker-up      # Start services with Docker Compose
pdm run docker-down    # Stop all services
pdm run docker-logs    # View service logs
pdm run docker-restart # Restart all services
```

### 🚀 Service Development

```bash
pdm run dev-content         # Run content service in development mode
pdm run dev-batch           # Run batch service in development mode
pdm run -p services/spell_checker_service start_worker    # Start spell checker worker
```

## Development Workflow

### 1. Code Changes

When making changes to any service:

```bash
# Format and check your code
pdm run format-all      # Ruff formatting
pdm run lint-all        # Ruff linting
pdm run typecheck-all

# Run tests
pdm run test-all
```

### 2. Testing Individual Services

```bash
# Test specific service
pdm run -p services/content_service pytest

# Test with coverage
pdm run pytest --cov=services/content_service
```

### 3. Running Services Locally

```bash
# Start infrastructure (Kafka, etc.)
pdm run docker-up

# Run individual services for development
pdm run dev-content
pdm run dev-batch
pdm run -p services/spell_checker_service start_worker
```

## AI Agent Development Notes

### 🤖 For OpenAI Codex Agents

This environment is optimized for AI coding agents with:

- **Complete Type Hints**: All code uses precise Pydantic models and type annotations
- **Comprehensive Testing**: Unit, integration, and contract tests
- **Clear Architecture**: Well-defined service boundaries and contracts
- **Development Tools**: Automated formatting, linting, and type checking
- **Documentation**: Extensive architectural documentation and code comments

### 📋 Current Development Phase

The project is currently in **Phase 1.2**, focusing on:

- ✅ Core service implementations
- 🔄 Enhanced testing and observability
- 🔄 Essay Lifecycle Service skeleton
- 🔄 Architectural refinements

See `TASKS/PHASE_1.2.md` for detailed current work.

### 🎯 Key Development Principles

1. **No "Vibe Coding"**: All implementations must follow architectural contracts
2. **Event-First**: Inter-service communication via explicit events
3. **Type Safety**: Comprehensive Pydantic models and mypy compliance
4. **Test Coverage**: All new features require tests
5. **Documentation**: Code must be self-documenting with clear docstrings

## Troubleshooting

### PDM Issues

```bash
# Reinstall PDM if needed
python3 -m pip install --user --upgrade pdm

# Clear PDM cache
pdm cache clear
```

### Dependency Issues

```bash
# Reinstall all dependencies
pdm install --clean

# Update lock file
pdm update
```

### Docker Issues

```bash
# Clean Docker environment
pdm run docker-down
docker system prune -f
pdm run docker-build
```

## Next Steps

After setup, you can:

1. **Explore the codebase**: Start with `README.md` for architectural overview
2. **Review current tasks**: Check `TASKS/PHASE_1.2.md` for active development
3. **Run tests**: Ensure everything works with `pdm run test-all`
4. **Start development**: Pick a service and begin coding!

## Support

For questions about:

- **Architecture**: See `README.md` and `.cursor/rules/` directory
- **Development Standards**: Check `.cursor/rules/050-python-coding-standards.md`
- **Testing**: Review `.cursor/rules/070-testing-and-quality-assurance.md`
- **Current Work**: See files in `TASKS/` directory

---

**Happy coding! The HuleEdu microservice ecosystem is ready for your contributions! 🚀**
