---
type: epic-catalog
id: epic-index
title: HuleEdu Product Epics
created: 2025-11-27
last_updated: 2025-11-30
---

# HuleEdu Product Epics

Epic catalog for tracking major product initiatives.

## Active Epics

| Epic ID | Title | Status | Priority | Notes |
|---------|-------|--------|----------|-------|
| EPIC-001 | Identity & Access | draft | high | School admin scope |
| EPIC-002 | Teacher Dashboard | draft | high | CJ results display |
| EPIC-003 | AI Feedback Service | draft | high | From implementation plan |
| EPIC-004 | CJ Assessment | draft | high | From runbook extraction |
| EPIC-005 | CJ Stability & Reliability | draft | high | Callback flow, completion gating |
| EPIC-006 | Grade Projection Quality | draft | high | Anchor calibration, confidence |
| EPIC-007 | Developer Experience & Testing | draft | medium | Test helpers, dev runner |
| EPIC-008 | ENG5 Runner Refactor & Prompt Tuning | draft | medium | ENG5 runner handlers + prompt harness |
| EPIC-009 | Observability & Metrics Alignment | draft | medium | Prometheus config, DatabaseMetrics, dashboards |

## Epic Status Legend

- **draft**: Epic defined but needs refinement
- **planned**: Epic ready for sprint planning
- **in_progress**: Active development
- **completed**: All acceptance criteria met

## Epic Overview

### EPIC-001: Identity & Access Management

**Status**: Draft

**Scope**:
- School admin role definition
- Teacher role and basic RBAC
- CJ Assessment flow permissions
- Basic account validation

**Out of Scope**: Enterprise OIDC/SSO, district admin, SAML, multi-tenant orchestration

**File**: [identity-access-epic.md](identity-access-epic.md)

---

### EPIC-002: Teacher Dashboard

**Status**: Draft

**Scope**:
- CJ Assessment result display
- Batch submission and file upload
- Real-time status via WebSocket
- Results viewing from RAS

**Out of Scope**: LMS integration, full analytics, mobile UI

**File**: [teacher-dashboard-epic.md](teacher-dashboard-epic.md)

---

### EPIC-003: AI Feedback Service

**Status**: Draft

**Scope**:
- Pure Kafka worker service
- Context-aware feedback generation
- Edited essay generation
- Data aggregation via RAS

**Out of Scope**: Grammar analysis (NLP Service), LLM API management

**File**: [ai-feedback-epic.md](ai-feedback-epic.md)

**Related ADRs**: ADR-0011, ADR-0012, ADR-0013, ADR-0014

---

### EPIC-004: CJ Assessment Feature Scope

**Status**: Draft

**Scope**:
- GUEST and REGULAR batch flows
- Convergence tuning
- Prompt caching optimization
- Wave-based submission

**Out of Scope**: Grade projections, anchor management

**File**: [cj-assessment-epic.md](cj-assessment-epic.md)

**Related ADRs**: ADR-0015, ADR-0016, ADR-0017

---

### EPIC-005: CJ Stability & Reliability

**Status**: Draft

**Scope**:
- Callback-driven continuation and safe completion gating
- Score stability semantics and early stopping
- Retry semantics and end-of-batch fairness
- Convergence tests for iterative/bundled mode

**Out of Scope**: Grade projection quality (EPIC-006), developer tooling (EPIC-007)

**File**: [cj-stability-and-reliability.md](cj-stability-and-reliability.md)

**Related ADRs**: ADR-0015

---

### EPIC-006: Grade Projection Quality & Anchors

**Status**: Draft

**Scope**:
- Anchor calibration semantics and isotonic constraints
- Robust projection with missing/degenerate anchors
- Confidence semantics and statistics

**Out of Scope**: Stability/reliability (EPIC-005), developer tooling (EPIC-007)

**File**: [cj-grade-projection-quality.md](cj-grade-projection-quality.md)

---

### EPIC-007: Developer Experience & Testing

**Status**: Draft

**Scope**:
- Matching strategy test helpers and fairness coverage
- Documentation for matching, budgets, stability cadence
- Dev runner and Kafka wrapper for CJ workflows
- Test architecture guardrails and strategy extension guide

**Out of Scope**: Stability/reliability (EPIC-005), grade projection quality (EPIC-006)

**File**: [cj-developer-experience-and-testing.md](cj-developer-experience-and-testing.md)

---

### EPIC-008: ENG5 NP Runner Refactor & Prompt Tuning

**Status**: Draft

**Scope**:
- Refactor ENG5 NP runner CLI into handler-based architecture.
- Introduce `anchor-align-test` mode and alignment reporting.
- Provide tests and runbooks for ENG5 prompt-tuning experiments.

**Out of Scope**: Core CJ convergence/projection algorithms (EPIC-005/EPIC-006).

**File**: [eng5-runner-refactor-and-prompt-tuning-epic.md](eng5-runner-refactor-and-prompt-tuning-epic.md)

---

### EPIC-009: Observability & Metrics Alignment

**Status**: Draft

**Scope**:
- Add missing services to Prometheus scraping configuration
- Add DatabaseMetrics to services with databases that lack instrumentation
- Enhance Grafana dashboards for full service coverage

**Out of Scope**: SERVICE_NAME standardization (separate infrastructure task), production AlertManager configuration

**File**: [observability-metrics-alignment-epic.md](observability-metrics-alignment-epic.md)
