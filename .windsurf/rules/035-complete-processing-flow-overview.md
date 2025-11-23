---
id: "035-complete-processing-flow-overview"
type: "workflow"
created: 2025-09-01
last_updated: 2025-11-17
scope: "cross-service"
---

# Complete Processing Flow Overview

**Purpose:** High-level map of HuleEdu's complete batch processing architecture  
**Scope:** End-to-end flow from batch registration to final results  
**Dependencies:** Rules 051 (Phase 1) and 052 (Phase 2) for detailed implementation

## Architecture Summary

HuleEdu processes essay batches through a two-phase architecture that handles both anonymous (GUEST) and class-based (REGULAR) workflows with different complexity requirements.

### Processing Phases Overview

```
BATCH REGISTRATION → CONTENT UPLOAD → PHASE 1 → PHASE 2 → CLIENT RESULTS
                                        ↓          ↓
                              [Student Matching] [Pipeline Services]
                                 (REGULAR only)   (All batches)
```

## Flow Differentiation

### GUEST Batch Flow (Anonymous Processing)
```
Register → Upload → Content Ready → Pipeline Processing → Results
    ↓        ↓           ↓               ↓                  ↓
   BOS      ELS         BOS       [Multi-Service]         BOS
                                   Processing
```
**Characteristics:**
- No class_id provided
- Skips student matching entirely
- Direct to pipeline processing
- Fast-track for anonymous usage

### REGULAR Batch Flow (Class-Based Processing)
```
Register → Upload → Content Ready → Student Matching → Validation → Pipeline → Results
    ↓        ↓           ↓              ↓                ↓           ↓          ↓
   BOS      ELS         BOS      [NLP + Class Mgmt]    Human      Multi-     BOS
                                                        Review     Service
```
**Characteristics:**
- Includes class_id for student roster
- Requires Phase 1 student matching
- Human-in-the-loop validation
- Complete educational workflow

## Service Orchestration Map

### Core Services and Responsibilities

**Batch Orchestrator Service (BOS)**
- Entry point for all batch operations
- Routing logic: GUEST vs REGULAR determination
- State management across both phases
- Client API interface

**Essay Lifecycle Service (ELS)**  
- Content provisioning coordination
- Event orchestration between services
- Processing state management
- Results aggregation

**NLP Service**
- Phase 1: Student name extraction and matching
- Phase 2: Text analysis and feature extraction
- Dual-mode operation handling

**Class Management Service**
- Student roster management
- Match suggestion storage and validation
- Human-in-the-loop coordination

**Processing Services**
- Spellcheck: Grammar and style analysis
- CJ Assessment: Comparative judgment scoring  
- AI Feedback: Automated feedback (not implemented)

## Key State Transitions

### Batch States (BOS perspective)
```
AWAITING_CONTENT_VALIDATION
    ↓
[GUEST] READY_FOR_PIPELINE_EXECUTION
    ↓
[REGULAR] AWAITING_STUDENT_VALIDATION  
    ↓
[REGULAR] STUDENT_VALIDATION_COMPLETED
    ↓
READY_FOR_PIPELINE_EXECUTION
    ↓  
PIPELINE_IN_PROGRESS
    ↓
COMPLETED
```

### Content States (ELS perspective)
```
CONTENT_PENDING
    ↓
CONTENT_PROVISIONED
    ↓
[REGULAR only] AWAITING_STUDENT_ASSOCIATIONS
    ↓
[REGULAR only] ASSOCIATIONS_CONFIRMED
    ↓
READY_FOR_PROCESSING
```

## Event Architecture Patterns

### Phase 1 Events (Student Matching)
- **Trigger**: `BatchContentProvisioningCompletedV1`
- **Command**: `BatchServiceStudentMatchingInitiateCommandDataV1`
- **Request**: `BatchStudentMatchingRequestedV1`
- **Response**: `BatchAuthorMatchesSuggestedV1`
- **Confirmation**: `StudentAssociationsConfirmedV1`
- **Completion**: `BatchEssaysReady`

### Phase 2 Events (Pipeline Processing)
- **Trigger**: `ClientBatchPipelineRequestV1`
- **Commands**: Service-specific initiate commands
- **Completions**: Service-specific completion events
- **Final**: `BatchPipelineCompletedV1`

## Critical Design Decisions

### Batch-Level Processing
- **Rationale**: Better UX, performance, and reliability than per-essay processing
- **Implementation**: All services process complete batches atomically
- **Benefits**: Single network calls, parallel processing, atomic success/failure

### Service Boundaries (DDD)
- **BOS**: Owns batch metadata and class_id information
- **ELS**: Owns essay content and processing state (stateless event router during Phase 1)
- **NLP**: Stateless processing service
- **Class Management**: Owns student roster and associations with 24h timeout auto-confirmation

### Error Handling Philosophy
- **Partial Success**: Batches can succeed with individual essay failures
- **Graceful Degradation**: Services continue with reduced functionality
- **Timeout Handling**: 24-hour timeout with automatic fallback
- **Idempotency**: All operations are safe to retry

## Performance Characteristics

### Processing Targets
- **Phase 1**: <10s for 30-essay batch (student matching)
- **Phase 2**: <5 minutes for 30-essay batch (full pipeline)
- **Concurrent Batches**: 1000+ supported across system
- **Maximum Batch Size**: 100 essays per batch

### Scalability Patterns
- **Horizontal**: Each service scales independently
- **Vertical**: Parallel processing within batches
- **Resource**: Configurable concurrency limits per service

## Monitoring Strategy

### Key Metrics Categories
- **Flow Metrics**: Batch progression through phases
- **Performance Metrics**: Processing duration per phase/service
- **Quality Metrics**: Success rates, error categorization
- **Business Metrics**: GUEST vs REGULAR usage patterns

### Critical Alerts
- Phase 1 timeout rates
- Service unavailability
- Processing queue backups
- Error rate spikes

## Integration Points

### External Dependencies
- **File Service**: Essay content storage and retrieval
- **Content Service**: Text content access for processing
- **Notification Service**: Teacher alerts and status updates
- **API Gateway**: Client request routing and authentication

### Internal Communication
- **Kafka**: Asynchronous event messaging
- **HTTP**: Synchronous service queries
- **Redis**: Caching and deduplication
- **PostgreSQL**: Service-specific data persistence

## Operational Runbooks

### Common Scenarios
- **GUEST batch stuck**: Check content provisioning, validate BOS state
- **REGULAR batch timeout**: Review student matching, check Class Management
- **Pipeline failure**: Identify failing service, check resource constraints
- **Performance degradation**: Monitor database connections, Kafka lag

### Recovery Procedures
- **Service restart**: Graceful shutdown, outbox processing completion
- **Event replay**: Redis-based deduplication prevents duplicates
- **Manual intervention**: Admin APIs for batch state correction
- **Rollback**: Feature flags for disabling Phase 1 integration

## Rule References

- **Rule 051**: Phase 1 Processing Flow (Student Matching Implementation)
- **Rule 052**: Phase 2 Processing Flow (Pipeline Services Implementation)
- **Rule 020.15**: NLP Service Architecture
- **Rule 030**: Event-Driven Architecture Standards
- **Rule 042**: Async Patterns and Dependency Injection
