# HuleEdu Developer Onboarding Guide

Welcome to the HuleEdu platform development team. This guide will help you set up your development environment, understand the codebase structure, and make your first contributions.

## Prerequisites

Before you begin, ensure you have the following installed:

### Required Software

1. **Docker Desktop** (v20.10+)
   - Download: <https://www.docker.com/products/docker-desktop>
   - Verify: `docker --version` and `docker compose version`
   - Note: HuleEdu uses Docker Compose v2 (not v1)

2. **Python 3.11**
   - Download: <https://www.python.org/downloads/>
   - Verify: `python --version` (should show 3.11.x)
   - Alternative: Use `pyenv` for Python version management

3. **PDM** (Python Development Master)
   - Install: `curl -sSL https://pdm-project.org/install-pdm.py | python3 -`
   - Or via pipx: `pipx install pdm`
   - Verify: `pdm --version`
   - Documentation: <https://pdm-project.org/>

4. **Git**
   - Verify: `git --version`
   - Configure: `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`

### Recommended Tools

- **VS Code** with Python and Docker extensions
- **Postman** or **HTTPie** for API testing
- **TablePlus** or **pgAdmin** for database inspection
- **Kafka Tool** or **kowl** for Kafka topic inspection

## Environment Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd huledu-reboot
```

### 2. Install Python Dependencies

HuleEdu uses a PDM monorepo with a single root lockfile. **Always run PDM commands from the repository root**.

```bash
# Install all dependencies (services + libraries)
pdm install

# Verify installation
pdm run python --version
```

### 3. Set Up Environment Variables

Create a `.env` file in the repository root:

```bash
cp .env.example .env
```

Key environment variables to configure:

```bash
# Database credentials (used by all services)
HULEEDU_DB_USER=huleedu_user
HULEEDU_DB_PASSWORD=huleedu_secure_password
HULEEDU_DB_HOST=localhost

# Kafka configuration
HULEEDU_KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Redis configuration
HULEEDU_REDIS_HOST=localhost
HULEEDU_REDIS_PORT=6379

# JWT secret for authentication
HULEEDU_JWT_SECRET=your-development-jwt-secret-key-change-in-production

# LLM provider configuration (for CJ assessment)
LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true  # Set to false for real LLM calls
ANTHROPIC_API_KEY=your-api-key-here
OPENAI_API_KEY=your-api-key-here

# Email service (optional for development)
HULEEDU_SMTP_HOST=localhost
HULEEDU_SMTP_PORT=1025  # Use mailhog for local testing
```

### 4. Start Infrastructure Services

Start Kafka, Zookeeper, Redis, and PostgreSQL containers:

```bash
# Start infrastructure only
docker compose up -d kafka zookeeper redis

# Verify infrastructure is running
docker ps | grep huleedu
```

### 5. Build and Start All Services

```bash
# Build and start all services (includes infrastructure)
pdm run dev-build-start

# Check service health
pdm run dev-logs
```

This command will:
- Build Docker images for all services
- Start all containers with hot-reload enabled
- Tail logs from all services

**Note**: First build may take 5-10 minutes as it downloads base images and installs dependencies.

### 6. Verify Installation

Check that all services are running:

```bash
# List running containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check API Gateway health
curl http://localhost:8000/healthz

# Check Batch Orchestrator health
curl http://localhost:8010/healthz
```

You should see 18+ containers running (services + infrastructure).

## Development Workflow

### Common Commands

All development commands are run via PDM from the repository root:

```bash
# Start services without rebuilding
pdm run dev-start

# Restart a specific service (after code changes)
pdm run dev-restart batch_orchestrator_service

# View logs for a specific service
pdm run dev-logs file_service

# Stop all services
pdm run dev-stop

# Rebuild a specific service
pdm run dev-build batch_orchestrator_service

# Format all code (REQUIRED before commit)
pdm run format-all

# Fix linting issues
pdm run lint-fix --unsafe-fixes

# Type check all code
pdm run typecheck-all

# Run tests
pdm run pytest-root services/file_service/tests/
pdm run pytest-root tests/integration/
```

### Development Aliases (Optional)

For convenience, source the development aliases:

```bash
source scripts/dev-aliases.sh

# Now you can use short aliases
pyp services/file_service/tests/  # Instead of pdm run pytest-root
pdmr typecheck-all                # Instead of pdm run typecheck-all
```

### Code Quality Checklist

Before committing any code, run:

```bash
pdm run format-all
pdm run lint-fix --unsafe-fixes
pdm run typecheck-all
```

All three commands must pass without errors.

## Understanding the Codebase

### Repository Structure

```
huledu-reboot/
├── .claude/                  # AI assistant rules and documentation
│   ├── rules/               # Development standards and patterns
│   └── work/                # Session context and task tracking
├── docs/                    # Platform documentation
│   ├── overview/           # This onboarding guide
│   ├── operations/         # Operational runbooks
│   ├── product/            # Product requirements
│   └── decisions/          # Architectural Decision Records
├── libs/                    # Shared libraries
│   ├── common_core/        # Event contracts, API models
│   └── huleedu_service_libs/  # Infrastructure utilities
├── services/                # Microservices
│   ├── api_gateway_service/
│   ├── batch_orchestrator_service/
│   ├── essay_lifecycle_service/
│   ├── file_service/
│   └── ... (18 services total)
├── tests/                   # Cross-service integration tests
├── scripts/                 # Utility scripts
├── TASKS/                   # Task documentation
├── CLAUDE.md               # Technical reference guide
└── pyproject.toml          # PDM configuration
```

### Key Documentation Files

Start by reading these in order:

1. **`CLAUDE.md`** - Comprehensive technical reference (workflow, commands, architecture)
2. **`.claude/rules/000-rule-index.md`** - Index of all development rules
3. **`.claude/rules/010-foundational-principles.md`** - Core architectural principles
4. **`.claude/rules/020-architectural-mandates.md`** - DDD and service boundaries
5. **`.claude/work/session/readme-first.md`** - Current development status

### First Service to Explore: File Service

We recommend starting with the **File Service** because it:
- Has a clear, focused responsibility (file upload and text extraction)
- Demonstrates standard service patterns (DI, protocols, HTTP endpoints)
- Shows event publishing patterns
- Includes comprehensive tests

#### File Service Structure

```
services/file_service/
├── api/
│   ├── file_routes.py       # HTTP endpoints (Blueprint pattern)
│   └── health_routes.py     # Health check endpoint
├── protocols.py             # Protocol interfaces (DI contracts)
├── implementations/         # Protocol implementations
│   ├── file_processor.py
│   └── text_extractor.py
├── di.py                    # Dependency injection providers
├── app.py                   # Application setup (<150 lines)
├── models.py                # SQLAlchemy models
├── config.py                # Service configuration
└── tests/
    ├── unit/                # Unit tests (mocked dependencies)
    ├── integration/         # Integration tests (real dependencies)
    └── conftest.py          # Test fixtures
```

#### Exploring File Service Code

1. **Start with `app.py`**: See how the service is bootstrapped
2. **Review `protocols.py`**: Understand the service interfaces
3. **Check `implementations/`**: See how protocols are implemented
4. **Examine `api/file_routes.py`**: Learn HTTP endpoint patterns
5. **Study `tests/`**: Understand testing approach

### Understanding Event Flows

HuleEdu uses event-driven architecture with Kafka. Read these flow documents:

1. **`.claude/rules/035-complete-processing-flow-overview.md`** - High-level system flow
2. **`.claude/rules/038-file-upload-processing-flow.md`** - File upload flow (FLOW-05)
3. **`.claude/rules/036-phase1-processing-flow.md`** - Phase 1: Student matching
4. **`.claude/rules/037-phase2-processing-flow.md`** - Phase 2: Pipeline processing

#### Key Event Concepts

- **EventEnvelope**: Standard wrapper for all Kafka events
- **Correlation ID**: Traces operations across services
- **Thin Events**: Events carry IDs, not full data payloads
- **Storage References**: Large content stored in Content Service, referenced by ID

Example event flow:

```
Client Upload → File Service → EssayContentReady event → Essay Lifecycle Service
                      ↓
              Content Service (store text)
```

### Running Tests

HuleEdu has comprehensive test coverage across multiple levels:

#### Test Organization

- **Service tests**: `services/<service>/tests/` (unit, integration)
- **Cross-service tests**: `tests/integration/` (contract, E2E)
- **Functional tests**: `tests/functional/` (full workflows)

#### Running Tests

Always use `pdm run pytest-root` (root-aware runner):

```bash
# Run all tests for a service
pdm run pytest-root services/file_service/tests/

# Run specific test file
pdm run pytest-root services/file_service/tests/unit/test_file_processor.py

# Run specific test
pdm run pytest-root 'services/file_service/tests/unit/test_file_processor.py::TestFileProcessor::test_upload_file'

# Run with markers
pdm run pytest-root services/file_service/tests/ -m unit
pdm run pytest-root tests/integration/ -m "not slow"

# Run integration tests (requires services running)
pdm run dev-build-start  # Start services first
pdm run pytest-root tests/integration/ -m integration
```

#### Understanding Test Markers

- `@pytest.mark.asyncio`: Async unit tests
- `@pytest.mark.integration`: Requires external services (Docker)
- `@pytest.mark.slow`: Long-running tests
- `@pytest.mark.e2e`: End-to-end tests
- `@pytest.mark.financial`: Incurs real costs (LLM API calls)

### Database Access

Each service has its own PostgreSQL database. Database names follow the pattern: `huleedu_<service_name>`.

#### Accessing Service Databases

```bash
# IMPORTANT: Source .env first to load credentials
source .env

# Access database (requires quotes around variables)
docker exec huleedu_file_service_db psql -U "$HULEEDU_DB_USER" -d huleedu_file -c "\dt"

# Or use hardcoded values
docker exec huleedu_file_service_db psql -U huleedu_user -d huleedu_file -c "SELECT * FROM files LIMIT 10;"

# Common database names
# huleedu_batch_orchestrator
# huleedu_essay_lifecycle
# huleedu_file
# huleedu_content
# huleedu_class_management
# huleedu_cj_assessment
# huleedu_result_aggregator
```

#### Database Migrations

HuleEdu uses Alembic for database migrations. See `.claude/rules/085-database-migration-standards.md` for detailed guidance.

```bash
# Generate migration for a service
cd services/file_service
pdm run alembic revision --autogenerate -m "Add filename column"

# Apply migrations
pdm run alembic upgrade head

# Rollback migration
pdm run alembic downgrade -1
```

## Making Your First Change

### Recommended First Task: Add a Health Check Detail

Let's add a simple feature to demonstrate the workflow.

#### 1. Choose a Service

We'll modify the File Service to add version info to its health check.

#### 2. Create a Task

```bash
pdm run new-task --domain infrastructure --title "Add version to file service health check"
```

This creates a task file in `TASKS/infrastructure/` with frontmatter for tracking.

#### 3. Make Code Changes

Edit `services/file_service/api/health_routes.py`:

```python
from quart import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz", methods=["GET"])
async def health_check():
    """Health check endpoint with version info."""
    return jsonify({
        "status": "healthy",
        "service": "file_service",
        "version": "1.0.0"  # Add this line
    })
```

#### 4. Write a Test

Edit `services/file_service/tests/integration/test_health_endpoint.py`:

```python
async def test_health_check_includes_version(test_client):
    """Test that health check returns version info."""
    response = await test_client.get("/healthz")
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "healthy"
    assert "version" in data  # Add this assertion
    assert data["version"] == "1.0.0"
```

#### 5. Run Quality Checks

```bash
# Format code
pdm run format-all

# Fix linting
pdm run lint-fix --unsafe-fixes

# Type check
pdm run typecheck-all

# Run tests
pdm run pytest-root services/file_service/tests/
```

#### 6. Restart Service and Test

```bash
# Restart file service to pick up changes
pdm run dev-restart file_service

# Test the endpoint
curl http://localhost:8030/healthz
```

#### 7. Commit Changes

```bash
git add services/file_service/api/health_routes.py
git add services/file_service/tests/integration/test_health_endpoint.py
git commit -m "feat: add version info to file service health check"
```

### Git Workflow

HuleEdu follows a feature branch workflow:

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes and commit frequently**:
   ```bash
   git add <files>
   git commit -m "type: description"
   ```

   Commit types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

3. **Run pre-commit hooks**:
   ```bash
   pdm run pre-commit install  # One-time setup
   # Hooks run automatically on commit
   ```

4. **Push to remote**:
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create pull request** (via GitHub/GitLab UI)

## Key Architectural Patterns

### 1. Protocol-First Design

All dependencies are defined as `typing.Protocol` interfaces:

```python
from typing import Protocol

class FileProcessorProtocol(Protocol):
    async def process_file(self, file_path: str) -> str:
        """Process uploaded file and return text content."""
        ...
```

Implementations are injected via Dishka DI container.

### 2. Event-Driven Communication

Services communicate via Kafka events, never direct calls:

```python
# FORBIDDEN: Direct service call
from services.other_service.api import some_function  # ❌

# CORRECT: Event-based communication
from common_core import EventEnvelope, EssayContentReadyV1
await kafka_bus.publish(EventEnvelope(
    event_type="essay.content.ready.v1",
    data=EssayContentReadyV1(...)
))  # ✅
```

### 3. Thin Events with Storage References

Events carry IDs, not large payloads:

```python
# CORRECT: Reference to stored content
EssayContentReadyV1(
    essay_id=uuid,
    text_storage_id="abc123",  # Reference, not full text
    correlation_id=correlation_id
)
```

### 4. Database Per Service

Each service owns its database exclusively:

```python
# FORBIDDEN: Cross-service database access
from services.other_service.models import OtherModel  # ❌

# CORRECT: Event-based data sharing
# Query via events or expose HTTP query endpoints
```

### 5. HTTP Service Blueprint Pattern

HTTP services keep `app.py` lean (<150 lines) and use Blueprints:

```python
# app.py - Setup only
from quart import Quart
from api.file_routes import file_bp
from api.health_routes import health_bp

app = Quart(__name__)
app.register_blueprint(file_bp, url_prefix="/api/v1")
app.register_blueprint(health_bp)
```

## Common Development Tasks

### Adding a New Event Contract

1. Define Pydantic model in `libs/common_core/src/common_core/`:
   ```python
   from pydantic import BaseModel, Field
   from uuid import UUID

   class MyNewEventV1(BaseModel):
       event_id: UUID
       correlation_id: str
       data_field: str = Field(description="Description")
   ```

2. Register in event enums if needed
3. Publish event: `await kafka_bus.publish(EventEnvelope(...))`
4. Consume event: Define handler and register with event bus

### Adding a New Service Endpoint

1. Define route in `services/<service>/api/<domain>_routes.py`
2. Implement protocol interface in `implementations/`
3. Register route Blueprint in `app.py`
4. Write integration test in `tests/integration/`
5. Document in service README or architecture rule

### Debugging Service Issues

See `.claude/rules/044-service-debugging-and-troubleshooting.md` for comprehensive debugging guide.

Quick debugging commands:

```bash
# View service logs
pdm run dev-logs file_service

# Access container shell
docker exec -it huleedu_file_service_container /bin/bash

# Check service health
curl http://localhost:8030/healthz

# Inspect Kafka topics
docker exec huleedu_kafka kafka-topics --list --bootstrap-server localhost:9092

# View Redis keys
docker exec -it huleedu_redis redis-cli KEYS "*"
```

## Next Steps

After completing this onboarding:

1. **Read architecture rules**: Start with `.claude/rules/010-foundational-principles.md`
2. **Explore a second service**: Try Essay Lifecycle Service or Batch Orchestrator
3. **Review event flows**: Study `.claude/rules/035-complete-processing-flow-overview.md`
4. **Run integration tests**: Understand cross-service workflows
5. **Pick a real task**: Check `TASKS/` for available work
6. **Join team channels**: Ask questions and share learnings

## Resources and Support

### Documentation

- **Technical reference**: `CLAUDE.md`
- **Architecture rules**: `.claude/rules/`
- **Service patterns**: `.claude/rules/040-service-implementation-guidelines.md`
- **Testing guide**: `.claude/rules/075-test-creation-methodology.md`
- **Docker workflow**: `.claude/rules/081.1-docker-development-workflow.md`

### Common Issues

- **Import errors**: Check `.claude/rules/055-import-resolution-patterns.md`
- **Docker problems**: See `.claude/rules/046-docker-container-debugging.md`
- **Test failures**: Review `.claude/rules/075-test-creation-methodology.md`
- **Database access**: Reference `CLAUDE.md` Database Access section

### Development Standards

- **Python style**: `.claude/rules/050-python-coding-standards.md`
- **Pydantic usage**: `.claude/rules/051-pydantic-v2-standards.md`
- **SQLAlchemy patterns**: `.claude/rules/053-sqlalchemy-standards.md`
- **Error handling**: `.claude/rules/048-structured-error-handling-standards.md`

### Getting Help

- Check `.claude/work/session/handoff.md` for current development status
- Review relevant service architecture in `.claude/rules/020.x-*-architecture.md`
- Search `TASKS/` for related task documentation
- Ask in team communication channels

Welcome to HuleEdu development. Happy coding!
