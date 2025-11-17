# HuleEdu Developer Reference

When operating in the Claude Code cloud sandbox (web, not access to local machine. To check if True: make tool call checking if local machine is available), apply `.claude/rules/111-cloud-vm-execution-standards.md` to understand tooling limits (no Docker/services) and required workflow.

## Core Workflow

### 1. Initial Setup

```markdown
- FIRST ACTION Read `.claude/rules/000-rule-index.md` first. The index contains onboard instructions for all services and project rules and standards. If the prompt contains a task description, use it to read and review all rule files related to the task at hand.
- SECOND ACTION Use the user's task description to read and review all rule files related to the task at hand.
- THIRD ACTION Read `.claude/work/session/handoff.md` and `.claude/work/session/readme-first.md` for **critical** cross-service task context.

- WHEN IMPLEMENTING NEW CODE using library dependencies: always use Context7 to ensure updated library API context.
- WHEN PERFORMING A **CODE REVIEW**: If task is **code review** create a new file in `.claude/archive/code-reviews/` using <WHAT_IS_BEING_REVIEWED_YEAR_MONTH_DAY.md>. After each task phase, Always stop to update `.claude/archive/code-reviews/<WHAT_IS_BEING_REVIEWED_YEAR_MONTH_DAY.md>` with any new information + ask user any clarifying questions to retain alignment with user's intent.

### 2. Task Execution

```markdown
1. **To avoid immediate task failure**: Read `.claude/work/session/handoff.md` and `.claude/work/session/readme-first.md` for **critical** cross-service task context.
2. **Select Mode**: Use `.claude/rules/110-ai-agent-interaction-modes.md` to choose mode (Planning, Coding, Debugging)
3. **Rule Reference**: Consult `.claude/rules/000-rule-index.md` for relevant rules
cross-service task context.
4. **Update**: After each task phase, Always stop to update `.claude/work/session/handoff.md` and `.claude/work/session/readme-first.md` with any new information + ask user any clarifying questions to retain alignment with user's intent.
```

### 3. Error Resolution Protocol

```markdown
1. **Investigate First**: Check implementation before proposing changes
2. **Follow Patterns**: Use existing code patterns over new abstractions
3. **Root Cause**: Fix immediate issues before redesigning
```

### 4. Documentation & Testing

```markdown
- Update relevant task documents per `.claude/rules/090-documentation-standards.md`
- Never create files in root - follow folder patterns
- All code changes require tests (run and verified)
- Never lint style issues manually before having run format-all and lint-fix --unsafe-fixes
- Always run typecheck-all from root after creating a test or implementing new code
```

---

## Technical Reference

### Architectural Overview

### Architecture (.claude/rules/010-foundational-principles.md)

```markdown
- **Pattern**: Event-driven microservices with STRICT DDD, CC principles, and small modular SRP files (<400-500 LoC HARD LIMIT FILE SIZE).
- **Stack**: 
  - Core: Python 3.11, Quart, monorepo PDM, Dishka, Pydantic classes for all data classes.
  - Data: PostgreSQL, SQLAlchemy, asyncpg
  - Comms: Kafka, aiohttp, Redis
  - Container: Docker, Docker Compose
  - Dependency management: PDM with single root lockfile. 
  - Client Facing Services: FastAPI 
```

**CRITICAL CONSTRAINT** Always use `pdm <command>` *from root directory* to run any command. *Never* use `pdm <command>` from subdirectory.

**dependency resolution** full path relative root for all imports. **NEVER** use relative imports when importing dependencies from outside service directory.

### Service Communication (.claude/rules/020-architectural-mandates.md)

```markdown
- **Primary**: Asynchronous via Kafka
- **Secondary**: Synchronous HTTP for queries requiring immediate response
- **Strict**: No direct DB access between services
- **Strict**: all boundary objects defined as event contracts and api models in libs/common_core/src/common_core. All events registered as topics in libs/common_core/src/common_core/event_enums.py. 
- **Strict**: all error and exception handling done using centralized and quart/fastapi specific error handling patterns `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/`+ error models in `libs/common_core/src/common_core/error_enums.py`
```

### Database & Persistence (.claude/rules/085-database-migration-standards.md)

```markdown
- **ORM**: SQLAlchemy async with `asyncpg`
- **Strict** ban on RAW SQL
- **Isolation**: Each service has its own PostgreSQL database
- **Migrations**: always consult .claude/rules/085-database-migration-standards.md
```

### HTTP Services (.claude/rules/042-async-patterns-and-di.md)

```markdown
- **app.py**: Setup only (<150 LoC)
- **Blueprints**: In `api/` directory
- **Example**: `@services/file_service/` structure
```

### Worker Services (.claude/rules/042-async-patterns-and-di.md)

- **Quart Deployment Patterns**:
  - [services/essay_lifecycle_service]: Standalone worker and API services (complex processing)
  - Other services: Integrated worker using Quart's `@app.before_serving` in `services/*/app.py` (simpler services)
- **Example**: `services/spellchecker_service/` (integrated) vs `services/essay_lifecycle_service/` (standalone)

### Dependency Injection (.claude/rules/042-async-patterns-and-di.md)

```markdown
- **Interfaces**: Define with `typing.Protocol` in `protocols.py`
- **Providers**: Implement `Provider` classes in `di.py`
- **Scopes**:
  - `APP`: Stateless singletons (settings, HTTP clients)
  - `REQUEST`: Per-operation instances (DB sessions)
```

### Event System (.claude/rules/051-event-contract-standards.md)

```markdown
- **Envelope**: All Kafka events use `EventEnvelope`
- **Topics**: Generate with `topic_name()` utility
- **Large Data**: Use `StorageReferenceMetadata` for payloads
```

## Testing & Quality

### Testing (strict adherence to `.claude/rules/075-test-creation-methodology.md` + `.claude/rules/075.1-parallel-test-creation-methodology.md`)

#### Test Types

```markdown
- **Unit**: Isolated function testing
- **Integration**: Component interaction
- **Contracts**: Event/API schema validation

Only cross-service integration and functional Dockers tests in `tests/` directory. Service code tests in services.
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
- `pytest.mark.asyncio`: Unit tests
- `@pytest.mark.integration`: External services required
- `@pytest.mark.financial`: incur real costs via external API calls
- `@pytest.mark.slow`: Long-running tests
- `@pytest.mark.e2e`: End-to-end tests (using docker-compose)
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

# Then access logs: read .cursor/rules/046-docker-container-debugging.md to properly debug containers.

#### Development

```bash
# Development (hot-reload enabled)
pdm run dev-start [service]          # Start existing images without rebuilding (fast)
pdm run dev-build [service]          # Build images with cache (doesn't start)
pdm run dev-build-start [service]    # Build with cache then start
pdm run dev-build-clean [service]    # Build without cache (slow, use when needed)
pdm run dev-restart [service]        # Restart running containers (for volume-mounted code changes)
pdm run dev-recreate [service]       # Force container recreation to pick up env var changes
pdm run dev-stop [service]           # Stop running containers
pdm run dev-logs [service]           # Follow container logs
pdm run dev-check                    # Check what needs rebuilding

# Production (optimized)
pdm run prod-build [service]         # Build for production with cache
pdm run prod-build-clean [service]   # Build for production without cache
pdm run prod-start [service]         # Start production containers
pdm run prod-stop [service]          # Stop production containers
pdm run prod-restart [service]       # Restart production containers
pdm run prod-logs [service]          # Follow production logs
pdm run prod-health                  # Check production service health
pdm run prod-deploy [service]        # Full production deployment workflow
```

### Database Access (Common Issue)

```markdown
# IMPORTANT: Shell doesn't have .env variables by default!
# Always source .env first (from repo root):
source .env

# Then access database (note: quotes around variable are required):
docker exec huleedu_<service>_db psql -U "$HULEEDU_DB_USER" -d <db_name> -c "SQL"

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

## Database Migrations

### follow established pattern in `.claude/rules/085-database-migration-standards.md`

## Monitoring & Observability

### Metrics

```markdown
- Use Prometheus for service metrics
- Instrument key operations with timing and counters
- Follow naming conventions: `service_operation_total`, `service_operation_duration_seconds`
```

## Documentation

### Standards (.claude/rules/090-documentation-standards.md)

- Keep documentation in sync with code changes
- Use Google-style docstrings for all public interfaces
- Document all environment variables
- Include examples in documentation
