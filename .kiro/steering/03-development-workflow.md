---
inclusion: always
---

# Development Workflow Standards

## Code Quality Requirements

### Pre-Implementation Checklist
Before writing any code, verify:
- [ ] Service follows DDD bounded context principles
- [ ] Protocol interfaces defined in `protocols.py`
- [ ] Dependency injection patterns planned with Dishka
- [ ] Event contracts exist in `common_core` if needed
- [ ] Test strategy planned (unit, integration, contract)

### Code Standards (Enforced by Tools)
- **Formatting**: Ruff with 100-character line limit
- **Linting**: Ruff with strict error checking
- **Type Checking**: MyPy with strict configuration
- **Testing**: Pytest with async support and comprehensive coverage

### PDM Commands (Use These)
```bash
# Code quality
pdm run format-all      # Format all code
pdm run lint-all        # Lint all code
pdm run typecheck-all   # Type check all code

# Testing
pdm run test-all        # Run all tests
pdm run test-parallel   # Parallel test execution

# Docker operations
pdm run dc-up          # Start services
pdm run dc-build       # Build and start services
pdm run dc-down        # Stop services
pdm run dc-logs        # View logs
```

### File Organization Standards
- Maximum 400 lines per file (enforced)
- Single responsibility principle
- Clear separation of concerns
- Consistent naming conventions (snake_case for Python)

### Import Standards
- Absolute **full path** imports preferred
- Group imports: standard library, third-party, local
- Use `from __future__ import annotations` for forward references
- Avoid circular imports through proper layering

### Testing Requirements
- Unit tests for all business logic
- Integration tests for external dependencies
- Contract tests for inter-service communication
- End-to-end tests for critical workflows
- Mock external dependencies appropriately

### Documentation Standards
- Docstrings for all public functions and classes
- README.md for each service with API documentation
- Architecture decision records for significant changes
- Keep documentation current with code changes