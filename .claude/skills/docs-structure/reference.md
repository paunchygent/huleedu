# Documentation Structure Maintainer - Detailed Reference

Deep reference for understanding and maintaining documentation and TASKS structure in HuleEdu.

## Table of Contents

1. [Normative Specifications](#normative-specifications)
2. [Project Documentation Workflows](#project-documentation-workflows)
3. [TASKS Workflows](#tasks-workflows)
4. [Automation & Validation Scripts](#automation--validation-scripts)
5. [Best Practices](#best-practices)

---

## Normative Specifications

These are the sources of truth for documentation and TASKS:

- `.claude/rules/090-documentation-standards.md`
  - Canonical rule for documentation location, structure, content, maintenance, and review.
- `docs/DOCS_STRUCTURE_SPEC.md`
  - Defines allowed top-level directories under `docs/` and their semantics.
  - Specifies file/directory naming rules and frontmatter for runbooks/decisions.
- **TASKS structure specification** (referenced from 090)
  - Defines `TASKS/` taxonomy, task frontmatter schema, filename rules, and enforcement.
- `.claude/agents/docs-structure-enforcer.md`
  - Agent behavior for enforcing the structure and naming rules.

As this skill, always align recommendations with these specs.

---

## Project Documentation Workflows

### 1. Creating or Updating Project-Level Docs

1. Determine document purpose:
   - Architecture, service summary, runbook, ADR, how-to, product/PRD, research.
2. Map to directory (from `DOCS_STRUCTURE_SPEC.md`):
   - `architecture/` – cross-service design, DDD boundaries, diagrams.
   - `services/` – per-service summaries and links to `services/<service>/README.md`.
   - `operations/` – runbooks, SRE procedures, environment/deployment guides.
   - `how-to/` – task-oriented guides.
   - `reference/` – APIs, schemas, config, metrics.
   - `decisions/` – ADRs and design records.
3. Enforce naming:
   - New `.md` filenames MUST be `kebab-case` (e.g. `llm-provider-queue-metrics.md`).
   - No spaces in any file or directory names.
4. Suggest frontmatter when applicable:
   - Runbooks (type, service, severity, last_reviewed).
   - Decision records (type, id, status, created, last_updated).
5. Recommend running:
   - `pdm run validate-docs`.

### 2. Adding a New Runbook

- Location: `docs/operations/`.
- Naming: `kebab-case`, e.g. `llm-provider-queue-debugging.md`.
- Frontmatter template:

```yaml
---
type: runbook
service: llm_provider_service  # or "global"
severity: high                 # low|medium|high|critical
last_reviewed: YYYY-MM-DD
---
```

- After creation or edits, suggest:

```bash
pdm run validate-docs
```

### 3. Adding an ADR

- Location: `docs/decisions/`.
- Filename pattern: `NNNN-short-descriptor.md` (e.g. `0005-llm-batching-architecture.md`).
- Frontmatter template:

```yaml
---
type: decision
id: ADR-0005
status: proposed            # proposed|accepted|superseded|rejected
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
---
```

- Encourage: keep the body focused on context, decision, consequences.

---

## TASKS Workflows

TASKS are governed by the canonical TASKS structure specification referenced in rule 090.

### 1. Creating a New Task

Recommended steps:

1. Determine `domain` and (optionally) `program` based on the specification:
   - Domains: `assessment`, `content`, `identity`, `frontend`, `infrastructure`, `security`, `integrations`, `architecture`, `programs`.
2. Use the task management script to scaffold a new task:

```bash
pdm run new-task --domain assessment --title "LLM batching configuration wiring"
```

3. Ensure frontmatter matches the canonical schema (id, title, status, priority, domain, service, owner_team, owner, program, created, last_updated, related, labels).
4. Verify the filename equals the `id` and uses only `A-Z`, `0-9`, `_`, `-`.

### 2. Validating Tasks

Use the validation and indexing scripts regularly:

```bash
pdm run validate-tasks
pdm run index-tasks
```

- `validate_front_matter.py` ensures all tasks conform to the schema and enums.
- `index_tasks.py` regenerates `TASKS/INDEX.md` (if configured) and surfaces misplaced or missing tasks.

### 3. Archiving Tasks

When tasks are finished and ready to be archived:

```bash
python scripts/task_mgmt/archive_task.py --id TASK-XXXX
```

This should:
- Move the task to `TASKS/archive/YYYY/MM/<domain>/`.
- Set `status: archived` and update `last_updated`.

---

## Automation & Validation Scripts

Key scripts to reference and propose:

- **Docs management** (`scripts/docs_mgmt/`):
  - `validate_docs_structure.py`
    - Validates `docs/` against `DOCS_STRUCTURE_SPEC.md`.
    - Supports `--root`, `--verbose`, `--strict`.
  - `migrate_docs_structure.py`
    - Assists with reorganizing existing docs into the canonical structure.

- **Task management** (`scripts/task_mgmt/`):
  - `new_task.py` – scaffolds new tasks with correct frontmatter.
  - `validate_front_matter.py` – validates TASKS frontmatter and enums.
  - `index_tasks.py` – builds/updates task index views.
  - `archive_task.py` – moves tasks into `archive/` and updates status.
  - `migrate_to_spec.py` – assists migrating legacy tasks to the current spec.

As this skill, you do not execute these scripts directly, but you **suggest exact commands** for the user or higher-level agents to run.

---

## Best Practices

1. **Always classify first**: Decide if a change belongs to project docs (`docs/`), tasks (`TASKS/`), service README, or rules.
2. **Respect normative specs**: Never improvise a new directory or naming scheme without updating the specs and rule 090.
3. **Prefer linking over duplication**: For standards and rules, link to `.claude/rules/` / `.windsurf/rules/` instead of copying content.
4. **Keep docs terse and technical**: High information density, minimal narrative.
5. **Encourage validation**: After structural changes, always recommend running the relevant validation scripts.
6. **Surface drift**: When you see files or tasks that clearly violate the specs, call it out and propose a migration plan.
