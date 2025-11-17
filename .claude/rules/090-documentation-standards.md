---
description: Read before any updates to documentation and rules
globs: 
alwaysApply: false
---
# 090: Documentation Standards

This rule is **normative** for all documentation in the repository.

## 1. Purpose and Normative References

- Define canonical rules for documentation **location**, **structure**, **content**, **formatting**, **maintenance**, and **review**.
- Provide a stable, machine-enforceable contract for AI agents and developers.

Normative references:

- `documentation/DOCS_STRUCTURE_SPEC.md` – Project documentation layout, taxonomy, and naming.
- `TASKS/_REORGANIZATION_PROPOSAL.md` – TASKS structure, task frontmatter, and enforcement.
- `.claude/rules/000-rule-index.md` – Rule index and rule management.

Where older documentation contradicts this rule or the normative references, it MUST be updated or removed.

## 2. Documentation Taxonomy and Locations

Types of documentation and their canonical locations:

- **Architectural Documentation**
  - High-level overviews, service boundaries, processing flows, DDD boundaries.
  - Location: `documentation/architecture/`, `documentation/decisions/`, and `documentation/overview/`.
- **Service Documentation**
  - Per-service responsibilities, endpoints, events, local setup.
  - Location: `documentation/services/` and `services/<service>/README.md`.
- **Contract Documentation**
  - HTTP APIs, events, schemas, and Pydantic models.
  - Location: code in `libs/common_core/` and generated or curated reference in `documentation/reference/`.
- **Code-Level Documentation**
  - Docstrings, inline comments, and type hints in source files.
  - Location: alongside the code in `services/`, `libs/`, and `scripts/`.
- **Development Rules**
  - Implementation and process rules (this file and related rules).
  - Location: `.claude/rules/` and `.windsurf/rules/`.
- **Task and Programme Documentation**
  - Work items, designs and implementation plans.
  - Location: `TASKS/`, governed by `TASKS/_REORGANIZATION_PROPOSAL.md`.

Any new documentation MUST be placed in the appropriate location above.

## 3. Project Documentation Layout (`documentation/`)

- All project-level documentation (other than service/library READMEs, rules, and TASKS documents) MUST live under `documentation/`.
- `documentation/` MUST follow the taxonomy defined in `documentation/DOCS_STRUCTURE_SPEC.md`:
  - Allowed top-level directories: `overview/`, `architecture/`, `services/`, `operations/`, `how-to/`, `reference/`, `decisions/`, `product/`, `research/`.
  - No additional top-level directories MAY be created without updating `DOCS_STRUCTURE_SPEC.md` and this rule.
- Naming:
  - Files MUST use `.md` extension and MUST NOT contain spaces.
  - New documentation file basenames MUST be `kebab-case` (lowercase words separated by `-`).
  - Existing `SCREAMING_SNAKE_CASE` filenames are permitted for backward compatibility but SHOULD be migrated to `kebab-case` ASAP and always when touched for other changes.
  - Directory names MUST be `kebab-case` or `lower_snake_case`.
- Runbooks:
  - Runbooks under `documentation/operations/` SHOULD include the frontmatter described in `DOCS_STRUCTURE_SPEC.md`.
- Decision records:
  - ADRs MUST live under `documentation/decisions/` and SHOULD follow the filename and frontmatter patterns in `DOCS_STRUCTURE_SPEC.md`.

## 4. Service READMEs

### 4.1 Mandatory Service READMEs

- Every microservice directory under `services/` **MUST** have a `README.md`.
- After any behavior change (APIs, events, core logic), the relevant service `README.md` MUST be reviewed and updated if necessary.

### 4.2 Content Requirements

Each service `README.md` MUST include:

- Concise purpose and responsibility within its bounded context.
- Overview of key domain entities it manages.
- List of events it produces and consumes (with links to contracts where applicable).
- Overview of any HTTP or message-based APIs it exposes.
- How to set up and run the service locally (including key environment variables).
- How to run its tests.

### 4.3 Keep Service READMEs Current

- Service READMEs MUST be updated when service functionality, contracts, or dependencies change.
- Any PR that changes a service in a way that affects its external behavior MUST either:
  - Update the service `README.md`, or
  - Explicitly justify in the PR why no documentation change is required.

## 5. Library Documentation

### 5.1 Mandatory Library READMEs

- Every shared library under `libs/` MUST have a comprehensive `README.md`.
- Library documentation MUST be more detailed than service documentation because of wider reuse.

### 5.2 Library Documentation Requirements

Library `README.md` files MUST include:

- **Overview**: Purpose and design philosophy of the library.
- **Installation/Usage**: Setup instructions and dependency expectations.
- **API Documentation**: Reference for public modules and types:
  - Module purpose and key design decisions.
  - Public functions/classes with signatures and type hints.
  - Parameters, return types, and raised exceptions.
  - Usage examples taken from real services or scripts.
- **Integration Patterns**: Recommended patterns for using the library from services.
- **Testing Guidelines**: How to test code that consumes the library.
- **Migration Guide**: How to migrate from previous versions or patterns when breaking changes occur.
- **Environment Variables / Configuration**: All relevant configuration options.

### 5.3 Module-Level Documentation

- Every library module SHOULD have a module-level docstring.
- All public functions and classes MUST have docstrings consistent with the library README and type hints.
- Examples in docstrings SHOULD be minimal, executable, and aligned with current patterns.

### 5.4 Keeping Library Documentation Current

- Library documentation MUST be updated with any public API changes.
- Usage examples MUST be updated when service usage patterns change.
- Backward-compatibility notes MUST be maintained where relevant.

## 6. Contract Documentation (Pydantic Models and Schemas)

### 6.1 Pydantic Models and Schemas as Source of Truth

- Pydantic models and schemas in the shared contract libraries (for example `libs/common_core/src/common_core/`) ARE the primary source of truth for event and HTTP API contracts.
- Documentation in `documentation/reference/` MUST reference these models rather than duplicating them by hand.

### 6.2 Auto-Generation and Synchronization

- Where feasible, contract documentation SHOULD be auto-generated (for example, OpenAPI from HTTP endpoints, schema docs from Pydantic models).
- When auto-generation is not available, manually curated docs MUST stay aligned with the underlying models; drift is not acceptable.

## 7. Development Rules Documentation

### 7.1 Rules Location

- Development rules MUST reside in `.claude/rules/` (for `.md` rule files) and `.windsurf/rules/` (for `.md` equivalents).
- No other directories may contain canonical development rules.

### 7.2 Rule File Format

- `.claude/rules/` rule files MUST use the `.md` extension with the standard frontmatter (`description`, `globs`, `alwaysApply`).
- `.windsurf/rules/` MUST contain the corresponding `.md` views.

### 7.3 Rule Index

- `000-rule-index.md` MUST be maintained as an up-to-date index of all rule files.
- Any addition, removal, or rename of a rule file MUST be accompanied by an update to `000-rule-index.md`.

## 8. Content Style and Formatting

- Documentation MUST be concise, technical, and free of promotional language.
- Prefer lists, short paragraphs, and explicit examples over long narrative text.
- Use Markdown consistently:
  - `#`/`##`/`###` headings for structure.
  - Bullet lists for enumerations.
  - Fenced code blocks with language hints for commands and code.
- Content SHOULD be optimized for AI tooling:
  - High information density per token.
  - Stable, machine-readable patterns (frontmatter, headings, enums).

## 9. Task Documentation and Compression

- All task and programme documents under `TASKS/` are governed by `TASKS/_REORGANIZATION_PROPOSAL.md`.
- Completed tasks in narrative documents (for example, task collections) MUST be compressed:
  - Use the format: `### Task Name ✅ COMPLETED`.
  - Provide a brief, hyper-technical implementation summary with essential details, code references, and any remaining work.
  - Avoid restating the entire history of the task; rely on Git history and referenced files instead.

## 10. Documentation as Part of Work and Review

- Updating relevant documentation (service READMEs, library READMEs, `documentation/` pages, TASKS, and rules where needed) is a REQUIRED part of any task that changes behavior, contracts, or architecture.
- Task descriptions MUST explicitly include required documentation updates in their implementation plan and success criteria.
- Code reviews MUST include verification that documentation has been updated or an explicit justification that no update is required.

## 11. Maintenance and Drift Control

- Documentation MUST be treated as versioned code:
  - Changes go through the same review process.
  - Large reorganizations MUST be captured as dedicated tasks under `TASKS/`.
- Periodic maintenance tasks SHOULD:
  - Reconcile `documentation/` with actual behavior and service READMEs.
  - Remove or clearly mark obsolete documents.
  - Ensure that rule files, docs specs, and TASKS specs remain consistent.
