# HuleEdu Docs Structure Specification

This document is **normative**. Project documentation MUST comply.

## 1. Purpose

- Define a canonical, machine-enforceable structure for project documentation.
- Provide a predictable layout for AI agents, developers, and tooling.
- Reduce duplication and drift between service docs, architecture docs, and tasks.

## 2. Scope

- Applies to Markdown documentation files under `docs/`.
- Covers:
  - Top-level documentation taxonomy.
  - Allowed subdirectories and their purpose.
  - Recommended frontmatter fields for runbooks and decisions.
- Does **not** cover `TASKS/` (governed by `TASKS/_REORGANIZATION_PROPOSAL.md`) or `.claude/` rule files.

## 3. Top-Level Documentation Taxonomy

The canonical documentation root is `docs/`.

Allowed top-level subdirectories under `docs/`:

- `overview/`
- `architecture/`
- `services/`
- `operations/`
- `how-to/`
- `reference/`
- `decisions/`
- `product/`
- `research/`

No additional top-level documentation directories MAY be created without updating this specification.

### 3.0.1 Root-Level Files

Root-level markdown files (directly under `docs/`) are permitted for:
- This specification (`DOCS_STRUCTURE_SPEC.md`)
- Master navigation/index files (`DOCUMENTATION_INDEX.md`)
- Other cross-cutting specification documents

Root-level files MUST be clearly scoped to documentation-wide concerns, not category-specific content.

### 3.1 Directory Semantics

- `overview/`
  - High-level system description and entrypoints for new developers.
  - Example: system overview, high-level data flow.
- `architecture/`
  - Cross-service architecture, DDD boundaries, diagrams.
  - May include subdirectories such as `events/`, `data-model/`.
- `services/`
  - Per-service summaries and links to `services/<service>/README.md`.
- `operations/`
  - Runbooks, SRE procedures, deployment and environment guides.
- `how-to/`
  - Task-oriented guides answering "How do I accomplish X?".
- `reference/`
  - API, schema, configuration and metrics reference.
- `decisions/`
  - Architecture Decision Records (ADRs) and similar design records.
- `product/`
  - PRDs and product-facing flows.
  - May include subdirectories such as `epics/` for product epic definitions.
- `research/`
  - Design spikes, experiments, and non-normative exploratory documents.

## 4. File and Directory Naming

- Documentation files MUST use the `.md` extension.
- New documentation file basenames (filename without extension) MUST be `kebab-case` (lowercase words separated by `-`) and contain no spaces.
  - Example: `processing-flow-overview.md`.
- Existing `SCREAMING_SNAKE_CASE` filenames (for example, `API_PRODUCTIZATION_PLAN.md`) are permitted for backward compatibility but SHOULD be migrated to `kebab-case` when the file is touched for other changes.
- Directory names under `docs/` and its subdirectories MUST be `kebab-case` or `lower_snake_case`.
- No spaces are allowed in any documentation file or directory names.

## 5. Runbook Frontmatter (operations/)

Runbooks under `docs/operations/` SHOULD include machine-readable frontmatter:

```yaml
---
type: runbook
service: cj_assessment_service      # or "global" for cross-cutting
severity: high                      # low|medium|high|critical
last_reviewed: YYYY-MM-DD
---
```

Tools MAY rely on this metadata to surface relevant runbooks.

## 6. Decision Records (decisions/)

- ADR-style records MUST live under `docs/decisions/`.
- Recommended filename pattern:
  - `NNNN-short-descriptor.md` (e.g. `0001-http-contracts-in-common-core.md`).
- Decision records SHOULD include frontmatter:

```yaml
---
type: decision
id: ADR-0001
status: accepted          # proposed|accepted|superseded|rejected
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
---
```

## 7. Service Documentation (services/)

- `docs/services/` MUST contain one Markdown file per major service or a small set of service grouping files.
- Each file SHOULD:
  - Summarize the service's responsibility and key endpoints.
  - Link to the service's in-repo `services/<service>/README.md`.

## 8. Relationship to TASKS and .claude

- `TASKS/` contains work items and planning documents and is governed by `TASKS/_REORGANIZATION_PROPOSAL.md`.
- `.claude/` and `.windsurf/rules/` contain AI- and tool-specific instructions and MUST NOT be treated as canonical human documentation.
- Where relevant, `docs/` SHOULD link to normative rules in `.windsurf/rules/` rather than duplicating content.

## 9. Enforcement

- New documentation files MUST be placed in one of the allowed top-level directories.
- CI MAY include checks to enforce directory membership and naming patterns, but this is not mandated by this specification.

## 10. Changes to This Specification

- Any changes to the documentation taxonomy or rules in this file MUST be performed via code review and committed with clear rationale.
- Tools and AI agents MUST treat this file as the source of truth for documentation layout.
