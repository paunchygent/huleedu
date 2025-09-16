# HuleEdu Developer Reference

## Core Workflow

### 1. Initial Setup

```markdown
- Read `.cursor/rules/000-rule-index.mdc` first. The index contains onboard instructions for all services and project rules and standards.
- Use the user's task description to read and review all rule files related to the task at hand.
- Key architectural documents in this order:
  1. `.claude/rules/080-repository-workflow-and-tooling.mdc`
  2. `.claude/rules/010-foundational-principles.mdc`
  3. `.claude/rules/020-architectural-mandates.mdc`
  4. `.claude/rules/030-event-driven-architecture-eda-standards.mdc`
  5. `.claude/rules/042-async-patterns-and-di.mdc`
  6. `.claude/rules/050-python-coding-standards.mdc`
  7. `.claude/rules/100-terminology-and-definitions.mdc`
  8. `.claude/rules/048-structured-error-handling-standards.mdc`
```

### 2. Task Execution

```markdown
1. **Select Mode**: Use `.claude/rules/110-ai-agent-interaction-modes.mdc` to choose mode (Planning, Coding, Debugging)
2. **Rule Reference**: Consult `.claude/rules/000-rule-index.mdc` for relevant rules
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
- Update relevant task documents per `.claude/rules/090-documentation-standards.mdc`
- Never create files in root - follow folder patterns
- All code changes require tests (run and verified)
- Never lint style issues manually before having run format-all and/or lint-fix --unsafe-fixes
- Always run typecheck-all from root after creating a test or implementing new code
```

---

## Technical Reference

### Architectural Overview

### Architecture (.claude/rules/010-foundational-principles.mdc)

```markdown
- **Pattern**: Event-driven microservices with DDD
- **Stack**: 
  - Core: Python 3.11, Quart, PDM, Dishka, Pydantic
  - Data: PostgreSQL, SQLAlchemy, asyncpg
  - Comms: Kafka, aiohttp
  - Container: Docker, Docker Compose
```

### Service Communication (.claude/rules/020-architectural-mandates.mdc)

```markdown
- **Primary**: Asynchronous via Kafka
- **Secondary**: Synchronous HTTP for queries requiring immediate response
- **Strict**: No direct DB access between services
```

### Database & Persistence (.claude/rules/085-database-migration-standards.md)

```markdown
- **ORM**: SQLAlchemy async with `asyncpg`
- **Isolation**: Each service has its own PostgreSQL database
- **Migrations**: see .claude/rules/085-database-migration-standards.md
```

### HTTP Services (.claude/rules/042-async-patterns-and-di.mdc)

```markdown
- **app.py**: Setup only (<150 LoC)
- **Blueprints**: In `api/` directory
- **Example**: `@services/file_service/` structure
```

### Worker Services (.claude/rules/042-async-patterns-and-di.mdc)

```markdown
- `worker_main.py`: Service lifecycle and DI
- `event_processor.py`: Core business logic
- **Example**: `@services/spell_checker_service/`
```

### Dependency Injection (.claude/rules/042-async-patterns-and-di.mdc)

```markdown
- **Interfaces**: Define with `typing.Protocol` in `protocols.py`
- **Providers**: Implement `Provider` classes in `di.py`
- **Scopes**:
  - `APP`: Stateless singletons (settings, HTTP clients)
  - `REQUEST`: Per-operation instances (DB sessions)
```

### Event System (.claude/rules/051-event-contract-standards.mdc)

```markdown
- **Envelope**: All Kafka events use `EventEnvelope`
- **Topics**: Generate with `topic_name()` utility
- **Large Data**: Use `StorageReferenceMetadata` for payloads
```

## Testing & Quality

### Testing (.claude/rules/070-test-creation-methodology.mdc)

#### Test Types

```markdown
- **Unit**: Isolated function testing
- **Integration**: Component interaction
- **Contracts**: Event/API schema validation
```

#### Test Execution

Preferred (root-aware runner)

```bash
# Go-to method (resolves paths relative to repo root)
pdm run pytest-root <path-or-nodeid> [pytest args]

# Examples (from repo root):
pdm run pytest-root services/class_management_service/tests/test_core_logic.py
pdm run pytest-root 'services/.../test_file.py::TestClass::test_case'
pdm run pytest-root services/... -k 'expr'          # selection with -k
pdm run pytest-root services/... -m 'unit'          # override markers

# From any subdirectory
bash "$(git rev-parse --show-toplevel)"/scripts/pytest-root.sh <path-or-nodeid> [args]

# Optional: enable alias and use `pyp` or `pdmr`
source scripts/dev-aliases.sh
pyp <path-or-nodeid> [args]
pdmr pytest-root <path-or-nodeid> [args]

# Force root project from any dir (PDM)
pdmr pytest-root <path-or-nodeid> [args]
```

#### Common Markers

```markdown
- `@pytest.mark.integration`: External services required
- `@pytest.mark.slow`: Long-running tests
- `@pytest.mark.docker`: Needs Docker Compose
- `@pytest.mark.kafka`: Requires Kafka
```

### Subagents

When asked to launch two or more agents in parallel: launch all agents in a single tool call for parallel execution

### Code Quality

```markdown
- **Linting**: `pdm run lint` (Ruff)
- **Pre-commit**: `pdm run pre-commit install`
```

### Docker Development

```markdown
# Always use docker ps | grep huleedu first to find container name

# Then access logs: read .cursor/rules/046-docker-container-debugging.mdc to properly debug containers.

#### Development

Always use development builds and services unless explicitly asked to use production builds.

```bash
# Main development workflow
pdm run dev <command> [service]     # Use main dev script

pdm run dev build clean             # Clean build (no cache) for production
pdm run dev build dev               # Build ALL dev images with hot-reload support
pdm run dev build dev nlp_service   # Build specific dev image

# Running services
pdm run dev dev                     # Start ALL services with hot-reload
pdm run dev dev nlp_service         # Start specific service with hot-reload

# Utilities
pdm run dev check                   # Check what needs rebuilding
pdm run dev incremental             # Incremental build using cache

# Quick commands
pdm run up                          # Start all services 
pdm run restart essay_lifecycle_worker      # Restart specific service
pdm run down                        # Stop all services
pdm run logs nlp_service         # Follow service logs
```

#### Production

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

### Database Environment Separation

```bash
# Development (default): Docker containers
HULEEDU_ENVIRONMENT=development

# Production: External managed databases  
HULEEDU_ENVIRONMENT=production
# Requires: HULEEDU_PROD_DB_HOST, HULEEDU_PROD_DB_PASSWORD

# Database management
pdm run db-reset                    # Reset development databases
pdm run db-seed                     # Seed development data
pdm run prod-validate              # Validate production config
pdm run prod-migrate               # Run production migrations
```

### Service Management

```markdown
- **Migrations**: `pdm run alembic upgrade head` (from service dir)
- **Rebuild Rule**: Always use `--no-cache` after code changes
```

## Database Migrations

### Standards (.claude/rules/085-database-migration-standards.md)

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

### Standards (.claude/rules/090-documentation-standards.md)

```markdown
- Keep documentation in sync with code changes
- Use Google-style docstrings for all public interfaces
- Document all environment variables
- Include examples in documentation
```

- ALWAYS USE   1. restart - for restarting specific services
  2. restart-all - for restarting all services
