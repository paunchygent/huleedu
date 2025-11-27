---
id: 'propagate-assignment-id-from-bos-to-cj-request-phase-a'
title: 'Propagate assignment_id from BOS to CJ request (Phase A)'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'assessment'
service: 'batch_orchestrator_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-27'
last_updated: '2025-11-27'
related: ['TASKS/assessment/propagate-assignment-id-from-cj-to-ras-storage-phase-b.md', '.claude/plans/cuddly-churning-sloth.md']
labels: ['cross-service', 'event-contract', 'anchor-mixing']
---
# Propagate assignment_id from BOS to CJ request (Phase A)

## Objective

Propagate `assignment_id` from pipeline request through BOS and ELS to CJ Assessment Service, enabling anchor essay mixing for grade calibration.

## Context

`assignment_id` is passed during pipeline requests via `ClientBatchPipelineRequestV1.prompt_payload.assignment_id` but never reaches CJ Assessment Service. The field exists in `ELS_CJAssessmentRequestV1` but is never populated.

**Current flow gap:**

| Boundary | Contract | Status |
|----------|----------|--------|
| Client → BOS | `prompt_payload.assignment_id` | ✅ Present |
| BOS → ELS | `BatchServiceCJAssessmentInitiateCommandDataV1` | ❌ Missing |
| ELS → CJ | `ELS_CJAssessmentRequestV1` | ⚠️ Field exists, never populated |

## Plan

### Step 1: Add `assignment_id` to BOS → ELS command
**File**: `libs/common_core/src/common_core/batch_service_models.py`
- Add `assignment_id: str | None = Field(default=None)` to `BatchServiceCJAssessmentInitiateCommandDataV1`

### Step 2: BOS passes `assignment_id` to command
**File**: `services/batch_orchestrator_service/implementations/cj_assessment_initiator_impl.py`
- Extract `assignment_id` from `batch_metadata` (stored during pipeline request handling)
- Pass to `BatchServiceCJAssessmentInitiateCommandDataV1`

### Step 3: ELS command handler forwards to dispatcher
**File**: `services/essay_lifecycle_service/implementations/cj_assessment_command_handler.py`
- Extract `assignment_id` from command
- Pass to `dispatch_cj_assessment_requests()`

### Step 4: Update ELS dispatcher protocol and implementation
**Files**:
- `services/essay_lifecycle_service/protocols.py`
- `services/essay_lifecycle_service/implementations/service_request_dispatcher.py`

Actions:
- Add `assignment_id` parameter to `dispatch_cj_assessment_requests()`
- Set `assignment_id` field on `ELS_CJAssessmentRequestV1`

### Step 5: Update tests
- `services/batch_orchestrator_service/tests/` - command construction tests
- `services/essay_lifecycle_service/tests/` - dispatcher tests

## Success Criteria

1. `assignment_id` is included in `BatchServiceCJAssessmentInitiateCommandDataV1`
2. `ELS_CJAssessmentRequestV1.assignment_id` is populated when CJ request is dispatched
3. CJ Assessment Service receives `assignment_id` and can use it for anchor lookup
4. All existing tests pass
5. New unit tests cover `assignment_id` propagation

## Related

- Phase B: `TASKS/assessment/propagate-assignment-id-from-cj-to-ras-storage-phase-b.md`
- Plan file: `.claude/plans/cuddly-churning-sloth.md`
