# NLP Phase 1 Event Flow Quick Reference

## Phase 1: Pre-Readiness (REGULAR Batches Only)

### 1. BatchContentProvisioningCompletedV1
- **Publisher:** ELS
- **Consumer:** BOS  
- **Topic:** `batch.content.provisioning.completed`
- **Trigger:** All essay slots filled with content
- **BOS Action:** Check class_id → initiate student matching if REGULAR

### 2. BatchServiceStudentMatchingInitiateCommandDataV1
- **Publisher:** BOS
- **Consumer:** ELS
- **Topic:** `batch.service.student.matching.initiate.command`
- **Trigger:** REGULAR batch with class_id
- **ELS Action:** Mark batch awaiting associations → publish to NLP

### 3. BatchStudentMatchingRequestedV1
- **Publisher:** ELS  
- **Consumer:** NLP Service
- **Topic:** `huleedu.batch.student.matching.requested.v1`
- **Contains:** All essays + class_id
- **NLP Action:** Extract names → match roster → publish suggestions

### 4. BatchAuthorMatchesSuggestedV1
- **Publisher:** NLP Service
- **Consumer:** Class Management
- **Topic:** `batch.author.matches.suggested`
- **Contains:** Match suggestions for all essays
- **CM Action:** Store → notify teacher → await validation

### 5. StudentAssociationsConfirmedV1
- **Publisher:** Class Management
- **Consumer:** ELS
- **Topic:** `huleedu.student.associations.confirmed.v1`
- **Trigger:** Human validation or 24hr timeout
- **ELS Action:** Update essays → publish BatchEssaysReady

### 6. BatchEssaysReady
- **Publisher:** ELS
- **Consumer:** BOS
- **Topic:** `batch.essays.ready`  
- **When:** REGULAR batches only, after associations
- **BOS Action:** Transition to READY_FOR_PIPELINE_EXECUTION

## Phase 2: Pipeline Processing (All Batches)

### 7. ClientBatchPipelineRequestV1
- **Publisher:** API Gateway
- **Consumer:** BOS
- **Topic:** `huleedu.commands.batch.pipeline.v1`
- **Trigger:** Client pipeline request
- **BOS Action:** Verify READY state → initiate pipeline

### 8. BatchServiceSpellcheckInitiateCommandDataV1
- **Publisher:** BOS
- **Consumer:** ELS  
- **Topic:** `batch.service.spellcheck.initiate.command`
- **When:** First pipeline command
- **ELS Action:** Forward to Spellcheck Service

## Key State Transitions

### GUEST Batches (No Student Matching)
```
AWAITING_CONTENT_VALIDATION
    ↓ (BatchContentProvisioningCompletedV1)
READY_FOR_PIPELINE_EXECUTION
```

### REGULAR Batches (With Student Matching)
```
AWAITING_CONTENT_VALIDATION
    ↓ (BatchContentProvisioningCompletedV1)
AWAITING_STUDENT_VALIDATION
    ↓ (StudentAssociationsConfirmedV1)
READY_FOR_PIPELINE_EXECUTION
```

## Missing Handlers

1. **BOS:** StudentAssociationsConfirmedV1 handler
2. **ELS:** BatchServiceStudentMatchingInitiateCommandDataV1 handler
3. **ELS:** StudentAssociationsConfirmedV1 handler  
4. **NLP:** BatchStudentMatchingRequestedV1 handler
5. **CM:** BatchAuthorMatchesSuggestedV1 handler

## Event Model Fixes Needed

1. **BatchContentProvisioningCompletedV1:** Make class_id optional
2. **Add topic documentation** to all event models