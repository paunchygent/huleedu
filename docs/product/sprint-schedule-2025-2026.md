---
type: schedule
id: sprint-schedule-2025-2026
created: 2025-11-27
last_updated: 2025-11-27
---

# HuleEdu Sprint Schedule 2025-2026

**Sprint Cadence:** 2-week sprints
**Sprint 1 Start:** December 2, 2025

---

## Current Priority: CJ Assessment POC Validation

The immediate focus is completing the CJ Assessment proof-of-concept validation, including confidence calibration, grade projection, and ENG5 runner validation.

**Active Programme Hub:** `TASKS/programs/cj_confidence/phase3-cj-confidence-hub.md`

---

## Sprint Calendar

| Sprint | Dates | Primary Focus | Key Deliverables |
|--------|-------|---------------|------------------|
| Sprint 1 | Dec 2-13, 2025 | CJ Assessment POC | Confidence calibration, ENG5 runner validation, empirical dataset |
| Sprint 2 | Dec 16-27, 2025 | CJ Hardening + AI Feedback Planning | Batch state fixes, AI Feedback Service architecture review |
| Sprint 3 | Jan 6-17, 2026 | AI Feedback Service Phase 1 | Event contracts, service scaffolding, prompt manager |
| Sprint 4 | Jan 20-31, 2026 | AI Feedback Service Phase 2-3 | Core logic, event processor, integration |
| Sprint 5 | Feb 3-14, 2026 | Frontend Integration Prep | BFF patterns, API Gateway readiness |
| Sprint 6+ | Feb 17+, 2026 | TBD based on POC outcomes | Teacher dashboard, extended pipelines |

---

## Sprint 1: CJ Assessment POC (Dec 2-13, 2025)

### Objectives
Continue Phase 3 CJ Confidence validation work:

1. **Mathematical Validation**
   - Empirical SE vs confidence calibration
   - Bootstrap analysis
   - Implement validation scripts

2. **Grade Scale Enablement**
   - ENG5 runner execute-mode validation
   - Artefact capture per schema
   - Operational playbook updates

3. **Prompt Architecture**
   - Downstream consumer alignment
   - Result Aggregator fixture updates
   - Metrics coverage expansion

### Key Tasks
- `TASKS/programs/cj_confidence/phase3-cj-confidence-hub.md`
- `TASKS/assessment/cj-assessment-code-hardening.md`
- `TASKS/assessment/cj-batch-state-and-completion-fixes.md`
- `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`

### Success Criteria
- [ ] ENG5 runner dry-run + execute artefacts validated
- [ ] Phase 3 empirical dataset ready
- [ ] Confidence recommendation draft completed

---

## Sprint 2: CJ Hardening + AI Feedback Planning (Dec 16-27, 2025)

### Objectives
1. Complete CJ Assessment hardening tasks
2. Review AI Feedback Service implementation plan
3. Prepare for AI Feedback Service development

### Key Tasks
- Complete outstanding CJ batch state fixes
- Review `TASKS/assessment/ai-feedback-service-implementation.md`
- Finalize AI Feedback event contracts

### Note
Holiday break Dec 23-Jan 3 (sprint shortened)

---

## Sprint 3-4: AI Feedback Service (Jan 6-31, 2026)

### Architecture Overview
AI Feedback Service = Data Collector + Prompt Curator + LLM Orchestrator

**Reference:** `TASKS/assessment/ai-feedback-service-implementation.md`

### Sprint 3 Deliverables
- Event contracts (BatchAIFeedbackRequestedV1, BatchAIFeedbackCompletedV1)
- Service scaffolding (Kafka worker, protocols, DI)
- Prompt manager with course-specific templates

### Sprint 4 Deliverables
- Context builder for rich upstream data aggregation
- LLM workflows (feedback + editing)
- Event processor and integration tests

---

## Future Sprints (Tentative)

Sprint timing and focus will be determined based on CJ POC outcomes and business priorities.

**Potential future work:**
- Frontend integration (Vue 3 + Vite teacher dashboard)
- Identity/SSO integration (MS 365 Education for school context)
- Multi-tenancy implementation
- API productization

---

## Planning References

- **CJ Confidence Hub:** `TASKS/programs/cj_confidence/phase3-cj-confidence-hub.md`
- **AI Feedback Plan:** `TASKS/assessment/ai-feedback-service-implementation.md`
- **Active Tasks:** `TASKS/INDEX.md`
- **Session Context:** `.claude/work/session/handoff.md`

---

## Change Log

- **2025-11-27:** Initial schedule created, focused on CJ POC validation
- **2025-11-27:** Revised to reflect actual priorities (was incorrectly assuming infrastructure/frontend focus)
