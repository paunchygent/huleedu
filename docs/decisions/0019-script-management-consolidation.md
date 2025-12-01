---
type: decision
id: ADR-0019
status: proposed
created: 2025-12-01
last_updated: 2025-12-01
---

# ADR-0019: Script Management Consolidation

## Status
Proposed

## Context
The repository has three script management domains (tasks, docs, rules) with asymmetric tooling:
- **Tasks**: Full tooling (create, validate, index, query)
- **Docs**: Validation only, no creation script, schema hardcoded in validator
- **Rules**: Validation + schema only, no creation script

Code duplication exists across domains:
- `read_front_matter()` duplicated in 5+ scripts
- Validation reporting patterns duplicated across 3 validators
- No unified validation entry point

LLM agents cannot create docs/rules programmatically due to missing creation scripts.

## Decision
Consolidate script management with:

1. **Shared utilities** (`scripts/utils/`): Extract `frontmatter_utils.py` and `validation_reporter.py`
2. **Schema parity**: Create `docs_frontmatter_schema.py`, add `get_allowed_values()` to all schemas for CLI hints
3. **Creation scripts**: Add `new_doc.py` (runbook, adr, epic) and `new_rule.py` with auto-increment IDs
4. **Indexing scripts**: Add `index_docs.py` and `index_rules.py`
5. **Unified validation**: Single `validate_all.py` integrated with `lint-fix`

All creation scripts use single CLI invocation (LLM-compatible, no interactive prompts).

## Consequences

### Positive
- Consistent developer experience across all domains
- LLM agents can create docs/rules programmatically
- Reduced code duplication and maintenance burden
- Single validation entry point for CI/pre-commit

### Negative
- Migration effort for existing scripts
- Temporary code churn during refactor

## References
- Plan: `.claude/plans/keen-growing-umbrella.md`
- Epic: EPIC-007
