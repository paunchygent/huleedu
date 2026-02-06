# Documentation Structure Skill Examples

Real-world style scenarios for using the Documentation Structure Maintainer skill.

**See also**:
- **SKILL.md**: Quick reference and activation criteria
- **reference.md**: Detailed workflows, scripts, and best practices

---

## Example 1: New Runbook for LLM Provider Queue Issues

**Objective**: Document a runbook for diagnosing `llm_provider_queue_depth` anomalies.

**User request**:
> "I need a runbook for debugging when the LLM provider queue depth spikes. Where should it go and what should it look like?"

**Skill reasoning**:
- Purpose: operational procedure → `docs/operations/`.
- Filename: `llm-provider-queue-depth-debugging.md` (kebab-case).
- Frontmatter: runbook schema.

**Suggested structure**:

- Path: `docs/operations/llm-provider-queue-depth-debugging.md`
- Frontmatter:

```yaml
---
type: runbook
service: llm_provider_service
severity: high
last_reviewed: 2025-11-17
---
```

- Body sections:
  - Symptoms
  - Quick Checks (Prometheus, Grafana, logs)
  - Detailed Investigation Steps
  - Rollback / Mitigation

**Suggested validation command**:

```bash
pdm run validate-docs
```

---

## Example 2: New ADR for HTTP Contracts in common_core

**Objective**: Record the decision to move HTTP API contracts into `common_core`.

**User request**:
> "We finalized the decision to centralize HTTP API contracts in common_core. Help me document this ADR correctly."

**Skill reasoning**:
- Type: architecture decision → `docs/decisions/`.
- Filename: `0006-http-contracts-in-common-core.md`.
- Frontmatter: ADR schema.

**Suggested structure**:

- Path: `docs/decisions/0006-http-contracts-in-common-core.md`
- Frontmatter:

```yaml
---
type: decision
id: ADR-0006
status: accepted
created: 2025-11-17
last_updated: 2025-11-17
---
```

- Body sections:
  - Context
  - Decision
  - Consequences
  - Related tasks / migrations

**Suggested validation command**:

```bash
pdm run validate-docs
```

---

## Example 3: Creating a New TASK for LLM Batching Configuration

**Objective**: Create a new TASK to implement CJ → LPS batching configuration wiring.

**User request**:
> "Create a new task doc for wiring up CJ LLM batching configuration to the provider." 

**Skill reasoning**:
- Domain: `assessment` (CJ-specific behavior).
- Likely program: e.g. `cj_confidence` if part of that initiative.
- Use task management script to ensure correct frontmatter and filename.

**Suggested workflow**:

1. Generate new task via script:

```bash
pdm run new-task \
  --domain assessment \
  --title "LLM batching configuration wiring" \
  --program cj_confidence
```

2. Verify the created file:
   - Lives under `TASKS/assessment/` (or appropriate domain path as defined by the TASKS spec).
   - Filename equals `id` and uses only `A-Z`, `0-9`, `_`, `-`.
   - Frontmatter fields match the canonical schema.

3. Run validation:

```bash
pdm run validate-tasks
pdm run index-tasks
```

---

## Example 4: Normalizing Legacy Documentation

**Objective**: Migrate older docs into the canonical `docs/` layout.

**User request**:
> "We have some old architecture docs scattered in legacy locations. Help me normalize them under docs/."

**Skill reasoning**:
- Use `docs/DOCS_STRUCTURE_SPEC.md` to classify each file.
- Propose a mapping plan (e.g. `docs/OPERATIONS/` → `docs/operations/`, `PRD:s/` → `docs/product/`).
- Use `migrate_docs_structure.py` where appropriate, then validate.

**Suggested workflow**:

1. Build a mapping table: old path → new path.
2. For each doc, decide target directory based on semantics.
3. Propose `git mv` operations (for the user) and filename normalizations to kebab-case.
4. After moves, validate:

```bash
pdm run validate-docs
```

5. Fix any reported violations (naming, missing frontmatter) and rerun.

---

## Example 5: CI/Pre-Commit Enforcement Planning

**Objective**: Plan enforcement of docs and TASKS rules in CI and pre-commit.

**User request**:
> "How should we wire up validation so docs and tasks stay compliant automatically?" 

**Skill reasoning**:
- Use docs validation for `docs/`.
- Use task validation for `TASKS/`.
- Integrate both into pre-commit and CI.

**Suggested configuration outline** (high-level):

- **Pre-commit**:
  - Run `pdm run validate-docs` on changed docs.
  - Run `pdm run validate-tasks` on changed files under `TASKS/`.

- **CI pipeline step**:

```bash
pdm run validate-docs
pdm run validate-tasks
```

- Treat non-zero exit codes as build failures.

This gives agents a concrete pattern to recommend whenever users mention "enforcing" documentation or TASKS rules.
