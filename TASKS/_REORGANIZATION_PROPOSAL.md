# HuleEdu TASKS Structure Specification

> NOTE: The canonical human-facing overview for `TASKS/` lives in `TASKS/README.md`.
> This specification is the machine-oriented, detailed version of the same rules
> and should not diverge from the README.

## 1. Purpose

- Define a canonical, machine-enforceable structure for `TASKS/`.
- Provide a stable schema for AI agents and tooling.
- Eliminate ad-hoc task organization and status handling.

## 2. Scope

- Applies to all Markdown files under `TASKS/`:
  - Includes: task specs, programme hubs, notes directly tied to tasks.
  - Excludes: historical files in `archive/` created before standard adoption.
- Covers:
  - Directory taxonomy.
  - Frontmatter schema and enums.
  - Ownership and lifecycle rules.
  - Archive policy.
  - Validation and CI requirements.

## 3. Directory Taxonomy (Top-Level)

Top-level directories under `TASKS/`:

- `programs/`
- `assessment/`
- `content/`
- `identity/`
- `infrastructure/`
- `security/`
- `integrations/`
- `architecture/`
- `archive/`

No other top-level directories are allowed under `TASKS/`.

> **Note:** Frontend tasks live in `frontend/TASKS/` (not `TASKS/frontend/`). This enables frontend-specific hooks, agents, and tooling when working from the `frontend/` directory.

### 3.1 Belongs-Here Rules

- `programs/`
  - Multi-team or multi-domain initiatives with a hub file.
  - Example: `programs/cj_confidence/HUB.md`.
- `assessment/`
  - CJ, NLP, grading, rubrics, result aggregation, runners.
  - Example: `assessment/nlp_lang_tool/*`.
- `content/`
  - Content Service, prompt references, storage-by-reference tasks.
- `identity/`
  - Identity, auth, JWT, roles, API Gateway auth flows.
  - Example: `identity/TASK-IDENTITY-RS256-JWT-ROLLOUT.md`.
- `infrastructure/`
  - DevOps, CI/CD, Docker/Compose, observability, shared scripts.
- `security/`
  - AppSec, threat models, secrets, audits, compliance tasks.
- `integrations/`
  - External APIs/providers, LLM providers, third-party integrations.
- `architecture/`
  - Cross-domain standards, architectural refactors, system-wide patterns.
- `archive/`
  - Year/month partitioned storage for completed or legacy tasks.

Files MUST be placed according to these rules. Ambiguous items default to the most specific domain (for example, CJ-specific infra goes under `assessment/`, not `infrastructure/`).

## 4. Archive Policy

- Archive path format:
  - `TASKS/archive/YYYY/MM/<domain>/`.
- When archiving a task:
  - Move the file to the appropriate `archive/YYYY/MM/<domain>/` directory.
  - Set `status: archived` in frontmatter.
  - Preserve `id` and `created` values.
- Bulk archive operations MUST NOT change task contents other than path and `status` field.

## 5. Status and Lifecycle

- Status is stored **only** in frontmatter, not in directory names or emojis.
- Allowed values for `status`:
  - `proposed`
  - `in_review`
  - `approved`
  - `blocked`
  - `in_progress`
  - `done`
  - `paused`
  - `archived`
- Any other value is invalid and MUST fail validation.
- When `status` changes, `last_updated` MUST be updated to the current date.

## 6. Frontmatter Schema (Canonical)

Every task or programme-related file under `TASKS/` (excluding this spec and generated indexes) MUST start with YAML frontmatter matching this schema:

```yaml
---
id: task-id-or-hub-id          # Globally unique identifier (kebab-case, matches filename)
title: Short, factual title
type: task                     # One of: task | story | doc | programme
status: proposed               # One of: proposed | in_review | approved | blocked | in_progress | done | paused | archived
priority: medium               # One of: low | medium | high | critical
domain: assessment             # One of: assessment | content | identity | frontend | infrastructure | security | integrations | architecture | programs
service: ""                    # Optional: service name (e.g. cj_assessment_service)
owner_team: agents             # Default: agents (AI + automation). May be another team.
owner: ""                      # Optional: human owner handle (e.g. "@username")
program: ""                    # Optional: program key (e.g. "cj_confidence")
created: YYYY-MM-DD            # Creation date
last_updated: YYYY-MM-DD       # Last meaningful content or status change
related: []                    # Optional: list of related task IDs or doc paths
labels: []                     # Optional: free-form tags
---
```

Additional fields are allowed but MUST NOT change the semantics of the required fields.

## 7. Ownership Rules

- `owner_team` MUST be set.
  - Default: `agents` for AI/automation-owned work.
  - Human teams may override (for example: `platform`, `frontend`, `data`).
- `owner` is optional but SHOULD be set for active, high-priority tasks.

## 8. Programme Hubs

- Programme hubs live under `programs/<name>/HUB.md`.
- Hubs MUST:
  - Use the same frontmatter schema with `type: programme`.
  - Set `program` to the programme key (for example, `cj_confidence`).
  - Link to related tasks across domains via `related` and explicit Markdown links.

## 9. Mapping from Current Structure (One-Time Migration)

The following mappings are REQUIRED for alignment with this standard:

- `TASKS/phase3_cj_confidence/*` → `TASKS/programs/cj_confidence/`
- `TASKS/nlp_lang_tool/*` → `TASKS/assessment/nlp_lang_tool/`
- `TASKS/SVELTE5_CORS_AND_DEV_UTILITIES.md` → `TASKS/frontend/`
- `TASKS/infrastructure/` remains under `TASKS/infrastructure/` and is treated as the canonical infrastructure domain root.

After migration, no new content MAY be added under the old locations.

## 10. Tooling and Enforcement

The following scripts MUST exist and be used for managing tasks. They MUST use only the Python standard library and operate on the schema above.

- `scripts/task_mgmt/new_task.py`
  - Allocate a new `id`.
  - Create a file in the correct domain directory with valid frontmatter.
- `scripts/task_mgmt/validate_front_matter.py`
  - Validate frontmatter for all `TASKS/**/*.md` files (excluding this spec and archived legacy files if configured).
  - Enforce enums for `status`, `priority`, and `domain`.
  - Enforce presence of required fields.
- `scripts/task_mgmt/index_tasks.py`
  - Generate `TASKS/INDEX.md` grouped by domain and status.
- `scripts/task_mgmt/archive_task.py`
  - Move a task to the correct `archive/YYYY/MM/<domain>/` path.
  - Set `status: archived` and update `last_updated`.

### 10.1 Pre-Commit

- A pre-commit hook MUST run `validate_front_matter.py` on staged changes under `TASKS/`.
- Commits that introduce invalid frontmatter MUST be rejected.

### 10.2 CI

- CI MUST run `validate_front_matter.py` over the entire `TASKS/` tree.
- CI MUST fail if:
  - Any required field is missing.
  - Any enum value is invalid.
  - Any file under `TASKS/` lacks frontmatter (excluding explicitly allowed legacy archives, if configured).

## 11. Forbidden Patterns (Do Not Reintroduce)

- Task status indicated only by emojis or inline text without frontmatter.
- Status encoded in directory names (for example, `in_progress/`, `completed/`).
- New top-level directories under `TASKS/` outside the allowed taxonomy.
- Cross-cutting programmes stored only as ad-hoc collections of files without a `programs/<name>/HUB.md` hub.

## 12. Maintenance

- Periodically run `index_tasks.py` to regenerate `TASKS/INDEX.md`.
- Periodically review tasks for:
  - Stale `status` or `last_updated` values.
  - Misplaced files that violate the taxonomy.
- Any changes to this standard MUST be explicit and version-controlled; implicit drift is not allowed.

## 13. Directory and Filename Conventions

- All task files MUST use the `.md` extension.
- Task file basenames (filename without extension) MUST be exactly equal to the `id` in frontmatter.
  - Example: `task-llm-model-family-filtering.md` → `id: task-llm-model-family-filtering`.
- `id` MUST match the following constraints:
  - Characters: `a-z`, `0-9`, `-` only (lowercase kebab-case).
  - MUST start with a lowercase letter or digit.
  - No spaces, uppercase letters, or underscores.
- Programme hub files MUST be named `HUB.md` inside `programs/<name>/` and MUST use `type: programme`.
- Subdirectory names under each domain or `programs/` MUST be `lower_snake_case`.
  - Example: `assessment/nlp_lang_tool/`, `programs/cj_confidence/`.
- No file or directory names under `TASKS/` may contain spaces.
