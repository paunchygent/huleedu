---
type: epic
id: EPIC-004
title: CJ Assessment Feature Scope
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-27
last_updated: 2025-11-27
---

# EPIC-004: CJ Assessment Feature Scope

## Summary

Define and stabilize Comparative Judgment assessment features including convergence tuning, prompt caching optimization, and wave-based submission patterns. This epic covers the product features of the existing CJ Assessment Service implementation.

**Business Value**: Cost-effective essay ranking through adaptive convergence and caching.

**Scope Boundaries**:
- **In Scope**: Convergence tuning, prompt caching, wave submission, GUEST/REGULAR batch flows
- **Out of Scope**: Grade projections (future), anchor management (future)

## User Stories

### US-004.1: GUEST Batch Assessment
**As a** teacher with essays not in a class roster
**I want to** upload essays and run CJ assessment without class association
**So that** I can quickly evaluate relative quality using filenames for identification.

**Acceptance Criteria**:
- [ ] Batch registration succeeds without class_id
- [ ] Pipeline executes spellcheck → CJ without student matching
- [ ] Results display filename-based identification
- [ ] Rankings returned with essay scores

### US-004.2: REGULAR Batch Assessment
**As a** teacher with a class roster
**I want to** upload essays and have them matched to enrolled students
**So that** results show student names and integrate with gradebook.

**Acceptance Criteria**:
- [ ] Essays matched to students via Class Management Service
- [ ] Results display student names (not just filenames)
- [ ] Pipeline includes student matching phase before CJ

### US-004.3: Adaptive Convergence
**As a** system operator
**I want** CJ to stop early when scores stabilize
**So that** we minimize LLM costs without sacrificing ranking quality.

**Acceptance Criteria**:
- [ ] SCORE_STABILITY_THRESHOLD configurable per environment
- [ ] Stability checked after each round of comparisons
- [ ] Early stop when max score change below threshold
- [ ] Metrics track iterations and convergence patterns

## Technical Architecture

### Data Flows
```
GUEST: Upload → Spellcheck → CJ Assessment → Rankings (filename-identified)
REGULAR: Upload → Student Matching → Spellcheck → CJ Assessment → Rankings (student-identified)
```

### Key Services
- **CJ Assessment Service**: `services/cj_assessment_service/`
- **LLM Provider Service**: `services/llm_provider_service/`
- **Essay Lifecycle Service**: `services/essay_lifecycle_service/`
- **Batch Orchestrator**: `services/batch_orchestrator_service/`

### Configuration Points
- Convergence: SCORE_STABILITY_THRESHOLD, MIN_COMPARISONS_FOR_STABILITY_CHECK
- Caching: PROMPT_CACHE_TTL_SECONDS, ENABLE_PROMPT_CACHING
- Submission: wave size emerges from batch size, matching strategy, and CJ comparison budget; stability thresholds and caps decide when to stop.

## Related ADRs
- ADR-0015: CJ Assessment Convergence Tuning Strategy
- ADR-0016: CJ Assessment Prompt Caching Strategy
- ADR-0017: CJ Assessment Wave-Based Submission Pattern

## Dependencies
- LLM Provider Service operational
- Spellchecker Service operational
- Essay Lifecycle Service orchestration

## Notes
- Runbook: docs/operations/cj-assessment-runbook.md
- Grade projections require assignment_id and anchors (future scope)
- Current focus: stabilize existing implementation
