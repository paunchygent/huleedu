# Code Standards

## File Size
**<400-500 LoC** hard limit per file (including tests).

## Formatting
```bash
pdm run format-all          # Ruff format
pdm run lint-fix --unsafe-fixes  # Auto-fix lints
pdm run typecheck-all       # MyPy from root
```

## Style
- **Line length**: 100 characters
- **Quotes**: Double quotes
- **Indent**: Spaces (4)
- **Imports**: Absolute from root, never relative across services

## Typing
- All public functions must have type hints
- Use `typing.Protocol` for interfaces
- Pydantic models for all data classes

## Forbidden
- Raw SQL (use SQLAlchemy ORM)
- `try/except pass` blocks
- Relative imports outside service directory
- Running `pdm` from subdirectories

**Detailed**: `.agent/rules/010-foundational-principles.md`
