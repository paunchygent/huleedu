---
id: tasks-readme
title: TASKS README
type: doc
status: archived
priority: medium
domain: architecture
service: ''
owner_team: architecture
owner: ''
program: ''
created: '2025-11-13'
last_updated: '2026-02-01'
related: []
labels: []
---
# HuleEdu TASKS – Canonical Overview

**Archived copy (2026-02-01).** Canonical overview now lives in:

- `docs/reference/ref-tasks-overview.md`

This README was previously the canonical entrypoint for the `TASKS/` tree. It aligns with
the formal structure spec in `_REORGANIZATION_PROPOSAL.md`, the task
frontmatter schema, and the validation scripts under `scripts/task_mgmt/`.

For full machine-readable rules, see:

- `TASKS/_REORGANIZATION_PROPOSAL.md`
- `scripts/schemas/task_schema.py`

Those documents and this README describe the **same** source of truth.

## Lifecycle v2 (reference)

- `docs/reference/ref-tasks-lifecycle-v2.md`
- `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`

## Directory taxonomy

Top-level directories under `TASKS/`:

- `programs/` – multi-team or multi-domain initiatives (programme hubs).
- `assessment/` – CJ, NLP, grading, runners, result aggregation.
- `content/` – Content Service, prompt references, storage-by-reference work.
- `identity/` – Identity, auth, JWT, roles, API Gateway auth flows.
- `frontend/` – SPA integration, dashboards, websockets, ENG5 UI.
- `infrastructure/` – DevOps, CI/CD, Docker/Compose, observability, shared scripts.
- `security/` – AppSec, secrets, audits, compliance.
- `integrations/` – external APIs/providers, LLM providers, SIS, etc.
- `architecture/` – cross-service patterns, refactors, system-wide plans.
- `archive/` – year/month-partitioned storage for archived/legacy tasks.

No other top-level directories are allowed. Ambiguous items default to the most
specific domain (for example, CJ-specific infra lives under `assessment/`).

## Frontmatter and status (single source of truth)

Every task-like file under `TASKS/` (excluding `_REORGANIZATION_PROPOSAL.md`,
indexes, and historical archive exceptions) MUST start with YAML frontmatter
matching the canonical schema:

- `id` – globally unique, lowercase kebab-case.
- `title` – short, factual title.
- `type` – typically `task`, `story`, `doc`, or `programme`.
- `status` – one of:
  - `proposed`, `in_review`, `approved`,
  - `blocked`, `in_progress`, `done`,
  - `paused`, `archived`.
- `priority` – `low` | `medium` | `high` | `critical`.
- `domain` – one of the top-level domains above (including `programs`).
- `service` – optional service name (e.g. `cj_assessment_service`).
- `owner_team` – team that owns the work (`agents` for AI-owned tasks by default).
- `owner` – optional human owner.
- `program` – optional programme key (e.g. `cj_confidence`, `eng5`).
- `created` / `last_updated` – ISO dates (YYYY-MM-DD).
- `related` – list of related task IDs or doc paths.
- `labels` – free-form tags.

Status is defined **only** in frontmatter. Emojis in the body are optional and
must not drift from the frontmatter state.

## Naming conventions

- File basename MUST match `id` exactly:
  - `TASKS/assessment/us-00xy-cleanup-unused-comparison-processing-code-paths.md`
    → `id: 'us-00xy-cleanup-unused-comparison-processing-code-paths'`.
- `id` and filename must:
  - Use lowercase letters, digits, and `-` only.
  - Be kebab-case (no spaces, underscores, or uppercase).
- Programme hubs:
  - Live under `programs/<name>/HUB.md`.
  - Use `type: programme` and set `program` to the programme key.

Legacy patterns like `NNN-DESCRIPTIVE_NAME.md` or all‑caps basenames are
considered historical only; new tasks must follow the `id == filename` rule.

## Task creation and lifecycle

- **Creating tasks**
  - Always use the helper:
    - `pdm run new-task --domain <domain> --title "Title"`
  - This allocates a unique `id`, locates the correct domain directory, and
    scaffolds valid frontmatter.

- **Updating tasks**
  - Update `status` and `last_updated` together when work state changes.
  - Keep `related` pointing at relevant tasks, ADRs, and epics as work evolves.

- **Archiving**
  - Archived tasks live under `TASKS/archive/YYYY/MM/<domain>/`.
  - When archiving:
    - Move the file to the archive path.
    - Set `status: archived`.
    - Preserve `id` and `created`.

## Relationship to epics, ADRs, and PRs

The `TASKS/` tree is the execution layer in the documentation-as-code stack:

- **ADRs** – `docs/decisions/*.md`
  - Capture architectural decisions and long-lived rules.
- **Epics / product docs** – `docs/product/epics/*.md`
  - Describe higher-level goals and user-facing outcomes.
- **Tasks (this directory)** – drive implementation and testing work:
  - Stories like `US-00YA` link back to epics and ADRs in `related`.
  - Tasks reference the code and tests they touch via paths inside the body.
- **PRs** – reference specific task IDs and ADRs in their descriptions.

Validation scripts (`validate_front_matter.py`, `index_tasks.py`) and CI enforce
that the TASKS tree stays consistent with this model. The underlying schema is
centralised in `scripts/schemas/task_schema.py` and imported by these scripts.

## Integration with other docs

Use this directory alongside:

- `.claude/work/session/readme-first.md` – current sprint focus and CJ-critical patterns.
- `.claude/work/session/handoff.md` – per-session active/next work.
- `.agent/rules/` – global development and architecture standards.
- `docs/operations/` – runbooks and operational guides.
- `services/*/README.md` – service-specific patterns and constraints.

In practice:

- Epics/ADRs define the **why** and **constraints**.
- TASKS entries define the **what** and **how** for concrete work.
- CI + scripts keep everything in sync.***
