# Phase 1 Processing Flow - Student Matching Integration

**Status:** COMPLETE - All services implemented and operational  
**Purpose:** Pre-readiness student matching for REGULAR batches  
**Scope:** Batch-level processing from content provisioning to association confirmation

## Overview

Phase 1 handles student-essay association for REGULAR batches before pipeline readiness. GUEST batches bypass this phase entirely, moving directly to Phase 2 pipeline processing.

### Core Principle
- **GUEST batches**: No class_id → Skip student matching → Direct to READY_FOR_PIPELINE_EXECUTION
- **REGULAR batches**: Has class_id → Phase 1 student matching → Human validation → READY_FOR_PIPELINE_EXECUTION

## Event Flow Architecture

### GUEST Batch Flow (Simple Path)
```
BOS → ELS → BOS
     ↓       ↑
Content → Immediate Ready
```

1. **BatchContentProvisioningCompletedV1** (ELS → BOS)
2. **BOS detects no class_id** → Direct state transition to READY_FOR_PIPELINE_EXECUTION

### REGULAR Batch Flow (Student Matching Path)
```
BOS → ELS → NLP → Class Management → ELS → BOS
     ↓                                     ↑
Content → Student Matching → Validation → Ready
```

1. **BatchContentProvisioningCompletedV1** (ELS → BOS)
2. **BatchServiceStudentMatchingInitiateCommandDataV1** (BOS → ELS)
3. **BatchStudentMatchingRequestedV1** (ELS → NLP)
4. **BatchAuthorMatchesSuggestedV1** (NLP → Class Management)
5. **StudentAssociationsConfirmedV1** (Class Management → ELS)
6. **BatchEssaysReady** (ELS → BOS)

## Service Responsibilities

### Batch Orchestrator Service (BOS)
- **Decision Authority**: Determines GUEST vs REGULAR based on class_id presence
- **State Management**: Tracks batch progression through Phase 1
- **Flow Control**: Initiates student matching or direct readiness

**Key Handlers:**
- `BatchContentProvisioningCompletedHandler`: Phase 1 entry point
- `StudentAssociationsConfirmedHandler`: Phase 1 completion (not yet implemented)

### Essay Lifecycle Service (ELS)
- **Command Processing**: Handles student matching initiation from BOS
- **Event Orchestration**: Publishes batch-level requests to NLP
- **Association Management**: Updates essays with confirmed student data

**Key Handlers:**
- `StudentMatchingCommandHandler`: Processes BOS commands
- `StudentAssociationHandler`: Handles confirmed associations

### NLP Service
- **Batch Processing**: Processes entire batch of essays in parallel
- **Name Extraction**: Extracts student identifiers from essay text
- **Roster Matching**: Matches extracted names against class roster

**Key Handler:**
- `StudentMatchingHandler`: Batch-level student matching processor

### Class Management Service
- **Match Storage**: Stores NLP suggestions in EssayStudentAssociation table
- **Human Validation**: Provides UI for teacher review and correction
- **Timeout Handling**: Auto-confirms after 24-hour timeout

**Key Handler:**
- `BatchAuthorMatchesHandler`: Processes NLP match suggestions

## Critical Implementation Details

### Batch-Level Processing Benefits
- **Performance**: Parallel processing of all essays, single network call
- **UX**: Teachers see complete batch results immediately
- **Reliability**: Single event to track, atomic success/failure
- **Consistency**: Aligns with Phase 2 service patterns

### State Transitions

**BOS Batch States:**
- `AWAITING_CONTENT_VALIDATION` → `AWAITING_STUDENT_VALIDATION` (REGULAR)
- `AWAITING_CONTENT_VALIDATION` → `READY_FOR_PIPELINE_EXECUTION` (GUEST)
- `AWAITING_STUDENT_VALIDATION` → `STUDENT_VALIDATION_COMPLETED` (after associations) *
- `STUDENT_VALIDATION_COMPLETED` → `READY_FOR_PIPELINE_EXECUTION` (after essays stored) *

* Note: Planned refactor to add intermediate state preventing race conditions

**ELS Batch States:**
- `CONTENT_PENDING` → `AWAITING_STUDENT_ASSOCIATIONS` → `ASSOCIATIONS_CONFIRMED`

### Error Handling Patterns

**Partial Batch Failures:**
- Some essays succeed, others fail during extraction/matching
- Include successful matches in results
- Mark failed essays with error reason in `no_match_reason`
- Batch continues with partial results

**Service Unavailability:**
- NLP Service down: Retry with exponential backoff, then proceed with no matches
- Class Management down: Queue suggestions using outbox pattern
- Roster not found: Continue with empty match results for all essays

## Key Event Models

### BatchStudentMatchingRequestedV1
```python
batch_id: str
essays_to_process: list[EssayProcessingInputRefV1]  # All essays in batch
class_id: str
```

### BatchAuthorMatchesSuggestedV1
```python
batch_id: str
class_id: str
match_results: list[EssayMatchResult]  # Results for all essays
processing_summary: dict[str, int]     # {matched: 7, no_match: 2, errors: 1}
```

### StudentAssociationsConfirmedV1
```python
batch_id: str
associations: list[EssayStudentAssociation]
validation_method: str  # "human", "timeout", "auto"
```

## Performance Requirements

- **Batch matching**: <100ms per essay (parallel processing)
- **Total batch time**: <10s for 30 essays
- **Association confirmation**: <50ms
- **Maximum batch size**: 100 essays
- **Concurrency**: 1000 concurrent batches supported

## Testing Strategy

### Key Test Scenarios
- GUEST batch bypass (no student matching events)
- REGULAR batch full flow (all events)
- Partial batch failures (some essays fail)
- Timeout scenarios (24-hour fallback)
- Idempotency (duplicate event handling)
- Race conditions (content vs association timing)

### Integration Points
- All Phase 1 handlers implemented and tested
- Event publishing uses transactional outbox pattern
- Redis-based deduplication for idempotency
- Comprehensive error handling with structured logging

## Operational Considerations

### Monitoring Metrics
- `nlp_phase1_student_matching_initiated_total`
- `nlp_phase1_batch_processing_duration_seconds`
- `nlp_phase1_associations_confirmed_total{validation_method}`
- `nlp_phase1_batch_match_outcomes_total{outcome}`

### Common Issues
- **No match suggestions**: Check NLP extraction logs, verify roster data
- **Timeout not triggering**: Verify timeout monitor, check Redis TTL
- **Duplicate associations**: Check idempotency keys, verify event deduplication
