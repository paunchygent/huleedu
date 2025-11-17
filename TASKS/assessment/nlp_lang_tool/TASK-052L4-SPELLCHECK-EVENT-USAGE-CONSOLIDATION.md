---
id: 'TASK-052L4-SPELLCHECK-EVENT-USAGE-CONSOLIDATION'
title: 'TASK-052L.4 — Consolidate Spellcheck Result Event Handling'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-20'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-052L.4 — Consolidate Spellcheck Result Event Handling

## Objective

Retire the legacy `SpellcheckResultDataV1`-driven state transition in Essay Lifecycle Service (ELS) and rely solely on the thin `SpellcheckPhaseCompletedV1` plus the rich `SpellcheckResultV1` for state updates and metric propagation. This aligns Spellchecker and ELS with the dual-event pattern used elsewhere and removes redundant event processing paths.

## Motivation

- Current implementation processes both `SpellcheckResultDataV1` and `SpellcheckResultV1`. The former is a legacy rich event needed before `SpellcheckResultV1` existed; the latter now carries full metrics.
- Maintaining both paths increases complexity and risks field drift. Consolidating to thin + rich mirrors the intended architecture and simplifies reasoning.

## Required Reading

- `.claude/rules/020-architectural-mandates.mdc`
- `.claude/rules/042-async-patterns-and-di.mdc`
- `.claude/rules/048-structured-error-handling-standards.mdc`
- `.claude/rules/051-event-contract-standards.mdc`
- `.claude/rules/090-documentation-standards.mdc`
- `TASKS/TASK-052L-feature-pipeline-integration-master.md`
- `TASKS/TASK-052L.1-feature-pipeline-scaffolding.md`

## Scope

1. **ELS spellcheck handlers**
   - Remove dependency on `SpellcheckResultDataV1` for state transitions.
   - Ensure thin event still drives state machine updates.
   - Migrate any metadata extraction (storage references, errors) to use thin event payloads or the rich event as appropriate.

2. **Spellchecker Service event publishing**
   - Confirm rich/thin events carry the data ELS needs post-removal.
   - Update documentation/examples if fields change.

3. **Tests**
   - Update unit/integration tests in `services/essay_lifecycle_service/tests/` and spellchecker service to reflect the new flow.
   - Add regression coverage for metric propagation solely via `SpellcheckResultV1`.

4. **Documentation**
   - Update ELS README/architecture notes to record the updated event-handling pattern.
   - Note the change in `TASK-052L-feature-pipeline-integration-master.md` progress section.

## Acceptance Criteria

- ELS no longer consumes `SpellcheckResultDataV1`; only the thin and rich events are processed.
- State transitions and metadata updates remain functional, with tests covering success/failure paths.
- Spellchecker documentation and code samples reference the consolidated pattern.
- No legacy references to `SpellcheckResultDataV1` remain in active code paths.

## Out of Scope

- Changes to downstream consumers (RAS, analytics) beyond ELS.
- Altering the structure of `SpellcheckResultV1` beyond what is required for ELS.

## Notes

- Coordinate with `TASK-052L.2-feature-bundles-and-tests.md` to ensure metric consumers continue to receive the needed data post-cleanup.
