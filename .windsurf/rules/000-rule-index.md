---
description: "Central index of all HuleEdu development rules. Always check here first to understand the complete rule set and their relationships."
globs:
alwaysApply: true
---
===
# HuleEdu Development Rules: Index

This index lists all development rules for the HuleEdu microservice ecosystem. You **MUST** adhere to these rules for all development, especially when generating code.

## Core Principles & Architecture
- [010-foundational-principles.md](mdc:010-foundational-principles.md): Core tenets and mindset.
- [015-project-structure-standards.md](mdc:015-project-structure-standards.md): File and folder organization standards.
- [020-architectural-mandates.md](mdc:020-architectural-mandates.md): DDD, Service Autonomy, Explicit Contracts.
- [021-content-service-architecture.md](mdc:021-content-service-architecture.md): Content Service architecture and implementation.
- [022-spell-checker-service-architecture.md](mdc:022-spell-checker-service-architecture.md): Spell Checker Service architecture and implementation.
- [023-batch-service-architecture.md](mdc:023-batch-service-architecture.md): Batch Service architecture and implementation.
- [024-common-core-architecture.md](mdc:024-common-core-architecture.md): Common Core package architecture and implementation.
- [030-event-driven-architecture-eda-standards.md](mdc:030-event-driven-architecture-eda-standards.md): Event-driven communication standards.

## Implementation & Coding Standards
- [040-service-implementation-guidelines.md](mdc:040-service-implementation-guidelines.md): Microservice implementation (Quart, async, state, logging).
- [050-python-coding-standards.md](mdc:050-python-coding-standards.md): Python style, formatting, linting, typing, documentation.
- [051-pydantic-v2-standards.md](mdc:051-pydantic-v2-standards.md): Pydantic v2 usage patterns, serialization, and configuration standards.
- [060-data-and-metadata-management.md](mdc:060-data-and-metadata-management.md): Data/metadata definition, storage, access, common models.

## Quality, Workflow & Documentation
- [070-testing-and-quality-assurance.md](mdc:070-testing-and-quality-assurance.md): Testing strategies (unit, contract, integration, E2E).
- [080-repository-workflow-and-tooling.md](mdc:080-repository-workflow-and-tooling.md): PDM monorepo usage, version control, CI/CD.
- [081-pdm-dependency-management.md](mdc:081-pdm-dependency-management.md): PDM configuration and dependency management standards.
- [082-ruff-linting-standards.md](mdc:082-ruff-linting-standards.md): Ruff linting and formatting configuration standards.
- [090-documentation-standards.md](mdc:090-documentation-standards.md): Service, contract, and architectural documentation.

## Terminology & Your Interaction Modes
- [100-terminology-and-definitions.md](mdc:100-terminology-and-definitions.md): Shared vocabulary and glossary.
- [110-ai-agent-interaction-modes.md](mdc:110-ai-agent-interaction-modes.md): Your general interaction principles.
  - [110.1-planning-mode.md](mdc:110.1-planning-mode.md): Your guidelines for task planning.
  - [110.2-coding-mode.md](mdc:110.2-coding-mode.md): Your guidelines for code implementation.
  - [110.3-testing-mode.md](mdc:110.3-testing-mode.md): Your guidelines for test creation and execution.
  - [110.4-debugging-mode.md](mdc:110.4-debugging-mode.md): Your guidelines for debugging.
  - [110.5-refactoring-linting-mode.md](mdc:110.5-refactoring-linting-mode.md): Your guidelines for refactoring and linting.

## Rule Management
- [999-rule-management.md](mdc:999-rule-management.md): Updating or proposing changes to these rules.
===
