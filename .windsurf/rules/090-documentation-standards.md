---
trigger: model_decision
description: "Documentation standards. Follow when creating or updating project documentation to ensure clarity, consistency, and maintainability."
---

---

description: Read before any updates to documentation and rules
globs:
alwaysApply: false
---

# 090: Documentation Standards

## 1. Types of Documentation

- **Architectural Documentation**: High-level overviews, service boundaries, data flow diagrams
- **Service Documentation**: READMEs for each service
- **Contract Documentation**: Documentation derived from Pydantic models
- **Code-Level Documentation**: Docstrings and comments
- **Development Rules**: This set of rules (managed via `.cursor/rules/`)

## 2. Service READMEs

### 2.1. Mandatory Service READMEs

- Every microservice directory under `services/` **MUST** have a `README.md` file

### 2.2. Content Requirements

Service READMEs **MUST** include:

- Concise service purpose and responsibility within its bounded context
- Overview of key domain entities it manages
- List of events it produces and consumes
- Overview of any APIs it exposes
- How to set up and run the service locally (including environment variables)
- How to run its tests

### 2.3. Keep READMEs Current

- Service READMEs **MUST** be updated when service functionality, events, or APIs change
- **MUST** propose updates to `README.md` when modifying a service

## 3. Contract Documentation (Pydantic Models)

### 3.1. Pydantic Models as Source of Truth

- Pydantic model definitions in `common/models/` **ARE** the primary source of truth for contract documentation
- **MUST** reference these models when explaining data structures for events or APIs

### 3.2. Auto-Generation

- Explore tools to automatically generate documentation (OpenAPI spec from Quart endpoints, documentation from Pydantic models)

## 4. Development Rules Documentation

### 4.1. Rules in `.cursor/rules/`

- Development rules **SHALL** reside exclusively in `.cursor/rules/` directory

### 4.2. MDC Format

- Rule files **MUST** use `.mdc` file extension

### 4.3. Rule Index

- `000-rule-index.mdc` file **MUST** be maintained as up-to-date index of all rule files
- **MUST** propose update to index when new rule files added or existing ones renamed

## 5. Updating Documentation

### 5.1. Documentation as Part of the Task

- Updating relevant documentation (READMEs, rules index) **MUST** be integral part of any task that changes code or architecture
- **MUST** include documentation updates in task completion steps

### 5.2. Task Documentation Compression

- **MUST** compress completed tasks in task documents to preserve only implementation summary
- **MUST** use hyper-technical language with code examples, no promotional language
- **MUST** maximize information density per token
- Format: `### Task Name ✅ COMPLETED` with implementation summary containing essential technical details, code snippets, and remaining work only
