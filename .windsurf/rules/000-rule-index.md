---
description: Index of all .cursor/rules/
globs: 
alwaysApply: false
---
# HuleEdu Development Rules: Index

**MUST** adhere to these rules for all development, especially when generating code.

## Core Principles & Architecture
- [010-foundational-principles.mdc](mdc:010-foundational-principles.mdc): Core tenets and mindset
- [015-project-structure-standards.mdc](mdc:015-project-structure-standards.mdc): File and folder organization standards
- [020-architectural-mandates.mdc](mdc:020-architectural-mandates.mdc): DDD, Service Autonomy, Explicit Contracts
- **Service-Specific Architectures (`020.x`)**
  - [020.1-content-service-architecture.mdc](mdc:020.1-content-service-architecture.mdc): Content Service
  - [020.2-spellchecker-service-architecture.mdc](mdc:020.2-spellchecker-service-architecture.mdc): Spell Checker Service
  - [020.3-batch-orchestrator-service-architecture.mdc](mdc:020.3-batch-orchestrator-service-architecture.mdc): Batch Orchestrator Service
  - [020.4-common-core-architecture.mdc](mdc:020.4-common-core-architecture.mdc): Common Core Library
  - [020.5-essay-lifecycle-service-architecture.mdc](mdc:020.5-essay-lifecycle-service-architecture.mdc): Essay Lifecycle Service
  - [020.6-file-service-architecture.mdc](mdc:020.6-file-service-architecture.mdc): File Service
  - [020.7-cj-assessment-service.mdc](mdc:020.7-cj-assessment-service.mdc): CJ Assessment Service
  - [020.8-batch-conductor-service.mdc](mdc:020.8-batch-conductor-service.mdc): Batch Conductor Service
  - [020.9-class-management-service.mdc](mdc:020.9-class-management-service.mdc): Class Management Service
  - [020.10-api-gateway-service.mdc](mdc:020.10-api-gateway-service.mdc): API Gateway Service
  - [020.11-service-libraries-architecture.mdc](mdc:020.11-service-libraries-architecture.mdc): Service Libraries (Kafka, Redis, Logging)
  - [020.12-result-aggregator-service-architecture.mdc](mdc:020.12-result-aggregator-service-architecture.mdc): Result Aggregator Service
  - [020.13-llm-provider-service-architecture.mdc](mdc:020.13-llm-provider-service-architecture.mdc): LLM Provider Service (Centralized provider abstraction with queue resilience)
  - [020.14-websocket-service.mdc](mdc:020.14-websocket-service.mdc): WebSocket Service
  - [020.15-nlp-service-architecture.mdc](mdc:020.15-nlp-service-architecture.mdc): NLP Service (Phase 1 student matching, Phase 2 text analysis)
- [030-event-driven-architecture-eda-standards.mdc](mdc:030-event-driven-architecture-eda-standards.mdc): Event-driven communication standards

## Implementation & Coding Standards
- [040-service-implementation-guidelines.mdc](mdc:040-service-implementation-guidelines.mdc): High-level service implementation principles and stack requirements
- [041-http-service-blueprint.mdc](mdc:041-http-service-blueprint.mdc): HTTP service architecture patterns and Blueprint implementation
- [041-fastapi-integration-patterns.mdc](mdc:041-fastapi-integration-patterns.mdc): FastAPI integration patterns with comprehensive observability and testing
- [042-async-patterns-and-di.mdc](mdc:042-async-patterns-and-di.mdc): Async patterns, protocols, dependency injection, and worker service structure
- [042.1-transactional-outbox-pattern.mdc](mdc:042.1-transactional-outbox-pattern.mdc): Transactional outbox pattern as fallback for Kafka failures
- [042-http-proxy-service-patterns.mdc](mdc:042-http-proxy-service-patterns.mdc): HTTP proxy service patterns for request forwarding, error handling, and observability
- [043-service-configuration-and-logging.mdc](mdc:043-service-configuration-and-logging.mdc): Configuration management and logging standards
- [044-service-debugging-and-troubleshooting.mdc](mdc:044-service-debugging-and-troubleshooting.mdc): CRITICAL debugging priority: service configuration over import patterns
- [044.1-circuit-breaker-observability.mdc](mdc:044.1-circuit-breaker-observability.mdc): Circuit breaker observability patterns and metrics integration standards
- [045-retry-logic.mdc](mdc:045-retry-logic.mdc): Natural retry via idempotency and user-initiated retry patterns
- [046-docker-container-debugging.mdc](mdc:046-docker-container-debugging.mdc): Systematic Docker container discovery and debugging protocol
- [048-structured-error-handling-standards.mdc](mdc:048-structured-error-handling-standards.mdc): Structured error handling patterns and observability integration standards
- [050-python-coding-standards.mdc](mdc:050-python-coding-standards.mdc): Python style, formatting, linting, typing, documentation
- [051-pydantic-v2-standards.mdc](mdc:051-pydantic-v2-standards.mdc): Pydantic v2 usage patterns, serialization, and configuration standards
- [052-event-contract-standards.mdc](mdc:052-event-contract-standards.mdc): Event contract standards and best practices
- [053-sqlalchemy-standards.mdc](mdc:053-sqlalchemy-standards.mdc): Database models and SQLAlchemy patterns
- [055-import-resolution-patterns.mdc](mdc:055-import-resolution-patterns.mdc): Import patterns to avoid module conflicts in monorepo

## Quality, Workflow & Documentation
- [060-data-and-metadata-management.mdc](mdc:060-data-and-metadata-management.mdc): Data models and metadata management standards
- [070-testing-and-quality-assurance.mdc](mdc:070-testing-and-quality-assurance.mdc): Testing strategies (unit, contract, integration, E2E) with Prometheus registry handling
- [070.1-performance-testing-methodology.mdc](mdc:070.1-performance-testing-methodology.mdc): Performance testing methodology and patterns
- [075-test-creation-methodology.mdc](mdc:075-test-creation-methodology.mdc): Systematic test creation methodology for comprehensive, maintainable test coverage following battle-tested patterns
- [075.1-parallel-test-creation-methodology.mdc](mdc:075.1-parallel-test-creation-methodology.mdc): Parallel test creation with mandatory architect validation
- **Observability (071.x)**
  - [071-observability-index.mdc](mdc:071-observability-index.mdc): Observability patterns index
  - [071-observability-core-patterns.mdc](mdc:071-observability-core-patterns.mdc): Core observability patterns
  - [071.1-prometheus-metrics-patterns.mdc](mdc:071.1-prometheus-metrics-patterns.mdc): Prometheus metrics patterns
  - [071.2-jaeger-tracing-patterns.mdc](mdc:071.2-jaeger-tracing-patterns.mdc): Distributed tracing with Jaeger
  - [071.3-grafana-loki-patterns.mdc](mdc:071.3-grafana-loki-patterns.mdc): Grafana dashboards and Loki logs
- [072-grafana-playbook-rules.mdc](mdc:072-grafana-playbook-rules.mdc): Grafana dashboard and alerting playbook
- [073-health-endpoint-implementation.mdc](mdc:073-health-endpoint-implementation.mdc): Health endpoint implementation patterns for HuleEdu services
- [077-service-anti-patterns.mdc](mdc:077-service-anti-patterns.mdc): Common anti-patterns to avoid and their corrections
- [080-repository-workflow-and-tooling.mdc](mdc:080-repository-workflow-and-tooling.mdc): PDM monorepo usage, version control, CI/CD
- [081-pdm-dependency-management.mdc](mdc:081-pdm-dependency-management.mdc): PDM configuration and dependency management standards
- [082-ruff-linting-standards.mdc](mdc:082-ruff-linting-standards.mdc): Ruff linting and formatting configuration
- [083-pdm-standards-2025.mdc](mdc:083-pdm-standards-2025.mdc): Correct modern PDM syntax that must never be questioned
- [084-docker-containerization-standards.mdc](mdc:084-docker-containerization-standards.mdc): Docker containerization patterns, import requirements, and troubleshooting
- [085-docker-compose-v2-command-reference.mdc](mdc:085-docker-compose-v2-command-reference.mdc): Docker Compose v2 command reference
- [086-mypy-configuration-standards.mdc](mdc:086-mypy-configuration-standards.mdc): MyPy configuration and monorepo type checking standards with module conflict resolution
- [090-documentation-standards.mdc](mdc:090-documentation-standards.mdc): Service, contract, and architectural documentation

## Frontend Development Standards
- [200-frontend-core-rules.mdc](mdc:200-frontend-core-rules.mdc): Core frontend architecture patterns (Svelte 5 + Vite, TypeScript, modular design)
- [210-frontend-dashboard-rules.mdc](mdc:210-frontend-dashboard-rules.mdc): Teacher dashboard patterns and real-time UI components

## Terminology & Your Interaction Modes
- [100-terminology-and-definitions.mdc](mdc:100-terminology-and-definitions.mdc): Shared vocabulary and glossary
- [110-ai-agent-interaction-modes.mdc](mdc:110-ai-agent-interaction-modes.mdc): Your general interaction principles
  - [110.1-planning-mode.mdc](mdc:110.1-planning-mode.mdc): Your guidelines for task planning
  - [110.2-coding-mode.mdc](mdc:110.2-coding-mode.mdc): Your guidelines for code implementation
  - [110.3-testing-mode.mdc](mdc:110.3-testing-mode.mdc): Your guidelines for test creation and execution
  - [110.4-debugging-mode.mdc](mdc:110.4-debugging-mode.mdc): Your guidelines for debugging
  - [110.5-refactoring-linting-mode.mdc](mdc:110.5-refactoring-linting-mode.mdc): Your guidelines for refactoring and linting

## Rule Management
- [999-rule-management.mdc](mdc:999-rule-management.mdc): Updating or proposing changes to these rules
