# HuleEdu Microservice Ecosystem - AI Agent Configuration

## Project Overview

**HuleEdu** is a sophisticated microservice ecosystem built on Domain-Driven Design (DDD) and Event-Driven Architecture (EDA) principles. This is a **production-grade educational platform** with strict architectural standards, comprehensive testing requirements, and zero tolerance for "vibe coding" or architectural deviations.

## 🚨 CRITICAL: Mandatory Rule Compliance

**BEFORE ANY TASK**: You **MUST** read and follow the comprehensive development rules located in `.cursor/rules/`. These rules are **NON-NEGOTIABLE** and define:

- **Foundational Principles** (010): Zero tolerance for architectural deviations
- **Project Structure Standards** (015): Mandatory file/folder organization  
- **Architectural Mandates** (020): DDD, Service Autonomy, Explicit Contracts
- **Python Coding Standards** (050): Mandatory type hints, Google-style docstrings
- **Testing Standards** (070): Unit, contract, integration, and E2E testing requirements
- **AI Agent Interaction Modes** (110.x): Your operational guidelines

**Rule Index**: Start with `.cursor/rules/000-rule-index.mdc` for complete rule navigation.

## Technology Stack & Architecture

### Core Technologies
- **Language**: Python 3.11+ with strict typing (`from __future__ import annotations`)
- **Framework**: Quart (async web framework)
- **Dependency Management**: PDM (Python Dependency Manager) monorepo
- **Data Validation**: Pydantic models with precise type definitions
- **Event Streaming**: Kafka for inter-service communication
- **Containerization**: Docker with docker-compose orchestration

### Microservices Architecture
```
huledu-reboot/
├── services/
│   ├── batch_service/          # Batch Orchestration Service (✅ Active)
│   ├── content_service/        # Content Management Service (✅ Active)
│   ├── spell_checker_service/  # Spell Checking Service (✅ Active)
│   ├── essay_service/          # Essay Lifecycle Service (🚧 Placeholder)
│   └── libs/                   # Shared Service Libraries (✅ Active)
├── common_core/                # Common Core Package (✅ Active)
├── scripts/                    # Project Scripts & Utilities
├── .cursor/rules/              # 🚨 MANDATORY DEVELOPMENT RULES
└── TASKS/                      # 🚨 PREVIOUS AND CURRENT DEVELOPMENT TASKS
```

## Development Commands (PDM Monorepo)

### Quality Assurance (MANDATORY before commits)
```bash
pdm run format-all      # Ruff formatting (REQUIRED)
pdm run lint-all        # Ruff linting (REQUIRED) 
pdm run typecheck-all   # mypy type checking (REQUIRED)
pdm run test-all        # pytest test suite (REQUIRED)
```

### Service Development
```bash
pdm run dev-content     # Run content service in development mode
pdm run dev-batch       # Run batch service in development mode
pdm run -p services/spell_checker_service start_worker  # Start spell checker worker
```

### Docker Operations
```bash
pdm run docker-build   # Build all service containers
pdm run docker-up      # Start services with docker-compose
```

## AI Agent Behavioral Guidelines

### 1. **ALWAYS Begin with WoofWoof** 
Every response must start with "WoofWoof" as per project requirements.

### 2. **Rule-First Development**
- **NEVER** start coding without consulting `.cursor/rules/`
- Use `fetch_rules` tool to access specific rule content
- **FORBIDDEN**: Architectural deviations, "vibe coding", or undocumented shortcuts

### 3. **Interaction Modes** (Reference: `.cursor/rules/110.x-*.mdc`)
- **Planning Mode** (110.1): Task analysis and execution planning
- **Coding Mode** (110.2): Code generation with full compliance
- **Testing Mode** (110.3): Test creation and execution
- **Debugging Mode** (110.4): Issue identification and resolution
- **Refactoring Mode** (110.5): Code improvement and linting fixes

### 4. **Code Quality Standards** (Reference: `.cursor/rules/050-python-coding-standards.mdc`)
```python
# MANDATORY: Future annotations import
from __future__ import annotations

# MANDATORY: Precise type hints (NO typing.Any for schemas/protocols)
def process_essay(essay_data: ProcessedEssayData) -> EssayProcessingResult:
    """Process essay data through validation pipeline.
    
    Args:
        essay_data: The essay data to process with metadata
        
    Returns:
        Processing result with status and validation details
        
    Raises:
        ValidationError: When essay data fails validation
    """
    # Implementation with proper error handling
```

### 5. **Testing Requirements** (Reference: `.cursor/rules/070-testing-and-quality-assurance.mdc`)
- **Unit Tests**: All business logic functions
- **Contract Tests**: Inter-service communication validation
- **Integration Tests**: Service interaction verification  
- **E2E Tests**: Complete workflow validation
- **Run Command**: `pdm run test-all` or `pdm pytest` for specific tests

### 6. **Event-Driven Communication** (Reference: `.cursor/rules/030-event-driven-architecture-eda-standards.mdc`)
```python
# MANDATORY: Use EventEnvelope for all events
from common_core.events import EventEnvelope

# Example event structure
event = EventEnvelope(
    event_type="essay.processing.completed",
    correlation_id=correlation_id,
    payload=EssayProcessingCompletedPayload(...)
)
```

### 7. **Network-Restricted Task Handling**
When encountering tasks with network dependencies:
```python
# Example: Skip network-dependent research
if task_requires_network_access:
    logger.warning("🌐 NETWORK ACCESS REQUIRED: Skipping PyPI research")
    logger.info("DEFERRED: Task requires network-enabled agent")
    # Continue with local portions only
```

### 8. **Documentation Standards** (Reference: `.cursor/rules/090-documentation-standards.mdc`)
- **Google-style docstrings** for all public functions/classes
- **Update documentation** after meaningful changes
- **Cite sources** using format: `12:15:app/components/Todo.tsx`

## Project-Specific Context

### Current Development Phase
**Phase 1.2**: Testing, observability, and architectural refinements

### Key Domain Concepts (Reference: `.cursor/rules/100-terminology-and-definitions.mdc`)
- **BatchUpload**: Collection of essays for processing (Batch Service)
- **ProcessedEssay**: Individual essay in lifecycle (Essay Service)
- **EssayStatus**: Lifecycle state enum (RECEIVED, VALIDATING, etc.)
- **EventEnvelope**: Standard event wrapper with correlation_id
- **Contract**: Versioned Pydantic models for inter-service communication

### Service Responsibilities
- **Batch Service**: Orchestrates essay processing pipelines
- **Content Service**: Manages essay content and metadata
- **Spell Checker Service**: Provides spell checking capabilities
- **Essay Service**: 🚧 **PLACEHOLDER** - Not yet implemented
- **Common Core**: Shared events, models, and utilities

## Security & Compliance

### File Access Restrictions
- **NEVER** access `.env*` files or sensitive configuration
- **RESPECT** `.gitignore` patterns for security
- **AVOID** exposing API keys, secrets, or credentials in code/logs

### Network Access Restrictions (Containerized Agents)
- **NO INTERNET ACCESS**: Containerized agents cannot access external networks for security
- **NO EXTERNAL API CALLS**: Cannot reach PyPI, GitHub, Docker Hub, or other external services
- **NO KAFKA/DATABASE CONNECTIONS**: Cannot connect to external infrastructure
- **LOCAL OPERATIONS ONLY**: Limited to file system operations and local code analysis

### Task Classification for Network-Restricted Agents

#### ✅ **SAFE TASKS** (No Network Required)
- Code refactoring and local file modifications
- Creating new files and directories
- Local testing and validation
- Configuration file updates
- Documentation updates
- Static code analysis and linting

#### 🌐 **NETWORK-DEPENDENT TASKS** (Defer to Network-Enabled Agents)
When encountering tasks marked with **🌐 NETWORK ACCESS REQUIRED**, containerized agents must:

1. **SKIP** the network-dependent portions
2. **DOCUMENT** what was skipped with clear reasoning
3. **DEFER** to AI agents with network access via terminal
4. **COMPLETE** any local/offline portions of the task

**Example Network-Dependent Tasks:**
- Research on PyPI, GitHub, or external documentation
- CI/CD pipeline setup and testing
- Docker image building and registry operations
- Database or message queue connections
- External API integrations
- Package installation or dependency updates

### Sandbox Behavior
- **READ-ONLY** access to sensitive directories
- **NETWORK-DISABLED** execution in full-auto mode
- **EXPLICIT APPROVAL** required for file modifications

## Error Handling & Debugging

### When Issues Arise
1. **Check Rules**: Consult `.cursor/rules/110.4-debugging-mode.mdc`
2. **Run Tests**: `pdm run test-all` to identify regressions
3. **Check Linting**: `pdm run lint-all` for Ruff code quality issues
4. **Verify Types**: `pdm run typecheck-all` for type errors

### Common Patterns
```python
# Proper exception handling with domain-specific errors
try:
    result = await process_essay(essay_data)
except ValidationError as e:
    logger.error(f"Essay validation failed: {e}", extra={"correlation_id": correlation_id})
    raise EssayProcessingError(f"Validation failed: {e}") from e
```

## Success Criteria

### For Every Task
- ✅ **Rules Compliance**: All `.cursor/rules/` standards followed
- ✅ **Quality Gates**: format-all, lint-all, typecheck-all, test-all pass
- ✅ **Documentation**: Updated READMEs, docstrings, and relevant docs
- ✅ **Testing**: Appropriate test coverage for changes
- ✅ **Architecture**: DDD/EDA principles maintained

### Code Review Readiness
- ✅ **Type Safety**: Complete, precise type annotations
- ✅ **Error Handling**: Proper exception management
- ✅ **Logging**: Structured logging with correlation IDs
- ✅ **Contracts**: Pydantic models for all inter-service data

## Phase 1.2 Task Analysis Summary

### Network-Dependent Tasks Identified in TASKS/PHASE_1.2.md
- **A.2**: PyPI research for type stubs (🌐 NETWORK REQUIRED)
- **B.2**: Kafka topic creation and cluster connection (🌐 NETWORK REQUIRED)  
- **B.4**: CI/CD setup and Docker operations (🌐 NETWORK REQUIRED)

### Safe Tasks for Containerized Agents
- **A.1**: Code refactoring for `topic_name()` helper
- **A.3**: Creating `.dockerignore` file
- **B.1**: Unit test implementation with dependency injection
- **B.3**: Prometheus metrics implementation (local code changes)
- **B.5**: ELS skeleton service creation
- **C.1-C.4**: Configuration and architectural improvements

### Technical Issues Corrected
- Fixed Kafka message serialization (bytes vs dict)
- Corrected Pydantic v2 syntax for model configuration
- Improved async metrics server implementation
- Added network access warnings to relevant tasks

## Final Reminders

1. **MANDATORY**: Start every response with "WoofWoof"
2. **FORBIDDEN**: Any architectural deviations or "vibe coding"
3. **REQUIRED**: Consult `.cursor/rules/` before any development task
4. **ESSENTIAL**: Run all quality gates before considering work complete
5. **CRITICAL**: Maintain DDD/EDA architectural integrity at all times
6. **NETWORK-RESTRICTED**: Skip and defer network-dependent tasks with clear documentation

---

**This is a production-grade educational platform. Excellence is not optional.** 