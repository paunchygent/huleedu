# HuleEdu Documentation Index

Master navigation across all project documentation.

---

## Quick Navigation

| Purpose | Location | Description |
|---------|----------|-------------|
| **Getting Started** | [docs/overview/](overview/) | Platform overview, onboarding, architecture diagrams |
| **Architecture** | [docs/architecture/](architecture/) + [.agent/rules/](./../.agent/rules/) | System design, processing flows, service boundaries |
| **Operations** | [docs/operations/](operations/) | Runbooks, deployment, troubleshooting |
| **Product** | [docs/product/](product/) | PRD, epics, sprint schedule |
| **Decisions** | [docs/decisions/](decisions/) | Architecture Decision Records (ADRs) |
| **Tasks** | [TASKS/](../TASKS/) | Work tracking, programme hubs |

---

## Overview & Onboarding

| Document | Purpose |
|----------|---------|
| [overview/README.md](overview/README.md) | Platform vision, service landscape, getting started paths |
| [overview/architecture-diagram.md](overview/architecture-diagram.md) | Visual system topology, event bus, database isolation |
| [overview/developer-onboarding.md](overview/developer-onboarding.md) | Step-by-step environment setup, first contribution guide |

---

## Architecture

### Core Architecture Documents

| Document | Purpose |
|----------|---------|
| [architecture/processing-flow-map-and-pipeline-state-management-implementation-plan.md](architecture/processing-flow-map-and-pipeline-state-management-implementation-plan.md) | Complete pipeline state management |
| [architecture/bff-frontend-integration.md](architecture/bff-frontend-integration.md) | Backend-for-frontend integration design |
| [architecture/cj-assessment-service-map.md](architecture/cj-assessment-service-map.md) | CJ assessment domain map |

### Processing Flow Rules (.agent/rules/)

| Rule | Name | Scope |
|------|------|-------|
| [034](../.agent/rules/034-processing-flow-inventory.md) | Processing Flow Inventory | All flows |
| [035](../.agent/rules/035-complete-processing-flow-overview.md) | Complete Processing Overview | End-to-end |
| [036](../.agent/rules/036-phase1-processing-flow.md) | Phase 1: Student Matching | REGULAR batches |
| [037](../.agent/rules/037-phase2-processing-flow.md) | Phase 2: Pipeline Processing | All batches |
| [037.1](../.agent/rules/037.1-cj-assessment-phase-processing-flow.md) | CJ Assessment Phase | Assessment |
| [038](../.agent/rules/038-file-upload-processing-flow.md) | File Upload Flow | Content provisioning |
| [039](../.agent/rules/039-results-retrieval-flow.md) | Results Retrieval | Result aggregation |

---

## Operations Runbooks

| Runbook | Service | Severity |
|---------|---------|----------|
| [01-grafana-playbook.md](operations/01-grafana-playbook.md) | Global | Medium |
| [cj-assessment-runbook.md](operations/cj-assessment-runbook.md) | CJ Assessment | High |
| [eng5-np-runbook.md](operations/eng5-np-runbook.md) | ENG5 Runner | High |
| [ielts-task2-dataset-preparation.md](operations/ielts-task2-dataset-preparation.md) | Assessment | Medium |
| [llm-provider-configuration-hierarchy.md](operations/llm-provider-configuration-hierarchy.md) | LLM Provider | High |
| [ml-nlp-runbook.md](operations/ml-nlp-runbook.md) | Global | Medium |
| [hemma-server-operations-huleedu.md](operations/hemma-server-operations-huleedu.md) | Global | High |
| [gpu-ai-workloads-on-hemma-huleedu.md](operations/gpu-ai-workloads-on-hemma-huleedu.md) | Global | High |

---

## Architecture Decision Records (ADRs)

| ADR | Title | Status |
|-----|-------|--------|
| [0001](decisions/0001-class-management-course-skill-level.md) | Class Management Course/Skill Level | Proposed |
| [0002](decisions/0002-student-record-to-user-account-linking.md) | Student Record to User Account Linking | Proposed |
| [0003](decisions/0003-multi-tenancy-data-isolation-strategy.md) | Multi-Tenancy Data Isolation Strategy | Proposed |
| [0004](decisions/0004-llm-provider-batching-mode-selection.md) | LLM Provider Batching Mode Selection | Proposed |
| [0005](decisions/0005-event-schema-versioning-strategy.md) | Event Schema Versioning Strategy | Proposed |
| [0006](decisions/0006-pipeline-completion-state-management.md) | Pipeline Completion State Management | Proposed |
| [0007](decisions/0007-bff-vs-api-gateway-pattern.md) | BFF vs API Gateway Pattern | Proposed |
| [0011](decisions/0011-ai-feedback-data-aggregation-strategy.md) | AI Feedback Data Aggregation Strategy | Proposed |
| [0012](decisions/0012-ai-feedback-pure-kafka-worker-pattern.md) | AI Feedback Pure Kafka Worker Pattern | Proposed |
| [0013](decisions/0013-ai-feedback-name-resolution-strategy.md) | AI Feedback Name Resolution Strategy | Proposed |
| [0014](decisions/0014-ai-feedback-context-builder-pattern.md) | AI Feedback Context Builder Pattern | Proposed |
| [0015](decisions/0015-cj-assessment-convergence-tuning-strategy.md) | CJ Assessment Convergence Tuning Strategy | Proposed |
| [0016](decisions/0016-cj-assessment-prompt-caching-strategy.md) | CJ Assessment Prompt Caching Strategy | Proposed |
| [0017](decisions/0017-cj-assessment-wave-submission-pattern.md) | CJ Assessment Wave-Based Submission Pattern | Proposed |

---

## Product Documentation

| Document | Purpose |
|----------|---------|
| [product/PRD.md](product/PRD.md) | Product Requirements Document v3.1 |
| [product/sprint-schedule-2025-2026.md](product/sprint-schedule-2025-2026.md) | Sprint calendar (Sprint 1: Dec 2, 2025) |
| [product/epics/INDEX.md](product/epics/INDEX.md) | Epic catalog and status |
| [product/epics/identity-access-epic.md](product/epics/identity-access-epic.md) | EPIC-001: Identity & Access |
| [product/epics/teacher-dashboard-epic.md](product/epics/teacher-dashboard-epic.md) | EPIC-002: Teacher Dashboard |
| [product/epics/ai-feedback-epic.md](product/epics/ai-feedback-epic.md) | EPIC-003: AI Feedback Service |
| [product/epics/cj-assessment-epic.md](product/epics/cj-assessment-epic.md) | EPIC-004: CJ Assessment Feature Scope |
| [product/epics/ml-essay-scoring-pipeline.md](product/epics/ml-essay-scoring-pipeline.md) | EPIC-010: ML Essay Scoring Pipeline |

---

## Reference Documentation

| Document | Purpose |
|----------|---------|
| [reference/ref-tasks-overview.md](reference/ref-tasks-overview.md) | TASKS structure + frontmatter overview |
| [reference/ref-tasks-lifecycle-v2.md](reference/ref-tasks-lifecycle-v2.md) | Story review gate + `done` status |
| [reference/ref-infrastructure-tasks-how-we-track-platform-work.md](reference/ref-infrastructure-tasks-how-we-track-platform-work.md) | What belongs in TASKS/infrastructure + queries |
| [reference/ref-essay-scoring-research-hub.md](reference/ref-essay-scoring-research-hub.md) | Essay scoring navigation hub (runbook → epic → stories → tasks → artifacts) |
| [reference/apis/API_REFERENCE.md](reference/apis/API_REFERENCE.md) | Complete API documentation |
| [reference/apis/WEBSOCKET_API_DOCUMENTATION.md](reference/apis/WEBSOCKET_API_DOCUMENTATION.md) | WebSocket event schemas |
| [reference/apis/api-gateway-openapi.json](reference/apis/api-gateway-openapi.json) | OpenAPI 3.0 specification |

---

## How-To Guides

| Guide | Topic |
|-------|-------|
| [how-to/debugging-with-observability.md](how-to/debugging-with-observability.md) | Debugging with observability stack |
| [how-to/debugging-scenarios-with-tracing.md](how-to/debugging-scenarios-with-tracing.md) | Distributed tracing scenarios |
| [how-to/docker-build-optimization-guide.md](how-to/docker-build-optimization-guide.md) | Docker build performance |
| [how-to/quick-start-observability.md](how-to/quick-start-observability.md) | Observability quick start |
| [how-to/SVELTE_INTEGRATION_GUIDE.md](how-to/SVELTE_INTEGRATION_GUIDE.md) | Svelte frontend integration |

---

## Service READMEs

All services have comprehensive README documentation:

| Service | Path |
|---------|------|
| API Gateway | [services/api_gateway_service/README.md](../services/api_gateway_service/README.md) |
| Batch Conductor | [services/batch_conductor_service/README.md](../services/batch_conductor_service/README.md) |
| Batch Orchestrator | [services/batch_orchestrator_service/README.md](../services/batch_orchestrator_service/README.md) |
| CJ Assessment | [services/cj_assessment_service/README.md](../services/cj_assessment_service/README.md) |
| Class Management | [services/class_management_service/README.md](../services/class_management_service/README.md) |
| Content Service | [services/content_service/README.md](../services/content_service/README.md) |
| Email Service | [services/email_service/README.md](../services/email_service/README.md) |
| Entitlements | [services/entitlements_service/README.md](../services/entitlements_service/README.md) |
| Essay Lifecycle | [services/essay_lifecycle_service/README.md](../services/essay_lifecycle_service/README.md) |
| File Service | [services/file_service/README.md](../services/file_service/README.md) |
| Identity Service | [services/identity_service/README.md](../services/identity_service/README.md) |
| Language Tool | [services/language_tool_service/README.md](../services/language_tool_service/README.md) |
| LLM Provider | [services/llm_provider_service/README.md](../services/llm_provider_service/README.md) |
| NLP Service | [services/nlp_service/README.md](../services/nlp_service/README.md) |
| Result Aggregator | [services/result_aggregator_service/README.md](../services/result_aggregator_service/README.md) |
| Spellchecker | [services/spellchecker_service/README.md](../services/spellchecker_service/README.md) |
| WebSocket Service | [services/websocket_service/README.md](../services/websocket_service/README.md) |

---

## Task Tracking

| Resource | Purpose |
|----------|---------|
| [TASKS/INDEX.md](../TASKS/INDEX.md) | Generated task index by domain/status |
| [TASKS/programs/](../TASKS/programs/) | Programme hubs for multi-team initiatives |
| [docs/reference/ref-tasks-overview.md](reference/ref-tasks-overview.md) | Human-facing TASKS overview (canonical) |
| [.claude/work/session/handoff.md](../.claude/work/session/handoff.md) | Current session context and active work |

---

## AI Agent Documentation

| Resource | Purpose |
|----------|---------|
| [.agent/rules/000-rule-index.md](../.agent/rules/000-rule-index.md) | Master rule index |
| [CLAUDE.md](../CLAUDE.md) | Project instructions for Claude Code |
| [.claude/CLAUDE_STRUCTURE_SPEC.md](../.claude/CLAUDE_STRUCTURE_SPEC.md) | .claude/ directory specification |

---

## Governance Documents

| Document | Purpose |
|----------|---------|
| [DOCS_STRUCTURE_SPEC.md](DOCS_STRUCTURE_SPEC.md) | This directory's normative structure |
| [TASKS/_REORGANIZATION_PROPOSAL.md](../TASKS/_REORGANIZATION_PROPOSAL.md) | Task directory governance |

---

*Last updated: 2026-02-04*
