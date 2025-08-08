# HuleEdu Developer Reference

## Core Workflow

### 1. Initial Setup

```markdown
- Read `.cursor/rules/015-project-structure-standards.mdc` first
- Review key architectural documents in this order:
  1. `.cursor/rules/080-repository-workflow-and-tooling.mdc`
  2. `.cursor/rules/010-foundational-principles.mdc`
  3. `.cursor/rules/020-architectural-mandates.mdc`
  4. `.cursor/rules/030-event-driven-architecture-eda-standards.mdc`
  5. `.cursor/rules/042-async-patterns-and-di.mdc`
  6. `.cursor/rules/050-python-coding-standards.mdc`
  7. `.cursor/rules/100-terminology-and-definitions.mdc`
  8. `.cursor/rules/110.1-planning-mode.mdc`
  9. `.cursor/rules/110.2-coding-mode.mdc`
  10. `.cursor/rules/048-structured-error-handling-standards.mdc`
```

### 2. Task Execution

```markdown
1. **Select Mode**: Use `.cursor/rules/110-ai-agent-interaction-modes.mdc` to choose mode (Planning, Coding, Debugging)
2. **Rule Reference**: Consult `.cursor/rules/000-rule-index.mdc` for relevant rules
3. **Task Analysis**: Read full task from `TASKS/` directory
```

### 3. Error Resolution Protocol

```markdown
1. **Investigate First**: Check implementation before proposing changes
2. **Follow Patterns**: Use existing code patterns over new abstractions
3. **Root Cause**: Fix immediate issues before redesigning
```

### 4. Documentation & Testing

```markdown
- Update relevant task documents per `.cursor/rules/090-documentation-standards.mdc`
- Never create files in root - follow folder patterns
- All code changes require tests (run and verified)
- Never lint style issues manually before having run format-all and/or lint-fix --unsafe-fixes
- Always run typecheck-all from root after creating a test or implementing new code
```

---

## Technical Reference

### Architectural Overview

### Architecture (Rules 010, 020)

```markdown
- **Pattern**: Event-driven microservices with DDD
- **Stack**: 
  - Core: Python 3.11, Quart, PDM, Dishka, Pydantic
  - Data: PostgreSQL, SQLAlchemy, asyncpg
  - Comms: Kafka, aiohttp
  - Container: Docker, Docker Compose
```

### Service Communication (Rule 020)

```markdown
- **Primary**: Asynchronous via Kafka
- **Secondary**: Synchronous HTTP for queries requiring immediate response
- **Strict**: No direct DB access between services
```

### Database & Persistence

```markdown
- **ORM**: SQLAlchemy async with `asyncpg`
- **Isolation**: Each service has its own PostgreSQL database
- **Migrations**: See `.windsurf/rules/085-database-migration-standards.md`
```

### HTTP Services (Rule 042)

```markdown
- **app.py**: Setup only (<150 LoC)
- **Blueprints**: In `api/` directory
- **Example**: `@services/file_service/` structure
```

### Worker Services (Rule 042)

```markdown
- `worker_main.py`: Service lifecycle and DI
- `event_processor.py`: Core business logic
- **Example**: `@services/spell_checker_service/`
```

### Dependency Injection (Rule 042)

```markdown
- **Interfaces**: Define with `typing.Protocol` in `protocols.py`
- **Providers**: Implement `Provider` classes in `di.py`
- **Scopes**:
  - `APP`: Stateless singletons (settings, HTTP clients)
  - `REQUEST`: Per-operation instances (DB sessions)
```

### Event System (Rules 051, 052)

```markdown
- **Envelope**: All Kafka events use `EventEnvelope`
- **Topics**: Generate with `topic_name()` utility
- **Large Data**: Use `StorageReferenceMetadata` for payloads
```

## Testing & Quality

### Testing (Rule 070)

#### Test Types

```markdown
- **Unit**: Isolated function testing
- **Integration**: Component interaction
- **Contracts**: Event/API schema validation
```

#### Test Execution

```bash
# From repository root
pdm run test-all           # Full test suite
pdm run test-unit         # Unit tests only
pdm run test-integration  # Integration tests
pdm run test-cov          # With coverage report

# Specific test files
pdm run pytest path/to/test_file.py

# Test markers
pdm run pytest -m "not (slow or integration)"  # Fast tests only
```

#### Common Markers

```markdown
- `@pytest.mark.integration`: External services required
- `@pytest.mark.slow`: Long-running tests
- `@pytest.mark.docker`: Needs Docker Compose
- `@pytest.mark.kafka`: Requires Kafka
```

## Development Workflow (Rule 080)

### Code Quality

```markdown
- **Linting**: `pdm run lint` (Ruff)
- **Pre-commit**: `pdm run pre-commit install`
```

### Docker Development

```markdown
- **Rebuild**: `docker compose build --no-cache <service>`
- **Start**: `docker compose up -d`
- **Logs**: `docker compose logs -f <service>`
```

### Database Access (Common Issue)

```markdown
# IMPORTANT: Shell doesn't have .env variables by default!
# Always source .env first:
source /Users/olofs_mba/Documents/Repos/huledu-reboot/.env

# Then access database:
docker exec huleedu_<service>_db psql -U $HULEEDU_DB_USER -d <db_name> -c "SQL"

# Or use hardcoded values:
docker exec huleedu_class_management_db psql -U huleedu_user -d huleedu_class_management -c "\dt"

# Database names follow pattern: huleedu_<service_name>
# Example: huleedu_class_management, huleedu_essay_lifecycle, etc.
```

### Service Management

```markdown
- **Migrations**: `pdm run alembic upgrade head` (from service dir)
- **Rebuild Rule**: Always use `--no-cache` after code changes
```

## Database Migrations

### Standards (.windsurf/rules/085-database-migration-standards.md)

```markdown
- Always create migrations from service directory
- Include both upgrade and downgrade paths
- Test migrations in development before committing
- Never modify migration versions after pushing
```

## Monitoring & Observability

### Metrics

```markdown
- Use Prometheus for service metrics
- Instrument key operations with timing and counters
- Follow naming conventions: `service_operation_total`, `service_operation_duration_seconds`
```

## Documentation

### Standards (.windsurf/rules/090-documentation-standards.md)

```markdown
- Keep documentation in sync with code changes
- Use Google-style docstrings for all public interfaces
- Document all environment variables
- Include examples in documentation
```