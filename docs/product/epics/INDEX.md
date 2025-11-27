---
type: epic-catalog
id: epic-index
title: HuleEdu Product Epics
created: 2025-11-27
last_updated: 2025-11-27
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
