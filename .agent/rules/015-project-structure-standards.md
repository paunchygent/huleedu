---
id: "015-project-structure-standards"
type: "standards"
created: 2025-05-25
last_updated: 2025-11-17
scope: "all"
---
# 015: Project Structure Standards

## 1. Root Directory Structure

**Permitted Root Files:**
- `README.md`, `LICENSE`, `CHANGELOG.md`, `pyproject.toml`, `pdm.lock`
- `docker-compose.yml`, `docker-compose.*.yml` (env-specific overrides)
- `Dockerfile.deps` (shared dependency image)
- `.gitignore`, `.pdm-python`, `.dockerignore`
- `AGENTS.md`, `CODEX.md`, `GEMINI.md` (AI assistant references - expected in root)
- `CLAUDE.md`, `CLAUDE.local.md` (Claude Code instructions)

**Permitted Root Directories:**
- `.git/`, `.venv/`, `.mypy_cache/`, `__pycache__/`, `.cursor/`, `.ruff_cache/`, `.windsurf/`, `.claude/`
- `libs/`, `services/`, `scripts/`, `docs/`, `TASKS/`
- `frontend/` (frontend application), `observability/` (monitoring configs)
- `test_uploads/` (test fixtures), `tests/` (cross-service integration tests)
- `data/`, `output/`, `build/`, `dist/` (generated artifacts - gitignored)

**FORBIDDEN**: Setup scripts, service-specific files, temporary files in root

## 2. Scripts Directory Structure

```
scripts/
├── README.md
├── docker-rebuild.sh                 # Script to rebuild Docker containers
├── kafka_topic_bootstrap.py          # Python script to create Kafka topics
├── setup_huledu_environment.sh       # Main environment setup script
├── validate_batch_coordination.sh    # Test script for batch coordination
├── docs/
│   └── manual_validation_guide.md    # Manual for validation steps
├── tests/
│   └── __init__.py
└── utils/
    └── sync_rules.py                 # Syncs .md rules to .md files for pre-commit
```

## 3. Services Directory Structure **structural mandates**

This is a high-level overview. For detailed service architecture, see the `020.x` series of rules.

```
services/
├── api_gateway_service/             # FastAPI-based API Gateway
├── batch_conductor_service/         # Kafka worker service
├── batch_orchestrator_service/      # Quart-based orchestrator service
├── cj_assessment_service/           # Kafka worker service
├── class_management_service/        # FastAPI CRUD service
├── content_service/                 # Quart-based content storage service
├── essay_lifecycle_service/         # Hybrid Quart HTTP + Kafka worker service
├── file_service/                    # Quart-based file upload service
├── spellchecker_service/           # Kafka worker service
└── libs/                            # Shared libraries for services
```

### Representative Service Example (`essay_lifecycle_service`)

```
services/essay_lifecycle_service/    # Hybrid HTTP + Kafka service
    ├── app.py                     # Lean Quart HTTP API entry point
    ├── worker_main.py             # Kafka event consumer entry point
    ├── api/                       # **REQUIRED**: Blueprint API routes directory
    │   ├── __init__.py
    │   ├── health_routes.py
    │   └── essay_routes.py
    ├── implementations/           # **CLEAN ARCHITECTURE**: Protocol implementations
    │   ├── __init__.py
    │   ├── content_client.py
    │   ├── event_publisher.py
    │   └── ...
    ├── protocols.py               # Service behavioral contracts (typing.Protocol)
    ├── di.py                      # Dishka dependency injection providers
    ├── config.py                  # Pydantic settings configuration
    ├── state_store.py             # Essay state persistence layer (e.g., SQLite)
    ├── pyproject.toml
    ├── Dockerfile
    └── tests/
```

## 4. Service Architecture Patterns **MANDATORY**

### 4.1. Quart Services (Internal APIs)

**Use `api/` directory with Blueprint pattern**

See **[041-http-service-blueprint.md](mdc:041-http-service-blueprint.md)** for complete HTTP service patterns including:
- HuleEduApp initialization and requirements
- Blueprint structure and registration
- Health routes pattern
- Dishka DI integration

**Examples:** `content_service`, `file_service`, `batch_orchestrator_service`

### 4.2. FastAPI Services (Client-facing APIs)

**Use `routers/` directory with FastAPI router pattern**

**Structure:**
```
services/{service_name}/
├── app/
│   ├── main.py              # FastAPI app entry (< 150 LoC)
│   └── di.py                # Dependency injection
├── routers/                 # FastAPI routers (NOT api/)
│   ├── {domain}_routes.py
│   └── status_routes.py
├── implementations/
├── protocols.py
└── config.py
```

**See also:**
- [040-service-implementation-guidelines.md](mdc:040-service-implementation-guidelines.md) for core stack requirements
- [042.2-http-proxy-service-patterns.md](mdc:042.2-http-proxy-service-patterns.md) for API Gateway proxy patterns

**Examples:** `api_gateway_service`, `class_management_service`, `identity_service`, `entitlements_service`

### 4.3. Worker Services (Kafka Consumers)

**Simple Pattern** (business logic < 500 LoC):
```
services/{service_name}/
├── worker_main.py          # Service lifecycle, Kafka management
├── event_processor.py      # Message handling, routing
├── core_logic.py           # Business logic (single file)
├── protocols.py
└── di.py
```

**Complex Pattern** (business logic > 500 LoC, multiple domains):
```
services/{service_name}/
├── worker_main.py
├── event_processor.py
├── {domain}_logic/         # Domain-specific directory
│   ├── {feature}_handler.py
│   └── {feature}_validator.py
├── protocols.py
└── di.py
```

**Directory naming examples:** `cj_core_logic/`, `spell_logic/`, `command_handlers/`, `features/`

**See also:** [040-service-implementation-guidelines.md](mdc:040-service-implementation-guidelines.md) for Kafka integration requirements and `@idempotent_consumer` patterns

## 5. Common Core Structure

```
libs/common_core/
├── src/
│   └── common_core/
│       ├── __init__.py
│       ├── config_enums.py
│       ├── domain_enums.py
│       ├── error_enums.py
│       ├── event_enums.py
│       ├── status_enums.py
│       ├── observability_enums.py
│       ├── metadata_models.py
│       ├── pipeline_models.py
│       ├── events/
│       │   ├── __init__.py
│       │   ├── envelope.py
│       │   └── # all consumer defined and thin event contracts
│       └── py.typed
├── tests/
├── pyproject.toml
└── README.md
```

## 6. Documentation Directory Structure

```
docs/
├── overview/
├── architecture/
├── services/
├── operations/
├── how-to/
├── reference/
├── decisions/
├── product/
└── research/
```

## 7. Documentation Placement Rules

- **Root README.md**: Project overview and architecture
- **Service README.md**: `services/{service_name}/README.md`
- **Common Core README.md**: `libs/common_core/README.md`
- **FORBIDDEN**: README.md files in separate documentation folders

## 8. File Creation Rules

**MUST** verify target directory exists and follows this structure before creating files.
**MUST** create necessary parent directories if they don't exist.
**FORBIDDEN**: Files that violate this structure.
**HTTP Services**: MUST include api/ directory structure with Blueprint pattern.
