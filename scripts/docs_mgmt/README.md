# Documentation Management Scripts

## Canonical Topology Commands

Use these commands as the single command surface for topology contracts:

1. `pdm run workstream-topology-scaffold` – scaffold one manifest + hub marker block.
2. `pdm run render-workstream-hubs` – regenerate hub topology blocks from manifests.
3. `pdm run validate-docs` – enforce docs structure + topology invariants.

Avoid ad-hoc/manual manifest and marker edits when these commands can do the work.
No superseded aliases are maintained for topology scaffolding.

## validate_docs_structure.py

Validates documentation structure compliance with `docs/DOCS_STRUCTURE_SPEC.md`.

### Usage

```bash
# Validate with default root (`docs/`)
python scripts/docs_mgmt/validate_docs_structure.py

# Validate with custom root
python scripts/docs_mgmt/validate_docs_structure.py --root /path/to/docs

# Show all validated files
python scripts/docs_mgmt/validate_docs_structure.py --verbose

# Treat warnings as errors
python scripts/docs_mgmt/validate_docs_structure.py --strict
```

### What it validates

1. **Top-level directory taxonomy (§3)**: Only allowed directories exist under `docs/`
2. **File naming (§4)**: Files use `.md` extension and kebab-case or SCREAMING_SNAKE_CASE
3. **Directory naming (§4)**: Directories use kebab-case or lower_snake_case
4. **No spaces (§4)**: No spaces in any file or directory names
5. **Runbook frontmatter (§5)**: Files in `operations/` have proper frontmatter (warnings)
6. **Decision frontmatter (§6)**: Files in `decisions/` have proper frontmatter and naming (warnings)

## validate_workstream_topology.py

Validates codified workstream topology manifests and hub link integrity.

### Usage

```bash
# Validate manifests + required backlinks
pdm run validate-docs

# Also validate generated hub sections are current
python -m scripts.docs_mgmt.validate_workstream_topology --check-hubs --verbose
```

## workstream_topology_scaffold.py

Scaffolds a strict topology manifest and updates hub markers in one command.

### Usage

```bash
pdm run workstream-topology-scaffold \
  --id tasks-lifecycle-v2 \
  --title "TASKS lifecycle v2 governance" \
  --hub docs/reference/ref-tasks-lifecycle-v2.md \
  --runbook docs/reference/ref-tasks-overview.md \
  --epic docs/product/epics/dev-tooling-script-consolidation-epic.md \
  --decision docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md \
  --gate-task TASKS/architecture/align-tasks-and-docs-lifecycle-v2.md \
  --research docs/research/research-tasks-lifecycle-v2-governance-and-topology-notes.md \
  --active-task TASKS/architecture/align-tasks-and-docs-lifecycle-v2.md \
  --review-record docs/product/reviews/review-example-story-approval.md \
  --evidence-root TASKS \
  --evidence-root docs/product/reviews
```

## render_workstream_hubs.py

Renders generated topology blocks into hub documents from manifests under
`scripts/docs_mgmt/workstream_topology/`.

### Usage

```bash
# Render/update generated hub sections
pdm run render-workstream-hubs

# Check-only mode (non-zero if stale)
python -m scripts.docs_mgmt.render_workstream_hubs --check --verbose
```

### Exit codes

- `0`: Validation passed (warnings ok unless --strict)
- `1`: Validation failed (errors found, or warnings in --strict mode)
- `2`: Usage error (invalid arguments, missing root directory)

### Examples

```bash
# Check for errors only
python scripts/docs_mgmt/validate_docs_structure.py

# Check everything including warnings
python scripts/docs_mgmt/validate_docs_structure.py --verbose

# Enforce warnings as errors in CI
python scripts/docs_mgmt/validate_docs_structure.py --strict
```
