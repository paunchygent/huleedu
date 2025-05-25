# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build, Lint and Test Commands
- Format code: `pdm run format-all` (ruff format)
- Lint code: `pdm run lint-all` (ruff check)
- Fix linting issues: `pdm run lint-fix` (ruff check --fix)
- Type checking: `pdm run typecheck-all` (mypy)
- Run all tests: `pdm run test-all` (pytest)
- Run single test: `pytest path/to/test_file.py::TestClass::test_method -v`
- Docker commands: `pdm run docker-build`, `pdm run docker-up`, `pdm run docker-down`

## Code Style Guidelines
- **Formatting**: Follow ruff standards (line length 100, double quotes, space indentation)
- **Imports**: Use absolute imports, sorted by ruff (import stdlib, third-party, local)
- **Types**: All public functions, methods, and classes must have precise type annotations
- **Naming**: snake_case for modules/files/functions/variables, PascalCase for classes
- **Documentation**: Use Google-style docstrings for all public modules, classes, and functions
- **Error Handling**: Catch specific exceptions, use domain-specific exceptions
- **Pydantic Models**: Use Pydantic v2 standards with ConfigDict, proper serialization
- **Architecture**: Follow microservice event-driven design with explicit contracts
- **Testing**: Write tests in pytest format with test_* prefix for functions

Always run linting and type checking before committing changes.