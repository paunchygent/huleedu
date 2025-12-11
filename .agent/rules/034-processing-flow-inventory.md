---
id: "034-processing-flow-inventory"
type: "workflow"
scope: "cross-service"
title: "Processing Flow Inventory"
category: "architecture"
priority: "high"
applies_to: "all"
created: "2025-11-27"
last_updated: "2025-11-27"
---

# Processing Flow Inventory

**Purpose:** Complete inventory of all cross-cutting processing flows in HuleEdu
**Status:** Living document - update when flows change

## Flow Inventory Summary

| Flow ID | Name | Documentation | Status | Priority |
|---------|------|---------------|--------|----------|
| FLOW-01 | Complete Processing Overview | 035-complete-processing-flow-overview.md | Documented | Validate |
| FLOW-02 | Phase 1: Student Matching | 036-phase1-processing-flow.md | Documented | Validate |
| FLOW-03 | Phase 2: Pipeline Processing | 037-phase2-processing-flow.md | Documented | Validate |
| FLOW-04 | CJ Assessment Phase | 037.1-cj-assessment-phase-processing-flow.md | Documented | Validate |
| FLOW-05 | File Upload → Essay Slot | None | **UNDOCUMENTED** | HIGH |
| FLOW-06 | Results Retrieval & Aggregation | None | **UNDOCUMENTED** | HIGH |
| FLOW-07 | Entitlements Credit Flow | None | **UNDOCUMENTED** | MEDIUM |
| FLOW-08 | LLM Provider Request Flow | 020.13 (partial) | Partial | MEDIUM |
| FLOW-09 | Error Handling & Validation | None | **UNDOCUMENTED** | MEDIUM |
| FLOW-10 | WebSocket Real-Time Updates | None | **UNDOCUMENTED** | LOW |
| FLOW-11 | Notification Flow | None | **UNDOCUMENTED** | LOW |
| FLOW-12 | Class Management Flow | None | **UNDOCUMENTED** | LOW |

---

## Documented Flows (Require Validation)

### FLOW-01: Complete Processing Overview
- **Rule:** `.agent/rules/035-complete-processing-flow-overview.md`
- **Last Updated:** 2025-11-17
- **Validation Notes:**
  - [ ] Verify assignment_id propagation reflects recent Phase A/B work
  - [ ] Confirm original_file_name field addition to EssaySlotAssignedV1
  - [ ] Validate GUEST vs REGULAR flow diagrams against current implementation

### FLOW-02: Phase 1 Student Matching
- **Rule:** `.agent/rules/036-phase1-processing-flow.md`
- **Last Updated:** Check file
- **Validation Notes:**
  - [ ] Verify BatchStudentMatchingRequestedV1 fields match current event
  - [ ] Confirm NLP → Class Management handoff
  - [ ] Validate 24h timeout auto-confirmation behavior

### FLOW-03: Phase 2 Pipeline Processing
- **Rule:** `.agent/rules/037-phase2-processing-flow.md`
- **Last Updated:** Check file
- **Validation Notes:**
  - [ ] Verify ClientBatchPipelineRequestV1 usage
  - [ ] Confirm multi-pipeline support via BatchPipelineCompletedV1
  - [ ] Validate PhaseSkippedV1 event handling

### FLOW-04: CJ Assessment Phase
- **Rule:** `.agent/rules/037.1-cj-assessment-phase-processing-flow.md`
- **Last Updated:** Check file
- **Validation Notes:**
  - [ ] Verify ELS_CJAssessmentRequestV1 includes assignment_id field
  - [ ] Confirm LLMConfigOverrides structure
  - [ ] Validate AssessmentResultV1 → RAS integration

---

## Undocumented Flows (HIGH Priority)

### FLOW-05: File Upload → Essay Slot Assignment

**Services:** File Service → ELS → BOS

**Event Sequence:**
```
Client Upload → File Service
    ↓
EssayContentProvisionedV1 (File Service → ELS)
    - entity_id: batch_id
    - file_upload_id: upload tracking
    - original_file_name: filename for display
    - raw_file_storage_id: blob reference
    - text_storage_id: extracted text reference
    ↓
ELS assigns content to essay slot
    ↓
EssaySlotAssignedV1 (ELS publishes)
    - batch_id, essay_id, file_upload_id
    - text_storage_id, original_file_name
    ↓
When all slots filled:
BatchContentProvisioningCompletedV1 (ELS → BOS)
    - batch_id, provisioned_count, expected_count
    - essays_for_processing: list[EssayProcessingInputRefV1]
```

**Failure Path:**
```
Validation fails in File Service
    ↓
EssayValidationFailedV1 (File Service → ELS)
    - file_upload_id, validation_error_code
    - validation_error_detail: ErrorDetail
```

**Documentation Needed:** `.agent/rules/038-file-upload-processing-flow.md`

---

### FLOW-06: Results Retrieval & Aggregation

**Services:** CJ Assessment → RAS → API Gateway → Client

**Event Sequence:**
```
CJ Assessment completes
    ↓
CJAssessmentCompletedV1 (CJ → ELS, thin event)
    - batch_id, cj_assessment_job_id
    - processing_summary (counts only)
    ↓
AssessmentResultV1 (CJ → RAS, rich event)
    - batch_id, assignment_id
    - essay_results: list[EssayResultV1]
    - assessment_metadata
    ↓
RAS stores and aggregates
    ↓
BatchResultsReadyV1 (RAS → notifications)
    - batch_id, user_id
    - phase_results summary
    ↓
Client queries RAS API for detailed results
```

**Query Patterns:**
- `/results/batch/{batch_id}` - All results for batch
- `/results/essay/{essay_id}` - Single essay result
- `/results/batch/{batch_id}/summary` - Aggregated metrics

**Documentation Needed:** `.agent/rules/039-results-retrieval-flow.md`

---

### FLOW-07: Entitlements Credit Flow

**Services:** BOS → Entitlements Service → Pipeline Services

**Event Sequence:**
```
Pipeline Request arrives at BOS
    ↓
BOS calls Entitlements Service (HTTP)
    - user_id, org_id
    - requested_pipeline
    - essay_count
    ↓
Entitlements checks credits
    ↓
[SUFFICIENT] → Pipeline proceeds
    ↓
[INSUFFICIENT] → PipelineDeniedV1 (BOS publishes)
    - denial_reason: 'insufficient_credits'
    - required_credits, available_credits
    - resource_breakdown
    ↓
After pipeline completion:
Credit deduction (implementation TBD)
```

**Documentation Needed:** `.agent/rules/040-entitlements-credit-flow.md`

---

## Undocumented Flows (MEDIUM Priority)

### FLOW-08: LLM Provider Request Flow

**Partial Documentation:** `.agent/rules/020.13-llm-provider-service-architecture.md`

**Event Sequence:**
```
CJ Assessment needs comparison
    ↓
Request queued in LLM Provider Service
    ↓
LLMRequestStartedV1 (internal tracking)
    ↓
Provider processes request
    ↓
LLMComparisonResultV1 (callback to CJ)
    - winner, justification, confidence
    - token_usage, cost_estimate
    - OR error_detail if failed
    ↓
LLMCostTrackingV1 (to billing/metrics)
```

**Gap:** Need dedicated flow rule covering queue management, retry, circuit breaker

### FLOW-09: Error Handling & Validation Flow

**Event Sequence:**
```
Validation failure in any service
    ↓
Service-specific failure event:
    - EssayValidationFailedV1 (File Service)
    - CJAssessmentFailedV1 (CJ Service)
    ↓
Aggregated at batch level:
BatchValidationErrorsV1
    - failed_essays: list[EssayValidationError]
    - error_summary: BatchErrorSummary
```

**Pattern:** Structured error handling via ErrorDetail model
**Reference:** `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/`

---

## Undocumented Flows (LOW Priority)

### FLOW-10: WebSocket Real-Time Updates
- WebSocket Manager pushes status updates to connected clients
- Triggered by batch state transitions
- **Events:** BatchStateChangedV1, ProcessingProgressV1

### FLOW-11: Notification Flow
- Teacher notifications for batch completion
- Email and in-app notifications
- **Services:** Notification Service, Email Service

### FLOW-12: Class Management Flow
- Student roster management
- Match suggestion storage and confirmation
- **Events:** StudentAssociationsConfirmedV1

---

## Event Source Files

| Category | Source File |
|----------|-------------|
| Batch Coordination | `events/batch_coordination_events.py` |
| File Management | `events/file_events.py` |
| Essay Lifecycle | `events/essay_lifecycle_events.py` |
| CJ Assessment | `events/cj_assessment_events.py` |
| Results | `events/result_events.py` |
| LLM Provider | `events/llm_provider_events.py` |
| Pipeline | `events/pipeline_events.py` |
| NLP | `events/nlp_events.py` |
| Notifications | `events/notification_events.py` |
| Class Events | `events/class_events.py` |
| Validation | `events/validation_events.py` |

---

## Recent Changes Requiring Flow Updates

### assignment_id Propagation (Phase A/B - Nov 2025)
- Added `assignment_id` field to `ELS_CJAssessmentRequestV1`
- Added `assignment_id` field to `AssessmentResultV1`
- Purpose: Grade projection context for anchored assessments
- **Status:** Phase A complete, Phase B pending

### original_file_name Propagation (Nov 2025)
- Added to `EssaySlotAssignedV1`
- Enables client-side filename display in results
- **Status:** Completed

### LLM Provider Configuration Hierarchy (Nov 2025)
- 3-tier override: Service defaults → Admin → Request
- `LLMConfigOverrides` in `ELS_CJAssessmentRequestV1`
- **Documentation:** `docs/operations/llm-provider-configuration-hierarchy.md`

---

## Next Actions

1. **Validate existing flows (035-037.1)** against recent changes
2. **Create FLOW-05 documentation** (File Upload flow)
3. **Create FLOW-06 documentation** (Results flow)
4. **Create FLOW-07 documentation** (Entitlements flow)
5. Update 034 inventory as flows are documented
