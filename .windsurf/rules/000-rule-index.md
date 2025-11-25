---
id: "000-rule-index"
type: "standards"
created: 2025-05-25
last_updated: 2025-11-17
scope: "all"
---
# HuleEdu Development Rules: Index

**MUST** adhere to these rules for all development, especially when generating code.

## Core Principles & Architecture
- [010-foundational-principles.md](mdc:010-foundational-principles.md): Core tenets and mindset
- [015-project-structure-standards.md](mdc:015-project-structure-standards.md): File and folder organization standards
- [020-architectural-mandates.md](mdc:020-architectural-mandates.md): DDD, Service Autonomy, Explicit Contracts
- **Service-Specific Architectures (`020.x`)**
  - [020.1-content-service-architecture.md](mdc:020.1-content-service-architecture.md): Content Service
  - [020.2-spellchecker-service-architecture.md](mdc:020.2-spellchecker-service-architecture.md): Spell Checker Service
  - [020.3-batch-orchestrator-service-architecture.md](mdc:020.3-batch-orchestrator-service-architecture.md): Batch Orchestrator Service
  - [020.4-common-core-architecture.md](mdc:020.4-common-core-architecture.md): Common Core Library
  - [020.5-essay-lifecycle-service-architecture.md](mdc:020.5-essay-lifecycle-service-architecture.md): Essay Lifecycle Service
  - [020.6-file-service-architecture.md](mdc:020.6-file-service-architecture.md): File Service
  - [020.7-cj-assessment-service.md](mdc:020.7-cj-assessment-service.md): CJ Assessment Service
  - [020.8-batch-conductor-service.md](mdc:020.8-batch-conductor-service.md): Batch Conductor Service
  - [020.9-class-management-service.md](mdc:020.9-class-management-service.md): Class Management Service
  - [020.10-api-gateway-service.md](mdc:020.10-api-gateway-service.md): API Gateway Service
  - [020.11-service-libraries-architecture.md](mdc:020.11-service-libraries-architecture.md): Service Libraries (Kafka, Redis, Logging)
  - [020.12-result-aggregator-service-architecture.md](mdc:020.12-result-aggregator-service-architecture.md): Result Aggregator Service
  - [020.13-llm-provider-service-architecture.md](mdc:020.13-llm-provider-service-architecture.md): LLM Provider Service (Centralized provider abstraction with queue resilience)
  - [020.14-websocket-service.md](mdc:020.14-websocket-service.md): WebSocket Service
  - [020.15-nlp-service-architecture.md](mdc:020.15-nlp-service-architecture.md): NLP Service (Phase 1 student matching, Phase 2 text analysis)
  - [020.16-email-service-architecture.md](mdc:020.16-email-service-architecture.md): Email Service
  - [020.17-entitlements-service-architecture.md](mdc:020.17-entitlements-service-architecture.md): Entitlements Service
  - [020.18-language-tool-service-patterns.md](mdc:020.18-language-tool-service-patterns.md): Language Tool Service (Grammar checking via Java subprocess)
  - [020.19-eng5-np-runner-container.md](mdc:020.19-eng5-np-runner-container.md): ENG5 NP Runner containerization patterns and volume mount standards
  - [020.20-cj-llm-prompt-contract.md](mdc:020.20-cj-llm-prompt-contract.md): CJ → LLM prompt composition map (student assignment, rubric, essays, system prompt overrides)
- [030-event-driven-architecture-eda-standards.md](mdc:030-event-driven-architecture-eda-standards.md): Event-driven communication standards with header-first optimization

## Processing Flows
- [035-complete-processing-flow-overview.md](mdc:035-complete-processing-flow-overview.md): Complete processing flow overview
- [036-phase1-processing-flow.md](mdc:036-phase1-processing-flow.md): Phase 1 processing flow documentation
- [037-phase2-processing-flow.md](mdc:037-phase2-processing-flow.md): Phase 2 processing flow documentation

## Implementation & Coding Standards
- [040-service-implementation-guidelines.md](mdc:040-service-implementation-guidelines.md): High-level service implementation principles and stack requirements
- [041-http-service-blueprint.md](mdc:041-http-service-blueprint.md): HTTP service architecture patterns and Blueprint implementation
- [041.1-fastapi-integration-patterns.md](mdc:041.1-fastapi-integration-patterns.md): FastAPI integration patterns with comprehensive observability and testing
- [042-async-patterns-and-di.md](mdc:042-async-patterns-and-di.md): Async patterns, protocols, dependency injection, worker service structure, and DI testing with pure implementation pattern
- [042.1-transactional-outbox-pattern.md](mdc:042.1-transactional-outbox-pattern.md): Transactional outbox pattern as fallback for Kafka failures
- [042.2-http-proxy-service-patterns.md](mdc:042.2-http-proxy-service-patterns.md): HTTP proxy service patterns for request forwarding, error handling, and observability
- [043-service-configuration-and-logging.md](mdc:043-service-configuration-and-logging.md): Configuration management and logging standards
- [043.1-kafka-redis-configuration-standards.md](mdc:043.1-kafka-redis-configuration-standards.md): Kafka and Redis configuration standards
- [044-service-debugging-and-troubleshooting.md](mdc:044-service-debugging-and-troubleshooting.md): CRITICAL debugging priority: service configuration over import patterns
- [044.1-circuit-breaker-observability.md](mdc:044.1-circuit-breaker-observability.md): Circuit breaker observability patterns and metrics integration standards
- [044.2-redis-kafka-state-debugging.md](mdc:044.2-redis-kafka-state-debugging.md): Redis and Kafka state debugging patterns for distributed system failures
- [045-retry-logic.md](mdc:045-retry-logic.md): Natural retry via idempotency and user-initiated retry patterns
- [046-docker-container-debugging.md](mdc:046-docker-container-debugging.md): Systematic Docker container discovery and debugging protocol
- [047-security-configuration-standards.md](mdc:047-security-configuration-standards.md): Security configuration patterns for JWT, secrets management, and environment-aware security controls
- [048-structured-error-handling-standards.md](mdc:048-structured-error-handling-standards.md): Exception-based error handling for boundaries, Result monad for internal control flow, error payload design
- [049-smtp-email-provider-patterns.md](mdc:049-smtp-email-provider-patterns.md): SMTP email provider configuration patterns
- [050-python-coding-standards.md](mdc:050-python-coding-standards.md): Python style, formatting, linting, typing, documentation
- [051-pydantic-v2-standards.md](mdc:051-pydantic-v2-standards.md): Pydantic v2 usage patterns, serialization, and configuration standards
- [052-event-contract-standards.md](mdc:052-event-contract-standards.md): Event contract standards and best practices
- [053-sqlalchemy-standards.md](mdc:053-sqlalchemy-standards.md): Database models and SQLAlchemy patterns
- [054-utility-markdown-mermaid-conversion.md](mdc:054-utility-markdown-mermaid-conversion.md): Markdown/Mermaid to HTML conversion patterns
- [055-import-resolution-patterns.md](mdc:055-import-resolution-patterns.md): Import patterns to avoid module conflicts in monorepo

## Quality, Workflow & Documentation
- [060-data-and-metadata-management.md](mdc:060-data-and-metadata-management.md): Data models, metadata management, typed metadata overlay pattern for gradual dict-to-Pydantic migration
- [070-testing-and-quality-assurance.md](mdc:070-testing-and-quality-assurance.md): Testing strategies (unit, contract, integration, E2E) with Prometheus registry handling
- [070.1-performance-testing-methodology.md](mdc:070.1-performance-testing-methodology.md): Performance testing methodology and patterns
- [075-test-creation-methodology.md](mdc:075-test-creation-methodology.md): Systematic test creation methodology, JWT authentication testing, content client mocking patterns
- [075.1-parallel-test-creation-methodology.md](mdc:075.1-parallel-test-creation-methodology.md): Parallel test creation with mandatory architect validation
- **Observability (071.x)**
  - [071-observability-index.md](mdc:071-observability-index.md): Observability patterns index
  - [071.1-observability-core-patterns.md](mdc:071.1-observability-core-patterns.md): Core observability patterns
  - [071.2-prometheus-metrics-patterns.md](mdc:071.2-prometheus-metrics-patterns.md): Prometheus metrics patterns
  - [071.3-jaeger-tracing-patterns.md](mdc:071.3-jaeger-tracing-patterns.md): Distributed tracing with Jaeger
  - [071.4-grafana-loki-patterns.md](mdc:071.4-grafana-loki-patterns.md): Grafana dashboards and Loki logs
- [072-grafana-playbook-rules.md](mdc:072-grafana-playbook-rules.md): Grafana dashboard and alerting playbook
- [073-health-endpoint-implementation.md](mdc:073-health-endpoint-implementation.md): Health endpoint implementation patterns for HuleEdu services
- [077-service-anti-patterns.md](mdc:077-service-anti-patterns.md): Common anti-patterns to avoid and their corrections
- [080-repository-workflow-and-tooling.md](mdc:080-repository-workflow-and-tooling.md): PDM monorepo usage, version control, CI/CD
- [081-pdm-dependency-management.md](mdc:081-pdm-dependency-management.md): PDM configuration and dependency management standards
- [081.1-docker-development-workflow.md](mdc:081.1-docker-development-workflow.md): Comprehensive Docker development workflow for optimized builds and hot-reload
- [082-ruff-linting-standards.md](mdc:082-ruff-linting-standards.md): Ruff linting and formatting configuration
- [083-pdm-standards-2025.md](mdc:083-pdm-standards-2025.md): Correct modern PDM syntax that must never be questioned
- [084-docker-containerization-standards.md](mdc:084-docker-containerization-standards.md): Docker containerization patterns, import requirements, and troubleshooting
- [084.1-docker-compose-v2-command-reference.md](mdc:084.1-docker-compose-v2-command-reference.md): Docker Compose v2 command reference
- [085-database-migration-standards.md](mdc:085-database-migration-standards.md): Database migration standards for HuleEdu microservices
- [086-mypy-configuration-standards.md](mdc:086-mypy-configuration-standards.md): MyPy configuration and monorepo type checking standards with module conflict resolution
- [087-docker-development-container-patterns.md](mdc:087-docker-development-container-patterns.md): Docker development container patterns and optimization standards for layer caching and hot-reload
- [090-documentation-standards.md](mdc:090-documentation-standards.md): Service, contract, and architectural documentation
- [095-textual-tui-patterns.md](mdc:095-textual-tui-patterns.md): Textual TUI development patterns and corrections to AI training data

## Frontend Development Standards
- [200-frontend-core-rules.md](mdc:200-frontend-core-rules.md): Core frontend architecture patterns (Vue 3 + Vite, TypeScript, modular design)
- [201-frontend-development-utilities.md](mdc:201-frontend-development-utilities.md): Frontend development utilities
- [210-frontend-dashboard-rules.md](mdc:210-frontend-dashboard-rules.md): Teacher dashboard patterns and real-time UI components

## Terminology & Your Interaction Modes
- [100-terminology-and-definitions.md](mdc:100-terminology-and-definitions.md): Shared vocabulary and glossary
- [110-ai-agent-interaction-modes.md](mdc:110-ai-agent-interaction-modes.md): Your general interaction principles
  - [110.1-planning-mode.md](mdc:110.1-planning-mode.md): Your guidelines for task planning
  - [110.2-coding-mode.md](mdc:110.2-coding-mode.md): Your guidelines for code implementation
  - [110.3-testing-mode.md](mdc:110.3-testing-mode.md): Your guidelines for test creation and execution
  - [110.4-debugging-mode.md](mdc:110.4-debugging-mode.md): Your guidelines for debugging
  - [110.5-refactoring-linting-mode.md](mdc:110.5-refactoring-linting-mode.md): Your guidelines for refactoring and linting
  - [111-cloud-vm-execution-standards.md](mdc:111-cloud-vm-execution-standards.md): Claude cloud sandbox workflow and limitations

## Rule Management
- [999-rule-management.md](mdc:999-rule-management.md): Updating or proposing changes to these rules
