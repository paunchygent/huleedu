---
id: 'refactor-cj-assessment-service-for-compliance'
title: 'Refactor CJ Assessment Service for Compliance'
type: 'task'
status: 'paused'
priority: 'medium'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: 'Agent'
program: 'maintenance'
created: '2025-12-07'
last_updated: '2025-12-07'
related: ['batchmonitor-separation-of-concerns']
labels: ['refactoring', 'compliance', 'technical-debt']
---
# Refactor CJ Assessment Service for Compliance

## Objective
Bring `cj_assessment_service` into full compliance with strict codebase rules (specifically Rule 010: < 500 LoC limit) and improve maintainability by decomposing large modules and test files.

## Context
A recent architectural review confirmed the service is well-aligned with Rule 020.7 but identified specific implementation-level violations. Several core files exceed the hard 500-line limit, creating maintenance bottlenecks. Additionally, "stale" comments and monolithic test files need addressing to maintain high development velocity.

## Plan

### Phase 1: Immediate Cleanup
- [x] Remove stale TODO (`# TODO: To be implemented by Agent Beta`) in `kafka_consumer.py`.
- [ ] Verify validity of Idempotency TODOs in `api/anchor_management.py` and `implementations/content_client_impl.py` (convert to tickets or remove if obsolete).

### Phase 2: Code Decomposition (LoC Compliance)
- [x] **Refactor `cli_admin.py` (721 lines):**
    - Split into a `cli/` package with submodules (e.g., `cli/prompts.py`, `cli/instructions.py`).
- [ ] **Refactor `cj_core_logic/pair_generation.py` (670 lines):**
    - Extract specific matching strategies into a `pair_generation/` package.
- [ ] **Refactor `batch_monitor.py` (647 lines):**
    - Decompose into smaller monitoring task handlers.
- [ ] **Refactor `protocols.py` (642 lines):**
    - Split into `protocols/repositories.py`, `protocols/services.py`, etc.

### Phase 3: Test Suite Optimization
- [ ] **Split `tests/unit/test_batch_preparation_identity_flow.py` (961 lines):**
    - Break down by flow scenarios.
- [ ] **Split `tests/integration/test_retry_mechanisms_integration.py` (897 lines):**
    - Separate basic retry logic from complex circuit breaker scenarios.
- [ ] **Split `tests/unit/test_grade_projector_swedish.py` (888 lines):**
    - Separate projection logic tests from boundary condition tests.

## Success Criteria
- [ ] All Python source files in `services/cj_assessment_service` are strictly < 500 lines of code.
- [ ] `protocols.py` is replaced by a structured package.
- [ ] `pdm run pytest-root services/cj_assessment_service` passes 100%.
- [ ] No stale "Agent Beta" TODOs exist.
